# Kiểm soát phiên bản API và endpoint đã ngừng hỗ trợ: vòng đời, bảo mật và chuyển đổi an toàn

## 1. Vì sao phiên bản API là một chủ đề bảo mật mạng?

API và network service thường tồn tại lâu hơn một lần triển khai phần mềm. Cùng một dịch vụ có thể đồng thời phục vụ **v1 cho ứng dụng mobile cũ, v2 cho đối tác, v3 cho website mới**, ngoài ra còn các endpoint quản trị, webhook và giao tiếp nội bộ. Khi nâng cấp, việc chỉ đưa v3 vào production mà quên **v1 vẫn được công khai ở một load balancer, cổng trực tiếp hoặc hostname cũ** sẽ tạo ra một phần **attack surface không còn được bảo trì đầy đủ**.

**Kiểm soát phiên bản và endpoint đã ngừng hỗ trợ** là quy trình xác định, công bố, giám sát và cưỡng chế **phiên bản/route nào được phép sử dụng, trong khoảng thời gian nào, bởi ai và theo chính sách bảo mật nào**. Mục tiêu không đơn thuần là xóa URL cũ: cần giữ khách hàng hợp lệ hoạt động trong giai đoạn chuyển đổi mà **không duy trì vô thời hạn những đường truy cập không được vá, không được kiểm thử hoặc không có owner**.

Trong module **SECURITY_NETWORK_SECURITY**, chủ đề liên hệ trực tiếp với **phân đoạn mạng, gateway/firewall, reverse proxy và load balancer, TLS/mTLS, DNS, IDS/IPS, quản lý danh tính, cloud ingress và giám sát lưu lượng**. Một API version chỉ thực sự được ngừng hỗ trợ khi mọi **đường vào và đường gọi nội bộ** có thể tới implementation cũ đã được xử lý theo kế hoạch.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **API version**, **endpoint**, **contract**, **deprecation**, **sunset**, **end of support** và **retirement**.
2. Chọn cách định phiên bản qua **URL path, hostname, header, media type** và hiểu mặt lợi/hại của từng cách.
3. Đánh giá thay đổi **backward-compatible**, **breaking**, và những thay đổi bắt buộc vì an ninh.
4. Thiết kế danh mục API với **owner, consumer, thời hạn và trạng thái** trên cả gateway lẫn runtime.
5. Dùng tín hiệu **OpenAPI, Deprecation/Sunset, tài liệu chuyển đổi và telemetry** đúng mục đích.
6. Chặn endpoint hết hạn bằng **policy nhất quán**, giữ authentication/authorization và tránh route bypass.
7. Lập kế hoạch migration client, contract test, canary, fallback, rollout, rollback và điều tra sự cố.

## 2. Từ vựng và phạm vi của một phiên bản

Một **API contract** bao gồm cách gọi và ý nghĩa của request/response: route, method, query/body schema, authentication, authorization, status codes, error semantics, pagination, ordering, timeouts và các side effects. **API version** là cách tổ chức phát hành/phân biệt một hoặc nhiều tập contract để client biết hành vi nào được hỗ trợ.

| Thuật ngữ | Ý nghĩa | Có nghĩa là đã bị chặn? |
| --- | --- | --- |
| **Active / supported** | Được công bố, kiểm thử, hỗ trợ và duy trì bảo mật theo chính sách | Không |
| **Deprecated** | Không còn khuyến nghị dùng cho tích hợp mới; thường có thay thế và kế hoạch chuyển | **Không nhất thiết** |
| **Sunset scheduled** | Có mốc dự kiến ngừng cung cấp/đổi hành vi | Chưa, trừ policy hiện tại đã chặn |
| **End of support (EoS)** | Kết thúc hỗ trợ theo cam kết, có thể ngừng vá/triage hoặc hạn chế phạm vi | Tùy hợp đồng và trạng thái thực tế |
| **End of life (EoL)** | Hết vòng đời sản phẩm/phiên bản theo chính sách tổ chức | Không mặc định đồng nghĩa URL đã biến mất |
| **Retired / removed** | Endpoint không còn được phục vụ theo contract cũ qua các đường được kiểm soát | Thông thường **có** |
| **Disabled / blocked** | Đường vào bị chặn do an ninh, incident hoặc chính sách | Có đối với traffic thuộc scope |
| **Shadow / zombie API** | API còn reachable nhưng không nằm trong danh mục/quy trình chính thức | Có thể vẫn gọi được, rủi ro cao |

**Deprecated khác removed.** Một endpoint được đánh dấu **deprecated: true** trong OpenAPI nhưng gateway vẫn trả 200 là điều có thể đúng trong giai đoạn chuyển đổi. Ngược lại, một endpoint đã được xóa khỏi tài liệu nhưng vẫn trả 200 trên hostname cũ **chưa hề được retirement về mặt kỹ thuật**.

### 2.1. Endpoint không chỉ là đường dẫn

Hai API operations có thể cùng path nhưng khác method hoặc điều kiện lựa chọn:

~~~text
GET    /api/v1/orders           Lấy danh sách
POST   /api/v1/orders           Tạo đơn
GET    /api/v1/orders/{id}      Lấy một đơn
DELETE /api/v1/orders/{id}      Hủy/xóa theo quyền

Host: api.example.org
Accept: application/vnd.example.orders.v1+json
Authorization: Bearer [redacted]
~~~

Một **operation identity** thường cần **hostname/authority, path template, HTTP method, version negotiation và environment**. Không nên gom mọi thao tác ở /orders thành một policy vì **POST và DELETE có side effects** khác GET.

### 2.2. Scope phiên bản khác scope deployment

Version **v2** không đồng nghĩa deployment **release 2.7.14**. Một client-facing v2 có thể được phục vụ từ nhiều phiên bản build, region, cloud accounts hoặc microservices. Một service release mới có thể giữ contract v2 và vá lỗ hổng mà **không đổi public API version**.

**Tách ba loại ID:** API contract version (v1/v2), implementation release (build/commit) và configuration/security-policy revision (gateway/WAF/identity). Nhờ đó khi điều tra có thể biết một endpoint cũ bị lỗi do **contract**, **code runtime** hay **route cấu hình**.

## 3. Vòng đời phiên bản API có kiểm soát

~~~mermaid
flowchart LR
    A["Design / Review"] --> B["Preview / Beta"]
    B --> C["Active / Supported"]
    C --> D["Deprecated"]
    D --> E["Sunset scheduled"]
    E --> F["Retired / Blocked"]
    F --> G["Post-retirement monitoring"]
    C -. "Critical security incident" .-> H["Emergency disable"]
    D -. "Critical security incident" .-> H
    H --> I["Approved remediation / migration"]
~~~

Trạng thái có thể được đặt cho **một operation, một version, một hostname, một consumer cohort hoặc cả API product**. Không phải tất cả endpoint v1 bắt buộc nghỉ cùng ngày; nhưng sự khác nhau phải được ghi rõ để không có route nào bị bỏ quên.

### 3.1. Những mốc nên tách

| Mốc | Ý nghĩa | Công việc bắt buộc |
| --- | --- | --- |
| **T0 – công bố deprecation** | Client được thông báo contract cũ sẽ thay thế | Công bố migration guide, owners, support contacts |
| **T1 – đóng đăng ký mới** | Không cấp tích hợp mới vào version cũ | Portal/API key provisioning và gateway policy phải đồng nhất |
| **T2 – hết hỗ trợ thông thường** | Không tiếp tục phát triển version cũ theo SLA cũ | Vẫn xử lý nghĩa vụ security/incident theo cam kết |
| **T3 – sunset/cutoff** | Đường cũ bị từ chối theo kế hoạch | Readback ở mọi ingress, canary và regression tests |
| **T4 – xóa implementation/routing** | Dọn tài nguyên cũ, bí mật, IAM, DNS | Không để zombie routes, record decommission evidence |

**Không ngầm cam kết rằng sau EoS sẽ không vá lỗ hổng nghiêm trọng** nếu hợp đồng hoặc chính sách còn trách nhiệm. Với API public, cần công bố rõ **mốc ngừng hỗ trợ, mốc từ chối request và thời hạn lưu dữ liệu/log**, tránh sử dụng các từ EoS, EoL và Sunset thay cho nhau.

### 3.2. Hồ sơ vòng đời một endpoint

~~~yaml
# Schema giả định cho bài học; không phải chuẩn OpenAPI hay công cụ cụ thể.
api_id: orders-public
contract_version: v1
operation_id: listOrdersV1
authority: api.example.org
method: GET
path_template: /api/v1/orders
environment: production
owner: team-orders
security_owner: appsec-platform
status: deprecated
replacement: /api/v2/orders
deprecation_announced_at: "2026-01-15T00:00:00Z"
sunset_at: "2026-12-31T00:00:00Z"
last_security_review_at: "2026-10-01T00:00:00Z"
consumer_inventory: partner-register
gateway_policy_id: gw-orders-v1
telemetry_dashboard: orders-api-lifecycle
change_reference: CHG-EXAMPLE
~~~

Ví dụ này không quyết định **mọi operation cùng version** đều có sunset giống nhau. Trạng thái actual phải được kiểm tra trên gateway/runtime; một bảng YAML không tự chứng minh endpoint đã bị chặn.

## 4. Các chiến lược định phiên bản và đánh đổi bảo mật

### 4.1. Version trong URL path

~~~http
GET /api/v1/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer [redacted]
~~~

**Ưu điểm:** dễ thấy trong gateway path routing, logs và tài liệu; client dễ chỉ rõ version. **Nhược điểm:** dễ sinh nhiều route trùng lặp; một wildcard như /api/* có thể vô tình mở lại v1, còn đường backend trực tiếp có thể bypass policy retirement.

### 4.2. Version trong hostname/subdomain

~~~text
https://v1.api.example.org/orders
https://v2.api.example.org/orders
~~~

**Ưu điểm:** tách DNS/TLS/ingress rõ, có thể di chuyển độc lập. **Nhược điểm:** tăng số DNS records, certificates, WAF/ingress policies, khả năng **để sót hostname cũ**. Việc ngừng trả DNS record không đủ bảo đảm cổng/IP origin không còn phục vụ.

### 4.3. Version qua header hoặc media type

~~~http
GET /orders HTTP/1.1
Host: api.example.org
Accept: application/vnd.example.orders.v2+json
Authorization: Bearer [redacted]
~~~

**Ưu điểm:** URL ổn định; server có thể content negotiation. **Nhược điểm:** proxy/CDN cache, security logs, rate limit và test automation phải xét **header chọn version**; nếu default version thay đổi tùy client, có thể gây **cache confusion hoặc policy mismatch**.

### 4.4. Version qua query parameter

~~~text
GET /orders?api-version=2
~~~

Có thể dễ triển khai nhưng query string thường bị ghi vào logs, cache keys/route rules khác nhau theo hệ thống và dễ bị bỏ qua bởi thành phần trung gian. Nếu dùng, phải xác minh **cache variation, WAF policy, signing/auth và default behavior**.

### 4.5. Version nội bộ với GraphQL/gRPC

**GraphQL** thường tiến hóa schema bằng **thêm field, đánh dấu deprecate field, migration theo client usage**, thay vì mọi thay đổi tạo /v2 URL. Nhưng việc xóa field, đổi type hay thay auth resolver vẫn là breaking/security change cần governance.

**gRPC/Protobuf** định nghĩa API qua package/service/method và field numbers; thay đổi schema cần quan tâm **wire compatibility, reserved field numbers/names, enum handling, stream behavior** và chính sách auth. Không mặc định cùng package name nghĩa là client cũ tương thích.

### 4.6. Nguyên tắc chọn chiến lược

| Tiêu chí | Path/hostname version | Header/media-type version |
| --- | --- | --- |
| Khả năng quan sát version tại gateway | Thường trực tiếp | Cần parse/normalize header |
| Cache key | Thường tách theo URL/host | Phải cấu hình key/Vary đúng |
| Policy per version | Dễ tách listener/routes | Phải tránh header client spoofing/ambiguous values |
| Bảo trì chứng chỉ/DNS | Host-based tốn nhiều hơn | Có thể dùng chung host |
| Hợp với REST public API | Rất phổ biến | Khả thi khi có contract/client support |
| Rủi ro shadow endpoints | Path/host cũ vẫn có thể reachable | Default/legacy header logic có thể bị quên |

**Không nên trộn nhiều cách chọn version mà thiếu thứ tự ưu tiên rõ**. Ví dụ request tới /v1 nhưng header yêu cầu v2 phải có hành vi xác định và được kiểm thử, không để gateway xét path còn backend xét header rồi thực thi **hai bộ policy khác nhau**.

## 5. Backward compatibility không đơn thuần là “JSON vẫn parse được”

**Backward compatibility** trong API có nghĩa client hợp lệ đang dùng một contract cũ vẫn có thể thực hiện **hành vi được cam kết**, không chỉ đọc được schema. Một thay đổi có thể hợp lệ về kiểu dữ liệu mà vẫn phá trải nghiệm hoặc an ninh.

| Thay đổi | Tính tương thích thường gặp | Rủi ro cần thử |
| --- | --- | --- |
| Thêm field response tùy chọn | Thường không breaking với clients bỏ qua field lạ | Client strict schema có thể reject |
| Đổi tên/xóa response field | Thường breaking | Mobile/partner không parse được |
| Thêm request field tùy chọn có default cũ | Có thể compatible | Validation/server defaults cần kiểm tra |
| Biến optional field thành required | Thường breaking | Client cũ trả 400/422 |
| Đổi kiểu number→string hoặc enum values | Có thể breaking | Serialization, exhaustive switch, cache |
| Đổi pagination/sort default | Có thể breaking về hành vi | Missing/duplicate records, độ ổn định cursor |
| Đổi timezone/đơn vị tiền | Breaking về ngữ nghĩa dù JSON hợp lệ | Dữ liệu sai nghiệp vụ |
| Đổi authentication hoặc scope yêu cầu | Có thể breaking nhưng cần vì security | 401/403 tăng, phải migration credential |
| Siết validation đầu vào độc hại | Có thể ảnh hưởng client sai chuẩn | Không rollback vá an ninh chỉ để giữ bug |
| Bỏ operation hoặc ngừng version | Breaking theo chính sách | Cần timeline, telemetry, thông báo và fallback |

**Semantic versioning (SemVer)** hữu ích cho những API/release theo đúng quy ước, nhưng không tự xác định hợp đồng thay đổi. **Major/minor/patch** của package không bắt buộc trùng **v1/v2** của public API. Với public API, cần **chính sách tương thích bằng văn bản** gồm trường hợp được phép thay đổi mà không tạo version mới.

### 5.1. Security fix có thể phá client đang dựa vào lỗ hổng

Ví dụ v1 trước đây cho phép đọc order không có **object-level authorization** đầy đủ. Việc sửa để từ chối request trái quyền có thể khiến một số client từng hoạt động nay nhận **403**. Đây **không phải lý do để giữ hành vi không an toàn** chỉ nhằm đạt 100% backward compatibility.

Quy trình tốt: **vá lỗ hổng, phân loại nhóm client bị ảnh hưởng hợp lệ, thông báo/khắc phục dữ liệu hoặc quyền truy cập, giữ audit**, và chỉ nới ngoại lệ khi có kiểm soát/phê duyệt rủi ro phù hợp. Không coi version cũ được miễn authentication, rate limit hoặc input validation.

## 6. Kiểm kê API và xác định nguồn dữ liệu có thẩm quyền

Một chương trình sunset không thể đáng tin nếu chỉ dựa vào **OpenAPI đang được publish**. Những nguồn khác như gateway routes, reverse proxy configuration, DNS, Kubernetes ingress, cloud API endpoints, service mesh, traffic logs và partner SDKs có thể tiết lộ **đường gọi vẫn tồn tại** mà tài liệu không ghi nhận.

### 6.1. Đối soát source of truth với runtime

~~~mermaid
flowchart TB
    S["API registry: owner, version, lifecycle"] --> R["Reconciliation"]
    G["Gateway / ingress routes"] --> R
    D["DNS / hostnames / certificates"] --> R
    C["Cloud / Kubernetes / service mesh"] --> R
    T["HTTP access & tracing logs"] --> R
    P["SDK / Partner / Mobile consumer inventory"] --> R
    R --> X{"Có sai lệch?"}
    X -- "Không" --> K["Record last-verified + evidence"]
    X -- "Có" --> I["Drift ticket, owner, security review"]
~~~

**Registry** thể hiện trạng thái đã phê duyệt. **Observed runtime** cho biết những gì hệ thống thực sự phục vụ. Một API có thể hiện **retired trong registry** nhưng vẫn reachable qua listener hoặc private IP khác: phải xử lý như **drift an ninh**.

### 6.2. Một API inventory cần tối thiểu những gì?

| Nhóm dữ liệu | Trường cần có | Vì sao |
| --- | --- | --- |
| Định danh | API ID, operation ID, method, normalized route template, version | Tránh trùng route hoặc đếm request IDs như endpoint |
| Exposure | Hostnames, public/internal, ingress gateway, IP family, region/AZ | Biết toàn bộ đường tiếp cận |
| Ownership | Product owner, technical owner, security owner, on-call | Xử lý incident, approve change |
| Lifecycle | Active/deprecated/sunset/retired, effective timestamps, timezone | Cưỡng chế mốc chính xác |
| Consumers | SDK/app versions, partner/client IDs, service accounts, owner contacts | Thông báo và xác định long tail |
| Auth | Scheme, scopes, issuer/audience, BOLA/BFLA policy, mTLS nếu có | Không bỏ sót kiểm soát phiên bản cũ |
| Operations | Backend deployment, OpenAPI/Proto schema, dependencies | Tìm điểm code thực thi và data access |
| Telemetry | Route version, request rate, active client count, failure metrics | Đo tiến độ chuyển đổi |
| Security | Risk review, unsupported library/CVE, rate limit, WAF profile | Ưu tiên vá hoặc tắt sớm |
| Governance | Change ID, exception approval, sunset notice, rollback | Kiểm toán quyết định |

**Địa chỉ IP và hostname không đủ để nhận diện operation** nếu API dùng shared gateway. Ngược lại, một operation có thể được phục vụ qua nhiều hostname/IP hoặc **HTTP/2, IPv4, IPv6**. Inventory nên sử dụng **khóa định danh ổn định cho contract** và liên kết những **exposure points** thực tế.

### 6.3. Discovery không có nghĩa quét bừa mạng

Ưu tiên **read-only inventory, API gateway exports, route tables, DNS, cloud control-plane, logs và service discovery**. Hoạt động chủ động trên mạng như probing/scanning chỉ thực hiện trong **phạm vi được phép** và có kế hoạch. Với endpoints chứa thông tin nhạy cảm, việc ghi URL đầy đủ có token vào logs có thể tạo thêm rủi ro.

### 6.4. Định danh client khi có nhiều người dùng chung NAT

Tổng request theo IP nguồn không phản ánh số **client tích hợp**. Một đối tác có thể đi qua nhiều IP, và hàng nghìn mobile users đi qua CGNAT. Để xác định consumer còn dùng v1, nên dùng **authenticated client ID/service account, app-version đã được chứng thực đến mức phù hợp, partner contract và request identity**. Không tin header **X-App-Version** do client tự khai như bằng chứng duy nhất cho quyết định khóa một đối tác.

## 7. Thiết lập chính sách vòng đời và các ngoại lệ có thời hạn

Không phải mọi API phải dùng cùng khoảng deprecation. Đường **mobile offline nhiều tháng**, webhook đến đối tác, hệ thống nhúng/IoT hoặc API liên quan nghĩa vụ hợp đồng có tốc độ nâng cấp khác nhau. Nhưng ngoại lệ phải **có hạn, có owner và có kiểm soát bảo mật**, không được biến thành “v1 vẫn chạy vì chưa ai dám tắt”.

### 7.1. Mẫu phân loại

| Nhóm | Đặc trưng | Cách ra quyết định |
| --- | --- | --- |
| Public interactive API | Client thường cập nhật tương đối nhanh | Có thông báo, metric, SDK migration và sunset date |
| Partner B2B | Phụ thuộc SLA/hợp đồng và lịch release bên ngoài | Gắn consumer owner, test sandbox, mốc hỗ trợ rõ |
| Mobile/IoT | Bản cũ có thể offline hoặc không thể cập nhật ngay | Version telemetry, grace policy, safe failure UX |
| Internal service API | Chủ động nâng cấp cả producer/consumer | Contract test, staged rollout, service discovery |
| Admin/privileged API | Quyền cao, nguy cơ bypass lớn | Sunset nhanh nếu rủi ro, ưu tiên least privilege |
| Vulnerable legacy endpoint | Lỗ hổng đã xác nhận hoặc không thể vá | Emergency block theo risk; không đợi đủ lịch marketing |

### 7.2. Tiêu chí cho phép extension

Một gia hạn nên ghi đủ **consumer ID, operation/version scope, business justification, compensating controls, expiration, owner, approver, metrics và cách thu hồi**. Chỉ gia hạn nếu có thể duy trì mức an toàn chấp nhận được.

**Không dùng allowlist theo IP đơn thuần thay cho auth**: địa chỉ nguồn có thể bị NAT, đổi ISP hoặc dùng chung. Nếu chỉ một đối tác được gia hạn, ưu tiên ràng buộc với **client credential/identity đã xác thực, scope và operation**. Quyền **extend** không cho phép dùng mọi endpoint trong cùng v1.

### 7.3. Deadline và timezone

Các mốc lifecycle nên lưu dưới dạng **UTC ISO 8601 có timezone**. Nếu công bố “ngừng ngày 31/12” nhưng không nói offset và giờ, client ở nhiều nước có thể hiểu khác nhau. Một sunset nên có:

~~~text
Deprecated announcement: 2026-01-15T00:00:00Z
Normal support end:      2026-11-30T23:59:59Z
Request cutoff:          2026-12-31T00:00:00Z
Policy execution:        API gateway + backend, theo clock được giám sát
Owner/exception contact: [public support channel]
Replacement contract:    v2
~~~

Đây là **lịch minh họa**. Cần xét **clock skew, rollout time giữa region, provider caches** và job chạy delayed: không mặc định một mốc tồn tại trên bảng là tất cả instances đã chặn đồng thời.

## 8. OpenAPI và contract catalog: cảnh báo deprecation đúng cách

OpenAPI hỗ trợ đánh dấu **deprecated** cho operation hoặc đối tượng schema phù hợp. Ví dụ:

~~~yaml
# Mảnh OpenAPI minh họa, không phải một tài liệu hoàn chỉnh.
paths:
  /api/v1/orders:
    get:
      operationId: listOrdersV1
      summary: List orders (legacy)
      deprecated: true
      description: >
        Endpoint này đang trong lộ trình ngừng hỗ trợ.
        Tích hợp mới hãy sử dụng GET /api/v2/orders.
      responses:
        "200":
          description: Successful legacy response
~~~

**deprecated: true là metadata mô tả**, không tự chặn HTTP requests và không có nghĩa hệ thống phát warning header. Người vận hành phải nối metadata vào **developer portal, SDK code generation, linting, gateway policy và migration workflow** nếu muốn có enforcement và cảnh báo trong thực tế.

### 8.1. Những thứ tài liệu cần công bố

Một thông báo chất lượng cần trả lời:

1. Endpoint/operation cụ thể bị deprecate, từ version nào, environments nào?
2. Tại sao chuyển: schema, behavior, performance hay **security requirement**?
3. Endpoint thay thế là gì và mapping các fields/response codes thế nào?
4. Cần cấp lại **OAuth scopes, API keys, mTLS certificates, webhook secrets** không?
5. Có thay **pagination, ordering, idempotency, rate limit, error semantics**?
6. Mốc **deprecation, support end, sunset** có timezone cụ thể?
7. Ở mốc cutoff sẽ trả **HTTP status/body** gì và có retry được không?
8. Có **sandbox/SDK migration guide và contact/escalation channel**?

### 8.2. Tài liệu phải hỗ trợ nhiều nhóm khách hàng

Không gửi mỗi email đến người đăng ký đầu tiên rồi mặc định tất cả app/partner đã nhận. Nên có **developer portal notice, release notes, in-product banner, support case, SDK warning, partner account management và API response signaling**. Với internal APIs, có thể dùng **CI contract checks, service catalog, change tickets** và owner review.

## 9. Tín hiệu HTTP Deprecation, Sunset và các link hướng dẫn

HTTP có các cơ chế giúp server thể hiện một tài nguyên **đã deprecated hoặc dự kiến ngừng sẵn sàng**, bổ sung cho tài liệu chính thức.

### 9.1. Deprecation response header

**Deprecation** (được chuẩn hóa trong RFC 9745) thông báo sự kiện deprecation của resource theo mô hình phù hợp. Nó **không có nghĩa ngay lập tức từ chối request**. Header có thể mang **Structured Field Date** theo định dạng của chuẩn, ví dụ minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1768435200
Link: <https://docs.example.org/api/migrate-v2>; rel="deprecation"

{"items":[]}
~~~

Trong Structured Field Date, dấu **@** đi trước Unix timestamp tính bằng giây; phải đảm bảo giá trị timestamp tương ứng với mốc công bố thực tế, không sử dụng con số mẫu như dữ liệu thật. **Rel=deprecation** có thể dẫn đến tài liệu chuyển đổi; client cần được thiết kế để hiểu hoặc đơn giản bỏ qua các header này theo protocol.

### 9.2. Sunset response header

**Sunset** (RFC 8594) cho biết thời điểm tài nguyên được dự kiến **không còn đáp ứng như hiện tại**. Giá trị là một **HTTP-date**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Sunset: Thu, 31 Dec 2026 00:00:00 GMT
Link: <https://docs.example.org/api/migrate-v2>; rel="sunset"

{"items":[]}
~~~

**Sunset là tín hiệu kế hoạch**, không phải cơ chế bật/tắt tự động và không luôn đồng nghĩa toàn server ngừng hoạt động. Mốc có thể thay đổi theo chính sách/cam kết, nhưng thay đổi phải **được thông báo** và quan sát trong triển khai.

### 9.3. Phối hợp hai header và caching

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1768435200
Sunset: Thu, 31 Dec 2026 00:00:00 GMT
Link: <https://docs.example.org/api/migrate-v2>; rel="deprecation"
Cache-Control: private, no-store

{"items":[]}
~~~

Trong ví dụ, **Cache-Control: private, no-store** là chính sách bảo vệ cho **response riêng tư minh họa**, không phải trường bắt buộc đi kèm deprecation. Với tài nguyên cacheable công khai, phải thiết kế **cache key, TTL, invalidation và header propagation** theo contract. CDN có thể cache một response không còn đúng ngày cutoff nếu không có chính sách kiểm soát.

### 9.4. Deprecation header không thay thế kiểm soát server-side

**Response header chỉ cung cấp thông tin**, không ép client nâng cấp, không thay auth, không chặn zombie route và không giải quyết lỗ hổng trong version cũ. Chỉ dựa vào header có thể khiến tổ chức tuyên bố “v1 đã sunset” trong khi traffic vẫn truy cập được.

## 10. Sau sunset, trả HTTP status nào?

Không có một status duy nhất bắt buộc cho mọi tổ chức và mọi API version. Cách chọn phụ thuộc hợp đồng, bảo mật, semantics và mức thông tin có thể công bố.

| Status | Ý nghĩa trong một số tình huống | Lưu ý |
| --- | --- | --- |
| **410 Gone** | Tài nguyên từng tồn tại và không còn được cung cấp theo chủ đích | Hữu ích cho endpoint đã retired khi có thể công bố sự tồn tại của nó |
| **404 Not Found** | Server không muốn/không thể cho biết resource hiện hữu | Có thể thích hợp cho resource nhạy cảm và chống enumeration |
| **401 Unauthorized** | Thiếu/sai authentication | Không dùng để nói version đã retired nếu vấn đề thực là retirement |
| **403 Forbidden** | Authenticated nhưng không có quyền | Có thể áp cho identity không đủ quyền hoặc cohort bị chặn |
| **400 Bad Request** | Request không hợp lệ theo schema/quy tắc | Không tự mặc định cho version cutoff |
| **406 Not Acceptable / 415 Unsupported Media Type** | Negotiation qua Accept/Content-Type không thể đáp ứng theo semantics | Hợp với trường hợp version nằm trong media type, không phải mã sunset tổng quát |
| **429 Too Many Requests** | Bị rate limit | Không dùng để thay status retirement |
| **503 Service Unavailable** | Tạm thời không phục vụ, thường có nghĩa có thể hồi phục | Không nên mô tả retirement vĩnh viễn là outage tạm |

**426 Upgrade Required** nói về **nâng cấp giao thức kết nối HTTP** (theo cơ chế Upgrade), **không phải status chung cho yêu cầu nâng API từ v1 lên v2**. Tránh dùng 426 chỉ vì từ *upgrade* nghe hợp nghĩa.

### 10.1. Thận trọng với chuyển hướng tự động

Không nên **301/302/307/308** mọi request v1 sang v2 mà không xem **method, body, schema, authentication, idempotency, redirect across origin và caching**. Một redirect **308** giữ method có thể khiến client gửi lại POST tới API có semantics khác; đây không phải migration an toàn mặc định.

Tốt hơn là **trả response rõ ràng theo chính sách**, cung cấp migration docs và cho client cập nhật contract chủ động. Có thể dùng redirect trong các tình huống **đã chứng minh tương đương và không rủi ro**, với test đầy đủ.

### 10.2. Lỗi nên có response contract nhất quán

~~~http
HTTP/1.1 410 Gone
Content-Type: application/problem+json
Cache-Control: no-store
Link: <https://docs.example.org/api/migrate-v2>; rel="deprecation"

{
  "type": "https://docs.example.org/problems/api-retired",
  "title": "API version no longer supported",
  "status": 410,
  "detail": "This operation was retired. Migrate to v2.",
  "instance": "/api/v1/orders"
}
~~~

**Problem Details JSON** là mô hình hữu ích cho error response; trường **instance** không nên lộ internal paths, token hoặc thông tin tenant bí mật. Đảm bảo response không cache nhầm giữa users nếu có dữ liệu cá nhân; không để stale CDN response khiến status về version cũ không nhất quán.

## 11. API gateway là điểm thực thi lifecycle, không phải nguồn bảo vệ duy nhất

Một API gateway hoặc L7 reverse proxy có thể phân tích **Host, path, method, authenticated client, headers** để phân luồng và chặn version đã retired. Nhưng cần kiểm tra cả **đường trực tiếp tới backend**, internal ingress, service mesh, private load balancer, DNS record cũ, WebSocket/HTTP/2 và những hostnames khác.

~~~mermaid
flowchart LR
    C["Client / Partner / Mobile"] --> E["DNS / CDN / WAF"]
    E --> G["API Gateway: auth + version policy"]
    G -->|"v2 allowed"| V2["Supported Backend v2"]
    G -. "v1 retired: 410 / deny" .-> OLD["Legacy v1"]
    C -. "Direct origin bypass?" .-> OLD
    OLD -. "Private ingress deny" .-> F["Firewall / SG / NetworkPolicy"]
~~~

**Quan trọng:** Sơ đồ nét đứt “Direct origin bypass?” mô tả **đường rủi ro cần kiểm tra**, không phải đường được phép sử dụng. Nếu backend cũ vẫn có public address hoặc private route mở từ zone không đúng, việc chặn /v1 ở gateway chính **chưa đủ**.

### 11.1. Một chuỗi policy nhất quán

Thứ tự xử lý thực tế tùy gateway, nhưng ý định bảo mật phải rõ:

1. Kiểm tra **TLS/mTLS và peer identity** ở ingress thích hợp.
2. Xác định **hostname, normalized route/method và API version**, từ chối ambiguity.
3. Thực thi **authentication, authorization, tenant/resource ownership và abuse controls** ở các điểm cần thiết.
4. Áp **lifecycle policy** cho version/operation/consumer; nếu bị retired không chuyển tới code cũ.
5. Áp **WAF, rate/body/timeouts và upstream routing** như được cấu hình.
6. Backend vẫn kiểm tra **application authorization**, không tin rằng gateway đã làm tất cả.
7. Ghi **policy version, quyết định, identity, route và request correlation** mà không ghi secrets.

Không nên coi đây là **thứ tự tuần tự bắt buộc trên mọi sản phẩm**. Ví dụ gateway có thể phát **410 cho mọi request tới một public path retired trước authentication**; điều đó phù hợp hay không phụ thuộc **privacy và enumeration threat model**. Cần bảo đảm **không có path bị bỏ qua kiểm tra bắt buộc** dù policy được chia thành nhiều lớp.

### 11.2. Match rule chính xác hơn wildcard

~~~text
Mong muốn:
  GET  /api/v2/orders             -> supported handler
  POST /api/v2/orders             -> supported handler
  GET  /api/v1/orders             -> retired response (410)
  POST /api/v1/orders             -> retired response (410)
  /api/v1/*                       -> kiểm tra policy từng operation
  Unknown method/version/Host     -> safe reject, không fallback v1

Rủi ro:
  /api/*                          -> proxy tất cả tới legacy router
  /internal/v1/orders             -> route cũ bị bỏ sót
  v1.api.example.org              -> hostname cũ còn lộ trên internet
~~~

**Đừng chỉ grep chuỗi /v1** để kết luận đã hết đường cũ. Có thể còn version trong **headers, query, hostname, RPC package name**, route rewrite, upstream alias hoặc service discovery.

### 11.3. Tránh route confusion và canonicalization drift

Gateway và backend có thể hiểu khác nhau về **percent-encoding, slash, dot segments, case, duplicate headers, HTTP/2 :path/:authority và proxy rewrites**. Nếu gateway áp lifecycle policy lên một normalized route nhưng backend lại diễn giải raw request thành route khác, request có thể đến **handler đã retired**. Cần dùng **trusted route classification và canonicalization policy thống nhất**, từ chối input không hợp lệ và kiểm thử trên staging. Không thử các chuỗi bypass trên hệ thống ngoài phạm vi được phép.

## 12. Authentication và authorization phải được bảo toàn xuyên phiên bản

Một version mới thường sửa lỗi về **object-level authorization (BOLA)**, **function-level authorization (BFLA)** hoặc tenant separation. Nếu phiên bản cũ tiếp tục được phục vụ không được vá, kẻ tấn công có thể cố ý **chọn v1** để đi qua đường có kiểm soát yếu hơn.

### 12.1. Ví dụ cùng tài nguyên, hai security behaviors

~~~text
Supported v2:
  GET /api/v2/orders/{id}
  Requires: authenticated user + owns order / valid delegated scope

Legacy v1 (lỗi giả định):
  GET /api/v1/orders/{id}
  Only requires: valid token (không kiểm tra ownership)

Risk:
  Attacker hoặc client sai quyền yêu cầu v1 để bỏ qua BOLA.
~~~

**Cách sửa:** Bảo đảm **authorization theo object/tenant** được thực thi ở backend hoặc lớp thống nhất cho **mọi version còn hoạt động**. Nếu không thể vá v1, cần **chặn hoặc giới hạn nghiêm ngặt** theo risk decision thay vì giữ đường an ninh yếu chỉ vì còn client cũ.

### 12.2. Authentication scheme thay đổi

Khi migration từ API keys sang OAuth 2.0/mTLS hoặc đổi issuer/audience/scopes:

- Xác định **credential của từng consumer**, chủ sở hữu và thời hạn, không phát key mới không kiểm soát.
- Phân biệt **401** (authentication) với **403** (authorization), kiểm tra token expiry/issuer/audience/signature.
- Không chấp nhận token dành cho **v1 với scope rộng** trên v2 chỉ vì cùng issuer; phải có **audience/scope policy phù hợp**.
- Không tin header **X-User-Id, X-Tenant-Id, X-Role** do client gửi như identity đã xác thực.
- Cân nhắc **dual credential support** có giới hạn trong migration, được ghi exception; không để backdoor lâu dài.
- Sau retirement, thu hồi **API keys/service accounts** chỉ dành cho v1 khi không còn use case hợp lệ, kiểm tra luồng khác có phụ thuộc không.

### 12.3. Security baseline không được giảm cho version cũ

| Kiểm soát | Phải áp trên v1 còn hoạt động và v2 |
| --- | --- |
| TLS/peer validation | Thuật toán và identity được phê duyệt, không để v1 dùng TLS lỗi thời ngoài risk exception |
| Authentication/authorization | Chính sách resource-level/tenant-level nhất quán về mục tiêu |
| Input validation | Ràng buộc schema/kích thước, không chấp nhận payload nguy hiểm vì “legacy” |
| Rate limits | Theo authenticated consumer/tenant, phương thức và operation cần thiết |
| WAF/abuse monitoring | Theo protocol/endpoint, có đo false positives |
| Logging | Identity hợp pháp, operation, status, version, audit ID, bảo vệ PII |
| Egress/network segmentation | Không cho v1 truy cập DB/metadata/admin ngoài quyền |
| Patch vulnerability | Sửa security bugs hoặc ngừng vận hành khi không thể chấp nhận rủi ro |

**API gateway không thay thế business authorization** nếu gateway không biết quyền sở hữu order/payment trên từng object. Hãy thiết kế rõ trách nhiệm của edge, service và data layer.

## 13. API version và phân đoạn mạng, firewall, WAF, IDS/IPS

### 13.1. Gateway là một trong nhiều trust boundaries

~~~mermaid
flowchart TB
    U["Untrusted Clients"] --> W["CDN/WAF/Rate Controls"]
    W --> G["API Gateway: lifecycle + identity"]
    G --> A["Application v2"]
    A --> DB[("Production Data")]
    I["Internal callers / service mesh"] --> MG["Internal Gateway / mTLS"]
    MG --> A
    L["Legacy application v1"] -. "retired, network blocked" .-> DB
    U -. "origin bypass denied" .-> L
~~~

Không có nghĩa **mỗi** service cần public+internal gateway riêng; sơ đồ nhấn mạnh **đường mạng khác nhau phải có enforcement phù hợp**. Client nội bộ không tự động được miễn version lifecycle hoặc authorization chỉ vì có thể đi qua private subnet.

### 13.2. Mối nguy của endpoint cũ trong IDS/IPS

Một version cũ có thể tạo:

- Các URI/headers không còn được **WAF rule set** của version mới bảo vệ.
- Các signatures/baselines IDS/IPS không được kiểm thử trên legacy protocol.
- Nhiều **404/410, auth failures, version fallback** mà SOC khó phân biệt migration hợp lệ với dò endpoint.
- Nội dung phản hồi cũ chứa **dữ liệu quá mức**; về sau dễ bị thu thập nếu client credential lộ.
- Các proxy rewrite **trước/sau TLS termination** khiến log nhận dạng route khác nhau.

Điều cần theo dõi: **tỷ lệ traffic tới deprecated/retired operations, client identity, rule hit, response status, source network, environment, backend deployment và thời điểm thay đổi**. Không suy mọi request tới v1 là tấn công; có thể là cronjob, SDK cũ hoặc thiết bị offline lâu ngày.

### 13.3. IPv4/IPv6 và nhiều đường đi

Một host có thể có **A và AAAA records** hoặc nhiều public/internal load balancers. Có thể gateway IPv4 đã chặn v1 nhưng IPv6 listener vẫn trỏ vào runtime cũ. Cần kiểm thử **cả hai address families, tất cả regions, failover route, CDN-to-origin và direct backend**, không chỉ một URL trả 410.

### 13.4. TLS không phải version lifecycle

TLS 1.3 bảo vệ **đường truyền**, không cho biết API v1 được hỗ trợ hay an toàn. **API version** và **TLS protocol version** là hai thứ khác nhau. Ngừng TLS 1.0/1.1 theo security policy không tự ngừng /api/v1; ngừng /api/v1 cũng không đảm bảo mọi request v2 dùng TLS cấu hình tốt.

## 14. Lộ trình di chuyển client và đối tác khỏi phiên bản cũ

Không thể chỉ đếm **request volume của v1 giảm** rồi tuyên bố có thể tắt: một partner có thể chạy **batch mỗi quý**, một thiết bị mobile có thể offline lâu, hoặc một webhook chỉ kích hoạt khi có sự kiện hiếm.

### 14.1. Quy trình migration

1. **Identify:** Lập danh sách consumers đã xác thực, active trong 7/30/90 ngày và lịch sử sự kiện hiếm.
2. **Classify:** Nhóm theo production/partner/mobile/internal/IoT, data sensitivity và contractual impact.
3. **Notify:** Gửi thông báo theo owner/channel có thể kiểm chứng, không chỉ publish blog.
4. **Compare contracts:** Document field, auth scope, error, pagination, idempotency, webhook payload, callback verification.
5. **Provide sandbox:** Cho client test v2, fixtures và SDK release notes có kiểm soát.
6. **Canary clients:** Chuyển một nhóm đã đồng ý, đo request success, latency và business correctness.
7. **Enforce cutoff:** Chặn theo operation/identity khi đến mốc và đã đạt risk/approval criteria.
8. **Monitor stragglers:** Ghi requests tới v1 sau cutoff, cung cấp lỗi có migration link phù hợp.
9. **Clean up:** Xóa runtime, routes, docs, credentials, certs/hostnames và test coverage cũ theo quy trình.

### 14.2. Giao tiếp theo từng vai trò

| Vai trò | Thông tin cần |
| --- | --- |
| External partner | Mốc timezone, replacement, sandbox, auth changes, contact hỗ trợ |
| Mobile app developer | Minimum supported app, retry/offline behavior, rollout percentages |
| Internal service owner | Consumer dependency graph, contract tests, deployment plan |
| SRE/Platform | Gateway/CDN routes, monitoring, canary, rollback, decommission checklist |
| Security/SOC | Risk of unpatched legacy route, identity changes, expected 410/403 trends |
| Customer support | Thông điệp dễ hiểu và cách hướng dẫn người dùng nâng cấp |

### 14.3. Trường hợp client không thể nâng cấp

Nếu một đối tác phải duy trì một thời gian do phần mềm đã ngừng được nhà cung cấp hỗ trợ, có các lựa chọn **trước khi chấp nhận ngoại lệ**: triển khai **compatibility adapter an toàn**, chuyển sang file exchange/queue có policy, dùng **isolated access gateway** hoặc hợp đồng nâng cấp/retirement có thời hạn.

Không dùng **allow-any firewall** hoặc duy trì endpoint thiếu authorization vì “đối tác không nâng được”. Nếu việc tiếp tục vận hành không thể đạt mức rủi ro chấp nhận được, cần kế hoạch **ngừng truy cập** và xử lý cam kết nghiệp vụ minh bạch.

## 15. Compatibility adapter, strangler migration và dữ liệu nhất quán

Một **compatibility adapter** có thể nhận request theo contract v1, xác thực/ủy quyền, chuyển cấu trúc sang v2 và trả response theo schema v1. Cách này giúp giảm phụ thuộc code cũ, nhưng nó **không tự loại bỏ mọi rủi ro**: vẫn phải hỗ trợ v1 semantics và các client cũ.

~~~mermaid
flowchart LR
    C["Legacy client v1"] --> G["Gateway: v1 còn được phép theo policy"]
    G --> A["Compatibility adapter: validate + translate"]
    A --> V2["Service v2: authorization + business logic"]
    V2 --> A
    A --> C
    N["New client v2"] --> G2["Gateway v2"]
    G2 --> V2
~~~

### 15.1. Điều adapter phải giữ đúng

- **Authentication, identity, tenant và object authorization** không được yếu hơn backend v2.
- Transform fields không gây **truncation, đổi tiền tệ/timezone, mất precision, default nguy hiểm**.
- Error mapping không che 401/403 thành **200 OK** hoặc tạo retry storm.
- Request side effects như **POST/payment** có idempotency contract; không gửi request hai lần chỉ để so kết quả.
- API version chọn qua path/header phải được **normalize trước khi auth/routing**.
- Không để adapter có **network privileges rộng hơn** nhu cầu đến DB/admin.
- Duy trì **deprecation/sunset signal** trên response v1 và ghi metric consumers thật.

### 15.2. Shadow traffic và so sánh kết quả an toàn

**Shadowing** là gửi bản sao traffic được chọn sang hệ thống mới để so sánh kết quả. Nó chỉ phù hợp khi đã phân loại dữ liệu và **không tạo side effects ngoài ý định**. Không mirror một **POST thanh toán, upload chứa PII hoặc request mang bearer token thật** tới môi trường thử thiếu kiểm soát.

Đối với request đọc, vẫn cần **quyền dữ liệu, giới hạn tải, bảo mật PII và caching**. Kết quả của read-only request cũng có thể gây side effect gián tiếp qua audit/billing; cần thiết kế kiểm thử và authorization của shadow path.

### 15.3. Rollback có giới hạn

Nếu v2 gây lỗi nghiêm trọng, **rollback deployment** không đồng nghĩa có thể **mở lại v1 đầy lỗ hổng**. Hồ sơ rollout phải liệt kê trước những phương án an toàn: fix forward, giảm traffic bằng bounded queue, fallback tới bản đã vá hoặc tạm ngừng chức năng nhạy cảm. **Không giữ old route khả dụng ngoài Internet như “cửa hậu phục hồi”**.

## 16. Telemetry: đo lường quá trình sunset

### 16.1. Không chỉ đếm tổng request

| Metric | Ý nghĩa | Chú ý |
| --- | --- | --- |
| **Deprecated requests/s** | Lưu lượng còn tới version cũ | Một batch có thể rất ít lần nhưng quan trọng |
| **Distinct authenticated consumers** | Số client/partner IDs còn dùng version cũ | Không lấy IP đơn lẻ thay identity |
| **Last seen per consumer/operation** | Lần cuối gọi hợp lệ | Xét các job định kỳ hiếm |
| **Migration adoption** | Tỷ lệ clients chuyển sang version mới | Phân biệt sandbox và production |
| **Old API 4xx/410 rates** | Requests tiếp tục gọi sau sunset | Có thể là zombie SDK hoặc probing |
| **Auth failures and BOLA/BFLA denies** | Mức độ sai quyền trên v1/v2 | Một spike có thể là issue migration hoặc abuse |
| **Gateway-to-backend route drift** | Request vào route cũ bị rewrite đi đâu | Tránh bypass lifecycle |
| **Vulnerability patch backlog** | Risk tồn đọng của old runtime/library | Dùng để quyết định cần disable sớm |
| **Version-specific SLI** | Availability, error, latency theo cohort | Migration không được làm giảm chất lượng âm thầm |
| **Exception count/age** | Số gia hạn và thời gian còn mở | Tránh trở thành hỗ trợ vô hạn |

### 16.2. Mẫu event đã giảm dữ liệu nhạy cảm

~~~json
{
  "timestamp": "2026-12-02T08:30:00Z",
  "service": "orders-public",
  "environment": "production",
  "region": "region-a",
  "authority": "api.example.org",
  "api_version": "v1",
  "operation_id": "listOrdersV1",
  "method": "GET",
  "route_template": "/api/v1/orders",
  "consumer_id": "partner-demo",
  "lifecycle_status": "sunset_scheduled",
  "gateway_policy_revision": "gw-rev-12",
  "decision": "allowed_during_grace_period",
  "response_status": 200,
  "request_id": "req-example-001",
  "authentication": "validated"
}
~~~

**Không ghi full bearer token, API key, password, card data, nguyên request body hoặc query PII** trong lifecycle logs. Thay vì URL có order ID, dùng **normalized route template**; consumer ID có thể cần pseudonymization/retention theo chính sách.

### 16.3. Một dashboard hữu ích

Một dashboard sunset nên cho phép lọc theo **service/operation, owner, environment, region, API version, client cohort, auth scheme, IP family, HTTP status**; hiển thị **lượng traffic cũ, consumers còn dùng, ngày cuối thấy, policy drift và security risks**. Nếu không thấy traffic, cần phân biệt **không có request thật** với **telemetry mất/route bypass**.

**Không có traffic 30 ngày chưa chắc an toàn để xóa.** Quyết định phải xét **consumer duty cycle, business event frequency, contractual window, backup/DR path và thử nghiệm hồi quy**.

## 17. Không chỉ REST: gRPC, GraphQL, WebSocket, webhook và event APIs

### 17.1. GraphQL field deprecation

GraphQL thường có một endpoint HTTP chính, nhưng schema gồm **types, fields, arguments, enum values, mutations và subscriptions**. Một field có thể được đánh dấu **deprecated** với lý do và thay thế; xóa field có thể phá client dù URL không đổi.

~~~graphql
type Order {
  id: ID!
  legacyTotal: Float @deprecated(reason: "Use amountCents")
  amountCents: Int!
}
~~~

**Phải giám sát usage ở mức field/operation**, không chỉ request tới /graphql. Một query do ứng dụng mobile cũ gửi có thể gọi legacyTotal sau nhiều tháng không xuất hiện. **Authorization của GraphQL resolver** cũng phải được kiểm tra khi chuyển field: một field alias mới không tự áp quyền giống field đã xóa.

### 17.2. gRPC và Protocol Buffers

Với gRPC, các operation thường được định danh bằng **service/method** và schema protobuf. Một contract migration có thể thay đổi **package name, method, wire type, field numbers, streaming behavior, status codes và deadline semantics**.

Nguyên tắc phòng tránh:

- Không **tái sử dụng field number đã xóa** cho trường mang nghĩa khác; dùng cơ chế **reserved** khi phù hợp.
- Một field mới tuy có thể wire-compatible nhưng **business semantics/authorization** vẫn có thể breaking.
- Để đổi service/method, hỗ trợ **đồng thời v1/v2 theo kế hoạch** hoặc adapter có kiểm soát.
- Kiểm tra **HTTP/2/gRPC routing, mTLS service identity, method-level authorization**, không chỉ health.
- Khi retired một method, bảo đảm **alternate cluster/service discovery route** không còn đưa traffic tới implementation cũ.

### 17.3. WebSocket và streaming endpoints

Một WebSocket connection có thể tồn tại lâu hơn mốc sunset. Cần định nghĩa:

1. **New connections** tới version cũ có bị từ chối sau cutoff không?
2. **Existing connections** được duy trì đến deadline drain hay đóng ngay khi phát hiện critical vulnerability?
3. Protocol messages có **schema/version** riêng sau upgrade không?
4. Khi server gửi thông báo ngừng hỗ trợ, client có thể **reconnect lên version mới** an toàn không?

Đối với gRPC streams/Server-Sent Events, cần xem **drain deadline và retry/replay semantics**. Việc trả 410 cho handshake mới không tự ngắt những sessions cũ đã được thiết lập.

### 17.4. Webhooks và callbacks

Webhooks đảo chiều giao tiếp: **nhà cung cấp gửi event tới endpoint của đối tác**. Version có thể nằm trong **payload schema, event type, signature scheme, callback URL** hoặc header. Việc sunset cần kiểm tra:

- Đối tác đã đăng ký callback version nào, còn xác thực chữ ký/mTLS?
- Có **events đang chờ retry** theo schema cũ không?
- Dữ liệu nào phải replay hoặc dead-letter, idempotency key có giữ được?
- Thay callback URL/secret làm mất khả năng xác thực hoặc giao hàng không?
- Nếu chỉ ngừng event v1, có cơ chế **opt-in/upgrade** và deadline được thông báo?

**Không replay hàng loạt events thật sang sandbox** để thử migration nếu event có side effects hoặc chứa dữ liệu nhạy cảm.

### 17.5. Mobile, offline và API clients cũ

Người dùng có thể mở ứng dụng mobile sau nhiều tháng hoặc thiết bị IoT hoạt động với firmware đã ngừng cập nhật. Một request v1 xuất hiện sau sunset không nhất thiết là traffic độc hại. Nên trả **error UX có thể xử lý được**, yêu cầu nâng cấp rõ ràng và logging có quản lý dữ liệu. Với thiết bị không thể cập nhật, quyết định **từ chối, gia hạn, thay thiết bị hoặc proxy compatibility** cần owner và đánh giá an ninh.

## 18. Retirement phải đóng đủ đường vào

Đánh dấu version retired trên **developer portal** không đủ. Hãy dùng một **ma trận exposure** đối chiếu các mặt phẳng:

| Entry point / nguồn gọi | Đường có thể còn tồn tại | Bằng chứng đóng đúng |
| --- | --- | --- |
| Public DNS A/AAAA/CNAME | Legacy host v1 hoặc region cụ thể | DNS và network ingress không tới runtime cũ ngoài chủ đích |
| CDN/WAF | Cache, path rules, legacy hostname | Rule/config readback, cache behavior, direct origin tests |
| L4/L7 LB | Listener, host/path, header route, default backend | Live route map và ALLOW/DENY regression |
| API gateway | API product, operation, consumer-specific override | Policy revision, metrics và 410/403/404 phù hợp |
| Kubernetes | Ingress/Gateway/HTTPRoute, NodePort, Service, sidecar | Effective rules/controller, NetworkPolicy, mTLS |
| Cloud | API managed gateway, private link, function URL, regional endpoint | Cloud inventory, IAM, SG/NSG, log reconciliation |
| Internal service mesh | Virtual service, route subset, service discovery | Traffic từ service accounts đã xác thực và policy |
| Direct origin | Public IP/host/port, alternative domain | Deny ở mạng và backend auth, không chỉ ẩn DNS |
| SDK/CLI/mobile | Hardcoded URL, fallback path, cached config | Consumer versions và migration telemetry |
| Batch/webhook | Ít request, retry queue, scheduled jobs | Replay/queue handling và consumer owner confirmation |
| DR/failover | Config cũ được giữ ở region dự phòng | Bật DR có kiểm thử vẫn không khôi phục route retired |
| IPv6 | AAAA/listener/profile riêng | Kiểm thử song song IPv4 và IPv6 |

### 18.1. “Xóa DNS rồi” vẫn có thể là lỗ hổng

DNS chỉ giúp tìm địa chỉ. Nếu người gọi biết **IP origin, Host header hoặc private route**, họ vẫn có thể tới endpoint đã bị loại khỏi DNS khi network ACL hoặc backend chưa chặn. **Xóa record DNS không phải access control.**

### 18.2. Phân biệt chặn request và xóa runtime

Một kế hoạch giảm rủi ro thường có hai pha:

1. **Chặn request tới old contract** ở gateway/ingress cùng network protections, xác minh không bypass.
2. **Decommission implementation, credentials, storage access, DNS, certs, deployment và routes** khi không còn phụ thuộc hợp lệ.

Pha 1 bảo vệ trước khi dọn hệ thống; pha 2 giảm **attack surface dài hạn**. Trước xóa phải kiểm tra **retention/legal hold, backup/DR, audit, migration dữ liệu**. Không xóa log hoặc bí mật phục vụ incident response trái chính sách.

### 18.3. Không làm mất quan sát sau retirement

Sau khi gỡ backend v1, giữ **tín hiệu request bị từ chối ở ingress** (đã redaction) trong thời gian thích hợp để phát hiện client cũ, tích hợp bị quên hoặc hoạt động bất thường. Không giữ runtime v1 chỉ để ghi log; gateway có thể phát **410 hoặc safe reject** mà không gọi code cũ.

## 19. Chẩn đoán lỗi khi phiên bản API thay đổi

Lỗi sau upgrade có thể là **auth, contract, DNS/cache, WAF, gateway routing, SDK hoặc dữ liệu**, không tự mặc định do deprecation.

### 19.1. Quy trình xác minh từng lớp

~~~mermaid
flowchart TB
    C["Client: URL, method, version, request ID"] --> D{"DNS/ingress đúng?"}
    D -- "Không" --> DN["DNS, TLS SNI/Host, IPv4/IPv6, CDN"]
    D -- "Có" --> V{"Version/operation được hỗ trợ?"}
    V -- "Không" --> S["Lifecycle response + migration guide"]
    V -- "Có" --> A{"Auth / scope / resource quyền?"}
    A -- "Không" --> F["401/403 và identity evidence"]
    A -- "Có" --> R{"Route + schema + backend đúng?"}
    R -- "Không" --> P["OpenAPI contract, proxy rewrite, errors"]
    R -- "Có" --> O["Business behavior, SLI, dependency, data"]
~~~

### 19.2. Các hiện tượng và nguyên nhân thường gặp

| Triệu chứng | Giả thuyết | Bước xác minh |
| --- | --- | --- |
| Request v1 vẫn nhận 200 sau cutoff | Gateway/region/backend bypass, exception còn mở | Ingress route readback, consumer identity, timestamp, policy |
| Request v2 nhận 410 nhầm | Wildcard lifecycle rule match nhầm route | Normalized path, method, route priority, test versions |
| 401 tăng sau migration | Issuer/audience/token credential khác | Auth logs đã redaction, token policy, client config |
| 403 tăng sau migration | Scope/resource permissions khác | BOLA/BFLA checks, account roles và migration mapping |
| 404 cho một region | Region/DNS/route config chưa đồng bộ | Regional config snapshots, IPv4/IPv6 |
| 406 hoặc 415 | Header media type version không được hỗ trợ | Accept/Content-Type negotiation, clients |
| 400/422 tăng | Schema/validation thay đổi | Contract diff, field defaults, error body |
| 429 tăng chỉ với v2 | Rate limit key/quota khác | Client ID, trusted identity, gateway policy |
| HTTP 502/503/504 | Upstream health/route/timeout, không nhất thiết lifecycle | Proxy vs backend logs, SLI, trace ID |
| Mobile app cũ xuất hiện sau 90 ngày | Offline/long-tail client | App lifecycle, owner, support strategy |
| Webhook fail sau migration | Signature schema/secret/callback đổi | Signature verification, queue/dead-letter, event IDs |
| v2 hoạt động ở IPv4 nhưng v1 mở ở IPv6 | Dual-stack route drift | A/AAAA, listeners, network policy, request tests |

### 19.3. Đừng chỉnh status code để che lỗi

Nếu một endpoint đã retired thật sự trả 410, đừng biến thành **503** chỉ để dashboard availability “đẹp hơn”. Metrics nên tách **expected policy rejection** khỏi **unintended 5xx outage**. Ngược lại, nếu v2 đang hỏng và gateway trả 410 do rule match sai, sửa **policy classification** chứ không tuyên bố client cần nâng cấp nữa.

## 20. Thực hành offline bằng Python: đánh giá chính sách sunset

Bài lab sử dụng **dữ liệu giả lập trong bộ nhớ**, không mở kết nối mạng, không đọc API keys hoặc logs thật và không thay cấu hình gateway. Mục tiêu là **mô hình hóa quyết định lifecycle** theo operation và thời điểm, trong khi vẫn nhắc rõ **authorization phải thực thi riêng**.

### 20.1. Bài toán

API Orders có v1 dự kiến sunset ngày **2026-12-31T00:00:00Z**, v2 đang active và một đối tác được phê duyệt **gia hạn ngắn đến 2027-01-15T00:00:00Z** trên đúng một operation. Sau cutoff, các client khác phải nhận **410 Gone**; version không biết phải trả **404** theo mô hình lab.

~~~python
from dataclasses import dataclass
from datetime import datetime, timezone


def utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class Operation:
    method: str
    route: str
    version: str
    lifecycle: str
    cutoff_at: datetime | None
    replacement: str | None = None


@dataclass(frozen=True)
class ExceptionGrant:
    consumer: str
    method: str
    route: str
    valid_until: datetime


operations = [
    Operation(
        "GET", "/api/v1/orders", "v1", "sunset_scheduled",
        utc("2026-12-31T00:00:00Z"), "/api/v2/orders",
    ),
    Operation("GET", "/api/v2/orders", "v2", "active", None),
]

exceptions = [
    ExceptionGrant(
        "partner-approved", "GET", "/api/v1/orders",
        utc("2027-01-15T00:00:00Z"),
    ),
]


def decide(
    method: str, route: str, consumer: str, now: datetime
) -> tuple[int, str]:
    """Mô phỏng lifecycle; GIẢ ĐỊNH consumer ID đã xác thực từ nơi khác."""
    now = now.astimezone(timezone.utc)
    op = next(
        (x for x in operations if x.method == method and x.route == route),
        None,
    )
    if op is None:
        return (404, "unknown_operation")
    if op.lifecycle == "retired":
        return (410, "retired")
    if op.cutoff_at is not None and now >= op.cutoff_at:
        allowed = any(
            g.consumer == consumer
            and g.method == method
            and g.route == route
            and now < g.valid_until
            for g in exceptions
        )
        if not allowed:
            return (410, "sunset_cutoff")
        return (200, "approved_temporary_exception")
    if op.lifecycle in ("deprecated", "sunset_scheduled"):
        return (200, "deprecation_notice")
    if op.lifecycle == "active":
        return (200, "supported")
    return (403, "unrecognized_lifecycle_state")


checks = [
    ("GET", "/api/v1/orders", "partner-normal",
     utc("2026-12-20T10:00:00Z")),
    ("GET", "/api/v1/orders", "partner-normal",
     utc("2027-01-02T10:00:00Z")),
    ("GET", "/api/v1/orders", "partner-approved",
     utc("2027-01-02T10:00:00Z")),
    ("GET", "/api/v1/orders", "partner-approved",
     utc("2027-01-16T00:00:00Z")),
    ("GET", "/api/v2/orders", "partner-normal",
     utc("2027-01-16T00:00:00Z")),
    ("POST", "/api/v1/orders", "partner-approved",
     utc("2027-01-02T10:00:00Z")),
]

for method, path, client, timestamp in checks:
    print(method, path, client, decide(method, path, client, timestamp))

assert decide(
    "GET", "/api/v1/orders", "partner-normal",
    utc("2027-01-02T10:00:00Z"),
) == (410, "sunset_cutoff")
assert decide(
    "GET", "/api/v1/orders", "partner-approved",
    utc("2027-01-02T10:00:00Z"),
) == (200, "approved_temporary_exception")
assert decide(
    "POST", "/api/v1/orders", "partner-approved",
    utc("2027-01-02T10:00:00Z"),
) == (404, "unknown_operation")
~~~

Kết quả dự kiến:

~~~text
GET /api/v1/orders partner-normal (200, 'deprecation_notice')
GET /api/v1/orders partner-normal (410, 'sunset_cutoff')
GET /api/v1/orders partner-approved (200, 'approved_temporary_exception')
GET /api/v1/orders partner-approved (410, 'sunset_cutoff')
GET /api/v2/orders partner-normal (200, 'supported')
POST /api/v1/orders partner-approved (404, 'unknown_operation')
~~~

### 20.2. Giới hạn bắt buộc của bài lab

- **Không có authentication/authorization thực tế**; hàm giả định consumer đã được xác thực bởi một thành phần khác. Không đưa giá trị do caller tự gửi làm quyền ngoại lệ.
- Không xử lý **routing, HTTP parsing, percent-encoding, CDN cache, Host headers, TLS, BOLA, tenant/data permission** hoặc multi-region convergence.
- **200** chỉ là kết quả *policy allow* mô phỏng; backend thực có thể trả 201/204/4xx/5xx.
- Exception chỉ xét **đúng method và route**, không cấp quyền wildcard, nhưng vẫn chưa có scope/approval audit trong code.
- Không tự áp chính sách này vào gateway production; cần transaction/config control, staging tests, canary, metrics và rollback.
- Không dùng datetime naïve; tất cả mốc có timezone rõ và so sánh theo UTC.

### 20.3. Bài tập mở rộng

1. Thêm **POST /api/v1/orders** rồi xem grant cho GET có áp sang POST không.
2. Thêm **environment, region, hostname** vào khóa operation để phát hiện route v1 còn tồn tại trên IPv6/DR.
3. Thêm **scope/tenant** và chỉ áp lifecycle sau khi xác thực/ủy quyền bằng một cơ chế thực.
4. Thêm trạng thái **disabled_due_to_security_incident** có độ ưu tiên cao hơn exception.
5. Tạo log event có **policy ID, status, timestamp, pseudonymous consumer ID** mà không chứa token.
6. Thiết kế **pre-cutoff warning**, lỗi 410 kèm migration docs; phân biệt status 410 ở gateway với status 410 do ứng dụng trả.

## 21. Case study A: v1 bị khai tử ở gateway nhưng vẫn có đường trực tiếp

**Bối cảnh giả định:** Tổ chức nâng cấp Orders API từ v1 sang v2. Gateway public chính đã chuyển route **/api/v1/orders** sang trả **410 Gone**. Đội vận hành báo đã “tắt v1”. Tuy nhiên một region dự phòng còn **internal load balancer public-facing do cấu hình nhầm**, và service v1 vẫn đăng ký endpoint trên subnet IPv6 khác.

### 21.1. Dấu hiệu

- Request vào **api.example.org** qua CDN/gateway chính trả 410 như dự kiến.
- Log v1 runtime vẫn ghi **200 responses** từ một số nguồn khi ngoài gateway.
- Endpoint ở **IPv4** được chặn nhưng listener/route qua **IPv6** còn truy cập được.
- Network flow logs cho thấy traffic tới **backend v1** không đi qua API gateway policy revision mới.
- Auth code v1 vẫn chỉ kiểm tra token hợp lệ, thiếu **object authorization** mới của v2.

### 21.2. Nguyên nhân gốc

Tổ chức đồng nhất **“trả 410 trên một URL qua một edge”** với **“retire toàn bộ implementation”**. Không có inventory đầy đủ về **hostnames, direct origin, regions, IP families, service discovery và service accounts**. Version cũ vì thế vẫn reachable ở một trust boundary khác.

~~~mermaid
flowchart LR
    C["External client"] --> G["Main API Gateway"]
    G -->|"v1 → 410 Gone"| STOP["Retired response"]
    G -->|"v2 → allowed"| V2["Orders v2"]
    C -. "Alternate path / IPv6" .-> O["Legacy origin v1 còn mở"]
    O --> DB[("Orders data")]
~~~

### 21.3. Ứng phó có kiểm soát

1. **Khoanh vùng exposure:** Xác định các listeners/hostnames/routes của v1, xác minh access logs theo timestamp, không tự suy tất cả sources là attacker.
2. **Ưu tiên đóng đường có rủi ro:** Với lỗ hổng quyền nghiêm trọng, chặn ingress/backend access theo chính sách khẩn cấp đã được phê duyệt.
3. **Xác định blast radius:** Phân biệt IP family, region, environment, credentials và dữ liệu có thể truy cập.
4. **Đối soát route state:** Kiểm tra gateway, cloud LB, Kubernetes ingress/NodePort, security group, network policy, service mesh và direct origin.
5. **Vá hoặc cô lập legacy code:** Nếu còn exception hợp lệ, không tiếp tục dùng code v1 lỗi BOLA; cần xử lý an ninh trước.
6. **Kiểm chứng cả ALLOW/DENY:** V2 vận hành tốt; v1 bị chặn trên tất cả đường; user không có quyền vẫn không đọc object khác.
7. **Bảo toàn bằng chứng:** Giữ audit/logs đúng retention, mở điều tra nếu có dấu hiệu khai thác.
8. **Ngăn tái diễn:** Bổ sung route-inventory reconciliation, policy-as-code, kiểm thử DR và IPv6 vào quy trình retirement.

### 21.4. Bài học

**Retirement là một thuộc tính được thực thi trên tất cả exposure points, không phải một dòng trạng thái trong portal.** Khi version có lỗ hổng nghiêm trọng, việc chỉ trả 410 ở một ingress có thể tạo **ảo giác đã giảm attack surface**.

## 22. Case study B: đối tác B2B chưa nâng SDK kịp ngày sunset

**Bối cảnh giả định:** Một đối tác chỉ đồng bộ dữ liệu vào ngày đầu mỗi quý, vẫn dùng v1. Dashboard 30 ngày gần nhất cho thấy **0 request v1** và đội sản phẩm muốn xóa implementation ngay. Đến ngày đồng bộ tiếp theo, đối tác gặp 410 và tiến trình đối soát dữ liệu không hoàn thành.

### 22.1. Tại sao metric dẫn đến kết luận sai?

- **Khoảng 30 ngày** không bao quát job chạy hàng quý.
- Client/partner **owner mapping** thiếu, không có báo xác nhận đã test v2.
- SDK của đối tác hardcode v1, nhưng tài liệu của công ty đã gỡ v1 khỏi portal.
- Không có **synthetic/contract test** cho hành trình đồng bộ hiếm.
- Hợp đồng có thể yêu cầu **thời hạn hỗ trợ** khác nội dung thông báo nội bộ.

### 22.2. Phương án chuyển đổi an toàn

| Phương án | Lợi ích | Đánh đổi và kiểm soát |
| --- | --- | --- |
| Đối tác nâng SDK và chạy sandbox v2 | Xóa dependency lâu dài | Cần lịch release, test contract/idempotency |
| Giữ v1 trong một khoảng extension hẹp | Giảm gián đoạn trước hạn | Chỉ nếu security posture chấp nhận; scope theo identity/operation và expiry |
| Compatibility adapter đã được bảo vệ | Chuyển v1 contract tới v2 runtime | Phải kiểm tra auth, data mapping và không giữ lỗ hổng v1 |
| Chuyển sang job/file exchange có bảo vệ | Phù hợp batch hiếm khi HTTP realtime không cần thiết | Thêm integration và nghĩa vụ bảo vệ file/PII |
| Dừng tích hợp khi legacy không an toàn | Ngăn tiếp tục phơi lộ hệ thống | Tác động nghiệp vụ/hợp đồng, cần kế hoạch truyền thông |

### 22.3. Các bước thực hiện

1. Liên hệ **technical owner và business owner** của đối tác qua kênh đã kiểm chứng.
2. Làm **contract diff** v1→v2, bao gồm auth, field mapping, pagination và idempotency.
3. Cung cấp sandbox/test data **không chứa dữ liệu Production thật**.
4. Thiết lập trial trong staging, xác định response/error semantics và lịch batch.
5. Nếu gia hạn, cấp **exception có expiry và audit**, không mở version cũ cho mọi consumer.
6. Theo dõi lượt dùng v1 trên chu kỳ thực tế đủ dài, xác nhận đối tác chuyển đổi.
7. Đóng v1 và loại bỏ token/route/implementation không còn cần.

**Bài học:** Đánh giá deprecation theo **đời sống thực của consumer**; chỉ dùng RPS để quyết định sunset dễ bỏ sót những tích hợp ít gọi nhưng có tác động cao.

## 23. Mô hình hóa mối đe dọa khi version cũ tiếp tục tồn tại

| Threat/failure scenario | Điểm yếu | Hậu quả | Phòng vệ |
| --- | --- | --- | --- |
| **Zombie API** | Route chưa inventory, owner rời dự án | Không được vá/giám sát | Discovery từ runtime, asset ownership và reconciliation |
| **Version downgrade to bypass auth** | V1 thiếu BOLA/BFLA fix của v2 | Truy cập data trái quyền | Vá mọi active versions hoặc emergency disable |
| **Gateway/backend route confusion** | Path/headers được normalize khác nhau | Request tới handler bị chặn ở gateway | Parsing/canonicalization nhất quán, route tests |
| **Token reuse across versions** | Token/scope v1 được tin quá rộng ở v2 | Lateral access/cross-tenant | Audience, scopes, identity-specific policy |
| **Old service account abuse** | Credentials không revoke sau retirement | Truy cập trái phép vào backend/data | Credential inventory, revoke và IAM audit |
| **Hidden public origin** | Chỉ xóa DNS/edge rule | Bypass WAF, auth gateway, rate limit | Private ingress, SG/ACL/NetworkPolicy, backend auth |
| **Replay during migration** | Shadow/dual-write request có side effect | Thanh toán/đơn hàng bị nhân đôi | Idempotency, non-prod fixtures, read-only shadow |
| **Invalid cache version variation** | CDN không key theo version header | Response version/tenant bị trộn | Cache key và Vary, no-store cho dữ liệu riêng tư |
| **Silent 301/308 redirect** | POST v1 gửi lại tới v2 semantics khác | Dữ liệu sai hoặc giao dịch lặp | Không redirect khi chưa chứng minh semantic equivalence |
| **Deprecated route lacks WAF** | Rule chỉ áp v2 | Lỗ hổng HTTP legacy bị khai thác | WAF coverage trên mọi live routes |
| **Old webhook secret** | Secret/signature scheme cũ tồn tại | Event spoofing/unauthorized callback | Rotation, signature verification, partner lifecycle |
| **Long-tail mobile fallback** | SDK tự fallback v1 khi v2 lỗi | Version cũ tái xuất bất ngờ | SDK policy, disable fallback không an toàn |
| **Drift ở DR/IPv6** | Policy không deploy nhất quán | v1 vẫn mở trên đường dự phòng | Canary/test trên từng region và IP family |
| **Excessive lifecycle logging** | Log token/PII để tìm client cũ | Rò dữ liệu nhạy cảm | Authenticated consumer ID, redaction, retention |
| **Uncontrolled extension** | Ngoại lệ không hạn | Hỗ trợ v1 vô thời hạn | Expiry, approval, compensating controls và review |

### 23.1. Kết nối STRIDE với vòng đời API

Trong một **data flow diagram (DFD)**, những khu vực cần xem gồm **Internet client → API gateway → version router → app service → database**, cùng đường webhook và internal service caller. Các nhóm câu hỏi:

- **Spoofing:** Client tự khai identity/version hay thông tin từ proxy có xác thực?
- **Tampering:** Policy/config routing có thể bị thay trái quyền?
- **Repudiation:** Có log version, consumer, operation, policy decision và UTC timestamp đủ để điều tra?
- **Information disclosure:** Version cũ có trả thêm trường nhạy cảm, hoặc error body tiết lộ sự tồn tại resource?
- **Denial of service:** Legacy pool/old parsers có giới hạn traffic/rate và upstream protection?
- **Elevation of privilege:** V1 cho gọi admin hoặc truy cập object khác tenant mà v2 đã chặn?

### 23.2. Phân biệt retirement với tăng cường chống dò endpoint

Sau khi tắt một đường cũ, việc nhận request tới URL v1 có thể là **client chưa nâng cấp, bot internet hoặc probing có chủ đích**. Một dashboard trả 410 nhiều không chứng minh bị tấn công. Phân loại theo **authenticated identity khi có, nguồn, lịch sử hành vi, tỷ lệ, phương thức, WAF/IDS correlation và policy impact**, không block toàn dải IP dựa vào một tín hiệu.

## 24. Runbook ngừng hỗ trợ một endpoint

### 24.1. Trước mốc deprecation

1. Chọn **target replacement contract** và xác nhận các tính năng/authorization tương đương hoặc được cải tiến.
2. Lập danh mục **entry points và client cohorts**, rà soát legal/contract và security risk.
3. Viết **migration guide, error behavior, tài liệu API và SDK changelog**.
4. Gán **technical/product/security owner**, định nghĩa support/deprecation/sunset timestamps theo UTC.
5. Thử **OpenAPI diff, schema contract tests, ingress policy, WAF và per-version metrics**.
6. Công bố lịch bằng kênh phù hợp, có **nguồn hỗ trợ và escalation**.

### 24.2. Trong giai đoạn deprecated

1. Gắn **deprecation metadata/headers** cho các responses phù hợp; đảm bảo CDN không mất header ngoài ý định.
2. Đóng **đăng ký tích hợp mới** tới v1 khi chính sách yêu cầu.
3. Theo dõi **consumer identity, traffic patterns, auth failures và business workflows**.
4. Chuyển client từng nhóm, kiểm tra **request success và dữ liệu**, không chỉ status 200.
5. Duy trì **security patches/segmentation** cho những phiên bản còn reachable.
6. Quản lý extension **đúng operation, client, owner, expiry**.

### 24.3. Tại mốc cutoff

~~~mermaid
flowchart TD
    A["Approval + inventory freeze"] --> B["Deploy lifecycle policy tới tất cả ingress"]
    B --> C["Canary/rollout theo scope"]
    C --> D{"Kiểm thử ALLOW v2 và DENY v1?"}
    D -- "Không" --> E["Rollback an toàn / incident response"]
    D -- "Có" --> F["Readback route/region/IPv4/IPv6"]
    F --> G["Observe 410, SLI, clients, WAF logs"]
    G --> H["Decommission runtime & credentials có kế hoạch"]
    H --> I["Post-retirement monitoring / audit"]
~~~

1. Xác minh mọi **gateway/ingress/CDN/backend routes**, bao gồm DR/IPv6.
2. Bật **policy chặn theo mốc**, không để backend cũ nhận request không được phép.
3. Kiểm thử **v2 ALLOW, v1 DENY, unknown version safe reject, auth/scope DENY**.
4. Đo errors/latency/SLI, tách **expected 410** khỏi outage 5xx.
5. Giữ khả năng **rollback an toàn**, không tự khôi phục đường có critical vulnerability.
6. Dọn code/runtime/credentials/DNS và kiểm tra **không còn dependency** theo kế hoạch.

### 24.4. Emergency retirement khi có lỗ hổng nghiêm trọng

**Security emergency** có thể yêu cầu tắt ngay mà **không chờ đủ grace period** nếu rủi ro và chính sách đòi hỏi. Khi đó:

- Security và incident commander phối hợp với product/owner để chốt mức ảnh hưởng và thẩm quyền.
- Ưu tiên **giới hạn đường rủi ro bằng ingress/auth/IAM/network policy**, không thao tác xóa dữ liệu hoặc phá log điều tra.
- Có thể cung cấp **maintenance response** và hướng dẫn chuyển v2 theo an toàn thông tin, tùy loại service.
- Không mở exception trên version vulnerable chỉ để né SLA nếu không có biện pháp giảm thiểu được phê duyệt.
- Thông báo cho consumers theo nghĩa vụ, lưu timeline UTC và hành động/approval.

### 24.5. Mẫu change record

~~~text
CHANGE ID:
API ID / OPERATION / VERSION / HOST / ENVIRONMENT:
OWNER / SECURITY REVIEWER:
MILESTONES: deprecated / support end / sunset / removal (UTC)
REPLACEMENT CONTRACT / SDK / MIGRATION GUIDE:
CONSUMER IMPACT / LAST-SEEN EVIDENCE:
EXCEPTION IDs / EXPIRY / APPROVAL:
AUTH / TENANT / RESOURCE-LEVEL POLICY:
INGRESS INVENTORY: CDN, gateway, LB, IPv4, IPv6, DR, internal
SECURITY: WAF, rate, origin restriction, CVEs and patching
DEPLOY PLAN: canary, stop-new-use, cutoff, backend cleanup
VALIDATION: ALLOW v2, DENY v1, origin bypass, auth, SLI
ROLLBACK: approved safe path and triggers
READBACK / LOGS / POSTMORTEM:
~~~

## 25. Ma trận kiểm thử phiên bản và endpoint ngừng hỗ trợ

Các phép thử bên dưới dành cho **lab, staging hoặc hệ thống được cấp quyền**. Chỉ thử requests và identity được ủy quyền; không brute force, fuzz hay quét endpoint của bên thứ ba. Mỗi test cần xác minh **kết quả chức năng** và **bảo mật**.

| Test ID | Tình huống | Kết quả / bằng chứng mong đợi |
| --- | --- | --- |
| API-01 | Client mới gọi operation v2 đang active | ALLOW khi được xác thực/ủy quyền đúng, SLI đạt |
| API-02 | Client hợp lệ gọi v1 trước deprecation | Contract/response đúng theo policy phiên bản cũ |
| API-03 | v1 đang deprecated, trước cutoff | Request được xử lý theo policy, deprecation notice/documentation phù hợp |
| API-04 | v1 sau cutoff, không có exception | Từ chối bằng 410/404 phù hợp hợp đồng, không tới backend cũ |
| API-05 | Exception đúng consumer/operation trước expiry | Chỉ được phép trong scope/khung giờ, có audit |
| API-06 | Exception đã hết hạn | Bị từ chối, không fallback tự động |
| API-07 | Exception GET v1 thử gọi POST v1 | Không được hưởng quyền của GET, method scope được tách |
| API-08 | Unknown Host/version/HTTP method | Safe reject, không route nhầm tới legacy admin handler |
| API-09 | URL v1 nhưng header chọn v2 | Chính sách rõ ràng, reject nếu version negotiation mâu thuẫn |
| API-10 | Media-type version qua Accept/Content-Type | Negotiation đúng, 406/415 khi thích hợp |
| API-11 | OpenAPI operation deprecated | Developer portal/SDK thấy cảnh báo; runtime không tự chặn nhầm |
| API-12 | Deprecation/Sunset response headers | Giá trị đúng format và thời gian, proxy/CDN không xóa |
| API-13 | Sunset date/time UTC trên nhiều regions | Quyết định nhất quán sau hội tụ, clock sync và readback |
| API-14 | V1 direct origin / alternate hostname | DENY sau retirement; không bypass gateway |
| API-15 | V1 qua IPv6 listener | DENY giống IPv4, không còn route ngoài ý định |
| API-16 | V1 ở DR region sau failover mô phỏng | Không khôi phục policy/route cũ trái chủ đích |
| API-17 | Client v2 thiếu authentication | 401 hoặc response phù hợp, không bị lifecycle rewrite cho phép |
| API-18 | Client v2 có token nhưng thiếu object permission | 403/deny theo policy, BOLA test PASS |
| API-19 | Client v1 dùng scope/token để truy cập v2 ngoài audience | Không được nâng quyền tự động |
| API-20 | Cross-tenant order access qua v1/v2 | DENY cho cả những operation còn phục vụ |
| API-21 | Rate limit theo identity trên từng version | Không vượt quota bằng cách chuyển v1↔v2 |
| API-22 | CDN cache với Accept/header chọn version | Không trộn nội dung v1/v2, user/tenant |
| API-23 | Client legacy dùng 301/308 redirect | Không tự gửi request có side effect sang semantics khác |
| API-24 | SDK mobile offline mở lại sau cutoff | Nhận lỗi có hướng dẫn nâng cấp, không tự downgrade không an toàn |
| API-25 | B2B batch hiếm theo lịch quý | Có owner/migration check; không bị bỏ sót vì metric 30 ngày |
| API-26 | GraphQL deprecated field | Field usage được giám sát, auth resolver và migration đúng |
| API-27 | gRPC removed field/service method | Wire compatibility/authorization được test, reserved fields đúng |
| API-28 | WebSocket/gRPC stream qua thời điểm sunset | New connections policy và existing sessions drain rõ ràng |
| API-29 | Webhook schema/signature version cũ | Retry/dead-letter, signature, idempotency và migration đúng |
| API-30 | Adapter nhận v1 và gọi v2 | Không mất tenant identity, authorization, data semantics |
| API-31 | Shadow traffic / canary v2 | Không double-write, không rò PII sang test environment |
| API-32 | V1 có critical security vulnerability | Emergency disable ưu tiên hơn exception, logs/approval đầy đủ |
| API-33 | Xóa runtime cũ sau chặn gateway | Không còn backend credentials/route cần thu hồi, retention đúng |
| API-34 | Rollback khi v2 lỗi | Không mở lại v1 vulnerable; áp phương án an toàn được phê duyệt |
| API-35 | Telemetry không thấy request v1 | Đối soát gateway/ingress để phân biệt không traffic với mất log |
| API-36 | Client gọi route đã retired từ mạng ngoài sau cutoff | Gateway vẫn thu metric đã redaction, backend cũ không được gọi |

### 25.1. Mẫu kết quả kiểm thử

~~~text
TEST ID / CHANGE ID:
UTC timestamp / test owner:
API ID, operation, method and version:
Host, route, environment, region, IPv4/IPv6:
Client cohort and authenticated identity (no secrets):
Lifecycle expected state and policy revision:
Actual decision / response status / backend selected:
Authorization and tenant-object result:
Deprecation/Sunset response metadata:
Gateway, WAF, firewall and application logs:
Application/business outcome and SLI:
Rollback/defect/remaining risk:
~~~

### 25.2. Ba mức xác minh

1. **Static:** API inventory, OpenAPI/Proto contract, policy-as-code, deprecation/sunset dates, exceptions và security review.
2. **Runtime:** Gateway/CDN/ingress/cloud/IPv6/DR route readback, negotiated auth, backend mapping và access logs.
3. **End-to-end:** Client thực trong phạm vi được phép nhận hành vi đúng; **v2 ALLOW**, **v1 DENY sau cutoff**, **cross-tenant/admin DENY**, thông báo migration rõ và không mất dữ liệu.

**Chỉ có contract tests PASS không chứng minh retirement đã hoàn tất**, vì một listener cũ có thể tồn tại ngoài CI/CD pipeline. Ngược lại, chỉ có gateway 410 không chứng minh v2 tương thích hoặc không có đường bypass.

## 26. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Đổi version nghĩa là nâng release của microservice.” | Public contract version khác implementation build/config revision. |
| “Xóa v1 khỏi docs là đã ngừng v1.” | Runtime routes, ingress, credentials và backend còn có thể reachable. |
| “Deprecated nghĩa là request đã bị chặn.” | Deprecated thường là cảnh báo và giai đoạn di chuyển, chưa nhất thiết retired. |
| “EoS, EoL, Sunset, Retired có nghĩa như nhau.” | Các mốc hỗ trợ, khả dụng và thực thi có thể khác nhau. |
| “Version luôn nằm trong /v1 path.” | Có thể qua host, header, media type, gRPC package hoặc GraphQL schema. |
| “Tăng minor version bảo đảm không breaking.” | Thay đổi schema/semantics/auth phải test; SemVer tùy chính sách áp dụng. |
| “Thêm field JSON chắc chắn compatible.” | Một số client validate schema strict hoặc có logic không chấp nhận field mới. |
| “V1 không cần vá vì sắp sunset.” | Nếu còn reachable vẫn mang rủi ro, có thể phải vá hoặc emergency disable. |
| “Sửa BOLA làm client cũ lỗi nên phải rollback.” | Security fix có thể bắt buộc, cần migration chứ không giữ bypass. |
| “API key v1 dùng được thì cứ cho token đó vào v2.” | Scope, audience, tenant và credential lifecycle phải xác minh. |
| “HTTP 426 là mã chuẩn báo cần dùng API v2.” | 426 liên quan nâng cấp protocol theo HTTP Upgrade, không phải generic API sunset. |
| “Sunset header tự tắt endpoint đúng ngày.” | Chỉ là tín hiệu; policy thực thi phải được triển khai riêng. |
| “410 và 404 luôn đổi cho nhau được.” | Có khác biệt semantics và rủi ro lộ sự tồn tại resource. |
| “301/308 redirect POST v1 sang v2 luôn an toàn.” | Method/side effects/schema có thể khác và tạo giao dịch lặp. |
| “Không thấy v1 30 ngày nghĩa là không có consumer.” | Partner batch quý/mobile offline/DR có thể chưa tạo traffic. |
| “Một đối tác dùng chung NAT nên có thể allowlist IP là đủ.” | IP không phải identity mạnh, cần client authentication/operation scope. |
| “V1 trả 410 ở CDN là mọi đường đã đóng.” | Direct origin, IPv6, private ingress và DR route có thể còn mở. |
| “Xóa DNS là xóa quyền truy cập API.” | DNS không là access control, origin IP/Host vẫn có thể reachable. |
| “Backend cũ không nhận HTTP public nhưng không cần dọn credential.” | Stale keys/accounts/routes vẫn có thể bị lạm dụng nội bộ. |
| “GraphQL không có version nên không cần lifecycle.” | Fields/types/mutations/schema vẫn có deprecation/removal cần quản trị. |
| “gRPC chỉ cần binary wire-compatible.” | Business semantics, auth, streaming và method lifecycle cũng quan trọng. |
| “WebSocket đã connect thì không cần quan tâm sunset.” | New vs existing sessions, drain/reconnect phải được quy định. |
| “429 nghĩa là API đã hết hạn.” | 429 là rate limit, không phải retirement. |
| “Có HTTPS/TLS 1.3 thì API v1 an toàn.” | Kênh mã hóa không thay thế authorization, code patching và version governance. |
| “Traffic 410 tăng là chắc bị tấn công.” | Có thể là client cũ, SDK fallback hoặc batch job chưa được migration. |

## 27. Câu hỏi tự kiểm tra và bài tập thiết kế

1. **Deprecated khác retired thế nào?** Deprecated thông báo không khuyến nghị dùng và sẽ thay thế; retired không còn phục vụ contract cũ theo chính sách.
2. **Một operation identity cần hơn route path ở đâu?** Host, method, version selection, environment và trong nhiều hệ thống còn tenant.
3. **Vì sao xóa DNS không đóng API?** Origin IP/alternate route vẫn có thể nhận traffic nếu network policy chưa chặn.
4. **Tại sao không thể dùng request count 30 ngày duy nhất để quyết định sunset?** Có long-tail mobile, partner batch quý và DR jobs.
5. **OpenAPI deprecated: true làm gì?** Gắn metadata thông báo cho operation/schema phù hợp; không tự chặn runtime.
6. **Deprecation response header có phải lệnh bắt buộc client nâng cấp?** Không; là tín hiệu mô tả theo chuẩn.
7. **Sunset header có tự disable endpoint?** Không; server/gateway lifecycle enforcement riêng.
8. **Khi nào 410 Gone thích hợp?** Khi resource/operation từng có nhưng đã không còn được cung cấp và có thể công bố điều đó.
9. **Vì sao 426 Upgrade Required không phải mã sunset chung?** Nó thuộc cơ chế nâng cấp giao thức HTTP, không mang semantics version API.
10. **Điều gì nguy hiểm khi redirect POST từ v1 sang v2?** Body/side effects/authorization/idempotency có thể khác.
11. **BOLA ở v1 có thể bị lợi dụng dù v2 đã vá thế nào?** Attacker chọn route v1 để bỏ qua kiểm soát object ownership.
12. **Vì sao token v1 không tự có quyền v2?** Audience/scopes/resource policy có thể khác, cần xác thực/ủy quyền lại.
13. **Extension cho một partner cần những trường nào?** Consumer identity, operation, lý do, approval, expiry và compensating controls.
14. **Vì sao header chọn version gây rủi ro cache?** Cần vary/cache key đúng, tránh trộn versions/users.
15. **GraphQL cần theo dõi điều gì ngoài /graphql request count?** Field/operation usage, schema deprecation và resolver authorization.
16. **gRPC cần chú ý gì khi xóa field?** Reserved field numbers/names, wire compatibility và semantic/permission changes.
17. **WebSocket có cần shutdown ngay lúc sunset không?** Phải định nghĩa new connections và existing sessions/drain theo hợp đồng/risk.
18. **Shadowing POST payment sai ở đâu?** Có thể gây giao dịch trùng; phải dùng test data hoặc cơ chế không side effect.
19. **Tại sao 410 ở IPv4 chưa đủ?** IPv6/DR/alternate ingress còn có thể đi tới code cũ.
20. **Khi nào được rollback bật lại v1?** Chỉ khi có giải pháp được phê duyệt không tái đưa lỗ hổng nghiêm trọng vào đường truy cập.

### Bài tập cuối chương

Một doanh nghiệp có API thanh toán REST v1/v2, GraphQL cho mobile, gRPC cho nội bộ và webhook cho đối tác. Tổ chức triển khai qua CDN, WAF, API gateway, load balancer đa vùng, dual-stack IPv4/IPv6 và service mesh. V1 đã deprecated, còn ba đối tác B2B dùng batch định kỳ và một app mobile cũ. V2 sửa lỗ hổng quyền sở hữu đối tượng mà v1 vẫn có.

Hãy:

1. Vẽ **sơ đồ end-to-end** gồm Internet/CDN/gateway/ingress/service/DB, chỉ ra tất cả đường bypass.
2. Tạo **registry tối thiểu** cho operations REST, GraphQL fields, gRPC methods và webhook event types.
3. Chọn **versioning strategy**, thứ tự ưu tiên nếu có path + header cùng xuất hiện.
4. Xác định **mốc deprecation, support end, sunset, runtime removal** với UTC/owner/approval.
5. Đề xuất **phương án khẩn xử lý v1 BOLA**: vá, chặn, adapter hoặc ngừng dịch vụ theo policy.
6. Thiết kế **client migration** cho batch quý/mobile offline, xác định exception scope và expiry nếu được phép.
7. Xây dựng **HTTP response examples** cho trước và sau cutoff, giải thích chọn 410/404/403.
8. Lập **ít nhất 12 ca kiểm thử** gồm v2 ALLOW, v1 DENY, origin bypass, IPv6/DR, scope, cache, idempotency và rollback.
9. Thiết kế dashboard theo **authenticated consumer**, last-seen/usage, exception age và security events.
10. Viết checklist **decommission** gồm gateway, backend, secrets, docs, DNS, logs và retention.

**Tiêu chí đánh giá:** Bản thiết kế phải vừa chứng minh **các client hợp lệ có đường chuyển đổi rõ**, vừa đảm bảo **endpoint đã hết hạn không tiếp tục mở lối truy cập trái quyền hoặc không được giám sát**.

## 28. Checklist kiểm soát phiên bản và endpoint đã ngừng hỗ trợ

- [ ] Có **API contract registry** với version, operation, method, hostname, owner, environment?
- [ ] Đã phân biệt **implementation release** và API contract version?
- [ ] Đã chọn cách versioning qua path/host/header/media type và thứ tự ưu tiên rõ?
- [ ] Có chính sách **backward compatibility và breaking change** được phê duyệt?
- [ ] Security fixes được áp cho **mọi version còn reachable** hoặc version không thể vá đã bị chặn?
- [ ] Đã định nghĩa **deprecated, support end, sunset, retired và emergency disabled**?
- [ ] Có **UTC timestamps, communication plan, migration guide và replacement links**?
- [ ] OpenAPI/GraphQL/Proto/SDK documents có deprecation annotations phù hợp?
- [ ] Response **Deprecation/Sunset/Link** đúng format/contract, được edge/CDN truyền đúng?
- [ ] Cơ chế cutoff dùng HTTP status đúng semantics, không lạm dụng 426/429/503?
- [ ] **Host/path/method/header** được normalize nhất quán ở gateway và backend?
- [ ] Không có wildcard/default route đưa unknown version tới legacy/admin?
- [ ] Gateway áp **authentication/authorization, scope, tenant và BOLA/BFLA** đúng?
- [ ] Version cũ không được giảm **TLS, WAF, rate limit, logging và network segregation**?
- [ ] Đã đối soát **CDN, WAF, public/internal gateway, LB, direct origin**?
- [ ] Đã kiểm tra **IPv4/IPv6, mọi region, DR/failover, Kubernetes/service mesh**?
- [ ] Đã phát hiện **zombie/shadow APIs** bằng registry + runtime reconciliation?
- [ ] Có inventory **authenticated clients, SDK/mobile builds, batch jobs, partners và webhooks**?
- [ ] Có policy cho **extension scope, identity, expiry, approval và compensating controls**?
- [ ] Có **contract tests, semantic tests, security ALLOW/DENY và error contract tests**?
- [ ] GraphQL fields, gRPC methods và streams được quản trị vòng đời phù hợp?
- [ ] Với migration adapter, **auth/tenant/idempotency** không suy yếu và không double-write?
- [ ] Cache key/Vary, CDN invalidation, DNS và các client fallback paths được kiểm thử?
- [ ] Có telemetry **version/operation/consumer/route/policy revision** đã redaction?
- [ ] Đã xác minh **không traffic** khác với **mất telemetry hoặc đường bypass**?
- [ ] Có canary, rollout, rollback an toàn, owner, change record và readback?
- [ ] Sau cutoff, requests v1 bị chặn ở mọi đường còn hỗ trợ, v2 vẫn ALLOW theo quyền?
- [ ] Đã thu hồi **stale credentials/service accounts, runtime, routes và certificates** đúng scope?
- [ ] Logs/audit/backups được bảo vệ và giữ theo retention/legal requirements?
- [ ] Có runbook ứng phó khi **legacy vulnerability** buộc đóng sớm hơn kế hoạch?

**Kết luận:** Kiểm soát phiên bản API an toàn là một quy trình **quản trị contract, authentication, network exposure và vòng đời consumer**, không chỉ là đặt /v1 hay /v2 trong URL. **Deprecated** là thông báo và chuẩn bị migration; **sunset/retired** phải được kiểm chứng bằng policy, route và runtime thực tế trên mọi ingress, region và IP family. Một API version cũ vẫn có thể mang rủi ro nghiêm trọng nếu không được vá hoặc còn đường bypass. Để đóng endpoint đúng cách, cần **danh mục có owner, mốc UTC, theo dõi consumer, kiểm thử ALLOW/DENY, kế hoạch chuyển đổi, thu hồi tài nguyên và bằng chứng readback** — vừa giữ hoạt động hợp lệ, vừa thu nhỏ attack surface một cách có kiểm soát.

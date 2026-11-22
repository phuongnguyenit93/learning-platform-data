# API catalog, chủ sở hữu và vòng đời endpoint

## 1. Bài toán: API hoạt động nhưng không ai biết ai chịu trách nhiệm

Một tổ chức có các dịch vụ Orders, Inventory, Payment và Customer. Mỗi nhóm tự xuất bản REST endpoint, viết một ít OpenAPI, đôi khi để lại link Swagger UI trong README. Sau hai năm, nhóm tích hợp đối tác muốn dùng `GET /api/v1/orders/{orderId}` nhưng gặp những câu hỏi không ai trả lời chắc chắn:

- URL production và sandbox chính thức là gì? Hợp đồng OpenAPI nào đúng với phiên bản đang chạy?
- API có dành cho đối tác bên ngoài, hay chỉ dành cho mạng nội bộ? Ai được quyền gọi, cần OAuth scope và tenant nào?
- Nếu response thay đổi hoặc endpoint chậm, nên liên hệ **nhóm nào** và ai trực sự cố?
- Endpoint còn được hỗ trợ bao lâu? Có bản thay thế `/api/v2/orders/{orderId}` không?
- Một lần trả `200 OK` có đồng nghĩa công việc nghiệp vụ hoàn tất không? Mã `404`/`409`/`429` được cam kết ra sao?
- Trước khi xóa endpoint cũ, làm sao chứng minh không còn consumer quan trọng?

**API catalog** giúp trả lời những câu hỏi ấy bằng một nơi tra cứu có cấu trúc cho các API và endpoint. Catalog không chỉ là danh sách URL: đó là bản đồ **hợp đồng, người sở hữu, khả năng truy cập, trạng thái vòng đời và liên kết vận hành** của từng năng lực API.

Bài này thuộc chương **Tài liệu và trải nghiệm** của module **INTEGRATION_API_REST**, nơi người học đã thiết kế REST dựa trên resource/URI, HTTP method/status, phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền và kiểm thử Java/Spring. Mục tiêu là đưa các thiết kế đó thành **một sản phẩm API có thể được tìm thấy, hiểu đúng, tin cậy và thay đổi an toàn**.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **API catalog**, **API registry**, **developer portal**, **OpenAPI contract** và **runtime discovery**.
2. Thiết kế schema metadata cho service/endpoint: identity, owner, consumer, version, security, lifecycle, SLO, tài liệu, hỗ trợ.
3. Đặt trách nhiệm kỹ thuật, nghiệp vụ, bảo mật và vận hành theo một mô hình ownership có thể kiểm chứng.
4. Xây vòng đời endpoint từ đề xuất, thử nghiệm, GA, deprecated đến retired; quản lý sunset/migration và compatibility.
5. Dùng HTTP `Deprecation`, `Sunset`, `Link` đúng semantics; triển khai ví dụ Java/Spring.
6. Tạo kiểm tra tự động từ OpenAPI/CI, contract tests, thống kê consumer và checklist trước khi retirement.
7. Thiết kế catalog có tìm kiếm tốt nhưng không vô tình công khai endpoint, token hoặc tài liệu nhạy cảm.

## 2. Catalog khác OpenAPI và developer portal như thế nào?

| Thành phần | Trả lời câu hỏi | Đầu ra / ví dụ |
|---|---|---|
| **OpenAPI document** | Một API có những operation, parameter, schema, response và security scheme nào? | `openapi.yaml` hoặc JSON, client SDK, mock/contract validation |
| **API registry** | Bản hợp đồng/phiên bản nào đã được đăng ký, có ID và trạng thái ra sao? | Kho spec có version/commit/digest, policy gate |
| **API catalog** | API nằm ở đâu, ai sở hữu, ai dùng, hỗ trợ thế nào, có đang deprecated không? | Danh mục service + operation + ownership + lifecycle |
| **Developer portal** | Nhà phát triển tìm, thử, đăng ký và học sử dụng API như thế nào? | Trang tìm kiếm, quickstart, auth guide, sandbox, examples, changelog |
| **Service discovery** | Runtime instance/IP nào đang phục vụ một service? | DNS, Kubernetes Service, service registry |
| **API gateway** | Traffic thật được route, xác thực, giới hạn và quan sát ra sao? | Gateway routes, auth/rate-limit policy, access logs |

Các thành phần có thể được một nền tảng tích hợp chung, nhưng **không cùng chức năng**. Một OpenAPI file hợp lệ không nói chắc endpoint đang bật ở production, ai on-call, hay ngày dừng hỗ trợ. Một service được tìm thấy qua Kubernetes DNS không đồng nghĩa consumer có quyền gọi API của nó.

**Catalog là sản phẩm dữ liệu**, không chỉ một wiki. Mỗi trường quan trọng cần có nguồn gốc, chủ sở hữu, quy trình cập nhật và cách xác minh với runtime. Developer portal thường là giao diện sử dụng dữ liệu đó cho đúng đối tượng truy cập.

### 2.1. Ba cấp đối tượng không nên gộp

- **API product/domain**: năng lực nghiệp vụ, ví dụ “Order Management API”, đối tượng sử dụng và điều khoản hỗ trợ.
- **Service/deployment**: ứng dụng triển khai, ví dụ `orders-api` ở khu vực `ap-southeast`, có health/observability và team owner.
- **Operation/endpoint**: cặp phương thức + URI template như `GET /api/v1/orders/{orderId}`, với `operationId`, scope, data classification, lifecycle riêng.

Một service có thể có endpoint cũ đã deprecated và endpoint mới vẫn GA. Nếu chỉ gán trạng thái `ACTIVE` cho cả service, catalog sẽ cung cấp thông tin sai về endpoint cũ.

### 2.2. Catalog không phải nguồn sự thật duy nhất cho mọi thông tin

Nguồn sự thật nên phân tách rõ ràng:

| Dữ liệu | Nguồn chính phù hợp | Cách catalog sử dụng |
|---|---|---|
| HTTP path, method, schema, response, security scheme | OpenAPI trong repository được kiểm soát | Import theo commit/digest |
| Team owner và support contact | Team/service ownership registry được duyệt | Tham chiếu team ID ổn định |
| Runtime route/traffic | API gateway/ingress/telemetry | Đối chiếu đã deploy và consumer usage |
| SLO/incident/runbook | SRE/service catalog hoặc chính sách vận hành | Liên kết đúng version/endpoint |
| Lifecycle, sunset plan và migration | Quyết định governance đã duyệt | Gắn với operation/version, hiển thị timeline |
| Phân quyền truy cập tài liệu | IAM và data classification | Lọc những gì từng audience được phép xem |

**Không nên đồng bộ hai chiều thiếu quy tắc** khiến portal ghi đè OpenAPI trong Git hoặc gateway ghi đè owner. Mỗi trường nên có authority cụ thể; catalog có thể cảnh báo mismatch thay vì sửa một cách âm thầm.

## 3. Những trường cần có trong một API catalog

Một entry tốt phải đủ để người khác **tìm, đánh giá, tích hợp và hỗ trợ** mà không cần hỏi riêng tác giả.

| Nhóm | Trường metadata | Vì sao quan trọng |
|---|---|---|
| Identity | `apiId`, `serviceId`, `operationId`, `method`, `pathTemplate` | ID bền vững; tránh trùng tên, route |
| Mô tả | `summary`, business capability, tags, examples | Tìm kiếm theo việc cần làm, không chỉ hostname |
| Environment | base URL production/sandbox, region, API version | Tránh gọi nhầm prod và test |
| Contract | OpenAPI URL, immutable revision/digest, schema, changelog | Biết chính xác hợp đồng được triển khai |
| Ownership | team ID, technical owner, business owner, support tier, escalation | Có người chịu trách nhiệm và phê duyệt thay đổi |
| Consumer | audience internal/partner/public; supported SDK/languages | Giới hạn đối tượng và giảm friction |
| Security | auth type, OAuth scopes, tenant boundary, data classification | Chọn đúng token và quyền |
| Behavior | HTTP statuses, pagination, caching, ETag, idempotency, rate limit | Client xử lý được lỗi và retries |
| Lifecycle | `state`, dates, successor, migration guide, support end | Không dùng nhầm endpoint sắp nghỉ |
| Reliability | SLO, latency expectation, dependency/availability notes | Đánh giá đáp ứng sản phẩm |
| Operations | docs, runbook, support channel, issue link, telemetry dashboard | Điều tra và xử lý sự cố |
| Governance | approvers, last reviewed, exception expiry, compliance flags | Phát hiện metadata mục nát |

Không nhất thiết mọi trường đều nằm ngay trong OpenAPI. Những trường nhạy cảm (số điện thoại cá nhân của người trực, tài khoản nội bộ, internal topology, lỗ hổng, dữ liệu consumer chi tiết) **không được xuất công khai** chỉ vì catalog cũng phục vụ partner.

### 3.1. Identity ổn định: path và operationId không phải lúc nào cũng đủ

Khóa dữ liệu có thể là `apiId + contractVersion + operationId`. OpenAPI `operationId` phải duy nhất trong một document; nên giữ ổn định khi operation chưa đổi semantics để tooling/SDK không bị phá vỡ. `method + normalized path template` giúp đối chiếu route thực tế.

Các tình huống cần kiểm tra:

- `GET /api/v1/orders/{id}` và `GET /api/v1/orders/{orderId}` có **cùng cấu trúc route**, nhưng khác tên biến path; không nên coi là hai endpoint khác chỉ vì chuỗi khác.
- `GET /orders/{id}` khác `DELETE /orders/{id}`; lifecycle và security có thể khác nhau.
- `GET /api/v1/orders` với filter/pagination mới không nhất thiết là endpoint mới, nhưng contract/schema đã thay đổi và cần version/diff.
- Một operation được chuyển sang service khác vẫn cần lịch sử owner và migration để consumer biết ai chịu trách nhiệm.

Cần quản lý **alias/mapping** khi đổi operationId hoặc tách service. Không dùng raw URL có ID thật làm key catalog vì sẽ sinh hàng triệu entry không cần thiết.

### 3.2. Ví dụ một entry JSON

Dữ liệu dưới đây là **mô hình catalog nội bộ minh họa**, không phải format chuẩn duy nhất:

~~~json
{
  "apiId": "order-management",
  "serviceId": "orders-api",
  "operationId": "getOrderById",
  "method": "GET",
  "pathTemplate": "/api/v1/orders/{orderId}",
  "audience": ["partner", "internal"],
  "environment": {
    "productionBaseUrl": "https://api.example.test",
    "sandboxBaseUrl": "https://sandbox-api.example.test"
  },
  "contract": {
    "format": "openapi",
    "version": "1.5.0",
    "revision": "git:7f2e9a1"
  },
  "security": {
    "scheme": "oauth2-bearer",
    "requiredScopes": ["orders.read"],
    "tenantIsolation": true,
    "dataClassification": "confidential"
  },
  "ownership": {
    "technicalTeam": "commerce-orders",
    "businessTeam": "order-product",
    "supportTier": "critical"
  },
  "lifecycle": {
    "state": "GENERAL_AVAILABILITY",
    "deprecatedAt": null,
    "sunsetAt": null,
    "successorOperationId": null
  },
  "documentation": {
    "quickstart": "/developer/orders/quickstart",
    "runbook": "/internal/runbooks/orders-api"
  },
  "lastReviewedAt": "2026-11-18"
}
~~~

Không ghi credential hay access token vào catalog. `revision` cần có cách đối chiếu với artifact thật và version triển khai; mã commit giả định trên chỉ minh họa. `productionBaseUrl` phải được quản lý theo môi trường/quyền xem: nếu endpoint chỉ nội bộ, portal công khai không được hiển thị.

### 3.3. API catalog có thể phân loại theo audience

Một catalog đa đối tượng có thể xuất các **view khác nhau**:

- **Internal engineering view:** owner, route, dependencies, dashboard, incident/runbook và SLO.
- **Partner developer view:** endpoint được phép, sandbox, OAuth scopes, ví dụ request, errors, rate limit, changelog, deprecation dates.
- **Public view:** API được xuất bản công khai theo chính sách, không chứa topology hoặc runbook nội bộ.

Kiểm quyền tại **API trả dữ liệu catalog**, không chỉ ẩn nút bằng giao diện. Kết quả tìm kiếm, autocomplete, API export và documentation download cũng phải lọc cùng policy.

## 4. OpenAPI 3.1 là phần nền của catalog, không thay ownership

Một OpenAPI document phải giúp consumer hiểu hợp đồng request/response, xác thực và status. Có thể gắn custom extension `x-...` để liên kết catalog, nhưng extension không được chuẩn OpenAPI tự động diễn giải hoặc cưỡng chế.

Ví dụ rút gọn, có thể được mở rộng trong dự án:

~~~yaml
openapi: 3.1.0
info:
  title: Order Management API
  version: 1.5.0
  description: Truy vấn và quản lý đơn hàng theo tenant
servers:
  - url: https://api.example.test
paths:
  /api/v1/orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Lấy đơn hàng theo ID
      tags: [Orders]
      security:
        - bearerAuth: []
      x-catalog:
        apiId: order-management
        ownerTeam: commerce-orders
        lifecycle: GENERAL_AVAILABILITY
        supportTier: critical
      parameters:
        - in: path
          name: orderId
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: Đơn hàng thuộc phạm vi được phép
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderView"
        "401":
          description: Thiếu hoặc sai access token
        "403":
          description: Không đủ scope/quyền theo chính sách
        "404":
          description: Không tìm thấy hoặc không được tiết lộ
        "429":
          description: Vượt hạn mức client
        "503":
          description: Dịch vụ tạm thời không sẵn sàng
components:
  schemas:
    OrderView:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [NEW, PAID, CANCELLED]
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

`bearerFormat: JWT` chỉ là hint cho documentation/tooling; **không có nghĩa runtime sẽ tự xác minh token**, issuer, audience, expiry hoặc scope. Ví dụ security scheme trên mô tả bearer HTTP và để trống danh sách scope; nếu muốn OpenAPI khai báo OAuth scopes theo chuẩn, nên dùng `type: oauth2` cùng flow/scopes thực, không tự nhét scope vào mảng của HTTP bearer scheme rồi tưởng đó là kiểm soát quyền. Catalog vẫn có thể ghi requiredScopes dưới dạng metadata extension riêng và Spring Security thực thi thật.

**Nội dung cần bổ sung trong hợp đồng production:** schema lỗi `application/problem+json`, request IDs, phân trang và cursor, cache/ETag/`If-Match`, idempotency key cho POST, CORS khi phục vụ browser, rate-limit contract, timeout và ví dụ thành công/lỗi. Một document OpenAPI compile được nhưng thiếu các response 401/403/409/429/503 không mang lại trải nghiệm tích hợp đáng tin.

### 4.1. Chỉ công bố extension phù hợp đối tượng

`x-catalog.ownerTeam` hữu ích ở nội bộ nhưng không nhất thiết phù hợp cho OpenAPI public. Nếu cùng source phục vụ nhiều audience, build pipeline phải **lọc metadata nội bộ** một cách có kiểm thử và publish bản spec đã duyệt. Không publish nguyên các endpoint nội bộ, IP private, số điện thoại trực ca, địa chỉ dashboard yêu cầu quyền hoặc dữ liệu environment secret.

## 5. Chủ sở hữu API: ai quyết định, ai chịu trách nhiệm?

**Không nên chỉ ghi tên một cá nhân** làm owner của endpoint. Khi người đó chuyển nhóm, catalog lập tức mồ côi. Team ID và kênh hỗ trợ có quy trình bàn giao ổn định hơn; vẫn cần người phê duyệt cụ thể trong audit trail của quyết định thay đổi.

| Vai trò | Trách nhiệm chính | Quyết định tiêu biểu |
|---|---|---|
| **Technical owner** | Code, OpenAPI, backwards compatibility, deployment, migration | Cách thêm field, thiết kế route/HTTP contract, implementation |
| **Business/product owner** | Giá trị nghiệp vụ, consumer impact, support promise | Có nên duy trì endpoint, timeline deprecation và thay thế |
| **Operational owner/on-call** | SLO, alert, incident, capacity, runbook | Ai xử lý 503, latency, quota hoặc sự cố prod |
| **Security/data owner** | OAuth scopes, data classification, tenant isolation, API exposure | Có thể publish ra partner không, policy truy cập |
| **Consumer owner** | Ứng dụng đang dùng API, deadline migration và testing | Xác nhận đổi client/SDK, nhận thông báo retirement |
| **API governance/steward** | Chuẩn chung, catalog completeness, exceptions và approvals | Phê duyệt ngoại lệ, kiểm deadline và rủi ro cross-team |

Một team nhỏ có thể kiêm nhiều vai trò; điều kiện quan trọng là **không còn trách nhiệm nào trống**. Cùng lúc, quá nhiều owner ngang hàng mà không có người ra quyết định cuối cũng gây tê liệt. Chỉ định technical DRI và product approver rõ.

### 5.1. Ví dụ trách nhiệm RACI

RACI = Responsible (thực hiện), Accountable (chịu trách nhiệm cuối), Consulted (được tham vấn), Informed (được thông báo). Một bảng mẫu:

| Hoạt động | API team | Product owner | Security | Consumer teams | SRE |
|---|---|---|---|---|---|
| Tạo contract và ví dụ HTTP | R/A | C | C | C | I |
| Duyệt scope và tenant policy | R | C | A | I | C |
| Xác nhận SLO và runbook | R | C | C | I | A |
| Quyết định deprecate | R | A | C | C | C |
| Xác nhận migration readiness | R | A | C | R | C |
| Disable/retire route | R | A | C | I | R |

Bảng là thỏa thuận nội bộ minh họa, không có một RACI bắt buộc áp dụng cho mọi công ty. Điều quan trọng: **mỗi quyết định cần một Accountable rõ**, có đường escalation khi consumer chưa di chuyển.

### 5.2. Quy trình nhận ownership không bị “mồ côi”

Một endpoint mới chỉ vào `GENERAL_AVAILABILITY` nếu đã có:

- Team owner tồn tại trong hệ thống định danh tổ chức và kênh liên lạc hoạt động.
- Người phê duyệt business, phân loại dữ liệu, security review phù hợp.
- Tài liệu cho consumer, sandbox/example nếu phát hành cho partner.
- Runbook cho 5xx, 429, timeout, auth fail và cách xử lý incident.
- SLO/support tier phù hợp mục đích nghiệp vụ.
- Quy tắc đổi owner khi đội tổ chức lại, có xác nhận từ team nhận bàn giao.

Nếu owner thay đổi, cập nhật catalog, routing/escalation, codeowners/repository, dashboard và thông tin support **như một quy trình có audit**, không chỉ đổi một trường text rồi xem như xong.

## 6. Vòng đời endpoint: từ đề xuất tới nghỉ hưu

### 6.1. Những trạng thái không nên gộp

| Trạng thái | Ý nghĩa | Hợp đồng với consumer |
|---|---|---|
| `DRAFT` | Đang thiết kế, chưa cam kết khả dụng | Contract có thể đổi; không advertise production |
| `BETA` / `PREVIEW` | Consumer được chọn có thể thử | Ranh giới hỗ trợ và breaking-change policy phải nói rõ |
| `GENERAL_AVAILABILITY` (GA) | Được hỗ trợ chính thức | Có chủ sở hữu, chính sách compatibility, runbook/SLO |
| `DEPRECATED` | Vẫn hoạt động nhưng **không nên tích hợp mới**; có kế hoạch thay thế | Consumer cũ có thời gian migrate; thông báo deadline |
| `RETIRED` | Không còn cung cấp theo hợp đồng, route được gỡ/đóng | Tài liệu archive và tombstone phù hợp, không hứa endpoint còn chạy |

**Sunset date** là một **mốc thời gian dự kiến kết thúc khả dụng**, không nhất thiết là một trạng thái riêng. Một operation có thể ở `DEPRECATED` với `sunsetAt` trong tương lai. Khi qua mốc và hoàn tất điều kiện an toàn, operation chuyển `RETIRED`. Tách `state` khỏi `deprecatedAt`/`sunsetAt` để tránh một trường phải diễn đạt nhiều ý.

~~~mermaid
flowchart LR
    D[DRAFT] --> B[BETA / PREVIEW]
    B --> G[GENERAL AVAILABILITY]
    G --> P[DEPRECATED]
    P --> R[RETIRED]
    B -->|Không ra mắt| R
    P -->|Gia hạn có phê duyệt| P
    P -->|Hủy sunset sau review| G
~~~

Sơ đồ mô tả vòng đời **hợp đồng**, không phải trạng thái runtime. Một endpoint GA có thể bị outage 503 hôm nay; không được đổi lifecycle thành RETIRED chỉ vì đang có incident. Ngược lại, endpoint deprecated vẫn cần SLO, bảo mật và sửa lỗi trong thời gian hỗ trợ đã cam kết.

### 6.2. Transition gate

| Chuyển trạng thái | Điều kiện tối thiểu |
|---|---|
| DRAFT → BETA | Contract đủ thử, auth/sandbox và giới hạn sử dụng rõ, owner xác nhận |
| BETA → GA | Review OpenAPI, security, runbook, SLO, load/contract test, tài liệu hỗ trợ và migration policy |
| GA → DEPRECATED | Successor/migration guide nếu có; impact assessment; owner + product duyệt; thông báo |
| DEPRECATED → RETIRED | Đến lịch đã duyệt, kiểm consumer và lưu lượng còn lại, rollback/remediation plan, support/archive, quyết định cuối |
| Mọi trạng thái → thay owner | Team nhận xác nhận, escalation không đứt, audit cập nhật |

Bảng không quy định mọi lần ngừng API phải đợi một số ngày cố định. Phải xác định thời gian thông báo theo hợp đồng, độ quan trọng, quy định pháp lý, dữ liệu phải lưu và mức độ breaking change. Ví dụ 90 ngày có thể phù hợp với API nội bộ ít rủi ro nhưng không đủ cho partner có kỳ phát hành dài.

### 6.3. Một transition cần có dữ liệu và lịch sử

Metadata có thể lưu:

~~~yaml
apiId: order-management
operationId: getOrderById
contractVersion: "1.5.0"
lifecycle:
  state: DEPRECATED
  deprecatedAt: "2027-01-01T00:00:00Z"
  sunsetAt: "2027-06-30T23:59:59Z"
  successorOperationId: getOrderByIdV2
  migrationGuide: "/developer/orders/migrate-v1-to-v2"
  decisionId: "api-change-042"
  approvedByTeam: order-product
  lastReviewedAt: "2026-11-18T00:00:00Z"
~~~

Đây là **metadata minh họa**, không yêu cầu sửa file ngoài bài học. Trạng thái trong catalog phải khớp với thông báo thực tế ở API gateway/response và tài liệu phát hành. Các mốc ngày mẫu không phải quyết định đã có thật của một dịch vụ cụ thể.


## 7. Thông báo deprecation và sunset qua HTTP

Việc gắn nhãn `deprecated` trong portal là cần nhưng **chưa đủ**: nhiều consumer chỉ nhìn response và log của hệ thống, không đọc portal mỗi ngày. HTTP cung cấp các tín hiệu máy đọc được giúp client, gateway và công cụ quan sát nhận biết lịch thay đổi:

- **`Deprecation`:** header mô tả thời điểm tài nguyên hoặc một ngữ cảnh liên quan bị/sẽ bị deprecated. Theo RFC 9745, giá trị là **Structured Field Date** dạng `@<unix-seconds>`.
- **`Sunset`:** header theo RFC 8594 thông báo thời điểm tài nguyên dự kiến không còn sẵn sàng; giá trị là **HTTP-date**, không phải giây Unix.
- **`Link`:** có thể trỏ tới tài liệu chính sách deprecation/migration, ví dụ link relation `deprecation`.

### 7.1. Phản hồi GET vẫn thành công trong thời gian chuyển đổi

Ví dụ endpoint v1 còn hoạt động, nhưng được lên kế hoạch deprecated vào 1/1/2027 và sunset 30/6/2027:

~~~http
GET /api/v1/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
Deprecation: @1798761600
Sunset: Wed, 30 Jun 2027 23:59:59 GMT
Link: <https://docs.example.test/developer/orders/migrate-v2>; rel="deprecation"; type="text/html"

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "PAID"
}
~~~

`@1798761600` biểu diễn **2027-01-01T00:00:00Z** theo Unix seconds. `Wed, 30 Jun 2027 23:59:59 GMT` là HTTP-date của mốc sunset ví dụ. Một endpoint **không ngừng chạy chỉ vì đã có header Deprecation**: trước khi bị retired, API vẫn phải đáp ứng đúng hợp đồng và bảo mật đã công bố.

Phân biệt:

| Tín hiệu | Câu hỏi trả lời | Không đồng nghĩa |
|---|---|---|
| OpenAPI `deprecated: true` | Operation không nên dùng cho tích hợp mới? | Runtime tự dừng endpoint |
| `Deprecation` | Từ khi nào API được hoặc sẽ được coi là deprecated? | Deadline chắc chắn ngừng hoạt động |
| `Sunset` | Dự kiến lúc nào endpoint không còn khả dụng? | Đã hoàn tất migration cho mọi consumer |
| `Link` migration | Phải chuyển sang API nào và làm cách nào? | Có thể tự động thay path mà không sửa client |

Không tùy tiện dùng `Retry-After` để báo endpoint sắp ngừng hỗ trợ: header ấy gợi ý thời gian thử lại trong ngữ cảnh giao thức phù hợp, không phải thông báo lifecycle. Không giả định mọi HTTP client, gateway hoặc OpenAPI UI đều đọc các header deprecation; vẫn cần thông báo chủ động.

### 7.2. Thời điểm retirement và lựa chọn 404/410

Sau khi gỡ endpoint v1, hệ thống có thể:

- Trả **`410 Gone`** khi biết resource/endpoint đã bị loại vĩnh viễn và muốn công khai thông tin đó; kèm liên kết tới hướng dẫn migrate.
- Trả **`404 Not Found`** nếu không muốn tiết lộ sự tồn tại cũ, phù hợp chính sách bảo mật hoặc hạ tầng routing.
- Giữ một tầng gateway tương thích có thời hạn để trả thông điệp rõ, sau đó gỡ route.

**Không tự redirect tất cả request cũ sang v2**. Ví dụ `POST` có side effect, schema khác hoặc authorization khác; HTTP redirect tự động có thể làm client xử lý sai. Nếu lựa chọn redirect thật, cần hiểu semantics 307/308, quyền, idempotency và khả năng hỗ trợ của từng client. `404`/`410` khi retired phải được tài liệu hóa và kiểm từ góc nhìn consumer.

### 7.3. Header cache, CORS và thời gian

Nếu API cache response, header Deprecation/Sunset có thể được giữ trong cache. Khi timeline thay đổi, cần chính sách freshness/invalidation phù hợp; tránh edge tiếp tục trả deadline cũ sau khi quyết định đã được duyệt. Nếu header thay đổi theo version/tenant/audience, cache key và chính sách biến thể phải phản ánh chiều đó; không giả định `Vary: Origin` giải quyết mọi vấn đề cache.

Với browser cross-origin, JavaScript **không tự đọc được tất cả response headers**. Nếu dashboard frontend cần hiển thị lịch sunset, có thể cấu hình:

~~~http
Access-Control-Expose-Headers: Deprecation, Sunset, Link
~~~

Chỉ cấu hình khi thực sự cần, giới hạn CORS origins hợp lệ và đảm bảo `Link` không làm lộ URL tài liệu nội bộ. Browser cần CORS/credentials policy đúng, nhưng CORS **không thay access control** của API hay portal.

### 7.4. Nguồn dữ liệu phải thống nhất

Mốc `deprecatedAt`/`sunsetAt` trong catalog phải được sử dụng hoặc kiểm chứng bởi middleware/gateway phát header, docs và release notes. Nếu team thay ngày trong portal mà không update cấu hình runtime, consumer nhận thông tin mâu thuẫn. Nên có kiểm thử tự động đọc cấu hình lifecycle theo contract source và so response header ở staging.

## 8. Compatibility và versioning: khi nào cần endpoint mới?

Không phải mọi thay đổi là breaking change, và không phải cứ đặt `/v2` là giải quyết được trách nhiệm migration. Phải kiểm **tác động tới consumer thật**, bao gồm SDK, validation, security và semantics.

| Thay đổi | Có thể tương thích? | Điều kiện/cạm bẫy |
|---|---|---|
| Bổ sung endpoint hoàn toàn mới | Thường có | Không thay route hiện có hoặc auth policy của endpoint cũ |
| Thêm optional request query parameter | Thường có | Default behavior phải không đổi; proxy/SDK không bị ảnh hưởng |
| Thêm optional response field | Thường có | Client strict schema/deserializer có thể từ chối field mới |
| Thêm giá trị enum response | **Có thể breaking** | Consumer dùng switch exhaustive, generator đóng enum |
| Đổi type của `orderId` từ string sang integer | Breaking | Ảnh hưởng SDK, URL, parser, DB/business semantics |
| Đổi HTTP 200 sang 202 cho cùng tình huống | Có thể breaking | Contract completion chuyển từ đồng bộ sang bất đồng bộ |
| Thay response `404` bằng `200` với object rỗng | Có thể breaking | Client điều khiển luồng bằng status |
| Thêm scope bắt buộc hoặc tăng phân quyền | Breaking đối với caller cũ | Dù đúng mục tiêu security vẫn cần migration |
| Giảm page size mặc định hoặc đổi sort | Có thể breaking | Client phân trang/sắp xếp phụ thuộc default |
| Đổi key idempotency/TTL mà không báo | Có thể breaking và nguy hiểm | Có thể tạo duplicate side effect |
| Chuyển `POST` sang `PUT` | Breaking | HTTP semantics, SDK, idempotency và CORS thay đổi |
| Sửa lỗi lộ dữ liệu hoặc bypass authorization | Thay đổi hành vi cần xử lý khẩn cấp | Không trì hoãn bản vá bảo mật chỉ để giữ hành vi sai |

**Quy tắc thực hành:** đánh giá ở mức hợp đồng và kỳ vọng consumer, không chỉ ở mức schema diff. Tool có thể phát hiện path/field thay đổi nhưng không chứng minh một lần thay đổi pagination default hoặc business rule là an toàn.

### 8.1. Version strategy

- **Path versioning**: `/api/v1/orders`, `/api/v2/orders` dễ nhìn và hỗ trợ chạy song song, nhưng nhân đôi tài liệu và routing.
- **Header/media type versioning**: ví dụ `Accept: application/vnd.example.orders.v2+json`, giữ URI nhưng yêu cầu tooling/documentation quản lý negotiation rõ.
- **Compatible evolution**: giữ contract hiện tại khi có thể; chỉ tạo major version khi khác biệt có thật và kế hoạch hỗ trợ v1/v2 rõ.

`info.version` của OpenAPI có thể là **phiên bản tài liệu/hợp đồng**, không tự bằng phiên bản URI. Catalog nên lưu cả contract revision và API version để tránh nhầm một lần sửa mô tả OpenAPI với một breaking change runtime.

### 8.2. Sửa security bug không phải “giữ backwards compatibility bằng mọi giá”

Nếu endpoint trước đó cho phép một user đọc dữ liệu tenant khác, việc sửa BOLA/IDOR có thể khiến một số client từng khai thác hành vi sai nhận 403/404. Đây là **sửa lỗi bảo mật**, không phải lý do tiếp tục duy trì truy cập trái phép. Vẫn cần cập nhật release note, incident/runbook và trợ giúp consumer hợp lệ, nhưng không trì hoãn biện pháp bảo vệ tài nguyên vì lo breaking-change metric.

### 8.3. Contract diff phải xét cả HTTP behavior

Khi review thay đổi, so sánh:

1. Path/method/operationId, request/response media type và schema.
2. Headers bắt buộc như `If-Match`, `Idempotency-Key`, `Retry-After`.
3. HTTP status và Problem Details `type`/`code`.
4. Security schemes, OAuth scopes, token audience và tenant/owner authorization.
5. Pagination/cursor, sorting/filtering, cache/ETag và timeout semantics.
6. Rate-limit/quota, SLO và khả năng retry của client.
7. Compatibility của generated SDK và consumer representative.

Chỉ so diff OpenAPI chưa đủ cho các thay đổi business semantics, nên bổ sung contract tests, consumer-driven tests hoặc manual review cho các trường không thể được máy kiểm.

## 9. Migration và retirement: phải có bằng chứng, không chỉ ngày trên lịch

Một kế hoạch bỏ endpoint v1 gồm nhiều giai đoạn và có **go/no-go gate** cụ thể.

~~~mermaid
flowchart TD
    A[Đề xuất deprecate v1] --> B[Impact assessment: consumers, traffic, contracts]
    B --> C[Chuẩn bị v2 + migration guide + SDK]
    C --> D[Duyệt owner, product, security, operations]
    D --> E[Công bố: catalog, portal, header, changelog]
    E --> F[Thông báo consumer + deadline]
    F --> G[Theo dõi adoption, canary, support]
    G --> H{Đủ điều kiện retire?}
    H -->|Chưa| I[Gia hạn/giải quyết blocker với quyết định ghi nhận]
    I --> G
    H -->|Có| J[Disable/gỡ route có rollout và rollback]
    J --> K[Monitor lỗi, archive catalog, đóng migration]
~~~

### 9.1. Trước deprecation: inventory consumer

Không thể xóa một API an toàn nếu không biết ai đang gọi. Có thể tổng hợp:

- **API gateway access logs** theo operation/route template, API key/client ID/tenant đã được xác minh và timestamp.
- **Traces** qua các backend nội bộ gọi nhau, quan hệ service-to-service.
- **Đăng ký ứng dụng/SDK** trong portal, contact chủ sở hữu consumer.
- **Tài liệu batch job/mobile release** có chu kỳ gọi dài; một tuần không traffic không chứng minh không còn consumer.
- **Event/async integrations** nếu endpoint được gọi từ job sau queue/callback.

Dùng thông tin định danh consumer theo đúng quyền truy cập/retention. Không đưa API key nguyên văn hoặc user ID vào metric labels; consumer registry có thể lưu mã tham chiếu hoặc hash/tokenization và quyền xem chi tiết được kiểm soát. Một phép đo “0 calls trong 7 ngày” **không chứng minh** consumer đã bỏ endpoint nếu có job cuối tháng, disaster recovery hoặc môi trường vùng khác.

### 9.2. Migration guide cần cụ thể đến HTTP và SDK

Một guide tốt không chỉ viết “dùng v2” mà phải có:

- URL/method cũ và mới, lý do thay đổi, bảng ánh xạ request/response, khác biệt error codes.
- Ví dụ trước/sau bằng HTTP và Java/Spring client hoặc SDK phổ biến.
- OAuth scopes/audience và thủ tục cấp quyền nếu thay đổi.
- Cách chuyển pagination cursor, ETag, cache policy, idempotency key; xử lý retries an toàn.
- Kịch bản kiểm thử trên sandbox và checklist rollout có thể quay lại v1 trong giai đoạn hỗ trợ.
- Ngày bắt đầu deprecated, sunset dự kiến, contact hỗ trợ, quy định gia hạn.
- Những giới hạn của auto-migration, đặc biệt với `POST` thanh toán và dữ liệu cá nhân.

Ví dụ (chỉ là minh họa về mặt hình thức; v2 thực phải có schema được công bố):

~~~http
GET /api/v1/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
~~~

~~~http
GET /api/v2/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
Accept: application/json
~~~

Nếu v2 đổi tên field `status` thành `state`, migration guide phải nêu chính xác cách ánh xạ enum, nullability, error codes và SDK types; **không yêu cầu consumer tự đoán**. Một guide có thể kèm ví dụ request cho 401/403, 404/410, 429 và 503 để người tích hợp hiểu hành vi runtime.

### 9.3. Exit criteria và các trường hợp cần hoãn

| Tiêu chí | Bằng chứng |
|---|---|
| API v2 đã hoạt động và đúng quyền | Contract/integration/security tests, canary |
| Consumer quan trọng đã di chuyển | Owner confirmation + traffic/telemetry |
| Không có hidden batch/mobile consumer | Khảo sát theo chu kỳ đủ dài + telemetry nhiều region |
| Runbook cho 404/410 hoặc lỗi sau sunset | Kịch bản hỗ trợ, alert, rollback |
| Thông báo deprecation đúng | Catalog/portal/HTTP headers/changelog nhất quán |
| Không còn rủi ro pháp lý, SLA hoặc dữ liệu | Phê duyệt product/security/compliance |
| Kế hoạch đóng và theo dõi | Phased rollout, guardrail và thời gian đánh giá |

Nếu consumer quan trọng chưa di chuyển, đội sở hữu phải quyết định **gia hạn**, tạo compatibility adapter có thời hạn hoặc thực hiện migration có hỗ trợ; không tùy ý kéo ngày sunset trong một file mà không thông báo. Gia hạn cần có approver và lịch review mới, không biến endpoint deprecated thành hỗ trợ vô hạn mặc định.

## 10. Triển khai thông báo lifecycle trong Java/Spring Boot

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring MVC. `OncePerRequestFilter` giúp gắn các header deprecation cho route v1 cụ thể; không thay đổi logic authentication/authorization hoặc status code.

### 10.1. Filter phát header cho endpoint được lên lịch thay thế

~~~java
import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class DeprecatedOrderEndpointHeadersFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        // Ví dụ app chạy ở context root; bỏ contextPath nếu có.
        String path = request.getRequestURI()
            .substring(request.getContextPath().length());

        boolean deprecatedOperation =
            "GET".equals(request.getMethod())
                && path.matches("^/api/v1/orders/[^/]+$");

        if (deprecatedOperation) {
            // Structured Field Date, 2027-01-01T00:00:00Z.
            response.setHeader("Deprecation", "@1798761600");
            // HTTP-date, ngày dự kiến ngừng hỗ trợ.
            response.setHeader(
                "Sunset", "Wed, 30 Jun 2027 23:59:59 GMT");
            response.addHeader(
                "Link",
                "<https://docs.example.test/developer/orders/migrate-v2>"
                    + "; rel=\"deprecation\"; type=\"text/html\"");
        }

        chain.doFilter(request, response);
    }
}
~~~

Đây là ví dụ cho **một route cụ thể**: chỉ `GET /api/v1/orders/{id}` được gắn header. Trong ứng dụng thật, nên **tạo cấu hình lifecycle từ nguồn catalog đã được duyệt** thay vì hardcode ngày ở nhiều file. Đường match bằng regex đơn giản không tự giải quyết mọi route mapping, suffix, servlet context, API gateway rewriting; cần test từ edge tới app. Lớp filter có thể nằm trước/sau SecurityFilterChain tùy cấu hình nên cần kiểm header trên các status phản hồi mong muốn, không giả định nó sẽ tự xuất hiện trên mọi 401/403 do gateway/security tạo.

**Không gỡ endpoint ngay khi thêm filter**, vì header chỉ cảnh báo. Endpoint cũ vẫn phải giữ scope, kiểm JWT issuer/audience, owner/tenant authorization, response status và caching theo hợp đồng đang hỗ trợ. Đừng để filter rewrite route hoặc tự forward Authorization sang host v2.

### 10.2. Tích hợp OpenAPI bằng `deprecated: true`

Trong Spring MVC có thể dùng springdoc-openapi (nếu dự án đã chọn dependency/phiên bản tương thích) để phản ánh trạng thái operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderQueryController {
    @Operation(
        operationId = "getOrderById",
        summary = "Đọc đơn hàng qua API v1",
        deprecated = true,
        description = "Chuyển sang API v2 trước ngày sunset."
    )
    @GetMapping("/api/v1/orders/{orderId}")
    ResponseEntity<OrderView> getLegacy(
            @PathVariable String orderId) {
        // Minh họa vị trí controller. Service thực phải kiểm
        // access token, scope, tenant và quyền trên đơn hàng.
        throw new UnsupportedOperationException(
            "Demo only: implement your authorized query service");
    }
}
~~~

**Đoạn này là khung chỉ chỗ đặt annotation, không phải endpoint chạy hoàn chỉnh.** Khi triển khai, thay ngoại lệ minh họa bằng service có kiểm quyền và xử lý lỗi HTTP đúng. `@Operation(deprecated = true)` tạo metadata OpenAPI nếu library được cấu hình; nó **không tự thêm** `Deprecation`/`Sunset` vào runtime response và không ngắt endpoint.

Nếu chưa dùng springdoc, có thể ghi `deprecated: true` trực tiếp trong OpenAPI source. Tránh nguồn sự thật mâu thuẫn: thiết kế pipeline cần kiểm status giữa annotation/contract/catalog, không để hai nhóm cập nhật độc lập.

### 10.3. Spring Security và quyền truy cập không được thay đổi ngầm

Một endpoint đang deprecated vẫn phải bảo vệ theo contract:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .sessionManagement(s ->
            s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET, "/api/v1/orders/**", "/api/v2/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Các import và cấu hình đầy đủ phụ thuộc ứng dụng. Mẫu này chỉ thể hiện scope gate; hệ thống thực cần xác minh token, issuer, audience, expiry và **quyền theo đối tượng/tenant**, không thể thay bằng `SCOPE_orders.read`. Nếu API chỉ nhận Bearer header và stateless thì cấu hình CSRF cần theo threat model; nếu dùng cookie session/browser, phải thiết kế CSRF và CORS riêng. Thông báo lifecycle không làm yếu security.

### 10.4. Xử lý route đã retired

Khi retirement được phê duyệt, nên gỡ route thực sự hoặc cấu hình gateway có chủ ý. Nếu contract chọn tombstone 410:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RetiredOrderRoute {
    @GetMapping("/api/v1/orders/{orderId}")
    ResponseEntity<ProblemDetail> gone() {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.GONE,
            "Endpoint này đã ngừng hỗ trợ; dùng API v2.");
        problem.setProperty("code", "ENDPOINT_RETIRED");

        return ResponseEntity.status(HttpStatus.GONE)
            .header(
                "Link",
                "<https://docs.example.test/developer/orders/migrate-v2>"
                    + "; rel=\"deprecation\"; type=\"text/html\"")
            .cacheControl(CacheControl.noStore())
            .body(problem);
    }
}
~~~

**Không đăng ký đồng thời** controller retired này và controller v1 đang hoạt động ở cùng mapping vì sẽ gây trùng route. Đây là hai phương án cho **hai giai đoạn khác nhau**. Cũng không được để tombstone bypass authentication một cách vô ý; chọn hiển thị 410 hay 404 theo policy exposure của từng audience.

## 11. Catalog as code và kiểm soát chất lượng ở CI

Metadata catalog nên nằm dưới version control hoặc được cập nhật qua workflow có audit. Khi developer tạo endpoint/đổi contract, pipeline cần cập nhật tài liệu cùng thay đổi code chứ không chờ đến cuối quý mới sửa.

~~~mermaid
flowchart TD
    A[Pull request: code + OpenAPI + metadata] --> B[Parse & lint OpenAPI]
    B --> C[Check unique operationId, path/method, schema]
    C --> D[Verify owner and lifecycle metadata]
    D --> E[Contract diff + breaking-change review]
    E --> F[Security/tenant authorization review]
    F --> G[Consumer impact / migration gate]
    G --> H[Build, tests, deploy]
    H --> I[Publish catalog entry + version + docs]
    I --> J[Compare gateway traffic/routes with catalog]
~~~

### 11.1. Các bất biến máy có thể kiểm

Một catalog validator có thể từ chối PR nếu:

- Operation thiếu `operationId`/mô tả hoặc trùng khóa `method + normalized path`.
- Owner team không tồn tại, không có kênh escalation hoặc không có business approver cho GA.
- Path được quảng bá public nhưng security classification là internal-only.
- Operation GA thiếu response errors phổ biến, auth requirements, examples hoặc link runbook theo support tier.
- OpenAPI thêm breaking change mà không có version/exception/migration decision.
- `state=DEPRECATED` nhưng không có `deprecatedAt`, người phê duyệt và hướng dẫn migration thích hợp.
- `sunsetAt <= deprecatedAt` mà không có ngoại lệ/phê duyệt hợp lệ.
- Đổi `state=RETIRED` hoặc xóa route khi consumer impact và approvals chưa hoàn tất.
- Gateway còn route production không có entry catalog hoặc entry GA không có deployment đối chiếu.
- Catalog public export chứa internal-only endpoint, on-call contact cá nhân hoặc secret.

Các gate này nên đủ nghiêm với **rủi ro thực**, không chặn mọi thay đổi nhỏ vì metadata hoàn toàn tùy chọn. Có quy trình exception có owner, lý do, thời hạn kết thúc và audit.

### 11.2. API diff không chỉ là so chuỗi YAML

So sánh OpenAPI được chuẩn hóa (resolve refs, normalize path template/ordering) thay vì so diff dòng. Tool có thể phát hiện:

- Operation bị xóa hoặc đổi method/path.
- Request field chuyển từ optional sang required.
- Response field bị xóa/đổi type, enum changed, media type changed.
- Security scheme/scope changed; response status changed.

Những thay đổi như pagination default, idempotency semantics, cache invalidation hoặc authorization policy cũng có thể phá client dù schema diff không thấy; cần **test nghiệp vụ và review**. Một cảnh báo breaking change không luôn có nghĩa phải từ chối sửa lỗi bảo mật: quy trình exception/phê duyệt phải xử lý trường hợp khẩn cấp.

### 11.3. Drift detection sau triển khai

Ngay cả spec hoàn hảo trong Git cũng không bảo đảm runtime đúng. Sau deploy:

1. So danh sách route thực tế ở gateway/app với catalog theo environment.
2. Kiểm HTTP smoke test trên version đang phục vụ và schema/code trả về.
3. Kiểm header lifecycle, OAuth/security, 401/403/404/429/503 và rate-limit behavior.
4. Lưu deployment revision, contract digest và thời điểm xác nhận.
5. Khi có mismatch, mở incident/ticket cho owner; không tự ghi đè contract theo runtime không được duyệt.

Drift có thể do rollout canary, reverse proxy rewrite, manual hotfix hoặc tài liệu không cập nhật. Pipeline phải phân biệt mismatch tạm thời **được lên lịch** với drift kéo dài bất thường.

## 12. Developer experience: từ tìm kiếm tới request đầu tiên

Một catalog có đủ metadata nhưng UX kém vẫn khiến developer chọn sai API. Một đường sử dụng tốt:

1. **Tìm theo nhu cầu:** “Lấy đơn hàng của khách”, không chỉ tìm theo `GET`.
2. **Đánh giá nhanh:** mô tả, audience, lifecycle, version, support tier, owner team, sandbox và quota.
3. **Đọc contract:** request/response, required scope, examples, pagination và error codes.
4. **Lấy quyền đúng:** hướng dẫn OAuth 2.0/OIDC theo grant được hỗ trợ (ví dụ Authorization Code + PKCE cho ứng dụng trình duyệt), audience API và scope.
5. **Chạy quickstart an toàn:** sandbox, fake/test data, không hardcode production secret.
6. **Xử lý lỗi/tái thử:** 400/401/403/404/409/412/429/503, `Retry-After`, idempotency và deadlines.
7. **Theo dõi thay đổi:** subscription theo API/operation/version, release note, deprecation timeline và migration guide.
8. **Gửi phản hồi:** tạo ticket/issue liên kết `operationId`, contract revision và request ID.

### 12.1. Ví dụ quickstart HTTP cho một GET có xác thực

~~~http
GET /api/v2/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: sandbox-api.example.test
Authorization: Bearer <test-access-token>
Accept: application/json
X-Request-Id: demo-request-001
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "PAID"
}
~~~

Client nên xử lý phản hồi không phải 200, body `application/problem+json` và các header hỗ trợ khi phù hợp. Quickstart cần nói rõ **đây là token sandbox**, không khuyến khích dán production token vào website bên thứ ba. Nếu tài liệu có interactive “Try it”, hệ thống cần bảo vệ token, CORS, callback/redirect URI và môi trường chạy đúng.

### 12.2. Catalog phải có ví dụ về tác dụng phụ

Đối với `POST /orders`, docs cần giải thích `Idempotency-Key` và kết quả `201`/`202` thay vì chỉ cho mẫu JSON. Một request tạo đơn có thể có kết quả chưa biết sau timeout, nên không thể khuyên “gửi lại với key mới” khi bị 503. Đối với `PATCH`, docs cần ETag/`If-Match` và semantics 412/409. Đối với endpoint phân trang, docs cần page size, cursor, sort stability, stale cursor behavior và yêu cầu bảo mật cho tenant.

**Developer experience tốt đồng nghĩa giúp consumer viết client an toàn**, không chỉ làm trang tài liệu đẹp.


## 13. Quan sát mức độ sử dụng và chất lượng catalog

### 13.1. Hai nhóm metric khác nhau

Một API catalog có hai loại “sức khỏe” cần được quan sát:

| Góc nhìn | Metric / tín hiệu | Câu hỏi |
|---|---|---|
| **Tính đầy đủ metadata** | % GA operations có owner, security policy, OpenAPI, changelog, support info | Endpoint có thể được hỗ trợ không? |
| **Tính mới của metadata** | Age since last review, runtime/catalog drift, stale contact | Catalog còn đúng thực tế không? |
| **Trạng thái vòng đời** | Số deprecated operations, tuổi deprecation, days-to-sunset | Có deadline sắp bị lỡ không? |
| **Tác động consumer** | Lượt gọi legacy theo operation, active client cohorts, tenant tier | Ai còn phụ thuộc endpoint cũ? |
| **Mức độ chuyển đổi** | Tỷ lệ call v1/v2, consumer migration confirmations | Chuyển đổi có tiến triển không? |
| **Độ tin cậy API** | 5xx/timeout/p95/p99, 429, authorization failures | Endpoint được hỗ trợ có đáp ứng SLO không? |
| **Trải nghiệm nhà phát triển** | Search success, docs click-through, sandbox onboarding success, support tickets | Có dễ tìm và tích hợp API không? |
| **Chất lượng contract** | Breaking-change violations, docs/spec drift, failed contract tests | Quy trình có bắt được hồi quy không? |

Nhóm **catalog quality** không thay thế HTTP SLI/SLO. Một operation có owner và OpenAPI đầy đủ vẫn có thể trả 503 liên tục. Một request nhận 404 vì consumer gọi URI sai là một kết quả HTTP có thể dự kiến, nhưng 404 hàng loạt sau retirement chưa được thông báo là một sự cố **trải nghiệm tích hợp**.

### 13.2. Phân tích consumer còn sử dụng endpoint cũ

Ví dụ dashboard migration:

~~~text
Operation: getOrderById v1
Lifecycle: DEPRECATED
Sunset: 2027-06-30T23:59:59Z

7-day request volume (legacy):
  internal services:   24,000
  partner clients:      6,800
  unknown clients:        120

Important consumers not confirmed migrated:
  order-report-worker (monthly scheduled job)
  partner-fulfillment-adapter (SDK release pending)

Decision:
  NOT READY to retire
  owner follow-up + planned re-evaluation
~~~

Những con số chỉ là ví dụ. Một dashboard thật phải phân biệt **requests**, **distinct logical consumers** và **registered client applications**. Không đếm mỗi JWT rotation hoặc mỗi pod như một consumer khác; không kết luận một ứng dụng inactive chỉ vì không có traffic ngắn hạn.

Một consumer đã đăng ký nhưng không có traffic có thể là job dự phòng hoặc luồng khẩn cấp. Một client có traffic có thể là bot/unknown integration. Vì thế **analytics là bằng chứng hỗ trợ quyết định, không thay xác nhận với owner của consumer quan trọng**.

### 13.3. Metric labels và quyền riêng tư

Prometheus labels nên dùng `apiId`, `operationId`, lifecycle state, environment, route template, support tier, status và error class từ tập giá trị giới hạn. Không dùng raw `userId`, email, access token, API key, order ID hoặc bất kỳ query string nào làm label.

Thông tin chi tiết “consumer nào còn gọi” có thể được lưu trong hệ thống registry/log có phân quyền và retention, liên kết theo **client application ID đã xác minh**, không hiển thị ở trang public. Audit sự kiện deprecation cần ghi người phê duyệt, source revision và thời điểm, tránh việc ai đó âm thầm kéo dài sunset sau một cuộc họp.

### 13.4. Cảnh báo có hành động

- `sunsetAt` còn 30 ngày nhưng consumer quan trọng chưa xác nhận chuyển đổi → **ticket đến owner + product**, không tự disable.
- Gateway có route chưa xuất hiện trong catalog → **drift/security review**.
- Endpoint `RETIRED` vẫn nhận nhiều traffic → kiểm compatibility/tombstone, liên hệ consumer và đo user impact.
- OpenAPI của deployment khác digest đã publish → cảnh báo build/release integrity.
- Metadata GA không có owner hợp lệ → chặn thay đổi rủi ro hoặc điều phối bàn giao.
- 401/403 tăng trên v2 sau migration → kiểm scope/JWKS/audience, không bỏ qua authorization để “làm migration xanh”.
- 5xx hoặc 429 tăng trên v2 trong lúc chuyển traffic → rollout pause/rollback theo SLO.

Không nên page on-call mỗi khi một API deprecated có 1 request lẻ; dùng **mức độ nghiêm trọng, deadline, business impact và runbook**.

## 14. Kiểm thử Java/Spring, OpenAPI và lifecycle governance

### 14.1. Kiểm header deprecation bằng JUnit 5

Có thể kiểm filter ở mục 10 mà không cần server hoặc DB thật:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class DeprecatedOrderEndpointHeadersFilterTest {
    private final DeprecatedOrderEndpointHeadersFilter filter =
        new DeprecatedOrderEndpointHeadersFilter();

    @Test
    void legacyGetHasDeprecationAndSunset() throws Exception {
        var request = new MockHttpServletRequest(
            "GET", "/api/v1/orders/order-101");
        var response = new MockHttpServletResponse();

        filter.doFilter(
            request, response, new MockFilterChain());

        assertEquals(
            "@1798761600", response.getHeader("Deprecation"));
        assertEquals(
            "Wed, 30 Jun 2027 23:59:59 GMT",
            response.getHeader("Sunset"));
        assertTrue(response.getHeader("Link")
            .contains("rel=\"deprecation\""));
    }

    @Test
    void currentVersionDoesNotReceiveLegacyHeader() throws Exception {
        var request = new MockHttpServletRequest(
            "GET", "/api/v2/orders/order-101");
        var response = new MockHttpServletResponse();

        filter.doFilter(
            request, response, new MockFilterChain());

        assertNull(response.getHeader("Deprecation"));
        assertNull(response.getHeader("Sunset"));
    }

    @Test
    void differentMethodDoesNotReceiveLegacyHeader() throws Exception {
        var request = new MockHttpServletRequest(
            "POST", "/api/v1/orders/order-101");
        var response = new MockHttpServletResponse();

        filter.doFilter(
            request, response, new MockFilterChain());

        assertNull(response.getHeader("Deprecation"));
    }
}
~~~

Đây là **filter unit/integration test tối thiểu**, không chứng minh gateway đã forward header hoặc OpenAPI document chứa `deprecated: true`. Phải bổ sung `MockMvc`/real HTTP test trên ứng dụng thực với route, security và JSON contract, rồi test end-to-end qua reverse proxy/CDN nếu ở production có lớp đó.

### 14.2. Kiểm HTTP contract có xác thực, không chỉ header

Một ma trận nên có:

| Request/kịch bản | Kỳ vọng | Điều quan sát thêm |
|---|---|---|
| `GET /api/v1/orders/{id}` với JWT hợp lệ, có quyền owner/tenant | 200, payload đúng, Deprecation/Sunset/Link | Header tại app và gateway thống nhất |
| Cùng GET trên v2 | 200, không có deprecation v1 | Contract v2 đúng |
| Thiếu token | 401 | Không lộ order, security filter hoạt động |
| Token hợp lệ nhưng thiếu scope | 403 | Không cho đọc, không cần biết trạng thái deprecation |
| Token tenant khác đoán ID | 403/404 theo policy | Không BOLA, không lộ ID/data |
| `GET` v1 sau retirement theo contract chọn tombstone | 410, Problem Details + migration link | Không còn controller cũ cùng mapping |
| Lệnh POST cũ có side effect khi retired | Error theo contract, không redirect mù | Không tạo đơn/thanh toán trùng |
| CORS request từ allowed origin | ACAO và expose headers phù hợp | Không leak internal link |
| Browser preflight sai origin/header | Từ chối theo CORS policy | Không mở wildcard để sửa nhanh |
| Gateway có cache | Mốc sunset nhất quán, có invalidation | Không trả metadata stale |
| Rollout canary v2 | Error/latency không vượt guardrail | Có rollback plan |

**Quan trọng:** `jwt()` của `spring-security-test` giả lập principal để kiểm authorization, **không kiểm chữ ký, issuer hoặc audience của JWT thật**. Đối với auth integration test cần dùng `JwtDecoder` thật với test keys/JWKS hoặc introspection fake theo contract. Lifecycle metadata không làm giảm yêu cầu kiểm auth hoặc tenant isolation.

### 14.3. Kiểm nội dung OpenAPI và catalog

Trong CI, parse OpenAPI thay vì dùng regex tìm text trong YAML. Các assertion quan trọng:

1. `operationId` duy nhất, path/method hợp lệ, schema có ví dụ/response errors cần thiết.
2. `getOrderById` trong v1 có `deprecated: true` sau khi lifecycle đã deprecated.
3. Catalog entry trỏ đúng `apiId/serviceId/operationId` và contract revision.
4. OwnerTeam resolve được về một team đang hoạt động, có support channel và người phê duyệt.
5. `sunsetAt` sau hoặc bằng `deprecatedAt` theo policy; dữ liệu ngày hợp lệ UTC.
6. Successor operation v2 thực sự có trong bản spec/runtime được hỗ trợ, migration link hợp lệ.
7. Contract diff phát hiện xóa hoặc thay đổi breaking với v1/v2 mà không có quyết định.
8. Bản public export không chứa security classification internal-only, URL quản trị, secret hoặc số điện thoại cá nhân.
9. Tài liệu migration có ví dụ 401/403/404/429/503, xử lý idempotency và pagination khi phù hợp.
10. Reconciliation job phát hiện route đang deploy mà catalog không có, và entry catalog GA không có route sau cutoff rollout.

Ở đây **gỡ endpoint phải là thay đổi có kiểm soát**, không thể chỉ xóa đoạn `@GetMapping` và nhận PR xanh vì tất cả unit tests còn chạy. Cần kiểm consumer evidence và gate phê duyệt retirement ngoài việc test source.

### 14.4. Ma trận lỗi tài liệu dễ bị bỏ qua

| Sai lệch | Cách phát hiện | Tác động |
|---|---|---|
| OpenAPI ghi `GET` nhưng app dùng `POST` | Contract HTTP test/drift | SDK/client gửi sai method |
| Catalog ghi owner cũ đã giải thể | Ownership registry validation | Không ai nhận incident |
| Trang portal ghi sunset khác header | Contract+lifecycle consistency check | Consumer nhận deadline mâu thuẫn |
| Gateway chặn request trước khi đến app | Edge smoke test | App test vẫn xanh nhưng khách nhận lỗi |
| Spec cho scope `orders.read` nhưng backend yêu cầu scope khác | Authorization integration test | 403 diện rộng |
| Endpoint retired mà scheduler vẫn gọi | Consumer telemetry theo chu kỳ | Job batch mất chức năng |
| V2 đổi enum mà SDK v1/v2 không kiểm | Consumer contract test | Deserialize lỗi ở client |
| User mất quyền nhưng swagger vẫn thử thành công bằng token admin | Test với least-privileged principal | Docs đưa kỳ vọng sai |
| CORS/ETag/429 thiếu trong docs | Review contract và error examples | Client cache/retry sai |
| Một operation bị đặt `DEPRECATED` do rollback nhầm | Lifecycle audit & release gates | Consumer ngừng tích hợp không cần thiết |

## 15. Một quy trình thay đổi API có thể vận hành

Giả sử nhóm Orders quyết định đổi `GET /api/v1/orders/{id}` sang v2 vì thiết kế schema và phân quyền mới. Quy trình đề xuất:


  - **Thiết kế** — Viết lý do thay đổi, đối tượng sử dụng, v2 schema, status/errors, security và ngày đề xuất
  - **Đánh giá tác động** — Trích consumer registry + gateway usage, xác định SDK/batch/mobile đặc biệt và support tier
  - **Duyệt** — Technical owner, product owner, security và operations ghi nhận quyết định và ngoại lệ
  - **Triển khai song song** — V1 tiếp tục đáp ứng contract; v2 được kiểm security, load, caching, idempotency và tenant
  - **Công bố** — Cập nhật OpenAPI, catalog, quickstart, migration guide, changelog, header deprecation/sunset
  - **Theo dõi** — Báo cáo adoption theo app/operation, gửi nhắc consumer theo deadline, xử lý lỗi SDK và on-call
  - **Go/no-go** — Kiểm migration confirmation, bất thường traffic, SLO và rủi ro trước khi sunset
  - **Retirement** — Rollout gỡ/đóng route có guardrail; quan sát 404/410, rollback/remediation nếu ảnh hưởng trái dự kiến
  - **Hậu kiểm** — Lưu archived spec, migration decision, số consumer đã di chuyển và ownership của phiên bản còn sống


Đây là quy trình của ví dụ, không bắt buộc tổ chức nào cũng phải áp dụng đúng thứ tự từng cuộc họp. Giá trị nằm ở **nguồn dữ liệu và bằng chứng** để tránh phá vỡ consumer: một nhóm có thể tự động hóa phần lớn gate bằng catalog as code, CI/CD và API gateway telemetry.

### 15.1. Nghỉ hưu khác “đã xóa tài liệu”

Khi endpoint được retired, không nên xóa sạch dấu vết. Catalog có thể giữ **tombstone metadata**:

~~~json
{
  "apiId": "order-management",
  "operationId": "getOrderById",
  "version": "v1",
  "state": "RETIRED",
  "retiredAt": "2027-07-01T00:00:00Z",
  "successorOperationId": "getOrderByIdV2",
  "migrationGuide": "/developer/orders/migrate-v1-to-v2",
  "decisionId": "api-change-042",
  "archivedContractRevision": "git:7f2e9a1"
}
~~~

Như vậy developer vẫn giải thích được vì sao URL cũ không hoạt động, nhà vận hành biết phải điều tra consumer nào và auditor thấy lịch sử cam kết. Tất nhiên, dữ liệu catalog có thể phải được giữ/xóa theo retention/privacy policy, không lưu lịch sử consumer nhạy cảm vô hạn.

## 16. Bài tập thực hành

### Bài tập 1 — Xây catalog cho năm operation

Một Orders API có:

- `GET /api/v1/orders/{id}` — đọc đơn, scope `orders.read`.
- `POST /api/v1/orders` — tạo đơn, cần `Idempotency-Key`.
- `PATCH /api/v1/orders/{id}` — cập nhật, cần `If-Match`.
- `GET /api/v2/orders/{id}` — endpoint mới, scope `orders.read`.
- `GET /internal/orders/metrics` — endpoint chỉ dành cho vận hành.

Yêu cầu: tạo bảng catalog operation-level có owner team, audience, state, version, auth, dữ liệu phân loại và docs link. Chọn operation nào được hiển thị ở portal partner và vì sao.

**Tiêu chí đạt:** Không để entry internal lộ ra partner; mỗi operation có owner và lifecycle riêng; không gộp tất cả thành một service state.

### Bài tập 2 — Phân biệt OpenAPI, registry và portal

Một đội tuyên bố “chúng tôi đã có API catalog” vì repository chứa `openapi.yml`. Hãy liệt kê thông tin có thể lấy từ spec, thông tin cần owner registry, thông tin từ gateway/telemetry và trải nghiệm developer portal cần thêm.

**Tiêu chí đạt:** Nêu rõ contract không tự chứng minh trạng thái production, chủ sở hữu/on-call, consumer usage hoặc ngày sunset.

### Bài tập 3 — Deprecation và HTTP headers

V1 được deprecated từ 2027-01-01T00:00:00Z và sunset lúc 2027-06-30T23:59:59Z. Viết phản hồi `200 OK` cho v1 kèm `Deprecation`, `Sunset` và `Link` tới migration guide; viết test Spring MockMvc hoặc filter test kiểm header. Nêu vì sao OpenAPI `deprecated: true` không làm endpoint tự ngừng phục vụ.

**Tiêu chí đạt:** Phân biệt Unix timestamp Structured Field Date với HTTP-date, không dùng `Retry-After` thay lịch sunset.

### Bài tập 4 — Phân tích breaking changes

Đánh giá các thay đổi: thêm optional request parameter; xóa response field; thêm enum value; đổi 200 đồng bộ thành 202 bất đồng bộ; tăng scope; đổi pagination cursor; sửa lỗi lộ dữ liệu tenant.

Yêu cầu: phân nhóm **thường tương thích / có thể breaking / breaking / security fix bắt buộc**, đề xuất contract tests và migration communication.

**Tiêu chí đạt:** Không coi mọi “thêm field” là luôn an toàn; không duy trì BOLA chỉ để tránh breaking change.

### Bài tập 5 — Quyết định hoãn sunset

Dashboard 7 ngày cho thấy request v1 giảm 99%, nhưng một nightly job dùng v1 vẫn chạy; owner chưa xác nhận migration. Một client SDK cũ trên mobile có chu kỳ nâng cấp vài tháng.

Hãy viết **go/no-go memo** cho API owner: số liệu còn thiếu, consumer cần liên hệ, phương án gia hạn hoặc adapter có thời hạn, rủi ro 404/410 và rollback/monitoring.

**Tiêu chí đạt:** Không lấy traffic thấp làm bằng chứng chắc chắn không còn consumer; có owner/decision record và deadline review mới.

### Bài tập 6 — Bảo mật catalog và HTTP runtime

Portal public đang xuất nguyên OpenAPI có `/internal/metrics`, SRE on-call numbers và các đường service nội bộ. Endpoint business dùng scope đúng nhưng service không kiểm tenant/owner.

Yêu cầu: thiết kế filtered catalog views, quyền export/search, endpoint authorization test, JWT audience check và kiểm không BOLA. Nêu vì sao CORS không thay authorization.

**Tiêu chí đạt:** Không lộ metadata nhạy cảm qua search/export; không nhầm khả năng khám phá với quyền truy cập API.

### Bài tập 7 — API catalog CI gate

Đề xuất một workflow CI cho pull request xóa `GET /api/v1/orders/{id}`, gồm lint OpenAPI, contract diff, metadata owner, lifecycle state, proof of consumer migration, security review, test 410/404 và release note.

**Tiêu chí đạt:** PR bị chặn nếu chưa có phê duyệt hoặc còn consumer quan trọng; có đường exception tạm thời và audit.

### Bài tập 8 — Java/Spring runtime và kiểm thử bảo mật

Dùng filter mục 10 để gắn lifecycle headers, controller cho v1/v2, Resource Server xác thực access token và service kiểm tenant. Viết kiểm thử cho: v1 GET owner đúng, v2 GET đúng, token sai audience, thiếu scope, tenant chéo, và retired route 410. Kiểm filter không gửi header cho method/route khác.

**Tiêu chí đạt:** Xác minh header **và** JSON/security, không chỉ test text trong source; phân biệt `jwt()` mock authorization test với decoder/JWKS test thật.

## 17. Sai lầm thường gặp và cách khắc phục

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Catalog chỉ có danh sách base URL | Không biết method/schema/owner/version | Gắn OpenAPI revision và operation-level metadata |
| Dùng path text như identity duy nhất | Trùng path template/đổi placeholder, mất lịch sử | Stable IDs + normalized route |
| Gắn owner là một nhân viên nghỉ việc | Không ai nhận trách nhiệm incident | Team owner, escalation và handover gate |
| Toàn bộ service một lifecycle state | Endpoint cũ và mới bị trộn | Lifecycle từng operation/version |
| Đánh dấu deprecated là xóa ngay | Consumer gãy không có thời gian migrate | Chạy song song theo chính sách và gửi thông báo |
| Chỉ sửa portal mà runtime không phát header | Client không nhận lifecycle signal | Đồng bộ catalog/OpenAPI/gateway và test |
| Đặt `Sunset` nhưng không có migration guide | Consumer không biết chuyển sang đâu | Link successor, examples, SDK changes |
| Mặc định redirect POST v1 sang v2 | Duplicate effects, sai schema/auth | Thiết kế migration chủ động và idempotency |
| Thấy 0 traffic một tuần là xóa | Job định kỳ/mobile/offline consumer bị phá | Cửa sổ đủ dài + owner confirmation |
| Đồng nhất OpenAPI version với URI major | Gây versioning và SDK drift | Quản lý contract revision và API version riêng |
| Mở API catalog public chứa endpoint nội bộ | Lộ topology và dữ liệu nhạy cảm | RBAC, data classification, filtered exports |
| Bỏ security vì endpoint retired | Có thể lộ thông tin tài nguyên cũ | Chính sách 404/410 có chủ đích |
| Không lưu archived spec | Không đối chiếu được cam kết đã công bố | Giữ revision và decision record theo retention |
| Không test deprecation headers qua gateway | Runtime trả thông tin khác docs | Smoke/contract tests ở edge |
| Chỉ quan sát 5xx khi retire | Không thấy hàng loạt 404/410 do migration thất bại | Consumer telemetry + SLI/business impact |

## 18. Checklist xuất bản và tài liệu chuẩn

### Checklist API catalog

- Operation có `apiId`, `serviceId`, `operationId`, method/path template và contract revision ổn định?
- Có mô tả business capability, audience, production/sandbox và hướng dẫn quickstart?
- OpenAPI mô tả request/response schema, status, pagination, caching, idempotency và error contract?
- Có technical owner, business approver, operational escalation, support tier và ngày review gần nhất?
- Auth type, scope, audience, tenant/owner policy và classification có được ghi rõ và thực thi thật?
- Lifecycle status là **operation-level**, có deprecation/sunset dates và successor khi phù hợp?
- Portal chỉ xuất metadata theo audience; search/export/API catalog bản public không lộ nội bộ?
- Runtime/OpenAPI/catalog/gateway có kiểm drift theo environment và deployment revision?
- Có bảo vệ người dùng trong thời gian deprecated và **phê duyệt rõ** trước retirement?
- Đã quan sát legacy traffic đủ lâu, liên hệ consumer quan trọng và có migration guide?
- Header `Deprecation`/`Sunset`/`Link` tuân thủ đúng định dạng, được test và giữ nhất quán qua cache/CDN?
- Có runbook, SLO, alert và rollback/canary cho thay đổi lifecycle?
- Archived contract, decision ID và ownership history được giữ theo chính sách lưu trữ?

### Tài liệu đối chiếu

- **OpenAPI Specification 3.1:** hợp đồng, operationId, security schemes và `deprecated` — https://spec.openapis.org/oas/v3.1.0
- **RFC 9110 — HTTP Semantics:** các HTTP methods, 404, 410, 401/403, 409, 429/5xx — https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9745 — Deprecation HTTP Response Header Field:** `Deprecation` dạng Structured Field Date — https://www.rfc-editor.org/rfc/rfc9745
- **RFC 8594 — The Sunset HTTP Header Field:** `Sunset` dạng HTTP-date — https://www.rfc-editor.org/rfc/rfc8594
- **RFC 8288 — Web Linking:** `Link` header và relation — https://www.rfc-editor.org/rfc/rfc8288
- **RFC 9457 — Problem Details for HTTP APIs:** lỗi có cấu trúc — https://www.rfc-editor.org/rfc/rfc9457
- **Spring Framework — REST controllers và HTTP handling:** https://docs.spring.io/spring-framework/reference/web/webmvc.html
- **Spring Security — OAuth2 Resource Server:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security — Testing:** https://docs.spring.io/spring-security/reference/servlet/test/index.html
- **Swagger/OpenAPI documentation (tooling reference):** https://swagger.io/specification/

**Điểm cốt lõi:** API catalog là **cam kết có thể tra cứu về API đang tồn tại, người chịu trách nhiệm và kế hoạch thay đổi**. OpenAPI nói endpoint nhận/trả gì; ownership nói ai bảo vệ và sửa nó; lifecycle cùng `Deprecation`/`Sunset` nói consumer cần chuẩn bị gì; telemetry và kiểm thử chứng minh có thể đổi hoặc nghỉ endpoint mà không phá vỡ những tích hợp hợp lệ. Catalog tốt được vận hành như một sản phẩm có dữ liệu nguồn, quy trình duyệt, phân quyền, CI và bằng chứng migration — chứ không chỉ một danh sách URL.

# Kiểm kê theo code, gateway, DNS và traffic

Không thể bảo vệ một API mà tổ chức không biết nó tồn tại ở đâu, được triển khai trong môi trường nào, ai sở hữu và đang được gọi như thế nào. Một dịch vụ có thể có endpoint trong source code nhưng chưa được đưa ra gateway; một route đã bị xóa khỏi tài liệu vẫn còn được cấu hình ở ingress; một hostname cũ vẫn trỏ tới load balancer; hoặc traffic thực tế đang gọi một API phiên bản cũ mà nhóm phát triển tưởng đã ngừng sử dụng.

API inventory (danh mục API) là tập hợp có quản lý về các API, endpoint, host, phiên bản, chủ sở hữu, môi trường, quyền truy cập, dữ liệu và trạng thái vòng đời. Để tạo inventory đủ tin cậy, cần đối chiếu nhiều nguồn bằng chứng: **source code**, **API gateway/ingress**, **DNS/service discovery** và **traffic/runtime telemetry**. Mỗi nguồn nhìn thấy một phần hệ thống; không nguồn nào tự nó mô tả toàn bộ bề mặt API.

Trong API Security, inventory là nền tảng để tìm shadow API, API cũ còn hoạt động, endpoint nội bộ bị phơi bày, route thiếu xác thực, phiên bản có rủi ro và service không còn owner. Danh mục cần được cập nhật liên tục theo thay đổi code, cấu hình triển khai và hoạt động thực tế, thay vì chỉ lập một bảng thủ công rồi để lỗi thời.

## 1. API inventory là gì và cần trả lời câu hỏi nào?

Một inventory hữu ích cần trả lời được:

- API nào tồn tại và endpoint nào được cung cấp?
- Endpoint được triển khai ở môi trường nào: development, staging, production hay nội bộ?
- Hostname, base path, method và upstream/service nào xử lý request?
- API được truy cập qua internet, VPN, private network, gateway hay service mesh?
- Nhóm hoặc cá nhân nào chịu trách nhiệm vận hành và xử lý sự cố?
- Endpoint yêu cầu authentication và authorization nào?
- API xử lý dữ liệu công khai, dữ liệu cá nhân, tài chính hay dữ liệu nhạy cảm khác?
- Endpoint còn được sử dụng không, lần cuối thấy traffic khi nào và từ nguồn nào?
- API có OpenAPI contract, version, SLA, rate limit và trạng thái vòng đời nào?
- Có endpoint nào đang hoạt động nhưng không được tài liệu hoặc gateway quản lý không?

Inventory không chỉ là danh sách URL. Một URL đơn lẻ không cho biết method, route template, audience, auth policy, owner hay dữ liệu mà endpoint trả về. Ví dụ `GET /api/v1/users/{id}` và `DELETE /api/v1/users/{id}` cùng path nhưng có rủi ro và quyền rất khác nhau.

## 2. Bốn nguồn bằng chứng chính

| Nguồn | Cho biết điều gì? | Điểm mù thường gặp |
|---|---|---|
| Source code và API contract | Route được khai báo, method, handler, request/response schema, annotation và security metadata | Route tạo động, cấu hình runtime, code chưa deploy hoặc route bị feature flag tắt |
| API gateway, ingress và load balancer | Host/path routing, rewrite, upstream, TLS, authentication, rate limit và exposure | Traffic đi thẳng tới service, gateway khác, cấu hình chưa được triển khai hoặc route không còn dùng |
| DNS và service discovery | Hostname, CNAME, A/AAAA, wildcard, service name và quan hệ host/service | DNS không mô tả đầy đủ path/method; hostname có thể không phải API hoặc API dùng IP/service mesh |
| Traffic và runtime telemetry | Endpoint thực sự được gọi, caller, status, volume, thời điểm và dependency | Endpoint ít dùng, chưa được gọi trong cửa sổ quan sát hoặc bị chặn trước điểm thu thập |

Khi các nguồn không khớp nhau, sự khác biệt là tín hiệu cần điều tra chứ không phải lý do để tùy tiện chọn một nguồn làm sự thật tuyệt đối. Ví dụ, code cho thấy endpoint tồn tại nhưng traffic chưa từng ghi nhận có thể là endpoint dormant, route chỉ dùng trong sự cố hoặc môi trường chưa được quan sát.

## 3. Xây dựng inventory từ source code

Source code cho biết endpoint mà ứng dụng dự định cung cấp. Đây là nguồn quan trọng để tìm route chưa được công bố hoặc route không đi qua gateway.

### Các thành phần cần quét

- Controller, router, handler, servlet mapping và annotation route.
- OpenAPI/Swagger specification, API schema và generated client contract.
- GraphQL schema/resolver, gRPC service definition và RPC handler nếu nằm trong phạm vi inventory.
- Webhook endpoint, callback, health/admin endpoint và endpoint dành cho batch job.
- Security annotation, middleware, filter, interceptor và policy gắn với route.
- Cấu hình route tạo động, feature flag, profile và module được nạp theo môi trường.
- Dependency gọi API ngoài hoặc endpoint nội bộ do service khác sở hữu.

Ví dụ với Spring MVC:

```java
@RestController
@RequestMapping("/api/v1/orders")
class OrderController {

    @GetMapping("/{orderId}")
    OrderResponse getOrder(@PathVariable UUID orderId) {
        return orderService.getOrder(orderId);
    }

    @PostMapping
    OrderResponse createOrder(@Valid @RequestBody CreateOrderRequest request) {
        return orderService.createOrder(request);
    }
}
```

Từ khai báo này, inventory có thể tạo hai operation: `GET /api/v1/orders/{orderId}` và `POST /api/v1/orders`. Cần lưu route template thay vì chỉ ghi URL có ID thực tế trong log, vì `/orders/1001` và `/orders/1002` là cùng một endpoint template.

### Phân biệt route được khai báo với route thực sự được deploy

Một controller có thể nằm trong source nhưng không được đóng gói hoặc kích hoạt trong production. Ngược lại, route có thể được tạo bởi plugin, framework, gateway filter hoặc cấu hình runtime mà tìm kiếm annotation không phát hiện được.

Do đó, source scan nên được gắn với commit, build artifact, module, profile và môi trường triển khai. Kết quả static scan là bằng chứng về code, không phải bằng chứng duy nhất rằng endpoint đang hoạt động trên production.

### Ví dụ tìm route trong repository

Có thể dùng công cụ tìm kiếm code để hỗ trợ rà soát, ví dụ với ripgrep:

```bash
rg -n "@(Get|Post|Put|Patch|Delete|Request)Mapping|router\.(get|post|put|patch|delete)" src
rg -n "@Path\(|@GET|@POST|@PUT|@PATCH|@DELETE" src
rg -n "openapi:|swagger:|paths:" . -g '*.yaml' -g '*.yml' -g '*.json'
```

Các biểu thức trên chỉ là điểm bắt đầu. Chúng không hiểu đầy đủ inheritance, meta-annotation, route registration bằng code, conditional bean hoặc DSL riêng. Nên ưu tiên parser/plugin phù hợp framework và xác minh với route map thực tế ở runtime.

## 4. Dùng OpenAPI và contract làm nguồn chuẩn hóa

OpenAPI mô tả path, HTTP method, parameter, request body, response, authentication scheme và metadata của operation. Một inventory có thể import nhiều OpenAPI document, sau đó chuẩn hóa các operation theo môi trường và service.

Ví dụ rút gọn:

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.4.0
servers:
  - url: https://api.example.com
paths:
  /api/v1/orders/{orderId}:
    get:
      operationId: getOrder
      security:
        - bearerAuth: []
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Order details
        '404':
          description: Order not found
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

Contract có thể bổ sung owner, data classification, environment, lifecycle và security contact bằng extension hoặc metadata trong hệ thống inventory. Không nên nhầm việc có `security` trong OpenAPI với việc endpoint đã được bảo vệ đúng: cần xác minh runtime configuration, audience, scope và object-level authorization.

OpenAPI có thể không mô tả route nội bộ, route dynamic, endpoint của framework hoặc behavior thực tế của gateway. Hãy dùng contract làm nguồn quan trọng nhưng vẫn đối chiếu với các nguồn runtime.

## 5. Kiểm kê API Gateway, ingress và load balancer

Gateway/ingress thường là nơi tập trung routing và policy ở lớp edge. Cấu hình tại đây cho biết client có thể đi từ hostname/path nào tới upstream nào và lớp kiểm soát nào được áp dụng.

Thông tin cần thu thập:

- Gateway, listener, hostname, port, TLS certificate và environment.
- Route path, method, path matching, priority và rewrite/strip prefix.
- Upstream service, cluster, target group hoặc destination.
- Authentication plugin, JWT validation, API key, mTLS hoặc policy khác.
- Rate limit, quota, body size, timeout, CORS và IP restriction.
- Public/private exposure, source allowlist và network zone.
- Route status, thời điểm tạo/sửa, cấu hình version và owner.

### Chú ý route rewrite và route wildcard

Gateway có thể nhận `/public/orders/{id}` rồi rewrite thành `/internal/v2/orders/{id}`. Nếu inventory chỉ ghi path public hoặc chỉ ghi path backend, nhóm vận hành sẽ không nhìn thấy quan hệ giữa hai endpoint.

Route wildcard như `/api/**` có thể phơi bày endpoint mới trong service mà không có review riêng. Một route catch-all hoặc proxy pass tới upstream có thể khiến API nội bộ xuất hiện công khai ngoài dự kiến. Hãy ghi cả public path, upstream path, method, match priority và rule rewrite.

### Không giả định mọi request đều qua gateway

Backend có thể có LoadBalancer/NodePort, ingress thứ hai, service mesh ingress, DNS nội bộ hoặc địa chỉ truy cập trực tiếp. Hãy đối chiếu listener và network path với cloud load balancer, Kubernetes Service/Ingress/Gateway API và network policy. Nếu gateway là lớp duy nhất áp dụng auth nhưng backend vẫn truy cập trực tiếp, policy có thể bị bypass.

## 6. Kiểm kê hostname từ DNS và service discovery

DNS giúp tìm các hostname có thể dẫn tới API hoặc service. Các record thường gặp:

| Record | Ý nghĩa | Giá trị đối với inventory |
|---|---|---|
| `A` | Hostname tới IPv4 | Tìm địa chỉ đích và vùng mạng |
| `AAAA` | Hostname tới IPv6 | Tránh bỏ sót endpoint chỉ phục vụ IPv6 |
| `CNAME` | Bí danh tới hostname khác | Theo dõi chuỗi alias và dịch vụ đích |
| `SRV` | Service, port và target | Có thể phát hiện service discovery cho giao thức/API |
| `TXT` | Metadata hoặc xác minh domain | Có thể hỗ trợ phân loại, nhưng không phải nguồn route API |
| Wildcard DNS | Nhiều hostname cùng được phân giải | Cần xác minh host nào thực sự được phục vụ |

Nên thu thập authoritative zone nội bộ, DNS cloud, private DNS zone, service registry và record công khai trong phạm vi được phép. Với Kubernetes, có thể kết hợp Service, Ingress, Gateway API và DNS do cluster quản lý.

### Theo dõi CNAME và dangling record

Một CNAME có thể trỏ tới dịch vụ cloud hoặc SaaS đã bị xóa. Nếu resource đích không còn được sở hữu nhưng DNS vẫn tồn tại, hostname có thể trở thành dangling record và có nguy cơ bị chiếm quyền theo cơ chế subdomain takeover của nhà cung cấp.

Inventory nên ghi chuỗi CNAME, target hiện tại, TTL, trạng thái phân giải và owner. Record không phân giải được hoặc target báo chưa cấu hình không tự động chứng minh có thể takeover; cần xác minh theo dịch vụ đích và xử lý bằng quy trình quản lý domain.

### DNS không mô tả endpoint

Một hostname có thể phục vụ hàng trăm path và method thông qua gateway. DNS chỉ cho biết tên có thể được phân giải tới đâu, không chứng minh API nào tồn tại trên hostname. Ngược lại, service nội bộ có thể được gọi bằng service name hoặc discovery registry mà không có hostname public.

Không dựa vào zone transfer hoặc quét DNS không giới hạn để khám phá ngoài phạm vi được phép. Thu thập DNS phải tuân theo quyền quản trị domain và chính sách của tổ chức.

## 7. Khám phá API từ traffic và runtime telemetry

Traffic cho biết endpoint nào thực sự được gọi. Đây là cách quan trọng để phát hiện API không có trong tài liệu hoặc cấu hình dự kiến.

Nguồn telemetry có thể gồm:

- API gateway access log và analytics.
- Ingress/load balancer access log.
- Service mesh telemetry hoặc proxy access log.
- Application access log và framework route metrics.
- Distributed tracing và span HTTP/RPC.
- WAF/security event và network flow log.
- Message broker hoặc event consumer telemetry nếu inventory mở rộng sang API bất đồng bộ.

Các trường nên thu thập ở mức tối thiểu:

- Timestamp và environment.
- Host, method, route template và service/upstream.
- Status code, latency, request/response bytes.
- Caller/client identity đã được xác minh ở dạng định danh phù hợp.
- Authentication result, policy decision hoặc auth scheme ở dạng metadata.
- Trace/request ID và nguồn telemetry.

Không ghi raw Authorization header, cookie, API key, query chứa token hoặc toàn bộ body chỉ để xây inventory. Nếu cần phân tích payload, dùng schema metadata hoặc sampling đã lọc dữ liệu nhạy cảm theo chính sách.

### Route template quan trọng hơn URL thô

Traffic log có thể chứa hàng triệu URL như `/orders/123`, `/orders/124`, `/orders/125`. Inventory cần chuẩn hóa chúng thành `/orders/{orderId}` để đếm endpoint, gắn owner và so sánh với OpenAPI.

Việc chuẩn hóa cần tránh gộp nhầm route. Ví dụ `/users/me` có thể là route tĩnh riêng, không phải `/users/{id}`; `/files/{fileName}` có thể có quy tắc matching khác. Dùng route template từ framework/gateway khi có thể, thay vì chỉ suy đoán bằng regex.

### Cửa sổ quan sát traffic

Một endpoint không có traffic trong 7 ngày chưa chắc đã chết. API có thể chạy theo tháng, theo mùa, chỉ dùng khi disaster recovery hoặc chỉ được gọi từ batch job. Hãy chọn cửa sổ quan sát phù hợp với chu kỳ nghiệp vụ và ghi rõ thời gian quan sát, nguồn log, độ phủ và retention.

Traffic là bằng chứng endpoint đã được gọi trong khoảng thời gian quan sát; không có traffic không phải bằng chứng chắc chắn endpoint không tồn tại hoặc không cần thiết.

## 8. Chuẩn hóa và hợp nhất dữ liệu từ nhiều nguồn

Trước khi hợp nhất, cần chuẩn hóa các thành phần để tránh coi cùng endpoint là nhiều API khác nhau hoặc gộp hai endpoint khác nhau thành một.

Các trường chuẩn hóa thường gồm:

- Scheme, hostname, port, base path và environment.
- HTTP method và route template.
- API/service name, version và operation ID nếu có.
- Public path và upstream/internal path.
- Protocol: HTTP/REST, GraphQL, gRPC, WebSocket hoặc webhook.
- Owner/team, business capability và data classification.
- Authentication mechanism, authorization policy và exposure.
- Source evidence, timestamp, confidence và trạng thái lifecycle.

Một endpoint identity có thể được tạo từ environment, host/service, protocol, method và normalized route. Không chỉ dùng path làm khóa vì nhiều service có thể cùng cung cấp `/health` hoặc `/api/v1/users` trên các host khác nhau.

Ví dụ record chuẩn hóa:

```json
{
  "apiId": "orders-prod-get-order",
  "environment": "production",
  "protocol": "http",
  "host": "api.example.com",
  "method": "GET",
  "publicPath": "/api/v1/orders/{orderId}",
  "upstreamService": "orders-service",
  "upstreamPath": "/internal/orders/{orderId}",
  "ownerTeam": "commerce-platform",
  "authentication": "oauth2-bearer",
  "dataClassification": "confidential",
  "exposure": "internet",
  "sources": ["openapi", "gateway", "traffic"],
  "lastSeenAt": "2026-11-18T08:00:00Z",
  "lifecycle": "active"
}
```

Record là ví dụ minh họa. `ownerTeam`, `dataClassification` và authentication phải được xác nhận từ metadata hoặc chủ sở hữu; không suy ra chắc chắn chỉ từ tên service hoặc URL.

### Lưu nguồn gốc và độ tin cậy

Mỗi thuộc tính nên có nguồn và thời điểm quan sát. Ví dụ host lấy từ DNS, public path lấy từ gateway, method/route lấy từ code, `lastSeenAt` lấy từ traffic. Nếu hai nguồn mâu thuẫn, lưu cả hai bằng chứng và đánh dấu cần xác minh thay vì âm thầm ghi đè.

Có thể dùng confidence level như `confirmed`, `observed`, `inferred` hoặc `unknown`. Endpoint thấy trong gateway và traffic có thể được xác nhận đang hoạt động; endpoint chỉ thấy trong một file OpenAPI cũ nên được đánh dấu contract-only cho tới khi xác minh deploy.

## 9. Đối chiếu chéo để tìm shadow, orphan và zombie API

Khi có các tập dữ liệu từ code, gateway, DNS và traffic, hãy so sánh chúng:

| Dấu hiệu | Cách hiểu có thể có | Việc cần làm |
|---|---|---|
| Có trong code và gateway, có traffic | API được triển khai và sử dụng | Xác minh owner, policy và data classification |
| Có traffic nhưng không có OpenAPI/code record | Shadow API, route dynamic hoặc thiếu nguồn dữ liệu | Xác định upstream và owner; kiểm tra auth/exposure |
| Có trong code nhưng không có gateway | API nội bộ, route chưa publish hoặc đường gọi trực tiếp | Kiểm tra service exposure và network path |
| Có trong gateway nhưng không thấy code | Route rewrite, upstream ngoài phạm vi, code khác hoặc cấu hình cũ | Truy vết upstream và xác minh deployment |
| Có DNS/hostname nhưng không có route/traffic | Host cũ, dịch vụ khác hoặc endpoint dormant | Kiểm tra target, owner, certificate và lifecycle |
| Có trong tài liệu nhưng không có code/gateway/traffic | Contract cũ hoặc API đã ngừng | Xác nhận với owner trước khi deprecate |
| Có traffic tới version cũ | Client vẫn dùng API legacy | Xác định caller và lập kế hoạch migration |
| Không có owner hoặc owner không còn tồn tại | Orphan API | Gán owner hoặc cô lập/ngừng theo quy trình |

Các thuật ngữ `shadow API`, `orphan API` và `zombie API` có thể được tổ chức định nghĩa hơi khác nhau. Hãy công bố tiêu chí nội bộ. Ví dụ, shadow API là endpoint đang hoạt động nhưng chưa được inventory/contract quản lý; zombie API là endpoint đã được coi là ngừng nhưng vẫn có traffic hoặc còn reachable.

Không tự động xóa route chỉ vì traffic không xuất hiện trong một cửa sổ ngắn. Xác minh owner, batch schedule, disaster recovery, client partner và yêu cầu lưu trữ trước khi thay đổi production.

## 10. Xây dựng schema inventory và lưu evidence

Một bảng inventory đơn giản có thể gồm:

```sql
CREATE TABLE api_inventory (
    api_id VARCHAR(160) PRIMARY KEY,
    environment VARCHAR(30) NOT NULL,
    protocol VARCHAR(30) NOT NULL,
    host VARCHAR(255),
    http_method VARCHAR(12),
    route_template VARCHAR(1000),
    upstream_service VARCHAR(255),
    upstream_path VARCHAR(1000),
    api_version VARCHAR(80),
    owner_team VARCHAR(160),
    exposure VARCHAR(30),
    authentication VARCHAR(80),
    data_classification VARCHAR(80),
    lifecycle VARCHAR(30) NOT NULL,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE api_inventory_evidence (
    evidence_id UUID PRIMARY KEY,
    api_id VARCHAR(160) NOT NULL REFERENCES api_inventory(api_id),
    source_type VARCHAR(40) NOT NULL,
    source_ref VARCHAR(1000),
    observed_at TIMESTAMPTZ NOT NULL,
    confidence VARCHAR(30) NOT NULL,
    attributes JSONB NOT NULL
);
```

Đây là schema khái niệm. Hệ thống thực tế có thể cần bảng riêng cho host, deployment, owner, auth policy, data classification, version và relationship. Evidence nên giữ nguồn gốc mà không lưu raw secret hoặc body nhạy cảm. Cần phân quyền đọc inventory vì hostname nội bộ, route admin và service topology cũng là thông tin nhạy cảm.

## 11. Gắn security posture vào từng endpoint

Inventory chỉ hữu ích cho bảo mật khi có thể đánh giá endpoint. Với mỗi operation, cần ghi nhận hoặc liên kết tới:

- Authentication: public, session, OAuth bearer, API key, mTLS, workload identity hay cơ chế khác.
- Authorization: scope/role, object-level, tenant-level và property-level policy.
- Exposure: internet-facing, partner, internal, management plane hoặc restricted network.
- Data classification: public, internal, confidential, restricted hoặc phân loại của tổ chức.
- Input controls: schema validation, body size, file type, query limits và nested depth.
- Output controls: response DTO, field filtering, cache policy và error envelope.
- Abuse controls: rate limit, quota, concurrency, timeout và cost limit.
- Version/lifecycle: active, deprecated, sunset, disabled hoặc unknown.
- Owner, incident contact và review date.

Một route được đánh dấu `authenticated` không đồng nghĩa an toàn. Cần biết token audience/scope, quyền trên object, tenant isolation và dữ liệu response. Inventory nên liên kết tới kết quả security review hoặc test, không chỉ lưu một checkbox “auth enabled”.

## 12. Phân loại mức độ ưu tiên khi xử lý phát hiện

Không phải mọi endpoint chưa có trong tài liệu đều có cùng mức độ nguy hiểm. Có thể ưu tiên theo exposure, dữ liệu, chức năng và bằng chứng hoạt động.

Ví dụ các yếu tố đánh giá:

| Yếu tố | Mức rủi ro tăng khi |
|---|---|
| Exposure | Endpoint internet-facing hoặc đi qua host public |
| Data | Trả dữ liệu cá nhân, tài chính, credential hoặc dữ liệu hạn chế |
| Action | Có thao tác ghi, xóa, quản trị, thanh toán hoặc thay đổi quyền |
| Authentication | Không có auth, auth yếu hoặc policy chưa xác minh |
| Authorization | Thiếu object/tenant/property checks hoặc quyền quá rộng |
| Usage | Có traffic thực tế, caller lạ hoặc lưu lượng tăng bất thường |
| Ownership | Không có owner hoặc không có người chịu trách nhiệm |
| Lifecycle | API legacy/deprecated vẫn hoạt động hoặc version đã hết hỗ trợ |

Có thể dùng thang điểm nội bộ, nhưng không nên để điểm tổng che mất một điều kiện nghiêm trọng. Một endpoint quản trị internet-facing không auth cần xử lý khẩn cấp dù traffic thấp. Ghi rõ lý do và evidence để người xử lý hiểu vì sao phát hiện được ưu tiên.

## 13. Quy trình discovery và reconciliation định kỳ

Một chu trình triển khai có thể gồm:

1. **Xác định phạm vi:** tài khoản cloud, cluster, repository, domain, gateway, environment và protocol được kiểm kê.
2. **Thu thập source evidence:** parse route code, OpenAPI và metadata build/deployment.
3. **Thu thập edge evidence:** export gateway, ingress, load balancer, route rewrite và policy.
4. **Thu thập DNS/service discovery:** zone, record, CNAME chain, service registry và target.
5. **Thu thập runtime evidence:** gateway/app/mesh logs, traces và flow metadata trong cửa sổ quan sát xác định.
6. **Chuẩn hóa:** host, method, route template, protocol, environment và version.
7. **Hợp nhất và đối chiếu:** tìm record trùng, record mâu thuẫn, shadow/orphan/zombie và route chưa có owner.
8. **Xác minh:** gửi finding cho team owner, kiểm tra deployment và xác nhận lifecycle.
9. **Đánh giá security posture:** exposure, auth, authorization, data, abuse control và version.
10. **Remediate và theo dõi:** sửa policy, gỡ route, migrate client hoặc gán owner; ghi lại bằng chứng sau xử lý.

Discovery nên chạy theo lịch và theo sự kiện. Ví dụ, CI/CD có thể cập nhật inventory khi deploy; gateway config change có thể kích hoạt reconciliation; DNS change có thể tạo finding; traffic job định kỳ phát hiện endpoint mới.

## 14. Tích hợp inventory vào CI/CD và quản lý thay đổi

Để inventory không lỗi thời, hãy biến nó thành một phần của vòng đời phát triển:

- Pull request cập nhật OpenAPI hoặc route metadata cùng code.
- CI so sánh endpoint mới/xóa/đổi method với contract đã duyệt.
- Endpoint mới phải có owner, exposure, authentication và data classification.
- Route có quyền quản trị hoặc dữ liệu nhạy cảm cần security review phù hợp.
- Deployment cập nhật build version, commit, environment và timestamp.
- Gateway config pipeline phát hiện wildcard route, public exposure hoặc upstream không có owner.
- Release deprecate phải có ngày sunset, client usage evidence và kế hoạch migration.
- Sau deploy, runtime discovery xác nhận endpoint thực sự xuất hiện hoặc đã biến mất.

Không nên tự động chặn mọi thay đổi endpoint chỉ vì OpenAPI diff. Có thể có thay đổi tương thích ngược hoặc route nội bộ không công bố; hãy dùng policy theo mức rủi ro và quy trình exception có thời hạn.

## 15. Quản lý API version và vòng đời

Inventory nên ghi version theo nhiều chiều: version trong path (`/v1`), version contract, build version, deployment version và version của upstream. Các giá trị này không nhất thiết giống nhau.

Một endpoint có thể ở các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `planned` | Đã khai báo nhưng chưa deploy |
| `active` | Đang được cung cấp và hỗ trợ |
| `deprecated` | Vẫn hoạt động nhưng đã công bố sẽ ngừng |
| `sunset` | Đã tới thời điểm ngừng theo chính sách; cần xác minh runtime |
| `disabled` | Đã tắt ở lớp được kiểm soát |
| `retired` | Đã xác nhận không còn triển khai hoặc route |
| `unknown` | Chưa đủ evidence để xác định |

Không chuyển `deprecated` thành `retired` chỉ dựa vào ngày trong tài liệu. Cần kiểm tra gateway, DNS, traffic, client partner và đường truy cập trực tiếp. Với API legacy, inventory giúp xác định client còn gọi trước khi tắt route.

## 16. Discovery an toàn và tránh gây ảnh hưởng production

Không phải discovery nào cũng cần active scan. Thu thập code, config, DNS và telemetry thường ít tác động hơn việc gửi hàng loạt request thử vào production.

Nếu cần probe hoặc xác minh endpoint:

- Có phê duyệt và scope rõ ràng cho host, environment, thời gian và phương thức.
- Ưu tiên staging/test hoặc endpoint health/read-only đã được chỉ định.
- Dùng rate limit thấp, timeout, concurrency nhỏ và user agent nhận diện rõ.
- Không thử payload ghi/xóa, không gửi dữ liệu giả vào nghiệp vụ thật.
- Không brute force path hoặc credential.
- Không vượt qua authentication, WAF hoặc network control để “khám phá cho đủ”.
- Dừng khi thấy latency, error rate hoặc tải hệ thống tăng bất thường.
- Ghi lại probe để phân biệt traffic kiểm thử với traffic người dùng.

Discovery chủ động chỉ là bước xác minh có kiểm soát. Không dùng kết quả scan làm bằng chứng duy nhất về API inventory vì scan có thể bỏ sót route yêu cầu auth, route chỉ bật theo điều kiện hoặc endpoint không phản hồi với phương thức thử.

## 17. Ví dụ đối chiếu bốn nguồn

Giả sử một hostname `api.example.com` có các bằng chứng:

| Nguồn | Evidence |
|---|---|
| Code | `GET /api/v1/orders/{id}`, `POST /api/v1/orders` |
| OpenAPI | Chỉ mô tả hai operation trên |
| Gateway | Route `/api/v1/**` chuyển tới `orders-service`; route rewrite `/legacy/orders/**` cũng chuyển tới service này |
| DNS | `api.example.com` CNAME tới public load balancer; `orders.internal` là private service name |
| Traffic | Có `GET /api/v1/orders/{id}` và `GET /legacy/orders/{id}`; không thấy `POST` trong cửa sổ 30 ngày |

Inventory không nên kết luận route legacy là vô dụng vì vẫn có traffic; cũng không nên coi `POST` đã chết chỉ vì không xuất hiện trong 30 ngày. Việc cần làm là xác định caller của route legacy, owner của rewrite, chu kỳ nghiệp vụ của POST và liệu backend có đường gọi khác không. Sau đó có thể lập kế hoạch đưa route legacy vào contract, migrate client hoặc sunset theo quy trình.

## 18. Kiểm thử chất lượng inventory

Inventory cần được kiểm tra về độ bao phủ và độ chính xác:

| Nhóm kiểm thử | Câu hỏi |
|---|---|
| Source coverage | Có scan tất cả repository, module, profile và route DSL không? |
| Gateway coverage | Có thu thập mọi gateway, ingress, load balancer và route rewrite không? |
| DNS coverage | Có cả public/private zone, A/AAAA, CNAME và service registry không? |
| Traffic coverage | Có gateway, application, mesh và môi trường liên quan trong cửa sổ đủ dài không? |
| Normalization | Route template có gộp đúng path động mà không gộp nhầm static route không? |
| Reconciliation | Finding giữa các nguồn có evidence, owner và trạng thái xử lý không? |
| Lifecycle | Deprecated/retired API có được xác minh bằng runtime và deployment evidence không? |
| Security metadata | Auth, scope, data classification, exposure và owner có được xác nhận không? |
| Freshness | Inventory ghi thời điểm cập nhật và nguồn dữ liệu mới nhất không? |
| Privacy | Log/telemetry có tránh token, cookie, body và dữ liệu nhạy cảm không? |

Có thể theo dõi các chỉ số: tỷ lệ endpoint có owner, tỷ lệ endpoint có contract, tỷ lệ internet-facing có auth policy được xác minh, số shadow API, số route legacy có traffic, số record không được cập nhật và thời gian xử lý finding.

## 19. Giám sát drift và phát hiện API mới

Drift xảy ra khi trạng thái thực tế khác inventory đã được phê duyệt. Ví dụ, một route mới xuất hiện trên gateway nhưng không có OpenAPI; DNS public mới được tạo cho service nội bộ; traffic bắt đầu gọi endpoint admin; hoặc một endpoint đã retired vẫn nhận request.

Có thể tạo finding tự động khi:

- Route/method mới xuất hiện trong gateway hoặc runtime traffic.
- Hostname public mới trỏ tới upstream nội bộ.
- Một endpoint hoạt động nhưng không có owner hoặc contract.
- Auth policy bị gỡ hoặc scope thay đổi ngoài quy trình.
- API deprecated vẫn có caller sau ngày sunset.
- Route public trỏ tới admin/debug/actuator endpoint.
- Traffic từ caller hoặc environment không thuộc baseline.
- Endpoint thay đổi data classification hoặc response schema.

Finding cần có severity, evidence, first seen, last seen, owner, trạng thái và hạn xử lý. Tránh gửi cảnh báo lặp lại cho cùng một finding không thay đổi; hãy cập nhật record và chỉ phát thông báo khi có thay đổi đáng kể hoặc quá hạn.

## 20. Checklist kiểm kê API theo code, gateway, DNS và traffic

- [ ] Phạm vi repository, cluster, domain, gateway và environment được xác định.
- [ ] Route từ source code, framework, OpenAPI và route động được thu thập.
- [ ] Gateway/ingress/load balancer được export gồm host, method, path, rewrite và upstream.
- [ ] DNS public/private, CNAME, A/AAAA, wildcard và service discovery được đối chiếu.
- [ ] Traffic từ gateway, application, mesh và tracing được thu thập với cửa sổ quan sát rõ.
- [ ] Route template được chuẩn hóa theo host, method, protocol và environment.
- [ ] Mỗi record có source evidence, timestamp, confidence và owner.
- [ ] Shadow, orphan, zombie, legacy và route chưa có contract được phân loại.
- [ ] Security posture gồm exposure, authentication, authorization, data classification và abuse controls.
- [ ] Không coi absence of traffic là bằng chứng chắc chắn API không tồn tại.
- [ ] Không coi DNS record là bằng chứng endpoint cụ thể đang hoạt động.
- [ ] Inventory được cập nhật theo CI/CD, gateway/DNS change và runtime discovery.
- [ ] Discovery active có scope, phê duyệt, giới hạn tải và kế hoạch dừng.
- [ ] Log/telemetry không lưu raw credential, cookie hoặc payload nhạy cảm.
- [ ] Finding có owner, severity, evidence, deadline và trạng thái remediation.

## Kết luận

Kiểm kê API đáng tin cậy phải kết hợp những gì code khai báo, gateway triển khai, DNS định tuyến và traffic thực tế quan sát được. Source code và OpenAPI cho biết thiết kế; gateway và ingress cho biết đường phơi bày; DNS và service discovery cho biết host/target; traffic cho biết endpoint nào đã được sử dụng trong một khoảng thời gian. Chuẩn hóa các nguồn thành inventory có owner, environment, security posture, lifecycle và evidence giúp tìm shadow/zombie API, phát hiện drift và ưu tiên xử lý theo rủi ro. Duy trì reconciliation theo CI/CD và runtime giúp danh mục phản ánh hệ thống đang chạy thay vì chỉ phản ánh tài liệu cũ.

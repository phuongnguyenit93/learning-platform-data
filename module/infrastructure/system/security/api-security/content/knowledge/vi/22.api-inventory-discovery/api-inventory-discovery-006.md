# Gateway route phải khớp service contract

## 1. Vì sao route của API Gateway phải khớp contract?

API Gateway là điểm vào tập trung cho nhiều client và service. Gateway nhận request, chọn route, áp dụng một phần chính sách bảo mật, rồi chuyển request tới upstream. Service contract mô tả API mà service thực sự cung cấp: path, method, request/response schema, authentication, lỗi và hành vi tương thích.

Hai cấu hình này phải khớp nhau. Nếu gateway và service contract lệch nhau, hệ thống có thể tạo ra API không được kiểm soát:

- Gateway công khai một route không có trong contract hoặc service không dự định expose.
- Contract mô tả endpoint cần authentication nhưng gateway route lại cho anonymous truy cập.
- Gateway chỉ kiểm tra một method, trong khi upstream nhận thêm method khác.
- Gateway route phiên bản v1 tới service v2 có schema hoặc authorization khác.
- Contract có endpoint nhưng gateway không route tới được, khiến client dùng một đường dẫn cũ hoặc gọi thẳng service.
- Gateway validate request theo schema cũ nhưng upstream đã thay đổi cách hiểu field.
- Một catch-all route hoặc route có độ ưu tiên cao hơn bắt request trước route cụ thể.
- Route được gỡ khỏi gateway nhưng vẫn tồn tại ở load balancer, ingress hoặc service public khác.

Gateway route đúng cú pháp chưa có nghĩa API được bảo vệ. Cần kiểm tra cả tính đầy đủ của inventory, mapping route-to-operation, authentication/authorization, schema validation, upstream identity và hành vi khi version thay đổi.

Nguyên tắc: **mỗi route được expose phải ánh xạ tới đúng một operation đã được phê duyệt trong contract; mọi operation được công bố phải có trạng thái expose rõ ràng; gateway và upstream phải thực thi cùng ý định bảo mật.**

## 2. Phân biệt service contract, gateway route và API inventory

Ba khái niệm có quan hệ nhưng không thay thế nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Service contract | Service cam kết cung cấp operation nào và dữ liệu ra/vào có hình dạng gì? | OpenAPI mô tả POST /v1/orders |
| Gateway route | Request nào được nhận ở biên và được chuyển tới upstream nào? | Host api.example.com, method POST, path /v1/orders, upstream order-service |
| API inventory | Toàn tổ chức đang có những API, version, host, owner và trạng thái nào? | Public, internal, partner, deprecated, shadow API |

Service contract có thể được mô tả bằng OpenAPI, gRPC/protobuf, AsyncAPI hoặc định dạng khác. Gateway route có thể nằm trong cấu hình gateway, ingress, service mesh, reverse proxy, load balancer hoặc code. Inventory hợp nhất các nguồn này để nhìn thấy API thực tế.

Không nên coi file OpenAPI là inventory hoàn chỉnh: một route có thể được cấu hình thủ công mà không có spec. Ngược lại, spec có thể mô tả endpoint chưa deploy hoặc đã bị gỡ. Cần đối chiếu contract với cấu hình triển khai và quan sát runtime.

## 3. Xác định nguồn chuẩn và ownership

Trước khi đồng bộ route, tổ chức cần xác định ai chịu trách nhiệm cho contract và route:

- Service owner chịu trách nhiệm operation, schema, semantics và version compatibility.
- API platform/gateway owner chịu trách nhiệm route, plugin/policy, upstream và cấu hình biên.
- Security owner xác nhận authentication, authorization, exposure level và yêu cầu bảo vệ.
- Product/domain owner xác nhận client, đối tác và luồng nghiệp vụ còn sử dụng API.
- Operations owner chịu trách nhiệm health, rollout, telemetry và rollback.

Mỗi API nên có metadata tối thiểu:

| Metadata | Mục đích |
|---|---|
| API/service ID | Định danh ổn định, không phụ thuộc tên hiển thị |
| Contract location và version | Xác định spec được phê duyệt |
| Service owner | Người/nhóm chịu trách nhiệm |
| Gateway route ID | Liên kết tới cấu hình route |
| Upstream service identity | Đích nhận request |
| Exposure | Public, partner, internal hoặc private |
| Lifecycle | Draft, active, deprecated, sunset hoặc retired |
| Data classification | Loại dữ liệu và mức nhạy cảm |
| Authentication/authorization policy | Cách xác minh principal và quyền |
| Rate/size/timeout policy | Giới hạn tài nguyên |
| Last verified / source | Thời điểm và nguồn đối chiếu |

Nguồn chuẩn phải được xác định theo từng loại thông tin. Contract là nguồn cho schema/operation; gateway configuration là nguồn cho route đang được triển khai; identity/policy registry là nguồn cho security requirement; runtime discovery cho biết điều gì thực sự được gọi. Không có một file duy nhất trả lời chính xác tất cả.

## 4. Mô hình route-to-contract mapping

Một gateway route thường gồm:

- Listener/host/domain và protocol.
- HTTP method hoặc gRPC service/method.
- Path template hoặc route matcher.
- Điều kiện header, query hoặc content type nếu có.
- Authentication plugin và authorization policy.
- Request validation / response transformation.
- Rate limit, quota, timeout và body size.
- Upstream cluster/service và service identity.
- Retry, circuit breaker, observability và lifecycle.

Một operation trong contract cũng có method, path, parameter, request body, response, security requirement, tags và version. Mapping phải xác định được route nào thực hiện operation nào.

Ví dụ:

~~~text
Contract operation:
  operationId: createOrder
  method: POST
  path: /v1/orders
  security: OAuth2 scope orders:write

Gateway route:
  routeId: public-orders-create-v1
  host: api.example.com
  method: POST
  path: /v1/orders
  auth: OAuth2
  requiredScope: orders:write
  upstream: order-service-v1
~~~

Đây là mapping khái niệm. Tên trường và cú pháp route khác nhau theo gateway sản phẩm; cần dùng cấu hình thực tế của nền tảng đang vận hành.

Một route nên có ID ổn định để telemetry, audit, policy và deployment tham chiếu. Không chỉ dựa vào URL làm định danh vì cùng path có thể tồn tại trên nhiều host, version hoặc exposure level.

## 5. Các điều kiện để route khớp contract

Một mapping được coi là khớp khi các yếu tố sau nhất quán:

| Yếu tố | Điều cần đối chiếu |
|---|---|
| Host/base path | Domain public và prefix có đúng exposure/version không |
| Method | Gateway chỉ cho phép method contract công bố |
| Path | Template, parameter và quy tắc matching giống contract |
| Query/header/path parameter | Tên, kiểu, required, multiplicity và encoding |
| Request body | Content-Type, schema, required field, size và validation |
| Response | Status code, content type, schema và header được công bố |
| Security | Authentication scheme, scope/role và operation-level override |
| Upstream | Đúng service, cluster, version và service identity |
| Transformation | Rewrite, strip prefix, header mapping không làm thay đổi semantics |
| Lifecycle | Deprecated/sunset/retired được phản ánh ở cả gateway và contract |
| Operational policy | Rate, quota, timeout, size và retry phù hợp với operation |

Không chỉ so sánh chuỗi path. Ví dụ /users/{id} và /users/me có thể xung đột nếu route parameter tổng quát được xét trước route tĩnh. Route order và specificity phải được kiểm tra theo semantics của gateway.

## 6. Path matching, method và route precedence

### 6.1 Template và parameter

Contract có thể mô tả /orders/{orderId}, còn gateway sử dụng wildcard hoặc regular expression. Cần xác minh hai cách biểu diễn tương đương:

- Segment nào là parameter và segment nào là literal.
- Có cho phép parameter rỗng hay không.
- Có chấp nhận dấu slash encoded trong parameter không.
- Có cho phép trailing slash hoặc path case variation không.
- Có giới hạn format/length cho ID không.
- Route có vô tình match path sâu hơn dự kiến không.

Không dùng wildcard rộng như /api/* nếu service chỉ công bố một tập operation cụ thể. Wildcard có thể khiến endpoint mới ở upstream tự động được expose mà chưa qua review.

### 6.2 Route precedence và collision

Ví dụ hai route:

~~~text
/users/me
/users/{userId}
~~~

Nếu route parameter tổng quát bắt trước, request /users/me có thể bị xử lý như userId=me. Hậu quả phụ thuộc implementation: gọi nhầm object, bypass policy hoặc trả lỗi khó hiểu.

Kiểm tra:

- Route tĩnh và route động có collision không.
- Wildcard/catch-all có bắt route cụ thể không.
- Regex có backtracking hoặc match ngoài phạm vi không.
- Route cùng method/path trên nhiều host có policy khác nhau không.
- Gateway có normalize path khác router upstream không.
- Route priority có ổn định sau khi thêm route mới không.

Ưu tiên route rõ ràng, ít wildcard và có test precedence. Nếu hai route có thể match cùng request, deployment nên fail hoặc yêu cầu cấu hình priority tường minh.

### 6.3 HTTP method

Contract công bố method nào thì gateway chỉ nên expose method đó. Không cho phép method wildcard hoặc tự động chuyển mọi method tới upstream nếu không có nhu cầu.

Đặc biệt xem xét:

- TRACE và CONNECT thường không cần cho API business.
- HEAD và OPTIONS có thể được framework/gateway xử lý riêng; cần định nghĩa rõ.
- CORS preflight OPTIONS không đồng nghĩa cho phép operation nghiệp vụ.
- PUT/PATCH/DELETE phải có authorization và CSRF protection phù hợp với kiểu client.
- Method override qua header hoặc query cần bị tắt nếu không có yêu cầu.

Kiểm tra cả behavior của upstream khi nhận method không được contract công bố. Gateway từ chối 405/404 phù hợp; không để request đi tiếp chỉ vì service framework có handler mặc định.

## 7. Canonical path và parser consistency

Gateway, WAF, reverse proxy và service framework có thể parse path khác nhau. Một route được bảo vệ trên raw path nhưng upstream normalize sau đó có thể tạo parser differential.

Các trường hợp cần test:

- Percent-encoded slash hoặc backslash.
- Dot segment như . và ...
- Double encoding.
- Unicode hoặc ký tự không hợp lệ.
- Path có nhiều slash liên tiếp.
- Trailing slash và case sensitivity.
- Query parameter trùng lặp.

Chọn một quy tắc canonicalization rõ ràng và bảo đảm gateway cùng upstream dùng kết quả tương thích. Từ chối representation mơ hồ nếu không cần hỗ trợ. Không để gateway authorize route A rồi upstream diễn giải thành route B.

Nếu gateway rewrite prefix, phải ghi rõ phép biến đổi:

~~~text
External path: /api/orders/v1/{id}
Rewrite:       /v1/orders/{id}
Upstream:      order-service
~~~

Test path trước và sau rewrite, bao gồm path parameter, query string và header. Không tự decode hoặc normalize lần nữa ở một plugin khác.

## 8. Security policy phải khớp contract

Contract và gateway cần mô tả nhất quán cách xác thực và phân quyền. OpenAPI có thể định nghĩa security scheme ở cấp root và override ở cấp operation. Cần hiểu đúng semantics:

- Security ở root áp dụng mặc định cho operations.
- Operation có security riêng có thể thay thế yêu cầu cấp root.
- security: [] ở operation có thể chủ ý đánh dấu operation không yêu cầu authentication.
- Một operation công khai phải được phê duyệt rõ ràng; không được trở thành public chỉ vì cấu hình bị bỏ sót.

Ví dụ contract:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.4.0
paths:
  /v1/orders:
    post:
      operationId: createOrder
      security:
        - oauth2:
            - orders:write
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Created
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.com/oauth/token
          scopes:
            orders:write: Create orders
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, items]
      properties:
        customerId:
          type: string
        items:
          type: array
          minItems: 1
~~~

Gateway route cho operation này phải xác minh token đúng issuer, audience và chữ ký; kiểm tra scope orders:write; chuyển principal context đáng tin cậy tới upstream theo cơ chế đã thiết kế. Chỉ có plugin xác thực token không chứng minh user được phép tạo order cho customer cụ thể. Object-level và business authorization vẫn phải được service thực hiện.

Không tự động suy ra policy từ tên operationId hoặc tag. Security metadata cần được parse từ contract và so sánh với policy registry được phê duyệt.

## 9. Request và response schema validation

Gateway có thể validate request trước khi chuyển upstream, nhưng validation ở gateway phải tương thích với parser và schema của service:

- Required/optional field.
- Kiểu dữ liệu, format, enum và giới hạn số.
- Nullability, default và unknown field.
- Nested object, array size và maximum depth.
- Content-Type và content encoding.
- Query/path/header parameter.
- Request body size và decompression limit.

Nếu gateway dùng schema cũ, nó có thể từ chối request hợp lệ mới hoặc cho qua field mà upstream xử lý khác. Nếu gateway và service dùng hai thư viện parser khác nhau, duplicate JSON key hoặc number coercion có thể tạo khác biệt.

Response validation cũng hữu ích để phát hiện drift hoặc dữ liệu vượt contract. Tuy nhiên, không nên mặc định validate toàn bộ response trên mọi đường production nếu gây latency hoặc lộ chi tiết lỗi; có thể dùng ở canary, sampling hoặc contract test. Dù có gateway validation, service vẫn phải tự validate dữ liệu vì có thể được gọi nội bộ hoặc qua đường khác.

Không xem schema validation là authorization. Một request đúng schema vẫn có thể truy cập object của tenant khác hoặc sửa field nhạy cảm.

## 10. Upstream mapping và service identity

Route phải trỏ đúng upstream service và version đã được phê duyệt. Một mapping sai có thể đưa request tới service có semantics hoặc security policy khác.

Kiểm tra:

- Upstream DNS/service discovery chỉ trỏ tới service đã đăng ký.
- Service identity hoặc mTLS xác thực gateway khi gọi upstream.
- Upstream xác thực gateway/client theo trust model, không tin mọi header do mạng nội bộ gửi.
- Header principal/tenant được gateway xóa giá trị client gửi rồi tự tạo từ token đã xác minh.
- Không cho client điều khiển upstream host, cluster, port hoặc service name.
- Timeout, retry và connection pool phù hợp với service.
- Health check không expose thông tin nhạy cảm.
- Route không trỏ tới debug/admin endpoint ngoài ý muốn.

Không dựa vào việc upstream nằm trong private network để bỏ authorization. Nếu service có thể được gọi từ worker, service mesh hoặc đường nội bộ khác, nó vẫn cần xác minh caller và quyền nghiệp vụ theo thiết kế.

## 11. Header transformation và trust boundary

Gateway thường thêm, xóa hoặc rewrite header. Các header ảnh hưởng bảo mật cần quy định rõ:

| Header/nhóm | Quy tắc |
|---|---|
| Authorization | Chỉ forward theo contract; không log token; không tự thay bằng credential khác nếu chưa thiết kế |
| X-User-ID / X-Principal | Xóa giá trị từ client; chỉ tạo từ principal đã xác minh nếu upstream tin header này |
| X-Tenant-ID | Lấy từ tenant context đã xác minh, không dùng raw header |
| Forwarded / X-Forwarded-* | Chỉ tin từ proxy hop được cấu hình; xóa hoặc ghi đè giá trị không tin cậy |
| Host / :authority | Đặt theo upstream/public host contract; không để client chọn upstream |
| Trace/correlation ID | Validate format và giới hạn length; không chứa secret |
| Content-Type | Kiểm tra với operation; không rewrite thành kiểu khác ngoài contract |

Nếu gateway thêm header danh tính, upstream phải chỉ chấp nhận header đó từ gateway đã xác thực. Không để một client gọi thẳng upstream và tự gửi X-User-ID để giả mạo principal.

Với mTLS, xác định rõ certificate identity nào đại diện gateway, cách xoay cert và cách upstream phân biệt gateway với service khác. TLS chỉ bảo vệ kênh; nó không thay thế kiểm tra quyền trên request.

## 12. Route policy cho rate, size, timeout và retry

Inventory và contract nên ghi nhận policy vận hành theo operation hoặc nhóm operation:

- Rate limit và quota theo tenant/client/principal.
- Concurrency và queue limit cho operation nặng.
- Request/response size.
- Timeout tổng và timeout upstream.
- Retry budget, idempotency và circuit breaker.
- Cache policy và dữ liệu có thể cache.
- Logging/redaction và retention.

Không gắn cùng một ngưỡng cho mọi route. API đọc metadata nhỏ và endpoint export lớn có chi phí khác nhau. Gateway policy cần phản ánh service contract và ngân sách tài nguyên của upstream.

Retry chỉ nên bật cho operation an toàn về mặt idempotency hoặc có idempotency key. Không tự retry POST tạo thanh toán/đơn hàng chỉ vì upstream timeout; trạng thái có thể đã commit. Contract cần mô tả idempotency semantics để gateway/client biết cách xử lý.

## 13. Versioning và backward compatibility

Gateway route thường tồn tại lâu hơn một lần deploy service. Khi contract đổi, phải xác định thay đổi có tương thích không:

| Thay đổi contract | Tác động thường gặp | Việc cần làm |
|---|---|---|
| Thêm optional field vào response | Client cũ có thể bỏ qua nhưng một số client strict parser có thể lỗi | Contract test và kiểm tra client |
| Thêm required request field | Breaking change với client cũ | Version mới hoặc migration có thời gian |
| Xóa field/enum value | Client có thể phụ thuộc | Deprecation và migration |
| Đổi kiểu hoặc semantics field | Có thể làm sai dữ liệu/quyền | Version mới, mapping rõ |
| Đổi auth scope | Thay đổi quyền truy cập | Security review và thông báo client |
| Đổi upstream service | Có thể đổi behavior/availability | Canary và contract test |
| Thêm operation mới | Có thể vô tình expose | Review exposure và gateway route riêng |

Version trong URL như /v1 hoặc media type là lựa chọn thiết kế; điều quan trọng là route, contract và upstream cùng chỉ tới một version semantics. Không route mọi /v1/* tới service latest chỉ vì tiện.

Khi deprecated:

1. Đánh dấu trong contract và inventory.
2. Công bố thời hạn sunset và migration path.
3. Theo dõi client/tenant còn gọi.
4. Có thể thêm header deprecation/sunset theo policy.
5. Gỡ route sau khi owner xác nhận không còn consumer hợp lệ.
6. Xóa service endpoint hoặc chặn direct access để không còn đường bypass gateway.

## 14. Discovery và phát hiện route ngoài inventory

Không thể chỉ dựa vào file contract để biết toàn bộ API. Dùng nhiều nguồn để phát hiện và đối chiếu:

| Nguồn | Phát hiện được | Hạn chế |
|---|---|---|
| Gateway configuration | Route được cấu hình | Có thể bỏ sót ingress/load balancer khác |
| OpenAPI/protobuf/AsyncAPI registry | Operation được công bố | Spec có thể stale hoặc chưa deploy |
| Service code/annotations | Endpoint trong source | Reflection/runtime plugin có thể tạo route động |
| Ingress/service mesh | Đường vào và service routing | Không phải lúc nào cũng hiểu operation schema |
| DNS/cloud load balancer | Host và listener public | Không mô tả method/schema |
| Access log/tracing | Route thực sự được gọi | Chỉ thấy traffic đã xảy ra trong thời gian quan sát |
| Client/mobile SDK | API client đang được tích hợp | Có thể chứa code cũ không còn chạy |
| External scan | Surface public quan sát được | Có thể bỏ sót auth-gated/low-traffic route |
| Internal scan | Surface nội bộ | Cần scope và quyền kiểm thử phù hợp |

Đối chiếu theo định danh route, host, method, path, upstream và version. Phân loại chênh lệch:

- Contract có, gateway không có: operation chưa expose, deploy thiếu hoặc contract stale.
- Gateway có, contract không có: undocumented/shadow route cần điều tra.
- Runtime có traffic nhưng inventory không có owner: cần gán ownership.
- Service có endpoint nhưng gateway không route: có thể là internal-only hoặc direct-access path cần xác minh.
- Gateway route không có traffic: có thể obsolete, nhưng cần xem chu kỳ nghiệp vụ trước khi gỡ.

Không tự động xóa route chỉ vì không thấy traffic trong một khoảng ngắn. Job theo mùa, tenant ít dùng hoặc endpoint khẩn cấp có thể không có traffic thường xuyên.

## 15. Phát hiện shadow API và đường bypass gateway

Shadow API là endpoint tồn tại nhưng không được quản lý trong inventory/contract hoặc không được owner biết tới. Zombie API là endpoint cũ vẫn chạy dù đã được cho là ngừng sử dụng.

Các nguồn thường tạo ra chúng:

- Service được expose qua LoadBalancer/NodePort ngoài gateway.
- Ingress cũ hoặc route còn sót trong cluster.
- Debug/admin endpoint bind vào interface public.
- Phiên bản service cũ còn chạy sau rollout.
- Hostname phụ hoặc domain thử nghiệm.
- API được thêm trực tiếp trong service nhưng không cập nhật contract.
- Internal endpoint bị expose qua service mesh gateway.

Biện pháp:

- Duy trì allowlist listener/public host ở cloud và network edge.
- Chặn truy cập trực tiếp tới upstream từ Internet; chỉ gateway/authorized caller được kết nối.
- Quét ingress, load balancer, DNS và service type định kỳ.
- So sánh route discovery với contract registry.
- Xác minh route có authentication, authorization và logging.
- Gắn owner và lifecycle cho mọi route.
- Gỡ endpoint cũ sau khi kiểm tra consumer và có kế hoạch rollback.

Không chỉ dùng firewall để tin tưởng mọi traffic từ private network. Một workload bị xâm nhập có thể gọi trực tiếp service khác; upstream vẫn cần xác thực service identity và authorization.

## 16. Kiểm tra contract và route trong CI/CD

Pipeline nên kiểm tra contract và gateway config như hai artifact liên quan:

~~~text
Pull request
    |
    v
Parse service contract
    |
    v
Parse gateway route config
    |
    v
Normalize operation/route model
    |
    v
Compare method + path + host + version
    |
    v
Compare auth + scopes + schema + upstream
    |
    v
Breaking-change and exposure review
    |
    v
Contract tests + route tests
    |
    v
Deploy canary -> observe -> promote
~~~

Các gate nên có:

1. Contract parse/schema validation thành công.
2. Gateway config lint và kiểm tra route collision/precedence.
3. Mỗi route public ánh xạ tới operation đã phê duyệt.
4. Mỗi operation có exposure status rõ: public, partner, internal hoặc not exposed.
5. Method/path/parameter/content type khớp.
6. Authentication/scope không yếu hơn contract/policy registry.
7. Upstream service/version nằm trong allowlist.
8. Request validation, size, rate, timeout và retry policy có cấu hình.
9. Breaking change được phát hiện và có approval/migration.
10. Integration test xác nhận route thực tế chuyển đúng upstream và từ chối request không hợp lệ.

Không chỉ so sánh file bằng text diff. Hai cấu hình khác thứ tự key có thể cùng semantics; ngược lại, một dòng wildcard hoặc thay đổi route priority nhỏ có thể làm exposure thay đổi lớn. Hãy parse thành mô hình route chuẩn rồi so sánh semantics.

## 17. Ví dụ kiểm tra mapping bằng mô hình chuẩn hóa

Một mô hình trung gian có thể gồm:

~~~json
{
  "routeId": "public-orders-create-v1",
  "host": "api.example.com",
  "method": "POST",
  "pathTemplate": "/v1/orders",
  "operationId": "createOrder",
  "contractVersion": "1.4.0",
  "upstreamService": "order-service",
  "upstreamVersion": "v1",
  "authentication": "oauth2",
  "requiredScopes": ["orders:write"],
  "exposure": "public"
}
~~~

Đây là representation minh họa để so sánh, không phải định dạng bắt buộc của gateway.

Một số invariant có thể kiểm tra tự động:

~~~text
assert route.method is declared by operation
assert route.pathTemplate matches operation.path
assert route.upstreamService is approved for operation
assert route.exposure is approved by API inventory
assert route.authentication is not weaker than approved policy
assert route.requiredScopes cover operation requirements
assert route.requestSchemaVersion matches contract
assert route has bounded size, timeout and rate policy
~~~

Nếu operation có policy đặc biệt, không suy ra chỉ từ policy chung ở root. Lấy security requirement đã resolve theo đúng semantics của contract rồi so với route policy.

## 18. Kiểm thử gateway route end-to-end

Kiểm thử cần đi qua listener và gateway thật trong môi trường test/staging:

| Test | Request/tình huống | Kết quả mong đợi |
|---|---|---|
| Exact route | Đúng host, method, path | Tới đúng upstream/version |
| Unknown path | Path không có trong contract | 404 hoặc reject tại gateway |
| Wrong method | Method không công bố | 405/reject; không forward ngoài ý muốn |
| Route collision | Path tĩnh và parameter cùng match | Route precedence đúng |
| Encoded path | Slash/dot segment/duplicate slash | Gateway và upstream hiểu nhất quán |
| Missing token | Gọi operation yêu cầu auth | Bị từ chối trước business handler |
| Wrong audience/issuer | Token không dành cho API | Bị từ chối |
| Missing scope | Token hợp lệ nhưng thiếu scope | Bị từ chối |
| Object authorization | Có scope nhưng truy cập object tenant khác | Service từ chối |
| Schema invalid | Thiếu field/kiểu sai/field không cho phép | Bị từ chối theo contract |
| Oversized body | Vượt request size | Từ chối trước khi tiêu thụ tài nguyên lớn |
| Wrong upstream | Config trỏ service/version khác | CI hoặc deployment gate fail |
| Direct upstream | Gọi upstream bỏ qua gateway | Network/service identity policy chặn |
| Deprecated route | Gọi operation đã sunset | Behavior theo lifecycle policy |
| Header spoofing | Client tự gửi X-User-ID/X-Tenant-ID | Gateway xóa và dựng lại từ context tin cậy |
| CORS preflight | OPTIONS không đúng policy | Không vô tình mở operation nghiệp vụ |
| Retry behavior | POST không idempotent bị timeout | Không tạo side effect trùng |
| Response drift | Upstream trả field/status ngoài contract | Test/monitor phát hiện |

Test cần kiểm tra cả upstream thực nhận request gì, không chỉ status code từ gateway. Dùng request ID để đối chiếu route, policy decision và service log.

## 19. Runtime monitoring và drift detection

Sau deployment, contract test không đủ vì cấu hình có thể bị thay đổi thủ công, service discovery có thể đổi target hoặc một listener khác có thể xuất hiện.

Theo dõi:

- Route ID, host, method, path template và upstream version.
- Request count, 404/405 và route không khớp inventory.
- Authentication/authorization deny rate theo operation.
- Request schema validation failure và response contract drift.
- Traffic tới deprecated route.
- Route không có owner hoặc chưa được xác minh gần đây.
- Upstream target thay đổi ngoài deployment đã duyệt.
- Direct-to-service traffic bỏ qua gateway.
- Rate/size/timeout/retry policy drift.
- Public listener hoặc DNS record mới chưa có inventory entry.

Metric nên dùng route ID/operation ID đã chuẩn hóa, tránh raw URL chứa ID người dùng làm label. Log không ghi token, cookie, body nhạy cảm hoặc query chứa secret. Trace nên gắn service/route/version và principal/tenant identifier ở dạng được phép.

Đặt cảnh báo khi có route public mới không có contract, route auth policy yếu đi, upstream đổi ngoài kế hoạch, traffic tăng đột biến trên endpoint deprecated hoặc service nhận request không qua gateway.

## 20. Rollout và thay đổi route an toàn

Thay đổi route có thể ảnh hưởng nhiều client cùng lúc. Quy trình triển khai nên có:

1. Review contract diff và route diff cùng nhau.
2. Xác định client, tenant và đối tác chịu ảnh hưởng.
3. Chạy contract test và end-to-end route test.
4. Deploy upstream tương thích trước hoặc dùng version mới song song.
5. Deploy gateway route canary cho nhóm traffic nhỏ.
6. Theo dõi 4xx/5xx, latency, auth deny, schema failure và upstream distribution.
7. Tăng traffic theo từng bước khi đạt tiêu chí.
8. Rollback route và upstream mapping nếu có drift hoặc lỗi.
9. Cập nhật inventory/lifecycle và thông báo consumer theo quy trình.

Không xóa route cũ trước khi xác minh consumer đã chuyển. Không giữ route cũ vô thời hạn chỉ vì không biết ai dùng; gán owner, đặt sunset date và theo dõi traffic để quyết định.

## 21. Các lỗi thiết kế thường gặp

1. **Gateway route không có contract:** endpoint không được review vẫn public.
2. **Contract có nhưng route không được inventory:** client tìm đường gọi thẳng service hoặc dùng endpoint khác.
3. **Wildcard quá rộng:** endpoint mới tự động bị expose.
4. **Method không giới hạn:** upstream nhận method ngoài contract.
5. **Route precedence sai:** route tổng quát bắt request trước route cụ thể.
6. **Path normalization khác nhau:** gateway kiểm tra một route, upstream xử lý route khác.
7. **Security inheritance bị hiểu sai:** operation public ngoài ý muốn do override security.
8. **Chỉ xác thực ở gateway:** service bị gọi trực tiếp hoặc authorization object bị bỏ qua.
9. **Tin identity header từ client:** principal/tenant bị giả mạo.
10. **Upstream version không cố định:** route v1 bất ngờ trỏ service latest.
11. **Gateway schema cũ:** request/response drift giữa gateway và service.
12. **Retry POST không idempotent:** side effect bị lặp.
13. **Chỉ dựa vào spec:** bỏ sót shadow route, ingress hoặc load balancer khác.
14. **Gỡ route dựa vào ít traffic:** làm hỏng client theo mùa hoặc đối tác ít gọi.
15. **Không kiểm tra direct upstream access:** gateway policy có thể bị bypass.

## 22. Quy trình rà soát gateway route với service contract

Với mỗi service/API:

1. Thu thập contract được phê duyệt và xác định version/owner.
2. Thu thập gateway route, ingress, load balancer và service mesh mapping.
3. Thu thập runtime evidence để phát hiện route đang hoạt động và direct access.
4. Chuẩn hóa operation và route thành mô hình so sánh.
5. Đối chiếu host, method, path, parameter, schema, response và version.
6. Đối chiếu authentication, scope, tenant context, upstream identity và exposure.
7. Kiểm tra wildcard, collision, precedence, rewrite và canonical path.
8. Kiểm tra rate, quota, size, timeout, retry và idempotency.
9. Phân loại mismatch: undocumented, inaccessible, wrong target, weaker policy, stale contract hoặc obsolete route.
10. Gán owner, severity, remediation và thời hạn cho từng mismatch.
11. Chạy contract/route/security test trong CI và staging.
12. Triển khai canary, giám sát runtime và cập nhật inventory/lifecycle.

## 23. Checklist rà soát

- [ ] Có contract versioned và owner cho mỗi API operation được expose.
- [ ] Mọi gateway route có route ID ổn định và mapping tới operation.
- [ ] Mọi operation có exposure state rõ ràng: public, partner, internal hoặc not exposed.
- [ ] Host, method, path, parameter và content type khớp contract.
- [ ] Route precedence, wildcard, rewrite và canonical path đã được kiểm tra.
- [ ] Security scheme, issuer, audience, scope và operation-level override khớp policy.
- [ ] Object/tenant authorization vẫn được service thực hiện.
- [ ] Upstream service/version được allowlist và xác thực bằng service identity.
- [ ] Identity/tenant forwarding header từ client bị xóa và dựng lại từ nguồn tin cậy.
- [ ] Request/response schema và size limit không drift giữa gateway và service.
- [ ] Rate, quota, timeout, concurrency, retry và idempotency phù hợp operation.
- [ ] Contract diff và route diff được kiểm tra trong CI.
- [ ] Có end-to-end test cho wrong method/path, missing scope, schema và direct upstream.
- [ ] Discovery đối chiếu gateway, ingress, DNS, service code, logs và external surface.
- [ ] Shadow/zombie API có owner, lifecycle và kế hoạch xử lý.
- [ ] Runtime monitoring phát hiện route mới, policy drift và traffic bypass gateway.
- [ ] Rollout có canary, rollback và migration cho consumer.

Gateway route phải khớp service contract để inventory phản ánh đúng API được expose và policy bảo vệ đúng operation. Việc đối chiếu contract, gateway configuration và runtime discovery giúp phát hiện route thừa, route thiếu, sai method/path, sai upstream, security drift và shadow API. Khi mapping có owner, được kiểm tra tự động trong CI và giám sát sau triển khai, gateway trở thành một lớp thực thi contract có thể kiểm chứng thay vì chỉ là bộ chuyển tiếp request.

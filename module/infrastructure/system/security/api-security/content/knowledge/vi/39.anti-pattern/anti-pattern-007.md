# Không kiểm kê shadow API và version cũ

Trong module `SECURITY_API_SECURITY`, bảo mật API phải được thiết kế theo từng endpoint, đối tượng dữ liệu và luồng nghiệp vụ. Một hệ thống chỉ kiểm soát những route đã được ghi trong tài liệu vẫn có thể để hở các đường truy cập khác: endpoint thử nghiệm còn hoạt động, route nội bộ vô tình public, API version cũ, hostname legacy, GraphQL field chưa được quản lý, webhook callback hoặc service endpoint được tạo từ một lần triển khai trước.

Các API không nằm trong catalog chính thức thường được gọi là **shadow API**. Một số API đã từng được công bố nhưng không còn được owner theo dõi hoặc không còn được hỗ trợ được gọi là **zombie API**. Version cũ có thể vẫn cần phục vụ consumer chưa migrate, nhưng nếu không có inventory, owner và security policy rõ ràng, nó dễ trở thành đường vòng cho authentication, authorization, validation, tenant isolation hoặc rate limit mới.

Anti-pattern là chỉ kiểm thử và bảo vệ các endpoint được nhóm phát triển nhớ tới, trong khi không có quy trình phát hiện và quản lý toàn bộ bề mặt API đang thực sự nhận traffic. Cách khắc phục là duy trì inventory có nguồn evidence, gắn owner và lifecycle cho từng operation, kiểm tra security parity giữa các version, và xác minh exposure tại runtime.

## 1. Shadow API, zombie API và version cũ là gì?

Các khái niệm liên quan nhưng không hoàn toàn giống nhau:

| Khái niệm | Mô tả | Ví dụ |
|---|---|---|
| Shadow API | API đang tồn tại hoặc nhận request nhưng không nằm trong inventory/catalog được quản lý | Route `/internal/debug-users` xuất hiện trong gateway nhưng không có owner |
| Zombie API | API cũ vẫn có thể truy cập dù đã bị xem là retired hoặc không còn được duy trì | `/v1/export` vẫn hoạt động sau khi thông báo sunset |
| Legacy version | Version cũ còn được giữ để tương thích với consumer | `/v1/orders` vẫn phục vụ mobile app chưa nâng cấp |
| Undocumented endpoint | Endpoint chưa có contract/tài liệu đầy đủ | Controller mới được merge nhưng OpenAPI không cập nhật |
| Orphaned route | Route còn trong gateway/Ingress/DNS nhưng service hoặc owner đã thay đổi | Hostname cũ trỏ tới service được tái sử dụng |
| Internal API exposed | API dành cho mạng/service nội bộ nhưng có thể truy cập từ public hoặc trust zone rộng hơn | Management endpoint được gắn public load balancer |

Một endpoint có thể thuộc nhiều nhóm. Ví dụ `/v1/admin/export` vừa là legacy version, vừa là zombie API nếu đã sunset nhưng chưa bị gỡ, và vừa là shadow API nếu không có team nào chịu trách nhiệm.

### 1.1. Vì sao chúng xuất hiện?

- Developer thêm route debug hoặc endpoint tạm để kiểm tra production issue rồi quên xóa.
- Một service cũ được thay thế nhưng gateway route, DNS record hoặc load balancer vẫn còn.
- Mobile app hoặc partner integration giữ version cũ lâu hơn dự kiến.
- Gateway rewrite tạo alias mới nhưng catalog chỉ ghi route backend.
- Controller được tạo nhưng OpenAPI/spec không cập nhật.
- GraphQL schema thêm field/mutation mà inventory chỉ theo dõi URL `/graphql`.
- Một webhook, callback, RPC method hoặc consumer endpoint không được tính là API trong quy trình quản lý.
- Team đổi tên, giải thể hoặc chuyển ownership nhưng route vẫn nhận traffic.
- Environment staging/test bị expose ra Internet hoặc dùng chung credential với production.
- Một bản triển khai rollback đưa endpoint cũ trở lại mà không cập nhật catalog.

### 1.2. Không phải mọi API cũ đều là shadow API

API version cũ có thể là một phần hợp lệ của chiến lược backward compatibility. Vấn đề nằm ở việc không biết nó đang tồn tại, ai sử dụng, policy nào áp dụng và khi nào sẽ ngừng hỗ trợ. Nếu version cũ được inventory, owner, kiểm thử và bảo vệ đầy đủ, nó có thể tiếp tục hoạt động trong thời hạn được quản lý.

Ngược lại, một endpoint mới có thể trở thành shadow API ngay ngày đầu nếu được triển khai mà không qua catalog, owner và security review. Tuổi của route không quyết định nó có được quản lý hay không.

## 2. Vì sao không kiểm kê API là rủi ro bảo mật?

Security control thường được áp dụng dựa trên catalog, gateway route, OpenAPI và các policy đã biết. Khi có endpoint nằm ngoài những nguồn này, đội bảo mật không thể chứng minh các kiểm soát đã bao phủ toàn bộ bề mặt.

### 2.1. Authentication và authorization không đồng nhất

Một route cũ có thể không nằm trong security matcher hoặc có một filter chain riêng. Kẻ tấn công tìm được route đó có thể gọi trực tiếp mà không qua authentication hiện hành.

Ngay cả khi endpoint yêu cầu đăng nhập, authorization có thể yếu hơn:

- Chỉ kiểm tra principal đã authenticated, không kiểm tra function permission.
- Truy vấn object theo ID nhưng không kiểm tra owner hoặc tenant.
- Tin `tenantId`, `userId` hoặc role từ request body.
- Serialize entity và trả field nội bộ đã bị ẩn trong version mới.
- Cho phép operation admin qua controller legacy.

### 2.2. Security fix chỉ được áp dụng cho version mới

Ví dụ V2 đã thêm tenant predicate và giới hạn bulk request, nhưng V1 vẫn dùng repository cũ. Client hợp lệ hoặc attacker có thể chọn V1 để bỏ qua control mới. Nếu version negotiation có fallback, caller thậm chí có thể vô tình được xử lý bằng contract yếu hơn.

### 2.3. Endpoint nội bộ có thể bị expose ngoài dự kiến

Route dành cho operator, debug hoặc service-to-service thường giả định rằng chỉ mạng nội bộ mới truy cập được. Nhưng DNS, load balancer, Ingress, gateway rewrite, firewall hoặc service mesh có thể thay đổi theo thời gian. Nếu route được public mà không có authentication và authorization riêng, network placement trở thành ranh giới bảo mật duy nhất.

### 2.4. Data exposure khó phát hiện

Shadow endpoint có thể trả:

- Field PII hoặc internal note không còn xuất hiện ở API mới.
- Danh sách user, tenant, role hoặc resource mà caller không được phép xem.
- Debug metadata, feature flag, configuration hoặc trạng thái hệ thống.
- Export file, signed URL hoặc object storage reference.
- Error detail, stack trace, database metadata hoặc internal hostname.

Vì endpoint không nằm trong inventory, data classification và log monitoring có thể không bao phủ nó.

### 2.5. Abuse và chi phí không có quota

Endpoint cũ có thể thiếu body limit, pagination cap, rate limit, concurrency control hoặc cost budget. Một request bulk, export, search sâu hay preview URL có thể tiêu thụ tài nguyên lớn hoặc gọi provider bên ngoài mà không bị theo dõi.

### 2.6. Không thể chứng minh đã sunset

Thông báo deprecation không làm route biến mất. Nếu không kiểm tra gateway, application, DNS và traffic sau ngày sunset, API có thể vẫn hoạt động nhiều tháng hoặc nhiều năm sau khi team nghĩ rằng đã tắt.

## 3. Những đường vào thường bị bỏ sót

Inventory không thể chỉ dựa vào danh sách `@RestController` hoặc file OpenAPI. API surface bao gồm nhiều giao thức và lớp triển khai.

### 3.1. HTTP REST và route alias

Kiểm tra:

- Các path version như `/v1`, `/v2`, `/legacy`, `/internal`.
- Header-based hoặc media-type versioning.
- Hostname/subdomain và route rewrite ở gateway.
- HTTP method khác nhau trên cùng path.
- Trailing slash, case handling và path normalization.
- Route debug, actuator, admin, health, metrics và management port.
- Alias được tạo bởi reverse proxy hoặc compatibility layer.

Một route backend có thể được expose dưới nhiều public path. Ngược lại, một public path có thể rewrite tới handler khác nhau theo header hoặc host.

### 3.2. GraphQL

GraphQL thường có một endpoint HTTP duy nhất, nhưng schema có thể chứa nhiều query, mutation, subscription và field resolver. Chỉ inventory `/graphql` không cho biết operation nào được expose.

Quản lý schema field/mutation, resolver authorization, introspection policy, persisted query và complexity/depth limit. Kiểm tra field legacy còn được gọi dù client mới đã ngừng sử dụng. Một field lồng sâu có thể truy cập dữ liệu khác tenant nếu resolver không áp dụng object policy.

### 3.3. gRPC, RPC và service-to-service API

Kiểm kê service/package/method, listener/port, reflection, mTLS identity, authorization policy và network exposure. Một gRPC method nội bộ không nên được coi là an toàn chỉ vì không có URL REST public.

### 3.4. Webhook, callback và URL đăng ký

Webhook receiver, callback URL, endpoint xác minh integration, OAuth redirect/callback và endpoint nhận event của partner đều là bề mặt API. Kiểm tra signature verification, replay protection, tenant mapping, rate limit và ownership của endpoint.

### 3.5. Async và message-driven interfaces

API có thể được kích hoạt thông qua queue/topic, event subscription, job submission hoặc worker command. Inventory cần ghi producer/consumer, message schema, broker ACL, consumer authorization, retry/DLQ và side effect. Không dừng ở HTTP endpoint tạo message.

### 3.6. File, export và object storage

Signed URL, pre-signed upload/download, report export, import job và direct object storage endpoint có thể tồn tại ngoài gateway. Quản lý issuer, object scope, expiry, method, content type/size, tenant isolation và lifecycle của URL.

### 3.7. Môi trường ngoài production

Staging, QA, demo, preview deployment, sandbox và development host có thể chứa dữ liệu hoặc credential nhạy cảm. Chúng vẫn cần inventory, owner, authentication, network exposure và thời hạn tồn tại. Không giả định môi trường test không có rủi ro vì “không phải production”.

## 4. Phát hiện API đang tồn tại bằng nhiều nguồn evidence

Không có một nguồn dữ liệu đơn lẻ nào cho thấy toàn bộ API surface. Cần đối chiếu nhiều nguồn để tìm chênh lệch giữa thiết kế, triển khai và traffic thực tế.

### 4.1. Nguồn từ thiết kế và source code

- OpenAPI/Swagger document và generated client/SDK.
- Spring MVC/WebFlux mappings, controller và functional route.
- GraphQL schema/resolver, gRPC proto/service implementation.
- Webhook registration, callback handler và message consumer.
- Gateway route definition, reverse proxy config và service mesh route.
- Infrastructure as Code, Kubernetes Service/Ingress/Gateway API.
- API management portal, developer portal và service registry.

Nguồn code cho biết endpoint có thể được triển khai, nhưng không chứng minh route có thể truy cập từ mạng nào hoặc đang nhận traffic.

### 4.2. Nguồn runtime và network

- Gateway access log và route metrics.
- Load balancer/listener, Ingress/Gateway API và DNS inventory.
- Service mesh telemetry và internal service registry.
- Cloud asset inventory, security group và firewall rule.
- Certificate transparency nội bộ, certificate inventory và hostname registry.
- WAF, API discovery và network flow log.
- Runtime endpoint/method mapping được xuất bởi framework hoặc service registry.

Chỉ thực hiện network discovery/scan trên tài sản và phạm vi được tổ chức cho phép. Dùng passive telemetry và asset inventory trước; nếu cần active validation, giới hạn tốc độ, cửa sổ thời gian và môi trường, tránh gây tải hoặc gọi operation có side effect.

### 4.3. Nguồn consumer và dependency

- Mobile app version và SDK usage.
- Partner integration registry và contract.
- Service-to-service call graph.
- Scheduled job, batch process và worker configuration.
- Frontend source, persisted GraphQL query và webhook subscription.
- Support ticket hoặc migration record có consumer còn dùng version cũ.

Consumer telemetry giúp xác định ai đang gọi API, nhưng không nên log token hoặc payload để lấy thông tin đó. Dùng client identity đã xác minh, operation ID và version.

### 4.4. Đối chiếu thiết kế với runtime

Tạo ba tập:

1. **Declared:** endpoint/operation trong catalog và contract.
2. **Deployed:** route, listener và handler thực tế đã triển khai.
3. **Observed:** operation thực sự nhận traffic trong cửa sổ quan sát.

So sánh các tập này để phân loại:

| Tình huống | Cách xử lý |
|---|---|
| Declared + deployed + observed | API đang hoạt động và có telemetry |
| Declared + deployed nhưng không observed | Có thể ít dùng, theo mùa hoặc chưa có traffic trong cửa sổ; không tự động xóa |
| Deployed nhưng không declared | Ứng viên shadow API; tìm owner và đánh giá exposure |
| Observed nhưng không declared | Kiểm tra route rewrite, alias, schema operation hoặc log thiếu mapping |
| Declared nhưng không deployed | Catalog có thể stale; xác minh release/lifecycle trước khi xóa |
| Không còn deployed nhưng DNS/listener còn tồn tại | Orphaned infrastructure cần dọn có kiểm soát |

Không coi “không có traffic trong 30 ngày” là bằng chứng API không còn được dùng. Batch theo tháng, client theo mùa hoặc integration khẩn cấp có thể ít xuất hiện. Chọn cửa sổ quan sát phù hợp với chu kỳ nghiệp vụ và hợp đồng consumer.

## 5. Duy trì API inventory có owner và lifecycle

Inventory chỉ có giá trị khi được cập nhật cùng thay đổi code và deployment. Một spreadsheet thủ công không có owner hoặc không gắn CI thường nhanh chóng lỗi thời.

### 5.1. Trường thông tin tối thiểu

| Trường | Mục đích |
|---|---|
| API/Service ID | Định danh ổn định của API family/service |
| Operation ID | Định danh query, mutation, method hoặc route operation |
| Protocol/transport | REST, GraphQL, gRPC, webhook, message, file API |
| Method/path/schema | Contract cụ thể và version |
| Exposure | Public, partner, internal, private hoặc admin plane |
| Environment | Production, staging, QA, sandbox, preview |
| Owner/team | Người chịu trách nhiệm kỹ thuật và security |
| Consumer/client | Web, mobile, partner, service hoặc job |
| Authentication | Session, JWT, API key, mTLS, workload identity |
| Authorization | Function, object, tenant và property policy |
| Data classification | Public, internal, confidential, restricted |
| Abuse controls | Rate, quota, body, depth, concurrency, cost |
| Dependencies/side effects | Database, queue, provider, outbound URL |
| Lifecycle | Draft, active, deprecated, sunset scheduled, retired |
| First/last seen | Thời điểm deploy/traffic quan sát được |
| Replacement | Version/operation thay thế |
| Evidence | OpenAPI, route ID, test, telemetry và deployment reference |

### 5.2. Owner phải là team chịu trách nhiệm thực tế

Không gán owner là một cá nhân đã rời tổ chức hoặc một email group không ai theo dõi. Mỗi API family cần team owner, escalation contact và người chịu trách nhiệm cho lifecycle/security review. Nếu service chuyển team, ownership phải được chuyển cùng catalog và alert.

### 5.3. Lifecycle rõ ràng

Một lifecycle có thể gồm:

```text
Draft -> Reviewed -> Active -> Deprecated -> Sunset scheduled -> Retired
```

- `Draft`: contract đang thiết kế, chưa nhận traffic production.
- `Reviewed`: đã có owner, security review và test criteria.
- `Active`: đang được hỗ trợ.
- `Deprecated`: đã thông báo sẽ ngừng, nhưng vẫn hoạt động trong thời gian chuyển đổi.
- `Sunset scheduled`: có ngày ngừng cụ thể và consumer migration plan.
- `Retired`: route/operation đã bị gỡ hoặc deny ở mọi enforcement point.

Không dùng `Deprecated` như trạng thái thay cho việc xử lý lỗ hổng. Security fix áp dụng ngay cho version đang active/deprecated; không chờ tới sunset.

### 5.4. Mọi route phải có trạng thái và owner

CI hoặc deployment policy nên từ chối route mới nếu thiếu operation ID, owner, authentication policy, data classification và contract. Với route tạm thời, yêu cầu expiry và lý do. Endpoint debug không được miễn inventory chỉ vì “chỉ bật trong staging”.

## 6. Kiểm soát shadow API trước khi chúng được triển khai

Phát hiện sau deployment là cần thiết, nhưng chặn ngay từ quy trình phát triển giúp giảm số endpoint không được quản lý.

### 6.1. API contract là một phần của pull request

Mỗi thay đổi route/schema phải cập nhật OpenAPI, GraphQL schema, proto hoặc message schema tương ứng. Pull request cần khai báo:

- Operation ID và owner.
- Consumer và exposure level.
- Authentication và authorization requirement.
- Request/response schema và data classification.
- Rate/body/cost limit.
- Error contract và audit event.
- Version/lifecycle impact.

Nếu route không xuất hiện trong contract hoặc catalog, CI có thể so sánh runtime mapping/source annotation với contract để phát hiện endpoint không được khai báo.

### 6.2. Không cho phép endpoint debug trong production

Debug, test, sample, mock, actuator env/config dump và internal diagnostics cần được loại khỏi production build hoặc khóa bằng policy riêng. Không chỉ dựa vào profile name; kiểm tra effective configuration và live listener. Nếu cần health endpoint public, trả thông tin tối thiểu và không tiết lộ dependency, version chi tiết hoặc secret.

### 6.3. Default deny ở gateway và service

Gateway nên chỉ route những API được đăng ký. Route không khớp phải bị từ chối. Service cũng cần authentication/authorization để không phụ thuộc gateway như ranh giới duy nhất, đặc biệt khi có internal load balancer hoặc direct service access.

Không tạo một route catch-all tới backend rồi dựa vào tài liệu để nói endpoint nào được phép. Không dùng wildcard path cho admin hoặc internal service nếu không có policy chi tiết.

### 6.4. Bảo vệ API management plane

Developer portal, API catalog, gateway admin API, service registry và route configuration là control plane nhạy cảm. Chỉ cấp quyền thay đổi route/credential/policy cho operator được ủy quyền, có MFA/step-up, audit và review. Kẻ tấn công sửa catalog/gateway có thể expose nhiều endpoint cùng lúc.

## 7. Quản lý version cũ mà không tạo đường vòng bảo mật

Version cũ thường tồn tại vì client không thể migrate cùng thời điểm. Quản lý nhiều version cần security invariant chung.

### 7.1. Security parity trên mọi version active

Các control cần nhất quán:

- Authentication, issuer/audience và token validation.
- Function permission và object authorization.
- Tenant predicate và property-level filtering.
- Input validation, parser/body limits và pagination.
- Rate limit, quota, concurrency và cost budget.
- SSRF destination policy và outbound client.
- Audit, logging, redaction và monitoring.
- Cache scope, signed URL, export và async worker.

Version adapter có thể khác DTO hoặc response format, nhưng nên chuyển thành canonical command/query và gọi application service/policy dùng chung. Không để V1 gọi repository trực tiếp trong khi V2 đi qua authorization service.

### 7.2. Version negotiation không được fallback sang version yếu hơn

Nếu client yêu cầu version không hỗ trợ, trả lỗi contract rõ ràng. Không âm thầm fallback sang V1 hoặc default version có control yếu hơn. Ghi requested version và resolved version trong telemetry để phát hiện gateway rewrite ngoài ý muốn.

### 7.3. Deprecation và sunset phải có ngày cụ thể

Thông báo deprecation nên nêu version/operation bị ảnh hưởng, replacement, migration guide, ngày sunset và owner hỗ trợ. Có thể dùng metadata như `Deprecation`, `Sunset` và `Link` theo contract của hệ thống; kiểm tra gateway giữ header và giá trị đồng nhất.

Không chỉ gửi email rồi để route tồn tại vô hạn. Theo dõi consumer/client ID đã xác minh, last seen và traffic theo operation. Xem xét chu kỳ batch hoặc mùa vụ trước khi kết luận không còn consumer.

### 7.4. Retire thật sự ở mọi lớp

Khi sunset:

1. Từ chối route/operation tại gateway.
2. Gỡ handler hoặc thêm deny rõ ràng ở application/service boundary.
3. Xóa alias, rewrite, listener và DNS record không còn dùng.
4. Thu hồi credential/scope chỉ dành cho version cũ nếu có.
5. Dọn consumer, SDK và scheduled job.
6. Xác minh không còn traffic trong cửa sổ phù hợp.
7. Lưu audit/evidence và cập nhật catalog thành `Retired`.

Không chỉ xóa route gateway nếu service vẫn có thể truy cập trực tiếp. Không xóa DNS hoặc credential trước khi xác minh dependency hợp lệ; việc retirement phải có owner và kế hoạch rollback an toàn.

## 8. Ví dụ inventory và phát hiện chênh lệch

Giả sử catalog khai báo:

| Operation ID | Route | Owner | Lifecycle | Exposure |
|---|---|---|---|---|
| `orders.get.v2` | `GET /v2/orders/{id}` | Commerce API | Active | Public |
| `orders.update.v2` | `PATCH /v2/orders/{id}` | Commerce API | Active | Public |
| `orders.get.v1` | `GET /v1/orders/{id}` | Commerce API | Deprecated | Public |
| `reports.export.v2` | `POST /v2/reports/export` | Reporting API | Active | Partner |

Runtime discovery lại thấy:

| Route/operation quan sát | Có trong catalog? | Phân loại ban đầu |
|---|---:|---|
| `GET /v2/orders/{id}` | Có | Expected |
| `PATCH /v2/orders/{id}` | Có | Expected |
| `GET /v1/orders/{id}` | Có | Legacy version, cần parity review |
| `POST /v2/reports/export` | Có | Expected, cần partner identity check |
| `GET /internal/user-dump` | Không | Shadow API, cần xác minh owner/exposure ngay |
| `POST /v1/reports/export` | Không | Có thể là alias/legacy shadow route |
| `GET /actuator/env` | Không | Management exposure cần xử lý khẩn cấp |

Các route chưa biết không nên bị xóa ngay chỉ dựa trên tên. Trước tiên xác minh nguồn, owner, consumer và exposure. Nếu endpoint public và trả dữ liệu nhạy cảm, áp dụng containment phù hợp trong lúc điều tra.

### 8.1. Ví dụ OpenAPI operation metadata

```yaml
paths:
  /v2/orders/{id}:
    get:
      operationId: orders.get.v2
      tags: [orders]
      security:
        - oauth2: [orders:read]
      x-api-owner: commerce-api
      x-api-lifecycle: active
      x-data-classification: confidential
      x-rate-limit-policy: orders-read
      responses:
        "200":
          description: Order representation visible to the caller
        "401":
          description: Authentication required
        "403":
          description: Operation or object access denied
```

`x-` extension là metadata riêng của tổ chức, không phải OpenAPI field chuẩn. CI có thể kiểm tra chúng có mặt và khớp catalog. Khai báo `security` trong OpenAPI không tự enforce authorization; runtime security configuration và test vẫn phải chứng minh policy được thực thi.

## 9. Ví dụ Java/Spring: kiểm kê route thực tế

Trong Spring MVC, có thể lấy mapping đã đăng ký để đối chiếu với API catalog. Cần giới hạn endpoint này cho operator hoặc chạy như một job nội bộ; không expose toàn bộ mapping cho public caller.

```java
@Component
public class ApiRouteInventoryCheck implements ApplicationRunner {
    private final RequestMappingHandlerMapping mappings;
    private final ApiCatalog catalog;

    public ApiRouteInventoryCheck(
            RequestMappingHandlerMapping mappings,
            ApiCatalog catalog) {
        this.mappings = mappings;
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        mappings.getHandlerMethods().forEach((mapping, handler) -> {
            mapping.getPatternValues().forEach(path -> {
                Set<RequestMethod> methods = mapping.getMethodsCondition().getMethods();
                if (methods.isEmpty()) {
                    catalog.reportUnmapped(path, "ALL_METHODS");
                    return;
                }
                methods.forEach(method -> {
                    if (!catalog.contains(path, method.name())) {
                        catalog.reportUnmapped(path, method.name());
                    }
                });
            });
        });
    }
}
```

Đây là ví dụ minh họa cho Spring MVC. Mapping có thể chứa condition về params, headers, consumes/produces; chỉ so sánh path và method có thể chưa đủ để xác định operation duy nhất. Cần canonicalize route, bao gồm context path, servlet mapping, gateway rewrite và version negotiation. WebFlux, GraphQL, gRPC, functional route và endpoint từ library cần nguồn inventory riêng.

Không tạo public endpoint kiểu `/debug/routes` để trả toàn bộ handler mapping. Xuất inventory trong startup report/CI artifact hoặc một control plane có authentication, authorization và audit.

### 9.1. CI gate cho route mới

Một kiểm tra CI có thể so sánh danh sách operation được khai báo với mapping được build:

```text
for each deployed operation:
    require operation_id
    require owner
    require exposure classification
    require authentication policy
    require authorization policy or explicit public justification
    require request/response contract
    require lifecycle state

if any operation is unmapped:
    fail build and request security review
```

Đây là pseudocode của policy gate. Cần có allowlist rõ cho endpoint framework/public-by-design như health check tối thiểu; allowlist phải có owner và test. Không dùng wildcard exemption như `/internal/**` để bỏ qua kiểm kê.

## 10. Security review cho shadow API được phát hiện

Khi tìm thấy endpoint ngoài catalog, đánh giá theo thứ tự để xác định mức khẩn cấp và hành động phù hợp.

### 10.1. Xác minh endpoint và owner

- Endpoint thuộc service nào, version nào và deploy từ artifact nào?
- Có owner/team hiện tại không?
- Ai tạo route và mục đích ban đầu là gì?
- Có consumer hợp lệ nào đang sử dụng?
- Endpoint được expose qua hostname, gateway, load balancer hoặc port nào?

Không tự suy đoán owner từ tên repository hoặc DNS. Dùng deployment metadata, code ownership, service registry và xác nhận của team.

### 10.2. Đánh giá exposure và authentication

- Public, partner, internal hay admin-only?
- Có thể gọi từ Internet hoặc network segment không dự kiến không?
- Authentication có bắt buộc và verify đúng issuer/audience/client identity không?
- Có route direct bypass gateway không?
- Debug/profile/Actuator có lộ thông tin cấu hình hoặc environment không?

### 10.3. Đánh giá authorization và dữ liệu

- Function permission có đúng operation không?
- Object authorization và tenant predicate có được áp dụng không?
- Property filtering có allowlist không?
- Có export/list/search/bulk/nested path dễ bỏ sót không?
- Response/error/log có chứa secret hoặc internal metadata không?

### 10.4. Đánh giá abuse và side effect

- Body size, parser depth, pagination, timeout và concurrency có giới hạn không?
- Rate limit/quota có theo identity đã xác minh không?
- Endpoint có gửi SMS/email/payment, tạo job hoặc gọi URL ngoài không?
- Retry/idempotency có bảo vệ duplicate side effect không?
- Audit và monitoring có bao phủ operation không?

### 10.5. Chọn hành động

| Kết quả review | Hành động |
|---|---|
| Endpoint hợp lệ nhưng thiếu catalog | Đăng ký owner, contract, policy và test; sau đó đưa vào quản lý |
| Endpoint không còn consumer, không có side effect | Lập kế hoạch retire sau khi kiểm tra chu kỳ sử dụng |
| Endpoint public và thiếu authentication | Containment theo risk, sau đó bổ sung auth hoặc retire |
| Có BOLA/cross-tenant exposure | Chặn operation hoặc siết policy ngay; xác định dữ liệu đã bị truy cập |
| Debug/management lộ secret/config | Hạn chế exposure, revoke secret nếu cần và điều tra access |
| Version cũ thiếu control | Áp dụng security parity hoặc sunset có kế hoạch |
| Không xác định được owner/consumer | Escalate; không để route không người chịu trách nhiệm tiếp tục vô thời hạn |

## 11. Kiểm thử inventory, exposure và version parity

Security test cần chứng minh catalog phản ánh runtime và mọi route đang hoạt động đều có control.

### 11.1. Inventory completeness test

- So sánh controller/route mapping với OpenAPI/catalog.
- So sánh gateway route và backend service route.
- So sánh GraphQL schema/resolver với operation registry.
- So sánh gRPC service/method với proto/catalog.
- Đối chiếu route deployed với traffic observed.
- Cảnh báo endpoint mới không có owner hoặc security classification.

### 11.2. Exposure test

Từ public vantage point được phép, xác minh chỉ route public-by-design có thể truy cập. Từ internal network segment không có quyền, xác minh admin/management endpoint bị chặn. Kiểm tra hostname cũ, listener, port, path alias và gateway rewrite.

Không chỉ assert route trả `404` ở gateway; kiểm tra direct service route và các alternate listener. Không chạy scan trên tài sản ngoài phạm vi được ủy quyền.

### 11.3. Security parity matrix

| Invariant | V1 | V2 | Alias/legacy | Shadow route mới phát hiện |
|---|---|---|---|---|
| Authentication | Test | Test | Test | Test trước khi giữ lại |
| Function authorization | Test | Test | Test | Test |
| Object/tenant isolation | Test | Test | Test | Test |
| Property filtering | Test | Test | Test | Test |
| Input/resource limits | Test | Test | Test | Test |
| Rate/quota | Test | Test | Test | Test |
| SSRF/outbound policy | Test | Test | Test | Test nếu có URL fetch |
| Audit/logging | Test | Test | Test | Test |

Status code có thể khác theo contract, nhưng không version/alias nào được trả dữ liệu hoặc tạo side effect bị policy hiện hành cấm.

### 11.4. Test deprecation và sunset

- Deprecation metadata đúng với lifecycle catalog.
- Consumer traffic được đo theo client/version/operation.
- Version retired trả lỗi contract rõ, không fallback sang version khác.
- Gateway, application và direct listener đều từ chối route đã retired.
- Credential/scope chỉ dành cho version cũ được thu hồi theo kế hoạch.
- Không còn scheduled job hoặc worker gọi logic đã retire.

### 11.5. Kiểm thử runtime drift

Sau deploy, xuất effective route mapping và cấu hình exposure từ môi trường đã triển khai. So sánh với artifact/config digest được phê duyệt. Phát hiện route mới, listener mới, wildcard policy hoặc debug endpoint được bật ngoài kế hoạch.

## 12. Monitoring và phát hiện API mồ côi

Inventory cần được đối chiếu định kỳ với runtime. Monitoring có thể phát hiện drift sớm hơn review thủ công.

Metric/event hữu ích:

- Route/operation mới xuất hiện trong gateway hoặc service mapping.
- Traffic tới version đã deprecated hoặc retired.
- Request tới path/host không có operation ID.
- API không có owner hoặc owner đã inactive.
- Route public mới hoặc listener/port mới được tạo.
- Tỷ lệ `401`, `403`, `404`, `410`, `413` và `429` theo operation/version.
- Consumer/client cuối cùng sử dụng version cũ và last-seen time.
- Deprecation usage và traffic sau sunset.
- API catalog drift giữa declared, deployed và observed.

Không dùng raw path/resource ID làm metric label nếu tạo cardinality cao. Chuẩn hóa route template và operation ID. Log request chi tiết phải tuân thủ redaction, access control và retention.

### 12.1. Cảnh báo cho zombie API

Nếu route đã `Retired` vẫn nhận request, kiểm tra gateway alias, DNS, CDN cache, direct service access và consumer chưa migrate. Nếu route đã bị gỡ nhưng traffic vẫn xuất hiện ở hostname cũ, có thể còn listener hoặc backend mapping chưa được dọn.

Không tự động mở lại route chỉ để xử lý client cũ. Xác minh consumer, đánh giá rủi ro và cung cấp migration path hoặc exception có thời hạn.

### 12.2. Review định kỳ

Review inventory theo chu kỳ release và định kỳ theo mức độ rủi ro. API public/partner/admin, API chứa dữ liệu nhạy cảm và API có side effect tốn chi phí cần review thường xuyên hơn endpoint nội bộ ít rủi ro. Review phải kiểm tra cả owner, consumer, data classification, policy và lifecycle.

## 13. Quy trình retirement an toàn

Gỡ API mà không làm gián đoạn consumer hợp lệ cần dữ liệu usage và kế hoạch.

1. Xác định route/operation/version và toàn bộ alias.
2. Xác định consumer từ client identity và telemetry trong cửa sổ phù hợp.
3. Xác nhận replacement API và khác biệt schema/permission.
4. Thông báo deprecation, sunset date và migration guide.
5. Áp dụng security fix ngay trong thời gian deprecation.
6. Theo dõi traffic, hỗ trợ consumer và đặt exception có owner/expiry nếu cần.
7. Tắt route ở gateway và application, dọn listener/DNS/credential/consumer.
8. Kiểm tra public/internal vantage point và direct service route.
9. Cập nhật catalog thành `Retired` và lưu evidence.

Nếu phát hiện lỗ hổng nghiêm trọng, có thể cần disable ngay trước sunset. Trong trường hợp đó, thông báo consumer theo incident process và cung cấp phương án thay thế an toàn; không trì hoãn containment chỉ vì lịch deprecation.

## 14. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ dựa vào OpenAPI | Bỏ sót route không được khai báo | Đối chiếu code, gateway, runtime và traffic |
| Chỉ inventory REST path | Bỏ sót GraphQL field, gRPC, webhook và async | Inventory theo operation/protocol |
| Không có owner | Không ai vá hoặc retire endpoint | Owner/team và escalation contact bắt buộc |
| Coi internal network là authentication | Direct exposure hoặc lateral movement | Authentication/authorization tại service boundary |
| Chỉ vá version mới | Version cũ trở thành bypass | Security parity trên mọi version active |
| Thông báo deprecation nhưng không sunset | Zombie API tiếp tục hoạt động | Ngày sunset, telemetry và retire verification |
| Xóa route gateway nhưng quên backend | Direct access vẫn hoạt động | Gỡ ở mọi enforcement point và listener |
| Tin không có traffic trong thời gian ngắn | Tắt nhầm batch/seasonal consumer | Cửa sổ quan sát theo chu kỳ nghiệp vụ |
| Để debug endpoint trong staging public | Lộ config, dữ liệu hoặc secret | Network restriction và auth riêng; không expose debug |
| Dùng wildcard allowlist | Route ngoài catalog có thể được expose | Default deny và route registration rõ |
| Chỉ kiểm tra status code | Data leak/side effect vẫn xảy ra | Kiểm tra response, DB, queue và provider |
| Catalog cập nhật thủ công sau deploy | Inventory nhanh chóng stale | CI/deployment gate và runtime reconciliation |

## 15. Checklist review trước khi phát hành

- [ ] Inventory bao phủ REST, GraphQL, gRPC/RPC, webhook, async, file/export và management endpoint.
- [ ] Đã đối chiếu declared, deployed và observed API surface.
- [ ] Mỗi API/operation có ID, owner, exposure, environment và lifecycle.
- [ ] Authentication và authorization được mô tả theo operation, object, tenant và property.
- [ ] Route mới không thể deploy production nếu thiếu contract/owner/policy.
- [ ] Gateway default deny; service có security boundary phù hợp khi bị gọi trực tiếp.
- [ ] Debug, test, actuator và management endpoint không bị public ngoài thiết kế.
- [ ] Version cũ có consumer inventory, security parity test và sunset date.
- [ ] Version negotiation không fallback sang route yếu hơn.
- [ ] Deprecation/sunset có migration guide, telemetry và owner.
- [ ] Retirement gỡ route ở gateway, application, listener, DNS và async consumer.
- [ ] API có body/parser/rate/quota/concurrency/cost limit phù hợp.
- [ ] SSRF/outbound integration và side effect được kiểm soát.
- [ ] Log/trace/audit có redaction, access control và retention.
- [ ] Runtime route/exposure drift được phát hiện sau deploy.
- [ ] Có test inventory completeness, public/internal exposure và version parity.
- [ ] Có kiểm tra direct service route và alternate hostname/port.
- [ ] Traffic không quan sát trong thời gian ngắn không bị xem là bằng chứng API vô dụng.
- [ ] API retired được xác minh không còn nhận traffic và catalog có evidence.

## Kết luận

Không kiểm kê shadow API và version cũ khiến tổ chức không biết đầy đủ những đường vào đang hoạt động, ai sử dụng chúng và security policy nào được áp dụng. Hãy đối chiếu contract, source code, gateway, hạ tầng, consumer và telemetry; duy trì inventory có owner, exposure, data classification và lifecycle; áp dụng security parity cho mọi version còn hoạt động; và xác minh retirement ở cả gateway lẫn service. API chỉ thực sự được quản lý khi trạng thái trong catalog khớp với những gì đang được triển khai và nhận traffic.

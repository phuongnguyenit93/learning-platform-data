# Danh mục endpoint, version và owner

API inventory là danh mục có kiểm soát về các API mà tổ chức cung cấp, sử dụng hoặc vận hành. Danh mục này cần cho biết endpoint nào đang tồn tại, được triển khai ở đâu, thuộc version nào, ai chịu trách nhiệm, ai được phép gọi, dữ liệu nào được xử lý và vòng đời hiện tại ra sao. Khi không có inventory đáng tin cậy, tổ chức khó biết bề mặt tấn công thực tế, khó thu hồi API cũ và khó xác định người chịu trách nhiệm khi xảy ra sự cố.

Một danh sách chỉ lấy từ OpenAPI/Swagger thường chưa đủ. Tài liệu có thể thiếu route cũ, endpoint nội bộ hoặc API được tạo động; gateway có thể không quan sát được service bị gọi trực tiếp; log runtime chỉ cho thấy những gì đã được gọi trong khoảng thời gian thu thập. Vì vậy, discovery cần kết hợp hợp đồng trong mã nguồn, cấu hình triển khai/gateway, quan sát runtime cùng thông tin ownership. Mỗi endpoint và version phải có owner cụ thể, trạng thái vòng đời và quy trình cập nhật rõ ràng.

## 1. API inventory là gì và quản lý những gì?

API inventory là nguồn dữ liệu tập trung mô tả bề mặt API theo cấu trúc có thể tìm kiếm, đối chiếu, kiểm tra và tự động hóa. Nó không chỉ là tài liệu dành cho developer; đây còn là đầu vào cho security review, quản lý thay đổi, incident response, kiểm soát truy cập, compliance và kế hoạch loại bỏ version cũ.

Cần phân biệt các cấp đối tượng:

- **API product/service:** một dịch vụ hoặc sản phẩm API có mục đích nghiệp vụ, ví dụ Customer API hoặc Billing API.
- **API version:** một hợp đồng hoặc phiên bản có vòng đời riêng, ví dụ v1, v2 hoặc phiên bản media type.
- **Endpoint/route:** một đường dẫn hoặc route được expose, ví dụ `/api/v2/customers/{customerId}`.
- **Operation:** một hành động cụ thể trên route, thường là tổ hợp HTTP method và path, ví dụ `GET /api/v2/customers/{customerId}`.
- **Deployment/instance:** nơi operation thực sự chạy, như production gateway, internal ingress, region hoặc cluster.
- **Consumer/client:** ứng dụng, đối tác, service hoặc nhóm người dùng đang gọi API.

Không nên gộp tất cả thành một tên API duy nhất. Cùng một path có thể có nhiều method với quyền khác nhau; cùng một version có thể được triển khai ở nhiều môi trường; một API product có thể chứa nhiều operation và nhiều owner phụ trách.

### 1.1. Phạm vi inventory

Tùy kiến trúc, inventory nên bao gồm:

- REST/HTTP API công khai, đối tác và nội bộ.
- GraphQL endpoint, schema, query/mutation và resolver nhạy cảm.
- gRPC service/method và protobuf contract.
- WebSocket, Server-Sent Events và các giao thức realtime.
- Webhook/callback endpoint inbound và outbound.
- API quản trị, vận hành, debug, health detail và endpoint hỗ trợ.
- API cũ, endpoint legacy, route chưa được tài liệu hóa hoặc chỉ được gọi từ ứng dụng cũ.
- Async API, message-driven interface và consumer/producer contract nếu chúng tạo bề mặt tích hợp.
- Endpoint được expose qua nhiều gateway, ingress, load balancer hoặc service mesh.

Inventory cần ghi rõ loại giao diện và ranh giới quản lý. Ví dụ, một message topic không phải HTTP endpoint, nhưng vẫn có thể là interface có dữ liệu nhạy cảm, owner và quyền truy cập cần kiểm soát trong danh mục API/interface chung.

## 2. Vì sao cần danh mục endpoint, version và owner?

### 2.1. Nhìn thấy bề mặt tấn công thực tế

Mỗi endpoint là một điểm có thể bị gọi. Nếu tổ chức không biết endpoint nào đang chạy, họ có thể bỏ sót:

- Route quản trị bị expose ra Internet.
- Endpoint cũ vẫn chấp nhận token hoặc cơ chế xác thực yếu.
- Version không còn được hỗ trợ nhưng chứa dữ liệu nhạy cảm.
- API nội bộ có thể truy cập trực tiếp, bỏ qua policy ở gateway.
- Endpoint thử nghiệm/debug vô tình được triển khai production.
- Route được thêm vào nhưng không có security review hoặc owner.

### 2.2. Xác định ai chịu trách nhiệm

Khi phát hiện endpoint không an toàn, cần biết ai có quyền sửa, ai hiểu nghiệp vụ, ai phê duyệt thay đổi và ai quyết định deprecate. Nếu chỉ có tên team chung hoặc một email cá nhân đã nghỉ việc, ownership chưa đủ tin cậy.

### 2.3. Quản lý version và consumer phụ thuộc

Một version cũ có thể vẫn được mobile app, đối tác hoặc service khác sử dụng. Tắt ngay có thể gây gián đoạn; giữ vô thời hạn lại kéo dài rủi ro. Inventory giúp xác định consumer, lưu lượng, owner và mốc sunset trước khi loại bỏ.

### 2.4. Đối chiếu chính sách bảo mật với triển khai

Inventory cho phép rà soát endpoint theo dữ liệu và chức năng:

- Endpoint nào xử lý PII, dữ liệu tài chính hoặc bí mật?
- Endpoint nào cần MFA/step-up, scope hoặc object-level authorization?
- Endpoint nào cho phép upload, export, fetch URL hoặc thao tác hàng loạt?
- Endpoint nào được public, partner-only, internal hoặc admin-only?
- Endpoint nào thiếu rate limit, audit hoặc giới hạn request size?

Không thể đánh giá API security đầy đủ nếu không biết API nào tồn tại và ai chịu trách nhiệm.

## 3. Các trường dữ liệu tối thiểu cho inventory

Nên thiết kế schema inventory có trường bắt buộc, trường tùy chọn và nguồn bằng chứng. Bảng dưới đây là bộ trường tham khảo.

| Nhóm | Trường | Ý nghĩa |
|---|---|---|
| Nhận diện | API ID, service name, endpoint ID | Khóa định danh ổn định, không phụ thuộc display name |
| Hợp đồng | Path, method, operationId, protocol | Mô tả operation cụ thể |
| Version | Version, versioning scheme, contract reference | Phiên bản và cách biểu diễn version |
| Môi trường | Environment, region, base URL, deployment | Nơi API đang chạy |
| Exposure | Public, partner, internal, admin | Phạm vi mạng và nhóm consumer |
| Authentication | Auth scheme, issuer/client identity | Cơ chế xác thực |
| Authorization | Scope, permission, role, object policy | Quyền cần có và phạm vi dữ liệu |
| Dữ liệu | Data classification, input/output fields | Loại dữ liệu được nhận và trả |
| Vận hành | Rate limit, timeout, body/page/batch limit | Giới hạn tài nguyên |
| Ownership | Business owner, technical owner, security contact | Người/nhóm chịu trách nhiệm |
| Consumer | Client, application, partner, dependency | Ai đang sử dụng |
| Lifecycle | Draft, active, deprecated, sunset, retired | Trạng thái vòng đời |
| Governance | Created date, last reviewed, next review | Lịch sử và kỳ rà soát |
| Evidence | Source, observed date, confidence | Nguồn phát hiện và mức tin cậy |

### 3.1. Định danh ổn định

Dùng ID ổn định cho API service và operation. Path có thể đổi khi refactor; display name có thể thay đổi; operationId cũng có thể bị sửa trong spec. Một inventory trưởng thành cần mapping lịch sử để nhận biết endpoint đã đổi tên hay được thay thế.

Ví dụ quy ước:

- API ID: `customer-profile-api`
- Operation ID: `customer-profile-read`
- Version: `v2`
- Environment: `production`

Không dùng URL production làm khóa duy nhất vì hostname, region hoặc gateway có thể thay đổi trong khi operation vẫn là cùng một API contract.

### 3.2. Owner không chỉ là một trường tên

Nên tách ít nhất:

- **Business owner:** chịu trách nhiệm về mục đích, dữ liệu và quyết định nghiệp vụ.
- **Technical/service owner:** chịu trách nhiệm triển khai, vận hành, sửa lỗi và deploy.
- **Security contact:** đầu mối xử lý security review, vulnerability và incident.
- **Platform/API governance owner:** duy trì chuẩn, catalog, lifecycle và quy trình phê duyệt.

Một người có thể kiêm nhiều vai trò ở team nhỏ, nhưng trách nhiệm phải rõ. Ghi tên team và kênh liên hệ ổn định bên cạnh cá nhân để tránh inventory lỗi thời khi nhân sự thay đổi.

### 3.3. Nguồn và độ tin cậy của dữ liệu

Mỗi record nên ghi nguồn phát hiện, thời điểm quan sát và mức tin cậy. Ví dụ:

- Contract trong repository: xác nhận ý định/hợp đồng đã khai báo.
- Gateway route: bằng chứng endpoint được expose qua gateway đó.
- Runtime telemetry: bằng chứng endpoint đã nhận request trong khoảng thời gian quan sát.
- Cloud/ingress config: bằng chứng deployment hoặc hostname được cấu hình.
- Owner confirmation: xác nhận nghiệp vụ và trách nhiệm.

Không nên đánh đồng “đã khai báo” với “đang chạy”, hoặc “đã quan sát request” với “được phép tồn tại”. Inventory cần giữ các trạng thái này riêng biệt.

## 4. Phát hiện API từ nhiều nguồn

Không có một nguồn duy nhất phát hiện được toàn bộ API. Kết hợp nhiều kỹ thuật và đối chiếu kết quả theo định kỳ.

### 4.1. Contract-first: OpenAPI và AsyncAPI

Thu thập OpenAPI specification từ repository và artifact build:

- Parse danh sách server/base URL, path, method và operationId.
- Đọc security scheme, scope, request/response schema và tag.
- Xác định version, deprecated operation và contact/owner nếu có.
- Kiểm tra spec có được publish hoặc deploy đúng môi trường không.
- So sánh contract giữa các release để phát hiện operation mới, bị xóa hoặc thay đổi.

Với event-driven interface, AsyncAPI hoặc schema registry có thể cung cấp channel, message, operation, producer/consumer và schema. Contract-first giúp hiểu API dự định cung cấp gì, nhưng không phát hiện route được tạo ngoài contract hoặc cấu hình runtime khác spec.

### 4.2. Phân tích mã nguồn và build artifact

Có thể discovery từ:

- Controller/route annotation và router configuration.
- API gateway plugin/config, route registry và framework mapping.
- GraphQL schema/resolver registration.
- gRPC service registration và reflection nếu bật.
- WebSocket handler và event subscription.
- Generated client/server stub và API specification được đóng gói trong artifact.

Static scanning có thể phát hiện route chưa có spec, nhưng cần xử lý false positive: route nội bộ trong test, code không được build hoặc handler không được đăng ký không nhất thiết là endpoint đang chạy.

### 4.3. Gateway, ingress và service mesh

Thu thập route từ mọi API gateway, reverse proxy, ingress controller và service mesh. Ghi lại:

- Hostname/base path và upstream service.
- Method/path matching.
- Authentication/authorization policy ở gateway.
- Rate limit, body limit và timeout.
- Public/private exposure.
- Route có bypass gateway hoặc được expose trực tiếp hay không.

Gateway inventory có thể không nhìn thấy endpoint chỉ truy cập qua internal load balancer, service-to-service network hoặc direct service port. Cần đối chiếu với service registry, deployment và network exposure.

### 4.4. Runtime discovery

Quan sát access log, tracing, API gateway analytics và service telemetry để phát hiện operation thực sự được gọi. Dữ liệu runtime có thể cho biết:

- Host, method, route template, status code và consumer/client.
- Lưu lượng theo version, tenant hoặc environment.
- Endpoint ít dùng, không có owner hoặc có traffic bất thường.
- Client còn sử dụng version đã deprecated.
- Route được gọi nhưng không xuất hiện trong contract.

Không ghi URL raw chứa token hoặc PII vào inventory. Chuẩn hóa thành route template, redact query string và dùng identifier đã kiểm soát. Cần phân biệt route template với path thực tế để không tạo hàng triệu record do ID động.

Runtime discovery không chứng minh endpoint chưa thấy traffic là không tồn tại. Một route có thể chỉ được gọi trong batch cuối tháng, quy trình khẩn cấp hoặc ứng dụng cũ chạy theo mùa.

### 4.5. DNS, certificate và cloud resource

Có thể tìm hostname và service exposure từ DNS zone, certificate inventory, cloud load balancer, container ingress, Kubernetes service/ingress và service registry. Những nguồn này giúp phát hiện API host bị bỏ sót, nhưng hostname không tự cho biết chính xác path/method hay contract.

### 4.6. Consumer và ứng dụng

Thu thập danh sách client từ OAuth client registry, API key registry, mobile/web application, partner integration, service dependency và tài liệu onboarding. Gắn consumer với version/operation mà họ sử dụng nếu telemetry cho phép.

Không suy ra toàn bộ consumer chỉ từ API key vì một key có thể được chia sẻ sai cách. Cần định danh client riêng và xác nhận owner.

## 5. Quy trình discovery và hợp nhất dữ liệu

Một quy trình có thể triển khai theo các bước:

1. **Thu thập:** lấy contract, route config, deployment, gateway, runtime telemetry, client registry và owner metadata.
2. **Chuẩn hóa:** chuẩn hóa protocol, hostname, base path, version, method và route template.
3. **Định danh:** ghép record theo API/service ID và operation ID; giữ quan hệ giữa alias, gateway route và upstream operation.
4. **Đối chiếu:** phát hiện operation có trong runtime nhưng thiếu contract, contract không được deploy, route bị expose ngoài dự kiến và version không có owner.
5. **Xác minh:** gửi danh sách chênh lệch cho technical/business owner xác nhận.
6. **Phân loại:** đánh giá exposure, dữ liệu, quyền, mức độ quan trọng và trạng thái lifecycle.
7. **Khắc phục:** bổ sung tài liệu/owner, đóng route không cần, sửa policy hoặc lập kế hoạch deprecation.
8. **Theo dõi:** chạy discovery định kỳ và trong CI/CD khi có thay đổi.

### 5.1. Sơ đồ luồng inventory

~~~mermaid
flowchart TD
    A[OpenAPI / AsyncAPI / source] --> D[Normalize and correlate]
    B[Gateway / ingress / service mesh] --> D
    C[Runtime logs / traces / DNS / cloud] --> D
    E[Client registry / owner metadata] --> D
    D --> F[API inventory catalog]
    F --> G[Security and lifecycle review]
    G --> H{Gap or risk found?}
    H -->|Yes| I[Assign owner and remediation]
    H -->|No| J[Periodic review]
    I --> J
    J --> D
~~~

### 5.2. Phát hiện chênh lệch quan trọng

| Chênh lệch | Ý nghĩa có thể có | Hành động |
|---|---|---|
| Runtime route không có trong OpenAPI | Shadow/undocumented API hoặc spec lỗi thời | Xác minh owner, contract và exposure |
| OpenAPI có nhưng không thấy runtime | API chưa deploy, không còn dùng hoặc chỉ chạy theo lịch | Xác minh deployment và consumer trước khi retire |
| Gateway route không có service owner | Route mồ côi hoặc mapping sai | Gán owner hoặc gỡ route sau xác minh |
| Service có public ingress nhưng inventory ghi internal | Sai phân loại exposure | Điều tra network path và sửa cấu hình |
| Production chạy version khác catalog | Drift giữa release và inventory | Đồng bộ metadata, đánh giá compatibility/security |
| Consumer dùng version đã sunset | Dependency chưa di trú | Liên hệ consumer owner và thực hiện migration |
| Endpoint không có auth policy rõ | Thiếu kiểm soát hoặc tài liệu | Security review và xác minh runtime behavior |

## 6. Quản lý version API

Version giúp thay đổi contract có kiểm soát. Nhưng versioning không tự tạo ra ranh giới bảo mật; mỗi version phải có auth, authorization, data scope, rate limit và owner phù hợp.

### 6.1. Các cách biểu diễn version

| Cách | Ví dụ | Điểm cần lưu ý |
|---|---|---|
| URL path | `/api/v1/orders` | Dễ quan sát trong route/gateway; version gắn với path |
| Query parameter | `/api/orders?version=1` | Dễ bị bỏ qua trong cache/routing nếu cấu hình sai |
| Custom header | `API-Version: 1` | Khó quan sát hơn trong log nếu không ghi header phù hợp |
| Media type | `Accept: application/vnd.example.v2+json` | Version gắn với representation; cần xử lý content negotiation |

Chọn một quy ước nhất quán và ghi trong inventory. Nếu API không version bằng URL, vẫn phải ghi version contract và cách client chọn version.

### 6.2. Version không đồng nghĩa deployment

Một version contract có thể chạy trên nhiều region hoặc cluster. Ngược lại, một deployment có thể tạm thời hỗ trợ nhiều version. Inventory nên liên kết version với deployment cụ thể thay vì chỉ ghi “API v2 đang tồn tại”.

### 6.3. Compatibility và thay đổi breaking

Thay đổi có thể ảnh hưởng consumer gồm:

- Xóa hoặc đổi tên field/operation.
- Thay đổi kiểu dữ liệu hoặc ý nghĩa field.
- Thay đổi required/optional, validation hoặc enum.
- Thay đổi authentication, scope hoặc permission.
- Thay đổi pagination, error format, rate limit hoặc semantics.
- Thay đổi dữ liệu trả về hoặc quyền truy cập object/tenant.

Security change cũng có thể là breaking change: ví dụ thu hẹp scope hoặc yêu cầu MFA có thể khiến consumer cũ ngừng hoạt động. Cần đánh giá cả compatibility lẫn rủi ro khi giữ hành vi cũ.

### 6.4. Deprecation và sunset

Mỗi version nên có trạng thái rõ ràng:

- **Draft:** đang thiết kế, chưa được phép dùng production.
- **Active:** được hỗ trợ và có owner.
- **Deprecated:** không khuyến khích consumer mới; đang trong thời gian di trú.
- **Sunset scheduled:** đã công bố thời điểm ngừng hỗ trợ.
- **Retired:** route đã bị gỡ hoặc bị chặn ở mọi môi trường được quản lý.

Khi deprecate:

1. Xác định consumer đang dùng version.
2. Thông báo owner, migration guide và deadline.
3. Theo dõi traffic theo client/version.
4. Hỗ trợ migration hoặc compatibility layer nếu cần.
5. Chặn tạo consumer mới nếu policy yêu cầu.
6. Gỡ route và credential/policy liên quan khi đã xác minh không còn dependency.
7. Cập nhật inventory và lưu bằng chứng retirement.

Không đánh dấu retired chỉ vì traffic bằng 0 trong vài ngày. Cần xét chu kỳ nghiệp vụ, batch schedule, backup/DR và consumer không có telemetry.

## 7. Quản lý owner và trách nhiệm

Mỗi API service và operation quan trọng cần có owner chịu trách nhiệm. Ownership không chỉ là thông tin liên hệ; nó gắn với quyết định vận hành và rủi ro.

### 7.1. Vai trò owner

| Vai trò | Trách nhiệm |
|---|---|
| Business owner | Mục đích, dữ liệu, người dùng và tác động nghiệp vụ |
| Technical/service owner | Code, deployment, availability, bug và lifecycle |
| Security owner/contact | Threat model, security review, incident và remediation |
| API platform/governance | Chuẩn contract, catalog, version và quy trình |
| Consumer owner | Tích hợp, migration và xác nhận ngừng sử dụng version |

Có thể áp dụng RACI cho các thay đổi lớn: owner chịu trách nhiệm thực hiện, approver chịu trách nhiệm quyết định, security/platform tham vấn, consumer được thông báo. Một thay đổi version hoặc sunset cần có người ra quyết định cuối cùng.

### 7.2. Không để owner rỗng hoặc lỗi thời

Inventory cần kiểm tra:

- Owner có còn là thành viên tổ chức/nhóm hay không.
- Email/team alias hoặc kênh liên hệ còn hoạt động.
- Owner có quyền sửa/deploy service không.
- API có owner thay thế khi team giải thể hoặc đổi tên không.
- Security contact có thể tiếp nhận vulnerability report không.

Nếu chưa xác định được owner, gắn trạng thái `owner_missing` hoặc tương đương, phân công cho platform/governance xử lý và tăng mức ưu tiên nếu endpoint đang public hoặc chứa dữ liệu nhạy cảm. Không tự gán owner theo tên thư mục hoặc tên repository.

### 7.3. Quy trình phê duyệt endpoint mới

Trước khi đưa operation mới lên production, cần ghi nhận:

- Business purpose và consumer dự kiến.
- Owner và security contact.
- Data classification và field input/output.
- Exposure: public, partner, internal hay admin.
- Authentication, scope/permission và object/tenant policy.
- Rate limit, timeout, body/page/batch size.
- Audit/logging và retention.
- Version/lifecycle, documentation và deprecation strategy.

Endpoint mới phải được thêm vào inventory như một phần của release, không phải tác vụ tài liệu làm sau.

## 8. Shadow API, zombie API và rogue API

Các thuật ngữ thường dùng:

- **Shadow API:** endpoint đang hoạt động nhưng không nằm trong inventory/contract chính thức hoặc không được đội quản trị biết đến.
- **Zombie API:** endpoint/version cũ được cho là đã ngừng nhưng vẫn còn hoạt động hoặc vẫn nhận traffic.
- **Rogue API:** API được triển khai hoặc expose ngoài quy trình/ủy quyền của tổ chức.

Các trường hợp này có thể xuất hiện khi:

- Team triển khai service trực tiếp mà không đăng ký gateway/catalog.
- API version cũ không được gỡ khỏi load balancer hoặc ingress.
- Test/staging route bị expose production.
- Một service tạo endpoint debug hoặc admin không qua review.
- Đối tác gọi trực tiếp upstream bỏ qua gateway.
- DNS/certificate vẫn tồn tại sau khi service bị xóa.

### 8.1. Cách xử lý

1. Xác minh endpoint có thật và đang được triển khai ở đâu.
2. Xác định dữ liệu, auth, consumer và owner.
3. Nếu có rủi ro cao, giới hạn exposure hoặc tạm chặn theo quy trình incident/change.
4. Gán owner và đưa vào inventory.
5. Quyết định giữ, sửa, deprecate hay retire.
6. Kiểm tra route trực tiếp, DNS, gateway, firewall và credential sau khi retire.
7. Lưu bằng chứng và cập nhật catalog.

Không tự động xóa endpoint chỉ vì nó không xuất hiện trong OpenAPI. Có thể đó là route hợp lệ được tạo động hoặc API vận hành theo lịch; cần xác minh owner và consumer trước khi thay đổi.

## 9. Kết nối inventory với bảo mật API

Inventory chỉ có giá trị khi các trường dữ liệu dẫn tới hành động kiểm soát.

### 9.1. Phân loại theo exposure và dữ liệu

Mỗi operation cần biết:

- Có thể truy cập từ Internet hay chỉ mạng nội bộ?
- Có chứa PII, tài chính, health data, bí mật kinh doanh hoặc credential không?
- Có thực hiện thay đổi trạng thái, thanh toán, quản trị hoặc export không?
- Có gọi outbound URL, nhận file hoặc xử lý batch không?
- Có phụ thuộc service khác hoặc bên thứ ba không?

Từ đó xác định mức review và kiểm soát cần thiết. Public API không đồng nghĩa dữ liệu public; internal API cũng không mặc nhiên an toàn.

### 9.2. Đối chiếu authentication và authorization

Inventory nên lưu auth scheme và permission theo operation, không chỉ theo service. Ví dụ:

| Operation | Exposure | Authentication | Authorization |
|---|---|---|---|
| `GET /catalog` | Public | Không hoặc client identity | Chỉ dữ liệu công khai, quota |
| `GET /customers/{id}` | Partner | OAuth access token | Scope + tenant + object policy |
| `POST /payments` | Partner/internal | Workload identity hoặc token | Payment permission, risk policy, idempotency |
| `PATCH /admin/users/{id}` | Admin | Strong auth/MFA | Permission chuyên biệt, audit/approval |

Không ghi một giá trị chung như “JWT required” cho toàn bộ service nếu từng operation có quyền khác nhau. Token hợp lệ không thay thế object authorization.

### 9.3. Endpoint có rủi ro đặc thù

Gắn nhãn để security review tập trung:

- File upload/download và document parsing.
- URL fetch/import, SSRF và webhook callback.
- Search, pagination, bulk export và resource consumption.
- Admin, role management, credential management.
- GraphQL query phức tạp hoặc resolver truy cập dữ liệu nhạy cảm.
- API xử lý PII, thanh toán hoặc dữ liệu tenant.

### 9.4. Inventory phục vụ incident response

Khi một credential bị lộ hoặc một API có lỗ hổng, catalog cần trả lời nhanh:

- Service/operation/version nào bị ảnh hưởng?
- Hostname và deployment nào đang expose?
- Owner và security contact là ai?
- Consumer/client nào đang sử dụng?
- Dữ liệu nào có thể bị truy cập?
- Có thể disable route, revoke credential hoặc giới hạn scope ở đâu?
- Version nào là bản thay thế an toàn?

## 10. Ví dụ record inventory

Một record đơn giản có thể biểu diễn như sau:

~~~yaml
apiId: customer-profile-api
serviceName: Customer Profile API
version: v2
environment: production
baseUrl: https://api.example.test
operation:
  operationId: customer-profile-read
  method: GET
  path: /api/v2/customers/{customerId}
  protocol: HTTP
exposure: partner
authentication:
  scheme: OAuth2
  issuer: https://identity.example.test
authorization:
  scopes:
    - customer:read
  objectPolicy: tenant-and-customer-membership
data:
  classification: confidential
  fieldsReturned:
    - customerId
    - displayName
    - status
limits:
  rateLimit: 120 requests/minute/client
  responsePageSize: 1
ownership:
  businessOwner: customer-platform
  technicalOwner: customer-api-team
  securityContact: security-oncall
consumers:
  - partner-portal
lifecycle:
  status: active
  lastReviewed: 2026-10-01
evidence:
  - source: openapi
  - source: production-gateway
  - source: runtime-telemetry
~~~

Đây là ví dụ minh họa cấu trúc, không phải schema bắt buộc. Không đưa secret, token, mật khẩu hoặc thông tin cá nhân thật vào inventory. Owner và consumer phải là định danh đã xác minh; trạng thái active cần có bằng chứng deployment/owner chứ không chỉ dựa vào file spec.

## 11. Tự động hóa inventory trong CI/CD

Discovery thủ công dễ lỗi thời. Nên đưa kiểm tra inventory vào pipeline:

- Khi build, parse OpenAPI/AsyncAPI và trích xuất operation.
- So sánh contract mới với version đang được catalog quản lý.
- Phát hiện operation mới chưa có owner hoặc chưa có auth/security metadata.
- Phát hiện operation bị xóa hoặc breaking change.
- Kiểm tra version, exposure, security scheme và data classification theo policy.
- Đối chiếu route config trước khi deploy.
- Sau deploy, lấy gateway/deployment metadata và xác nhận catalog.
- Định kỳ reconcile runtime telemetry với catalog.

### 11.1. Policy gate ví dụ

Một release có thể bị chặn hoặc yêu cầu phê duyệt nếu:

- Operation mới không có owner.
- Production endpoint không có authentication nhưng được phân loại dữ liệu nhạy cảm.
- Route admin bị expose public.
- Operation xử lý dữ liệu tenant nhưng không khai báo tenant/object policy.
- API mới có bulk export mà không có quota/permission.
- Version cũ bị xóa khi consumer vẫn đang sử dụng.
- OpenAPI contract và gateway route không khớp.

Không nên chỉ kiểm tra sự tồn tại của một trường text để coi là đã an toàn. Ví dụ `security: []` trong OpenAPI có thể hợp lệ cho endpoint public, nhưng cần xác minh data classification và exposure. Policy phải hiểu ngữ nghĩa và có ngoại lệ được phê duyệt, thời hạn rõ ràng.

### 11.2. Kiểm soát drift sau deploy

Catalog cần phản ánh runtime thực tế. Có thể so sánh định kỳ:

- Contract trong artifact đã deploy.
- Route trong gateway/ingress.
- Service/port đang expose.
- Traffic theo route/version.
- Owner và lifecycle metadata.

Khi phát hiện drift, tạo finding gắn với service owner và mức độ rủi ro. Không sửa inventory tự động theo mọi quan sát runtime mà không xác minh; nếu không, một endpoint rogue có thể được “hợp thức hóa” chỉ vì xuất hiện trong log.

## 12. Rà soát và chất lượng inventory

Đặt chu kỳ review dựa trên mức rủi ro:

- Public, admin, payment và sensitive-data API: rà soát thường xuyên hơn.
- Internal low-risk API: rà soát theo release hoặc chu kỳ định kỳ.
- Deprecated/sunset API: theo dõi consumer và ngày retire.
- API không owner hoặc có drift: đưa vào hàng đợi xử lý ưu tiên.

Các chỉ số chất lượng có thể theo dõi:

- Tỷ lệ API/operation có owner hợp lệ.
- Tỷ lệ production operation có contract và security metadata.
- Tỷ lệ endpoint được phân loại exposure/data.
- Số shadow/zombie API chưa xử lý.
- Số version deprecated còn traffic.
- Tuổi trung bình của lần review gần nhất.
- Số chênh lệch giữa gateway, deployment và catalog.
- Thời gian từ khi phát hiện endpoint mới tới khi xác minh owner.

Không tối ưu chỉ số bằng cách gán owner giả hoặc đánh dấu mọi endpoint active. Chất lượng inventory phụ thuộc độ chính xác, bằng chứng và quy trình xử lý chênh lệch.

## 13. Kiểm thử và xác minh inventory

| Nhóm kiểm thử | Tình huống | Kết quả mong đợi |
|---|---|---|
| Contract discovery | Parse tất cả OpenAPI/AsyncAPI trong artifact | Operation, version và schema được trích xuất đúng |
| Route discovery | So sánh source mapping và gateway route | Phát hiện route thiếu hoặc khác contract |
| Runtime discovery | Gửi request tới route test và kiểm tra telemetry | Operation được quan sát với route template chính xác |
| Hidden endpoint | Triển khai route test không có trong spec | Reconciliation phát hiện shadow/undocumented route |
| Version drift | Deploy v2 nhưng catalog ghi v1 | Có finding và yêu cầu cập nhật |
| Owner validation | Xóa hoặc làm sai owner/team alias trong fixture | Catalog đánh dấu owner missing/invalid |
| Consumer mapping | Client test gọi API theo version | Consumer/version được ghi nhận đúng nếu telemetry hỗ trợ |
| Deprecated version | Gọi version đã sunset trong môi trường test | Gateway/service từ chối theo policy và có audit |
| Exposure mismatch | Route nội bộ bị expose public trong fixture | Policy gate phát hiện sai phân loại |
| Auth metadata | Operation nhạy cảm thiếu auth/permission metadata | Release bị chặn hoặc cần exception có phê duyệt |
| Dynamic route | Route có path parameter hoặc wildcard | Chuẩn hóa thành route template, không sinh record theo từng ID |
| Data quality | Record thiếu protocol, environment hoặc lifecycle | Validation từ chối hoặc đánh dấu incomplete |
| Retirement | Gỡ route khỏi gateway và service | Inventory cập nhật retired sau khi xác minh các deployment liên quan |
| Auditability | Thay owner, version state hoặc exposure | Có lịch sử thay đổi, actor và timestamp |

Kiểm thử cần bao gồm cả false positive và false negative. Ví dụ một route không có traffic trong cửa sổ quan sát chưa chắc là zombie; một route không có trong gateway chưa chắc không được expose trực tiếp. Đánh giá discovery bằng nhiều nguồn bằng chứng.

## 14. Checklist trước khi đưa API vào production

- [ ] API service có ID ổn định, mô tả nghiệp vụ và owner.
- [ ] Mỗi operation có method, path template, protocol và version rõ ràng.
- [ ] Có deployment/environment/base URL và exposure classification.
- [ ] Authentication và authorization được ghi theo từng operation.
- [ ] Data classification và field input/output được xác định.
- [ ] Rate limit, timeout, body/page/batch limit và audit được khai báo.
- [ ] Business owner, technical owner và security contact còn hoạt động.
- [ ] Consumer/client và dependency quan trọng được liên kết.
- [ ] Contract trong repository được đối chiếu với gateway/ingress và runtime.
- [ ] Có quy trình review endpoint mới, version change và deprecation.
- [ ] Shadow, zombie và rogue API có quy trình phát hiện/xử lý.
- [ ] Production deploy cập nhật inventory và CI/CD kiểm tra drift.
- [ ] Không lưu secret hoặc dữ liệu cá nhân thật trong catalog.
- [ ] Có lịch review và chỉ số chất lượng inventory.

API inventory chỉ hữu ích khi mô tả được operation đang thực sự được expose, version đang được consumer sử dụng và owner có trách nhiệm xử lý. Hãy kết hợp contract, source, gateway, deployment, runtime và consumer registry; ghi bằng chứng cùng lifecycle; sau đó dùng catalog để kiểm soát security policy, version migration và incident response. Khi mỗi endpoint có owner và trạng thái rõ ràng, tổ chức có thể phát hiện API bị bỏ quên, giảm rủi ro từ version cũ và xử lý thay đổi có trách nhiệm.

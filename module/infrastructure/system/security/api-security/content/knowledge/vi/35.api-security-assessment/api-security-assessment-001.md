# Inventory endpoint trước khi kiểm thử

Một cuộc đánh giá API Security chỉ đáng tin khi nhóm kiểm thử biết chính xác hệ thống có những endpoint nào, chúng chạy ở môi trường nào, ai sở hữu, xử lý dữ liệu gì và được bảo vệ bằng cơ chế nào. Nếu chỉ lấy một file OpenAPI rồi bắt đầu gửi request, nhóm có thể bỏ sót route nội bộ, endpoint quản trị, webhook, phiên bản cũ, GraphQL resolver hoặc đường truy cập bypass API Gateway. Ngược lại, nếu quét mọi host và path tìm được mà không xác nhận phạm vi được phép, hoạt động kiểm thử có thể tác động tới hệ thống của bên thứ ba hoặc nghiệp vụ production ngoài dự kiến.

**Endpoint inventory** là danh mục có cấu trúc về các API operation mà cuộc đánh giá cần xem xét. Nó kết nối discovery với kế hoạch kiểm thử: mỗi record xác định một operation cụ thể, phương thức, route, môi trường, owner, authentication, authorization, dữ liệu, object/tenant, luồng nghiệp vụ và trạng thái kiểm thử. Inventory phải phản ánh cả thiết kế lẫn runtime, có nguồn bằng chứng và mức độ tin cậy.

Trong API Security, kiểm thử theo endpoint giúp đánh giá đúng từng điểm vào, đối tượng dữ liệu và luồng nghiệp vụ. Một API có thể dùng chung JWT ở toàn service nhưng từng endpoint có yêu cầu quyền khác nhau; một route đọc dữ liệu có thể an toàn trong khi route export hoặc refund vẫn có lỗi. Vì vậy, inventory cần đủ chi tiết để lập ma trận test theo endpoint, principal, object, property và trạng thái.

Sau bài học, người đọc có thể:

- Xác định phạm vi và quy tắc tham gia trước khi discovery hoặc kiểm thử.
- Thu thập endpoint từ OpenAPI, source code, gateway, cloud và runtime traffic.
- Chuẩn hóa route, method, version, host và environment để tránh trùng hoặc bỏ sót.
- Ghi nhận authentication, function/object/property authorization và tenant boundary.
- Phân loại dữ liệu, action, business flow, dependency và mức độ rủi ro.
- Đối chiếu tài liệu với endpoint đang chạy để tìm shadow, zombie và undocumented API.
- Chuyển inventory thành test matrix, ưu tiên kiểm thử và quản lý bằng chứng.

## 1. Inventory endpoint là gì và dùng để làm gì?

Inventory endpoint là danh mục các operation API có thể được gọi trong một phạm vi hệ thống. Một operation thường được định danh bằng tổ hợp:

- API/service hoặc sản phẩm sở hữu.
- Host/base URL và environment.
- HTTP method hoặc RPC operation.
- Route template, ví dụ /api/orders/{orderId}.
- API version và protocol.
- Cơ chế truy cập, ví dụ public, partner, internal hoặc admin.

Ví dụ, cùng một path nhưng method khác nhau là các operation khác nhau:

| Method | Route | Action nghiệp vụ | Vì sao cần record riêng? |
|---|---|---|---|
| GET | /api/orders/{orderId} | order.read | Trả dữ liệu đơn hàng, cần object/property authorization |
| PATCH | /api/orders/{orderId} | order.update | Thay đổi field và trạng thái, có nguy cơ mass assignment |
| POST | /api/orders/{orderId}/refunds | payment.refund.request | Tác động tài chính và có thể cần step-up approval |
| DELETE | /api/orders/{orderId} | order.cancel | Thay đổi trạng thái, có điều kiện nghiệp vụ và audit |

Không nên coi toàn bộ /api/orders là một endpoint duy nhất. Các method có thể có authentication, scope, dữ liệu trả về, tác động và rủi ro khác nhau.

### 1.1. Inventory phục vụ những quyết định nào?

Trước khi test, inventory giúp trả lời:

1. Những endpoint nào thuộc phạm vi đánh giá đã được phê duyệt?
2. Endpoint nào public, partner-facing, internal hoặc chỉ dành cho quản trị?
3. Mỗi endpoint yêu cầu authentication nào? Có endpoint nào vô tình public?
4. Ai được gọi chức năng? Có kiểm tra object, property và tenant không?
5. Endpoint đọc, tạo, sửa, xóa, export hay kích hoạt hành động nào?
6. Dữ liệu nào đi vào, đi ra hoặc được gửi tới downstream?
7. Endpoint có trạng thái, workflow hoặc điều kiện chuyển trạng thái nào?
8. Những role, tenant, object state và input nào cần có trong test matrix?
9. Ai xác nhận kết quả và xử lý finding?

Inventory cũng là baseline để so sánh sau khi sửa lỗi hoặc trước lần release tiếp theo. Khi route mới được triển khai, route cũ bị retire hoặc authentication policy thay đổi, inventory phải được cập nhật.

### 1.2. Inventory khác danh sách URL

Một danh sách URL không cho biết method, request schema, quyền, dữ liệu, owner hay mục đích nghiệp vụ. Ví dụ /api/users/{id} có thể có GET, PATCH và DELETE; GET có thể trả profile, PATCH thay đổi email hoặc role, DELETE có thể khóa tài khoản. Mỗi operation cần một record đủ ngữ cảnh để đánh giá riêng.

Inventory cũng không nhất thiết là một file duy nhất. Có thể lưu ở API management platform, security assessment repository, CMDB hoặc hệ thống quản lý API. Điều quan trọng là có nguồn dữ liệu có thẩm quyền, schema ổn định, owner và lịch sử thay đổi.

## 2. Xác định phạm vi và quyền kiểm thử trước khi discovery

Trước khi thu thập hoặc gửi request tới hệ thống, xác nhận phạm vi được phép. Endpoint inventory có thể phát hiện host và route ngoài dự kiến; việc tìm thấy một tài sản không đồng nghĩa đã được phép kiểm thử tài sản đó.

Tài liệu phạm vi nên xác định:

- Tổ chức, sản phẩm, service, domain và environment được phép đánh giá.
- Hostname, IP range, gateway, tenant hoặc test account nằm trong phạm vi.
- Endpoint hoặc loại dữ liệu bị loại trừ.
- Các kỹ thuật được phép: passive discovery, authenticated scan, fuzzing, load test hoặc test workflow.
- Những hành động không được thực hiện, ví dụ thanh toán thật, gửi email/SMS thật, xóa dữ liệu hoặc gọi webhook ra đối tác.
- Thời gian kiểm thử, giới hạn tốc độ, contact xử lý sự cố và điều kiện dừng.
- Quy trình phê duyệt nếu phát hiện endpoint mới nằm ngoài phạm vi.

Không thử nghiệm trên production bằng payload phá hủy hoặc tải lớn chỉ để xác minh endpoint tồn tại. Ưu tiên staging có cấu hình tương đương; nếu cần production validation, dùng request an toàn, tài khoản được cấp và giới hạn đã thống nhất.

### 2.1. Phân loại phát hiện ngoài phạm vi

Nếu discovery tìm thấy hostname hoặc route chưa có trong scope:

1. Ghi candidate, nguồn phát hiện và thời điểm.
2. Không gửi payload khai thác hoặc thực hiện hành động có side effect.
3. Đối chiếu với owner/inventory thông qua kênh được phép.
4. Xin xác nhận bổ sung phạm vi trước khi kiểm thử chủ động.
5. Giữ candidate ở trạng thái OUT_OF_SCOPE hoặc NEEDS_APPROVAL.

Điều này ngăn một hoạt động assessment hợp lệ biến thành kiểm thử trái phép đối với hệ thống vendor, đối tác hoặc môi trường khác.

## 3. Thu thập endpoint từ nhiều nguồn

Không có một nguồn nào phản ánh đầy đủ mọi endpoint. Cần kết hợp nguồn thiết kế, mã nguồn, hạ tầng triển khai và runtime.

| Nguồn | Có thể phát hiện | Giới hạn |
|---|---|---|
| OpenAPI/Swagger | Path, method, schema, security scheme, response | Có thể cũ, thiếu route mới hoặc không khớp runtime |
| API Gateway/API management | Public route, method, upstream, policy, quota | Có thể bỏ sót đường bypass gateway |
| Source code/controller | Mapping thực tế, annotation, handler, validation | Có thể chứa code chưa deploy hoặc profile không hoạt động |
| Ingress/reverse proxy/load balancer | Host, path routing, upstream và environment | Không luôn thấy business operation hoặc method đầy đủ |
| Cloud inventory/container/serverless | Service, public listener, function URL, ingress | Tài nguyên triển khai không tự chứng minh endpoint đang được sử dụng |
| Service mesh/service registry | Internal service và luồng service-to-service | Có thể không thấy route/operation bên trong HTTP |
| Runtime access log/tracing | Endpoint được gọi thực tế và caller context | Sampling, retention và đường truy cập thiếu có thể tạo khoảng trống |
| GraphQL schema | Type, query, mutation và field | Schema không cho biết mọi resolver có đang được expose |
| gRPC proto/reflection | Service, RPC method và message | Reflection có thể bị tắt; proto có thể khác binary đang chạy |
| Webhook/partner registry | Callback, event receiver và endpoint tích hợp | Có thể thiếu endpoint tự phát triển hoặc cấu hình thủ công |
| Mobile app/SDK/client config | Base URL, version và operation được client dùng | Client có thể cũ hoặc chứa endpoint không còn hoạt động |

### 3.1. OpenAPI là điểm bắt đầu, không phải sự thật duy nhất

OpenAPI hữu ích vì mô tả path, method, parameters, request body, response schema và security scheme. Tuy nhiên, cần kiểm tra:

- Spec có đúng version được deploy không?
- Spec có bao gồm admin/internal endpoints không?
- Có route được tạo bởi framework hoặc module plugin mà spec không mô tả không?
- Có endpoint deprecated nhưng runtime vẫn phục vụ không?
- Security scheme có được áp dụng ở operation-level hay chỉ khai báo ở top-level?
- Response schema có khớp dữ liệu thực tế và field nhạy cảm không?

Một operation có thể ghi đè security requirement ở cấp operation; vì vậy không chỉ đọc cấu hình security toàn document. Spec cũng có thể dùng security requirement rỗng cho endpoint public. Hãy xác minh ý nghĩa đó với implementation.

### 3.2. Discovery từ source code

Với Spring MVC/Spring Boot, có thể tìm các mapping như:

~~~java
@GetMapping("/api/orders/{orderId}")
@PostMapping("/api/orders/{orderId}/refunds")
@RequestMapping(path = "/api/users", method = RequestMethod.PATCH)
~~~

Đồng thời kiểm tra:

- Controller và functional route registration.
- Security matcher, method security và custom interceptor.
- Version prefix hoặc header-based versioning.
- Conditional mapping theo profile, feature flag, content type hoặc header.
- Management/actuator endpoints và custom admin handler.
- Webhook receiver, file upload, callback và export endpoint.

Source code cho biết implementation có thể tồn tại; cần xác minh route được bật trong environment đang đánh giá. Không chạy code hoặc bật profile chỉ để tạo endpoint nếu chưa được owner cho phép.

### 3.3. Runtime discovery

Access log, gateway log và trace cho biết operation nào thực sự nhận request. Chuẩn hóa route template thay vì lưu mọi URL chứa ID. Kiểm tra cả request thành công lẫn bị từ chối; một endpoint yêu cầu authentication vẫn có thể lộ ra qua phản hồi lỗi hoặc metadata.

Runtime traffic không có nghĩa mọi endpoint đã được phát hiện: endpoint hiếm dùng như khôi phục tài khoản, callback theo sự kiện hoặc báo cáo cuối quý có thể không xuất hiện trong cửa sổ log. Kết hợp runtime với spec, code và owner confirmation.

## 4. Chuẩn hóa và định danh endpoint

Các nguồn khác nhau có thể biểu diễn cùng một operation theo cách khác nhau. Trước khi hợp nhất, cần chuẩn hóa có kiểm soát.

### 4.1. Các thuộc tính định danh

Một endpoint record nên có tối thiểu:

- API/service ID.
- Environment.
- Scheme/host/base path.
- Protocol.
- API version.
- HTTP method hoặc RPC operation.
- Route template.
- Content type hoặc transport nếu ảnh hưởng đến contract.
- Source record và thời điểm xác minh.

Không gộp hai operation chỉ vì route giống nhau. GET trên host production và GET trên staging có thể khác data set, credential và policy. Route /admin/users trên internal host cũng không phải cùng tài sản với route tương tự trên public host.

### 4.2. Route template và path parameter

Chuẩn hóa:

~~~text
/api/orders/ord-1001  -> /api/orders/{orderId}
/api/orders/ord-1002  -> /api/orders/{orderId}
/api/users/u-17/files/f-9 -> /api/users/{userId}/files/{fileId}
~~~

Giữ tên parameter nếu có thể lấy từ route definition/OpenAPI. Không tự thay mọi segment số hoặc UUID thành parameter nếu chưa xác minh; một path segment tĩnh có thể chứa số, ví dụ /api/v2/2025/reports.

Query parameter cần được ghi riêng vì có thể thay đổi action hoặc response. Ví dụ /api/reports?format=csv và ?format=pdf có thể có khác biệt về content type, data exposure và resource consumption. Nếu query parameter chứa dữ liệu nhạy cảm, inventory chỉ lưu tên/kiểu và classification, không lưu giá trị thực.

### 4.3. Method override và alternate transport

Ghi nhận nếu ứng dụng dùng X-HTTP-Method-Override, tunneling qua POST, content negotiation hoặc custom header để chọn operation. Cần xác định method thực tế được security layer và business handler sử dụng. Không chỉ dựa vào method nhìn thấy ở access log nếu middleware có thể override.

Với GraphQL, một URL /graphql có thể phục vụ nhiều query/mutation; inventory cần bổ sung operation name/type, resolver/field nhạy cảm và giới hạn depth/cost. Với gRPC, ghi service/method, message type và authentication metadata. Với WebSocket, ghi handshake route và message action được expose sau khi kết nối.

## 5. Metadata cần có cho mỗi endpoint

Inventory nên cung cấp đủ ngữ cảnh để quyết định test nào cần chạy và ai có thể xác nhận kết quả.

| Nhóm metadata | Trường gợi ý | Mục đích |
|---|---|---|
| Identity | API ID, endpoint ID, service, host, environment | Định danh tài sản |
| Operation | Method, route, version, protocol, content type | Xác định cách gọi |
| Ownership | Business owner, technical owner, contact, repository | Biết ai chịu trách nhiệm |
| Exposure | Public, partner, internal, admin, private | Hiểu bề mặt truy cập |
| Authentication | JWT, session, API key, mTLS, anonymous | Xác định cách xác minh caller |
| Authorization | Function, object, property, tenant, relationship | Xác định quyền cần kiểm thử |
| Input | Path/query/header/body, schema, file, URL | Xác định input surface |
| Output | Response schema, data fields, download/export | Xác định nguy cơ lộ dữ liệu |
| Business | Action, state, precondition, side effect | Hiểu tác động nghiệp vụ |
| Resource controls | Rate limit, quota, pagination, timeout, size | Kiểm thử lạm dụng tài nguyên |
| Dependencies | Downstream, database, provider, queue | Hiểu trust boundary |
| Lifecycle | Active, deprecated, retired, version dates | Quản lý phiên bản |
| Assessment | In-scope, test status, findings, evidence | Theo dõi cuộc kiểm thử |

Không phải mọi trường đều bắt buộc cho mọi endpoint. Tuy nhiên, endpoint nhạy cảm cần có owner, exposure, data classification, authentication/authorization và business impact rõ ràng trước khi test sâu.

### 5.1. Authentication metadata

Ghi rõ:

- Có yêu cầu authentication không?
- Credential type nào được chấp nhận?
- Issuer, audience hoặc client registration nào được tin cậy?
- Endpoint có hỗ trợ user session, service identity hoặc delegated token không?
- Có MFA/step-up authentication cho action nhạy cảm không?
- Token/API key có scope hoặc expiry đặc biệt không?
- Anonymous access có chủ đích hay là cấu hình cần xác minh?

Không chỉ ghi “JWT protected”. Hai endpoint cùng nhận JWT có thể khác issuer, audience, scope và policy. Nếu token được chuyển tiếp từ service khác, ghi cả actor service và subject cuối.

### 5.2. Authorization metadata

Ghi riêng từng lớp:

- **Function-level:** principal/role/scope nào được gọi operation?
- **Object-level:** caller được truy cập object thuộc owner, tenant hoặc assignment nào?
- **Property-level:** field nào được đọc/ghi theo role và trạng thái object?
- **Tenant-level:** tenant context lấy từ đâu và được đối chiếu như thế nào?
- **Relationship/workflow:** có cần là người tạo, người duyệt hoặc người được phân công không?

Ví dụ endpoint PATCH order có thể cho customer sửa địa chỉ khi trạng thái DRAFT, nhưng chỉ staff được đổi trạng thái giao hàng. Inventory cần ghi nhận field/action và trạng thái có liên quan để test không chỉ gửi một payload chung.

### 5.3. Input và output metadata

Ghi các vị trí nhận input:

- Path/query/header/cookie.
- JSON/XML/form/multipart body.
- File, archive, image hoặc document.
- URL/hostname do caller cung cấp.
- Batch ID, cursor, filter, sort và search expression.
- GraphQL query/variables hoặc RPC message.

Với output, ghi loại dữ liệu và đường trả:

- JSON fields, nested object và metadata.
- File download, preview, export hoặc signed URL.
- Error response, header và redirect.
- Webhook/event payload.
- Aggregate/count/search result.

Điều này giúp xác định test validation, SSRF, mass assignment, excessive data exposure, file inspection và side-channel phù hợp.

## 6. Phân loại dữ liệu và mức độ nhạy cảm

Mỗi endpoint cần mô tả dữ liệu nhận, đọc, tạo, sửa, trả và chuyển tiếp. Phân loại có thể dùng các mức nội bộ như:

| Phân loại | Ví dụ | Yêu cầu kiểm thử gợi ý |
|---|---|---|
| Public | Catalog đã công bố, thông tin công khai | Kiểm tra tính toàn vẹn, abuse và rate limit |
| Internal | Metadata vận hành, thông tin không công khai | Kiểm tra network boundary và authentication |
| Confidential | Hợp đồng, dữ liệu doanh nghiệp, báo cáo nội bộ | Kiểm tra object/tenant/property authorization |
| Personal data | Email, địa chỉ, hồ sơ người dùng | Kiểm tra owner scope, masking, export và audit |
| Highly sensitive | Credential, recovery code, dữ liệu thanh toán hoặc hồ sơ được bảo vệ đặc biệt | Kiểm tra quyền chặt, redaction, retention và access audit |

Phân loại cần theo policy của tổ chức và pháp luật áp dụng; không tự gán nhãn pháp lý chỉ dựa trên tên field. Nếu endpoint trả nhiều loại dữ liệu, ghi mức cao nhất và liệt kê field group quan trọng.

### 6.1. Data flow và downstream

Endpoint có thể nhận dữ liệu rồi gửi sang service khác, queue hoặc provider. Ghi:

- Dữ liệu nào được truyền đi?
- Downstream service/provider nào nhận?
- Credential nào được dùng và audience/scope gì?
- Có transform, masking hoặc enrichment không?
- Dữ liệu được lưu ở đâu và retention bao lâu?
- Retry/dead-letter/export có thể tạo bản sao ở đâu?

Một endpoint có thể có authentication tốt ở ingress nhưng gọi downstream bằng service credential quyền rộng. Inventory cần thể hiện luồng này để đánh giá confused deputy và trust boundary.

## 7. Mapping business flow và object state

Endpoint inventory chỉ theo HTTP route có thể bỏ qua rủi ro nghiệp vụ. Nhiều API chỉ an toàn khi được gọi theo đúng thứ tự và trạng thái.

Ví dụ luồng hoàn tiền:

~~~text
GET /orders/{id}
  -> POST /orders/{id}/refund-requests
  -> POST /refund-requests/{requestId}/approve
  -> POST /refund-requests/{requestId}/execute
~~~

Các operation có thể yêu cầu:

- Chủ đơn hoặc support staff được tạo yêu cầu.
- Người phê duyệt phải khác người tạo nếu policy separation of duties yêu cầu.
- Chỉ đơn đã thanh toán và chưa hoàn tiền mới được xử lý.
- Amount không vượt số tiền còn được hoàn.
- Execute chỉ chạy sau khi approval hợp lệ.
- Request ID phải idempotent để retry không hoàn tiền hai lần.

Inventory nên liên kết endpoint với workflow ID, object type, state trước/sau và actor role. Khi lập test plan, kiểm tra cả endpoint riêng lẫn chuỗi thao tác: gọi sai thứ tự, replay, thay object ID, sửa amount hoặc bỏ qua approval.

### 7.1. Ma trận state/action

| Object state | Action | Principal | Kỳ vọng |
|---|---|---|---|
| DRAFT | update | Owner | Cho phép field được chỉnh |
| PENDING_REVIEW | update nội dung | Submitter | Từ chối hoặc yêu cầu withdraw theo workflow |
| PENDING_REVIEW | approve | Assigned reviewer | Cho phép nếu reviewer không phải submitter khi policy yêu cầu |
| APPROVED | execute | Service workflow | Chỉ thực hiện một lần, idempotent |
| CANCELLED | execute | Bất kỳ | Từ chối |

State matrix này là đầu vào cho test case, không phải kết quả authorization tự suy ra từ endpoint name.

## 8. Phát hiện endpoint thiếu tài liệu, shadow và zombie

So sánh nguồn thiết kế với runtime và source/deployment để tìm sai lệch:

- **Undocumented endpoint:** có route trong code/runtime nhưng không có spec/inventory.
- **Shadow API:** được triển khai hoặc sử dụng ngoài quy trình quản lý.
- **Zombie API:** version/route được xem là retired nhưng vẫn hoạt động.
- **Unexpected exposure:** service internal xuất hiện qua public host hoặc IP.
- **Unowned endpoint:** không tìm được owner.
- **Policy drift:** endpoint thực tế có authentication, method hoặc response khác contract.

### 8.1. So sánh theo nhiều chiều

Đối chiếu:

1. OpenAPI operation với route/controller đã deploy.
2. Gateway/ingress route với service listener.
3. Runtime traffic với endpoint inventory.
4. Version và environment với deployment metadata.
5. Security policy khai báo với filter chain/gateway config thực tế.
6. Response schema với data fields thực tế.

Một endpoint không có traffic trong thời gian ngắn chưa chắc là zombie; có thể chỉ chạy theo lịch tháng/quý hoặc sự kiện hiếm. Cần owner confirmation và cửa sổ quan sát phù hợp.

### 8.2. Endpoint không có owner

Gán trạng thái UNOWNED hoặc NEEDS_REVIEW, lưu nguồn discovery và mức confidence. Nếu endpoint public hoặc xử lý dữ liệu nhạy cảm, ưu tiên triage. Không tự tắt endpoint chỉ vì không tìm được owner; xác định dependency và impact trước khi thay đổi.

## 9. Từ inventory sang test matrix

Inventory tốt phải giúp tạo ra test case cụ thể. Một cách làm là kết hợp các chiều:

- Endpoint/method.
- Principal/role/client.
- Tenant/owner/relationship.
- Object state.
- Input class.
- Expected output/action.

Không cần tạo mọi tổ hợp Cartesian nếu số lượng quá lớn. Chọn tổ hợp theo threat model, rủi ro và business rule; bảo đảm có negative test cho các ranh giới quan trọng.

### 9.1. Ví dụ ma trận test endpoint

| Endpoint | Principal | Object | Test trọng tâm |
|---|---|---|---|
| GET /orders/{id} | Customer A | Order A | Đọc đúng dữ liệu và field được phép |
| GET /orders/{id} | Customer A | Order B | BOLA/tenant isolation |
| PATCH /orders/{id} | Customer A | Order A, DRAFT | Allowlist field và state transition |
| PATCH /orders/{id} | Customer A | Order A, SHIPPED | Từ chối sửa field không còn được phép |
| POST /refunds | Customer A | Order A | Amount, ownership, idempotency và business precondition |
| POST /refunds/{id}/approve | Submitter | Refund A | Separation of duties |
| POST /refunds/{id}/approve | Assigned reviewer | Refund A | Quyền và trạng thái approval |
| GET /admin/audit | Customer A | Tenant data | Function-level authorization và data exposure |

### 9.2. Các nhóm kiểm thử nên gắn với endpoint

| Nhóm | Câu hỏi kiểm thử |
|---|---|
| Authentication | Không credential/sai token/expired/revoked có bị từ chối? |
| Function authorization | Role/scope nào được gọi method này? |
| Object authorization | Đổi ID sang object của user/tenant khác có bị chặn? |
| Property authorization | Có thể đọc hoặc ghi field bị cấm không? |
| Input validation | Type, range, enum, length, nested object có được kiểm tra? |
| Mass assignment | Client có thể thay owner, role, price hoặc state không? |
| SSRF | URL/host do client gửi có thể truy cập mạng nội bộ không? |
| Resource consumption | Pagination, batch, file size, query cost và timeout có giới hạn? |
| Output filtering | Error, list, export, nested resource có lộ field không? |
| Business flow | Có thể bỏ qua bước, replay hoặc tạo trạng thái bất hợp lệ? |
| Logging/audit | Actor, object, tenant và decision có được ghi an toàn? |
| Version/lifecycle | API cũ có policy yếu hơn hoặc vẫn public không? |

Không phải mọi nhóm đều áp dụng cho mọi endpoint. Ví dụ endpoint không nhận URL có thể không cần SSRF test trực tiếp; endpoint download cần file state và cache test; endpoint nhận GraphQL query cần depth/cost test.

## 10. Ưu tiên endpoint theo rủi ro

Không nên test mọi endpoint theo cùng thứ tự và độ sâu. Ưu tiên theo tác động nếu endpoint bị khai thác, khả năng tiếp cận và mức độ phức tạp.

Các yếu tố gợi ý:

- Exposure: Internet/public, partner, internal hoặc admin.
- Data sensitivity: personal, financial, confidential, credential.
- Action impact: read, export, update, delete, approve, transfer, execute.
- Authentication strength và mức độ phức tạp của credential/delegation.
- Authorization complexity: tenant, ownership, assignment, property và state.
- Input risk: file, URL, batch, query expression, rich document.
- Resource risk: expensive search, report, export, fan-out hoặc streaming.
- Dependency risk: service credential, third-party provider và queue.
- Change history: endpoint mới, deprecated, recently modified hoặc thiếu owner.
- Threat signals: traffic bất thường, deny spikes, abuse reports hoặc incident trước đó.

Một cách phân nhóm:

| Mức | Ví dụ | Cách kiểm thử |
|---|---|---|
| Critical | Admin privilege, payment/refund, credential management, cross-tenant export | Kiểm thử sâu, nhiều principal/state, workflow và negative cases |
| High | PII, file upload/download, account management, partner webhook | Kiểm tra authn/authz, data exposure, input và abuse |
| Medium | CRUD dữ liệu nội bộ, search có giới hạn | Test contract, access boundary, validation và rate limit |
| Low | Public read-only catalog | Test integrity, availability và data contract; vẫn kiểm tra abuse |

Đây là cách phân loại tham khảo. Dùng risk model của tổ chức và không hạ mức chỉ vì endpoint nằm trong mạng nội bộ.

## 11. Ví dụ record inventory

Một record có thể lưu dưới YAML hoặc JSON. Ví dụ:

~~~yaml
apiId: order-api
endpointId: order-update-v2
environment: production
exposure: public
host: api.example.test
protocol: HTTPS
version: v2
operation:
  method: PATCH
  route: /api/v2/orders/{orderId}
  action: order.update
owner:
  team: commerce-platform
  contact: commerce-oncall
authentication:
  required: true
  mechanism: oauth2-jwt
  issuer: https://identity.example.test
  audience: order-api
authorization:
  function:
    - order:update
  object:
    rule: tenant-and-owner
  property:
    writable:
      - deliveryAddress
    forbidden:
      - tenantId
      - ownerId
      - total
      - status
data:
  input:
    - customer-delivery-address
  output:
    - order-summary
  classification: confidential
business:
  objectType: order
  allowedStates:
    - DRAFT
    - CONFIRMED
resourceControls:
  maxBodyBytes: 16384
  rateLimitProfile: customer-write
dependencies:
  - inventory-service
  - address-service
assessment:
  scope: in-scope
  priority: high
  status: not-tested
  evidenceSource:
    - openapi
    - gateway-config
    - runtime-traffic
~~~

Đây là ví dụ minh họa. Không lưu secret, token hoặc dữ liệu khách hàng thật trong inventory. Các trường cụ thể cần phù hợp schema quản lý API của tổ chức.

### 11.1. Không chỉ ghi policy mong muốn

Tách rõ:

- declared: policy trong OpenAPI/design.
- implemented: policy tìm thấy trong source/config.
- observed: hành vi kiểm chứng được ở runtime.
- verified_at: thời điểm và bằng chứng xác minh.

Nếu spec nói endpoint yêu cầu JWT nhưng runtime cho phép anonymous, inventory không được ghi đơn giản là “JWT protected”. Hãy ghi sai lệch và tạo finding cần kiểm tra.

## 12. Quy trình lập inventory trước assessment

Một quy trình có thể thực hiện theo thứ tự:

~~~mermaid
flowchart TD
    A[Phê duyệt scope và rules of engagement] --> B[Thu thập OpenAPI, code và cấu hình]
    B --> C[Discovery từ gateway, cloud và runtime]
    C --> D[Chuẩn hóa host, method, route và version]
    D --> E[Hợp nhất record và lưu nguồn bằng chứng]
    E --> F[Phân loại owner, exposure và dữ liệu]
    F --> G[Mapping authentication, authorization và business flow]
    G --> H[Đối chiếu spec với implementation/runtime]
    H --> I[Ưu tiên rủi ro và tạo test matrix]
    I --> J[Owner review và xác nhận test readiness]
    J --> K[Thực hiện assessment trong scope]
~~~

### Bước 1: Xác nhận scope

Ghi host, environment, account/test tenant, endpoint exclusions, giới hạn tốc độ và hành động bị cấm. Xác định contact để báo sự cố.

### Bước 2: Thu thập nguồn tĩnh

Lấy OpenAPI, GraphQL schema, proto, gateway config, route/controller mapping, deployment metadata và client SDK inventory. Ghi ngày/version của từng nguồn.

### Bước 3: Discovery runtime có kiểm soát

Đối chiếu gateway, ingress, access log, tracing và service registry. Nếu cần active discovery, chỉ dùng phương pháp an toàn trong scope. Không fuzz hoặc gửi payload thay đổi dữ liệu ở giai đoạn inventory.

### Bước 4: Chuẩn hóa và hợp nhất

Chuẩn hóa method, route template, host, version và environment. Gắn source record để biết endpoint đến từ spec, code, gateway hay runtime. Giữ các record khác nhau khi policy hoặc environment khác nhau.

### Bước 5: Phân loại dữ liệu và quyền

Xác định authentication, function/object/property authorization, tenant source, data classification và state/workflow. Nếu chưa biết, ghi UNKNOWN thay vì tự suy luận.

### Bước 6: Xác minh với owner

Owner xác nhận endpoint active, consumer, mục đích, test account, dữ liệu giả lập và giới hạn side effect. Endpoint không rõ owner được đưa vào triage.

### Bước 7: Tạo test matrix và ưu tiên

Chọn principal, tenant, object state, input và expected outcome cho từng endpoint. Ưu tiên endpoint rủi ro cao và luồng có thể gây tác động lớn.

### Bước 8: Baseline và quản lý thay đổi

Đóng băng phiên bản inventory cho assessment, lưu thời điểm và hash/source revision nếu phù hợp. Khi endpoint thay đổi trong lúc test, cập nhật record và đánh giá lại test case bị ảnh hưởng.

## 13. Kiểm tra chất lượng inventory

Inventory có thể dài nhưng vẫn thiếu chất lượng. Cần kiểm tra:

- **Completeness:** nguồn chính đã được thu thập chưa? Host, environment, protocol và endpoint family có bị bỏ sót?
- **Accuracy:** route/method/version có khớp runtime không?
- **Ownership:** có business/technical owner và contact không?
- **Security context:** authentication, authorization và tenant boundary có được xác minh hay chỉ suy đoán?
- **Data context:** input/output classification có đủ để ưu tiên không?
- **Traceability:** record có source, timestamp, confidence và evidence reference không?
- **Lifecycle:** active/deprecated/retired có phản ánh trạng thái thật không?
- **Testability:** có test account, test data, safe workflow và expected result không?

### 13.1. Confidence và trạng thái xác minh

Có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| DISCOVERED | Tìm thấy từ một nguồn, chưa xác minh |
| CORROBORATED | Có ít nhất hai nguồn hỗ trợ hoặc owner xác nhận một phần |
| VERIFIED | Host/route/method/environment và owner/policy đã được xác minh |
| NEEDS_REVIEW | Có mâu thuẫn hoặc thiếu thông tin quan trọng |
| OUT_OF_SCOPE | Phát hiện ngoài phạm vi được phép |
| RETIRED | Đã xác minh route không còn được phục vụ |

Không dùng một con số confidence duy nhất để thay thế bằng chứng. Ghi nguồn nào xác nhận điều gì. Ví dụ runtime log chứng minh route được gọi, nhưng không chứng minh owner hoặc data classification.

### 13.2. Coverage metrics

Một số chỉ số:

- Tỷ lệ endpoint đã có owner.
- Tỷ lệ endpoint có method/route/version/environment xác minh.
- Tỷ lệ endpoint có authn/authz metadata.
- Tỷ lệ endpoint có data classification.
- Số undocumented/shadow endpoint.
- Số endpoint public không xác định owner hoặc authentication.
- Số endpoint deprecated còn traffic.
- Tỷ lệ endpoint critical/high có test matrix và evidence.
- Số mâu thuẫn giữa spec, source, gateway và runtime.

Đừng dùng “số lượng endpoint đã thu thập” làm thước đo duy nhất. Inventory tốt cần đủ chính xác để đưa ra quyết định kiểm thử.

## 14. Quản lý test account, object và dữ liệu thử nghiệm

Inventory cần ghi endpoint có thể test bằng account/tenant nào và các object fixture nào được phép dùng. Không lưu password, token hoặc secret trong inventory; lưu reference tới hệ thống cấp test credential nếu có.

Chuẩn bị các principal và object đại diện:

- Anonymous/unauthenticated.
- User thường thuộc tenant A.
- User thuộc tenant B.
- Owner và non-owner.
- Staff/support.
- Reviewer/approver.
- Admin có scope giới hạn.
- Service identity/delegated subject.

Chuẩn bị object ở các trạng thái như DRAFT, PENDING, APPROVED, SUSPENDED, ARCHIVED hoặc DELETED tùy nghiệp vụ. Dùng dữ liệu giả lập có thể tái tạo, không dùng record khách hàng thật trừ khi có phê duyệt và kiểm soát phù hợp.

### 14.1. Safe test data và cleanup

Mỗi test case nên ghi:

- Test tenant/account.
- Object fixture ID.
- State ban đầu và expected state cuối.
- Side effect có thể xảy ra.
- Cách rollback hoặc cleanup.
- Người chịu trách nhiệm nếu test thất bại.

Với payment, email, SMS, webhook hoặc file processing, dùng sandbox/mock destination và dữ liệu giả. Nếu không thể tránh side effect, cần test plan riêng được phê duyệt. Không để test assessment tạo giao dịch thật hoặc gửi thông báo tới người dùng thật.

## 15. Bằng chứng và truy vết kết quả assessment

Mỗi test case nên liên kết với endpoint record để kết quả có thể tái lập:

- Endpoint ID và inventory version.
- Test case ID, thời điểm và tester/tool.
- Principal/client/tenant fixture được sử dụng.
- Object reference và state.
- Request/response đã redact.
- Authorization decision và business outcome quan sát được.
- Log/trace/request ID liên quan.
- Finding ID, severity và remediation owner nếu có.

Không lưu token, password, cookie hoặc payload nhạy cảm nguyên vẹn trong evidence. Chụp lại response đã mask; giữ raw artifact chỉ khi thật sự cần và có quyền truy cập/retention phù hợp.

### 15.1. Phân biệt finding với observation

Không phải mọi sai lệch inventory đều là vulnerability:

- Route không có trong spec là observation cần xác minh.
- Endpoint public không có authentication có thể là thiết kế hợp lệ nếu dữ liệu public; cần kiểm tra scope và abuse controls.
- Endpoint trả 403 cho user không có quyền là hành vi đúng, không phải finding.
- Endpoint có thể truy cập object tenant khác là finding cần bằng chứng và impact.

Ghi rõ expected behavior, observed behavior, evidence, affected endpoint, precondition và impact. Tránh kết luận chỉ từ tên route hoặc một status code.

## 16. Ví dụ đánh giá inventory cho một nhóm endpoint

Giả sử hệ thống quản lý tài liệu có các operation:

| Endpoint | Input chính | Dữ liệu/output | Quyền cần xác minh | Rủi ro nổi bật |
|---|---|---|---|---|
| POST /files | Multipart file, folder ID | Tạo file quarantine | Upload permission, tenant/folder scope | Malware, parser abuse, quota |
| GET /files/{id} | File ID | Metadata | Object/property authorization | BOLA, metadata leakage |
| GET /files/{id}/download | File ID | Binary/signed URL | Owner/share, file state CLEAN | Unauthorized download, stale URL |
| POST /files/{id}/share | User/email, permission | Share relationship | Owner/admin, allowed permission | Privilege escalation |
| GET /exports/{id} | Export ID | Report/file | Creator/tenant, export state | Cross-tenant data exposure |
| POST /webhooks | Event payload/signature | Event processing | Provider identity/signature | Spoofing, replay |

Từ inventory này, nhóm kiểm thử có thể xây dựng:

1. Upload file sai MIME, archive quá lớn và file test malware trong sandbox.
2. Đọc metadata/download file thuộc tenant khác.
3. Tải file khi trạng thái còn QUARANTINED hoặc đã REVOKED.
4. Thay permission trong share request để thử privilege escalation.
5. Truy cập export job do user khác tạo.
6. Gửi webhook signature sai hoặc replay event hợp lệ.

Mỗi test cần dùng fixture an toàn, endpoint nằm trong scope và expected result được owner xác nhận. Inventory chỉ định hướng test; kết luận cuối cùng phải dựa trên request/response, state và evidence thực tế.

## 17. Checklist trước khi bắt đầu kiểm thử

- [ ] Scope, environment, host, tenant, test account và rules of engagement đã được phê duyệt.
- [ ] Đã thu thập OpenAPI, source mapping, gateway/ingress, cloud và runtime evidence.
- [ ] Endpoint được định danh theo service, host, environment, version, method và route template.
- [ ] GraphQL, gRPC, WebSocket, webhook, file, admin và internal API nằm trong phạm vi đã được xem xét.
- [ ] Spec đã được đối chiếu với implementation và runtime.
- [ ] Endpoint ngoài scope được ghi nhận nhưng chưa active test khi chưa có phê duyệt.
- [ ] Mỗi endpoint có owner hoặc trạng thái unowned/needs review.
- [ ] Authentication mechanism và issuer/audience/client context được ghi nhận.
- [ ] Function, object, property và tenant authorization được mô tả.
- [ ] Input, output, data classification và downstream flow được ghi nhận.
- [ ] Business action, object state và side effect quan trọng được mapping.
- [ ] Rate limit, quota, size, timeout và pagination được ghi nhận nếu áp dụng.
- [ ] Endpoint được ưu tiên theo exposure, data sensitivity và business impact.
- [ ] Test matrix có principal, tenant, object, state, input và expected outcome.
- [ ] Test data là dữ liệu giả lập/sandbox; cleanup và rollback được xác định.
- [ ] Evidence format, redaction, request ID và finding owner đã được thống nhất.
- [ ] Inventory có version, nguồn bằng chứng, timestamp và trạng thái xác minh.

## Kết luận

Inventory endpoint là nền tảng để đánh giá API Security có phạm vi đầy đủ và kết quả có thể truy vết. Hãy xác nhận scope trước, discovery từ nhiều nguồn, chuẩn hóa từng operation theo host/environment/version/method/route, rồi bổ sung owner, authentication, authorization, object/tenant, dữ liệu và business flow. Đối chiếu spec với source và runtime để tìm endpoint bị bỏ sót; chuyển từng record thành test matrix và ưu tiên theo rủi ro. Khi inventory có nguồn bằng chứng, trạng thái xác minh và test data an toàn, nhóm đánh giá có thể kiểm thử đúng endpoint, đúng quyền và đúng tác động nghiệp vụ mà không vô tình mở rộng ra ngoài phạm vi được phép.

# Ghi endpoint, method, actor, object và tenant

Khi một API request bị từ chối sai, một người dùng đọc được dữ liệu tenant khác hoặc một service thực hiện hành động không được phép, đội vận hành cần trả lời được: request đi vào endpoint nào, dùng HTTP method nào, ai thực hiện, tác động tới object nào và thuộc tenant nào. Nếu log chỉ có dòng `POST /api/data returned 403`, điều tra thường không đủ dữ liệu để phân biệt người dùng, service, object và phạm vi tenant. Ngược lại, nếu log toàn bộ header và request body, hệ thống có thể vô tình lưu access token, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm.

API logging cần ghi nhận ngữ cảnh bảo mật theo cấu trúc rõ ràng. Endpoint và method cho biết bề mặt API được gọi; actor cho biết danh tính đã xác minh của caller; object cho biết tài nguyên bị truy cập; tenant cho biết ranh giới dữ liệu; action và outcome cho biết quyết định thực tế. Các trường này phải lấy từ nguồn tin cậy, được chuẩn hóa và bảo vệ theo chính sách dữ liệu.

Trong API Security, log không thay thế authorization và cũng không nên quyết định quyền truy cập. Log cung cấp bằng chứng để giám sát, điều tra, phát hiện lạm dụng và kiểm toán. Quyết định cho phép/từ chối vẫn phải được thực thi trong request path; log cần phản ánh quyết định đó một cách chính xác mà không làm lộ secret.

Sau bài học, người đọc có thể:

- Thiết kế event log có cấu trúc cho endpoint, method, actor, object và tenant.
- Phân biệt actor trực tiếp, subject/end user, client application và service identity.
- Ghi route template thay vì path chứa ID thực tế.
- Lấy object ID và tenant ID từ ngữ cảnh đã xác minh, không tin dữ liệu caller tự khai.
- Ghi action, authorization decision, status, outcome và correlation ID.
- Redact token, secret, payload và dữ liệu cá nhân khỏi log.
- Truyền context an toàn qua gateway, service, queue và background worker.
- Kiểm thử log cho request thành công, bị từ chối, cross-tenant và lỗi hệ thống.

## 1. Vì sao cần ghi endpoint, method, actor, object và tenant?

Một API request thường có nhiều chiều ngữ cảnh. Chỉ ghi URL hoặc status code không đủ để tái dựng sự kiện bảo mật.

| Trường | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Endpoint | Route/API nào được gọi? | `/api/orders/{orderId}` |
| Method | Request dùng HTTP method nào? | `GET`, `PATCH`, `POST` |
| Actor | Danh tính nào trực tiếp gửi request? | `user`, `service`, `api_client` |
| Subject | Hành động được thực hiện thay mặt ai? | `user-482` |
| Object | Tài nguyên nào bị đọc/thay đổi? | `order`, ID `ord-93` |
| Tenant | Tài nguyên và hành động thuộc phạm vi tenant nào? | `tenant-17` |
| Action | Ý nghĩa nghiệp vụ là gì? | `order.read`, `invoice.refund` |
| Outcome | Hành động được cho phép, từ chối hay thất bại? | `allowed`, `denied`, `error` |

Ví dụ hai request cùng gọi `GET /api/orders/{orderId}` có thể có kết quả khác nhau:

- User A đọc đơn hàng thuộc tenant A và được phép.
- User B đoán ID đơn hàng tenant A và bị từ chối.

Nếu log chỉ ghi endpoint, method và status, đội bảo mật khó xác định đây là truy cập hợp lệ hay hành vi dò object. Nếu có actor, object, tenant, authorization outcome và request ID, sự kiện có thể được phân tích rõ hơn.

### 1.1. Log phải phản ánh quyết định thực tế

Không ghi `allowed` chỉ vì controller đã được gọi; authorization có thể xảy ra sau đó. Không ghi `success` chỉ vì HTTP status là `200`; nghiệp vụ bên trong có thể trả kết quả thất bại trong response. Xác định rõ từng loại outcome:

- `authorization_decision`: `allow`, `deny`, `not_evaluated`.
- `http_status`: status HTTP cuối cùng.
- `operation_outcome`: `success`, `rejected`, `failed`, `partial` theo hợp đồng nghiệp vụ.
- `reason_code`: mã lý do có cấu trúc, không phải stack trace hay nội dung nhạy cảm.

Một request bị từ chối bởi authentication có thể chưa có actor user hợp lệ; khi đó actor có thể là `anonymous` hoặc `unknown`, kèm lý do `authentication_required`. Không bịa actor ID từ dữ liệu request chưa xác minh.

## 2. Phân biệt access log, security event và audit log

Các loại log có mục đích khác nhau. Có thể dùng chung nền tảng thu thập, nhưng nên phân biệt schema, retention, quyền truy cập và yêu cầu toàn vẹn.

| Loại log | Mục tiêu | Ví dụ | Đặc điểm |
|---|---|---|---|
| Access log | Ghi nhận request HTTP và kết quả ở mức vận hành | Method, route, status, latency, request ID | Khối lượng lớn, có thể sampling với endpoint ít nhạy cảm nếu vẫn giữ số liệu tổng hợp |
| Security event log | Ghi sự kiện liên quan xác thực, phân quyền và hành vi đáng ngờ | Login fail, cross-tenant deny, token invalid, privilege change | Cần giữ đủ chi tiết để phát hiện và điều tra |
| Audit log | Ghi bằng chứng hành động nghiệp vụ quan trọng | Ai đổi quyền, ai hoàn tiền, ai export dữ liệu | Cần actor, subject, object, tenant, before/after phù hợp, thời điểm và tính toàn vẹn cao |

Ví dụ, một lần gọi `GET /orders/123` có thể xuất hiện trong access log. Nếu bị từ chối do user không thuộc tenant, có thể tạo security event. Nếu một quản trị viên thay đổi owner của đơn hàng, hệ thống cần audit event ghi hành động nghiệp vụ và kết quả thay đổi.

Không phải mọi request đều cần lưu toàn bộ thành audit event. Hãy xác định hành động nào có giá trị kiểm toán hoặc rủi ro cao, chẳng hạn thay đổi quyền, truy cập dữ liệu nhạy cảm, export, download, thanh toán, hoàn tiền, xóa hoặc thay đổi cấu hình bảo mật.

## 3. Endpoint và method: ghi route template, không ghi URL tùy tiện

Endpoint nên được ghi theo route template do router/framework xác định, ví dụ:

```text
GET    /api/orders/{orderId}
PATCH  /api/orders/{orderId}
POST   /api/orders/{orderId}/refunds
GET    /api/tenants/{tenantId}/members
```

Tránh ghi raw URL đầy đủ nếu query string có thể chứa token, email, search term, reset code hoặc dữ liệu cá nhân. Route template cũng giúp nhóm log theo endpoint mà không tạo hàng triệu giá trị khác nhau do object ID.

### 3.1. Ghi HTTP method và action riêng biệt

HTTP method mô tả cách request tương tác với resource ở tầng HTTP. Action mô tả ý nghĩa nghiệp vụ. Ví dụ:

| HTTP method/endpoint | Action nghiệp vụ có thể ghi |
|---|---|
| `GET /api/orders/{id}` | `order.read` |
| `PATCH /api/orders/{id}` | `order.update` |
| `POST /api/orders/{id}/refunds` | `payment.refund.request` |
| `DELETE /api/users/{id}` | `user.delete` |

Không suy ra action chỉ từ method. Một `POST` có thể là search, create, approve hoặc execute; một `PATCH` có thể chỉ thay ghi chú hoặc thay đổi trạng thái quan trọng. Action nên là mã ổn định do ứng dụng định nghĩa, không lấy trực tiếp từ chuỗi client gửi.

### 3.2. Chuẩn hóa route và tránh log ID trong metric label

Route template phù hợp cho metric và dashboard. ID object có thể cần trong security/audit log để điều tra, nhưng không nên đưa ID tùy ý vào metric label vì cardinality tăng nhanh và có thể lộ định danh.

Ví dụ metric tốt:

```text
api_requests_total{
  route="/api/orders/{orderId}",
  method="GET",
  status="403"
}
```

Không tạo metric như `api_requests_total{url="/api/orders/ord-123456"}`. Nếu cần điều tra một object cụ thể, dùng log có kiểm soát và truy vấn theo request/object ID.

### 3.3. Không tin route/path do caller tự khai

Ghi route được framework match hoặc gateway đã chuẩn hóa. Không lấy `X-Original-URL`, `X-Rewrite-URL` hay header tương tự từ Internet làm endpoint thực tế nếu proxy chưa xóa và ghi đè. Nếu hệ thống có rewrite, cần ghi cả route public và route nội bộ bằng hai field riêng, kèm nguồn xác định tin cậy.

## 4. Actor, subject và client identity

Một request không phải lúc nào cũng chỉ có một danh tính. Trong kiến trúc API nhiều tầng, cần phân biệt:

- **Actor:** principal trực tiếp thực hiện request tại service hiện tại.
- **Subject:** người dùng hoặc thực thể mà hành động đang đại diện.
- **Client application:** ứng dụng gọi API, ví dụ web frontend, mobile app hoặc integration.
- **Service identity:** workload/service account gọi downstream.
- **Delegator/initiator:** actor đã ủy quyền hoặc khởi tạo hành động trong một workflow.

Ví dụ BFF nhận request từ user A rồi gọi `order-service`:

```text
actor.service = bff-service
subject.user = user-A
client.id = customer-web
delegation = user-A -> bff-service
```

Ở `order-service`, actor trực tiếp có thể là `bff-service`, subject vẫn là user A nếu delegation context được xác minh. Không ghi BFF như thể nó là end user; cũng không ghi user A như thể họ trực tiếp kết nối tới service nếu request thực tế đến từ workload.

### 4.1. Chỉ ghi danh tính đã xác minh

Nguồn đáng tin có thể là:

- Principal do authentication middleware tạo sau khi xác minh token/session.
- Workload identity hoặc mTLS principal đã được xác minh.
- API client ID đã được xác thực bằng credential tương ứng.
- Delegated subject/actor claim từ token/assertion có issuer, audience và chữ ký hợp lệ.

Không lấy `userId`, `role`, `actorId` hoặc `tenantId` từ JSON body hay query string rồi ghi thành danh tính tin cậy. Client có thể gửi các trường đó để giả mạo context. Nếu cần lưu giá trị caller yêu cầu, ghi riêng dưới tên như `requested_owner_id` hoặc `requested_tenant_id` và đánh dấu là untrusted; chỉ làm vậy khi thực sự cần cho điều tra.

### 4.2. Request chưa được xác thực

Với request bị từ chối trước authentication, có thể ghi:

```json
{
  "actor_type": "anonymous",
  "actor_id": null,
  "authentication_outcome": "failed",
  "reason_code": "INVALID_CREDENTIAL"
}
```

Không ghi toàn bộ token sai hoặc password để xác định caller. Có thể ghi nguồn mạng ở dạng phù hợp, client identifier không nhạy cảm nếu có và request ID.

### 4.3. Không dùng IP làm actor ID

IP không phải danh tính ổn định. Nhiều user có thể dùng chung NAT, proxy hoặc mobile carrier; một user có thể đổi IP. IP có thể là thuộc tính nguồn mạng hữu ích cho điều tra, nhưng không thay thế actor/client/workload identity.

## 5. Object: ghi tài nguyên nào bị tác động

Object context giúp điều tra truy cập sai phạm vi, dò ID, thay đổi dữ liệu và hành động đặc quyền. Tùy loại API, object có thể là:

- `order`, `invoice`, `payment`, `refund`.
- `user`, `profile`, `role`, `membership`.
- `file`, `document`, `report`, `export_job`.
- `tenant`, `project`, `workspace`, `subscription`.
- `webhook_endpoint`, `api_key`, `credential`, `policy`.

Nên ghi `object_type` và `object_id` tách biệt. Với hành động tác động nhiều object, có thể ghi `object_count` và danh sách reference có giới hạn hoặc tạo audit child event riêng. Không nhồi toàn bộ object payload vào log.

Ví dụ:

```json
{
  "object_type": "invoice",
  "object_id": "inv-83f2",
  "object_version": "17"
}
```

`object_version` hữu ích khi audit thay đổi hoặc điều tra race condition. Với dữ liệu nhạy cảm, cân nhắc dùng internal ID không mang ý nghĩa, tokenized reference hoặc HMAC pseudonym thay cho giá trị trực tiếp.

### 5.1. Object được yêu cầu và object thực tế

Một request có thể chứa ID do caller yêu cầu, nhưng service có thể resolve sang object khác hoặc từ chối trước khi tìm thấy. Nếu cần phân biệt, ghi:

- `requested_object_ref`: reference chưa được xác minh hoặc ID caller cung cấp.
- `object_type`/`object_id`: object đã resolve trong phạm vi tin cậy.
- `authorization_decision`: kết quả kiểm tra quyền.

Không ghi object ID chưa được xác minh như thể đó là object đã được truy cập thành công. Với response `404` được dùng để che giấu sự tồn tại, có thể không ghi chi tiết object cho log thông thường; security event nội bộ có thể giữ reference theo policy điều tra.

### 5.2. Nhiều object và bulk API

Với bulk update/export, một request có thể tác động hàng nghìn object. Không ghi một JSON array không giới hạn vào một log event. Có thể ghi:

- `object_type` và `object_count`.
- ID của batch/job.
- Số lượng thành công/thất bại.
- Một số reference mẫu nếu được phép.
- Audit event riêng theo từng object đối với hành động có rủi ro cao.

Giới hạn số reference trong event để tránh log injection, chi phí lưu trữ và lộ dữ liệu quá mức. Nếu cần truy vết đầy đủ, lưu manifest/batch result trong kho audit có kiểm soát và tham chiếu bằng ID.

## 6. Tenant: ghi đúng ranh giới dữ liệu

Trong hệ thống multi-tenant, tenant context rất quan trọng để phát hiện truy cập chéo tenant và điều tra hành động trên dữ liệu tổ chức. Nhưng tenant ID phải đến từ context đã xác minh.

Nguồn tenant đáng tin có thể là:

- Claim trong access token đã xác minh và có issuer/audience phù hợp.
- Membership/relationship được server tra cứu từ actor đã xác thực.
- Tenant context được gateway/service upstream xác thực, ký hoặc truyền qua kết nối workload tin cậy.
- Tenant được suy ra từ object đã resolve và đối chiếu với quyền caller.

Không tin `X-Tenant-Id` từ request Internet nếu gateway không xóa giá trị client gửi và tự thiết lập header mới trong trust boundary được bảo vệ. Không tin `tenantId` trong body chỉ vì frontend đã gửi.

### 6.1. Ghi cả requested tenant và effective tenant khi cần

Một request có thể yêu cầu tenant cụ thể nhưng authorization layer xác định tenant hiệu lực khác hoặc từ chối. Nếu điều tra cần cả hai, dùng tên rõ ràng:

```json
{
  "requested_tenant_id": "tenant-from-request",
  "effective_tenant_id": "tenant-17",
  "tenant_context_source": "verified_token_claim",
  "authorization_decision": "deny",
  "reason_code": "TENANT_SCOPE_MISMATCH"
}
```

Ví dụ trên minh họa cách phân biệt nguồn. Không nên lưu `requested_tenant_id` nếu nó không có giá trị điều tra; đây là dữ liệu do caller kiểm soát và phải được đánh dấu untrusted.

### 6.2. Không làm lộ tenant khác qua log

Log search/dashboard cần áp dụng quyền truy cập tương tự dữ liệu nghiệp vụ. Nhân viên tenant A không được tìm log có object ID hoặc tenant B nếu chính sách không cho phép. Dùng index/partition theo tenant khi phù hợp, nhưng vẫn kiểm soát authorization ở tầng truy vấn; partition vật lý không thay thế kiểm tra quyền.

Đội vận hành toàn hệ thống có thể cần quyền xem đa tenant, nhưng phải được cấp riêng, giới hạn mục đích, audit việc truy cập log và bảo vệ dữ liệu theo phân loại.

## 7. Event schema có cấu trúc

Log nên là event có field ổn định, kiểu dữ liệu nhất quán và có version. Ví dụ schema tối thiểu:

```json
{
  "schema_version": "1.0",
  "timestamp": "2026-11-18T10:15:30.123Z",
  "event_type": "api.request.completed",
  "service": "order-service",
  "environment": "production",
  "request_id": "req-7f31",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "http": {
    "method": "PATCH",
    "route": "/api/orders/{orderId}",
    "status_code": 200
  },
  "actor": {
    "type": "user",
    "id": "user-482"
  },
  "subject": {
    "type": "user",
    "id": "user-482"
  },
  "client": {
    "id": "customer-web"
  },
  "tenant": {
    "id": "tenant-17"
  },
  "action": "order.update",
  "object": {
    "type": "order",
    "id": "ord-93",
    "version": "8"
  },
  "authorization": {
    "decision": "allow",
    "policy": "order-owner-update"
  },
  "outcome": "success",
  "duration_ms": 42
}
```

Đây là ví dụ cấu trúc, không phải mọi event đều phải có tất cả field. Request anonymous sẽ không có actor ID; request chưa resolve object sẽ không có object ID; tenant không xác định phải là null/unknown thay vì tự suy đoán. Giữ tên field nhất quán giữa service để correlation và phân tích không cần đoán.

### 7.1. Tách field chuẩn và custom field

Định nghĩa schema chung cho các field như timestamp, service, environment, route, method, actor, tenant, request ID và outcome. Field riêng của domain có thể đặt dưới namespace `business` hoặc `attributes`, nhưng phải có quy ước tên, kiểu và giới hạn.

Không cho caller gửi key tùy ý rồi đưa nguyên map vào log. Attacker có thể tạo field giả như `authorization.decision=allow`, nhồi dữ liệu lớn hoặc đưa ký tự điều khiển vào log. Field bảo mật phải do server tạo; input bên ngoài nếu cần ghi phải được encode, giới hạn và đặt tên thể hiện nguồn không tin cậy.

### 7.2. Schema versioning

Khi đổi schema, thêm `schema_version` hoặc `event_version`. Thêm field optional thường dễ tương thích hơn đổi kiểu/xóa field. Consumer như SIEM, alert, audit viewer và data pipeline cần được cập nhật theo kế hoạch. Không tái sử dụng cùng tên field với ý nghĩa khác nhau giữa các service.

## 8. Correlation ID, trace ID và request ID

Để theo dõi một request qua nhiều service, dùng correlation/request ID và distributed trace ID. Các ID này giúp nối access log, security event, audit event và downstream call.

- `request_id`: định danh một request tại service/hop hiện tại hoặc theo quy ước xuyên suốt.
- `trace_id`: định danh trace phân tán theo W3C Trace Context hoặc tracing framework.
- `parent_span_id`: liên kết span hiện tại với caller span.
- `event_id`: định danh một audit/security event riêng biệt.

Không nhầm request ID với actor ID hoặc event ID. Một actor có thể tạo nhiều request; một request có thể phát sinh nhiều event.

### 8.1. Xử lý correlation ID do client gửi

Client có thể gửi `X-Request-Id` hoặc `traceparent`. Có thể tiếp nhận để hỗ trợ trace, nhưng cần validate định dạng và độ dài. Không dùng correlation ID làm bằng chứng xác thực, khóa authorization hoặc secret. Nếu cần ID nội bộ đáng tin, tạo ID mới tại edge hoặc ghi cả `external_request_id` và `request_id` do server cấp.

Không đưa dữ liệu nhạy cảm vào trace baggage hoặc span attributes. Trace thường được chia sẻ giữa nhiều hệ thống và có retention riêng; cần redaction giống log.

## 9. Không log secret và payload nhạy cảm

Log có thể trở thành kho dữ liệu nhạy cảm có phạm vi truy cập rộng. Tuyệt đối không ghi trực tiếp:

- Password, OTP, reset token và recovery code.
- `Authorization`, bearer token, refresh token, cookie và session ID thô.
- API key, client secret, private key và credential database.
- Nội dung file upload, raw multipart body hoặc signed URL đầy đủ.
- Số thẻ thanh toán, dữ liệu xác thực tài chính hoặc dữ liệu định danh không cần thiết.
- Toàn bộ request/response body nếu không có mục đích và kiểm soát cụ thể.

### 9.1. Allowlist field thay vì blocklist đơn thuần

An toàn hơn là định nghĩa field nào được phép log cho từng event. Ví dụ access log có route, method, status, duration và client ID; audit event có actor, object, tenant, action và outcome. Không serialize toàn bộ request object rồi cố xóa vài field nhạy cảm sau đó, vì field mới có thể được thêm mà không được redaction.

Nếu cần ghi một phần dữ liệu để điều tra, tạo representation riêng đã mask/tokenize. Ví dụ chỉ lưu 4 số cuối của mã tham chiếu nếu policy cho phép, không lưu toàn bộ số tài khoản. Với định danh cần đối chiếu nhưng không muốn lộ trực tiếp, có thể dùng HMAC với key quản lý riêng để tạo pseudonymous identifier; hash không khóa của email/phone có thể bị dò ngược bằng dictionary.

### 9.2. Redaction phải áp dụng ở mọi tầng

Kiểm tra redaction tại:

- Application logger và exception handler.
- API gateway, reverse proxy và web server access log.
- HTTP client log khi gọi downstream.
- Distributed tracing và baggage.
- Message broker, dead-letter queue và background worker.
- SIEM/observability exporter và diagnostic endpoint.

Không bật debug logging toàn bộ request trong production để xử lý sự cố mà không đánh giá dữ liệu. Nếu cần bật tạm, phải có phạm vi, thời hạn, quyền truy cập và redaction được kiểm chứng.

## 10. Log injection và dữ liệu do caller kiểm soát

Nếu ghi chuỗi do client gửi trực tiếp, attacker có thể chèn newline, tab hoặc ký tự điều khiển để giả mạo log entry hoặc phá cấu trúc parser. JSON logger thường escape ký tự chuỗi đúng cách, nhưng không nên giả định mọi sink và downstream parser đều xử lý an toàn.

Nguyên tắc:

- Dùng structured logger thay vì nối chuỗi tự do.
- Giới hạn độ dài field và loại bỏ/encode ký tự điều khiển theo schema.
- Không đưa raw URL/query/body vào message text.
- Dùng enum/code ổn định cho outcome và reason.
- Không cho caller điều khiển tên field hoặc log level.
- Xác minh parser downstream không diễn giải lại nội dung thành field mới.

Ví dụ không tốt:

```java
log.warn("Denied request from " + userInput + " because " + reason);
```

Ví dụ tốt hơn:

```java
log.atWarn()
   .addKeyValue("event_type", "authorization.denied")
   .addKeyValue("actor_id", actorId)
   .addKeyValue("route", routeTemplate)
   .addKeyValue("object_type", objectType)
   .addKeyValue("reason_code", "OBJECT_SCOPE_DENIED")
   .log("API request denied");
```

Ví dụ thứ hai vẫn cần bảo đảm `actorId`, `route` và `objectType` đã được chuẩn hóa, không phải field tùy ý do client cung cấp.

## 11. Ghi log trong Spring Boot

Một cách triển khai là dùng filter/interceptor để ghi access context và ghi security/audit event tại nơi quyết định nghiệp vụ. Filter có thể lấy method, route sau khi handler được xác định, status và request ID; service layer biết actor, tenant, object và action chính xác hơn.

### 11.1. Access context ở filter

Ví dụ khung với `OncePerRequestFilter`:

```java
@Component
class ApiAccessLoggingFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(ApiAccessLoggingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String requestId = requestIdProvider.getOrCreate(request);
        long started = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long durationMs = (System.nanoTime() - started) / 1_000_000;
            log.atInfo()
                    .addKeyValue("event_type", "api.request.completed")
                    .addKeyValue("request_id", requestId)
                    .addKeyValue("method", request.getMethod())
                    .addKeyValue("status_code", response.getStatus())
                    .addKeyValue("duration_ms", durationMs)
                    .log("API request completed");
        }
    }
}
```

Đây là skeleton. `requestIdProvider` cần validate ID do client gửi hoặc tạo ID nội bộ. `request.getRequestURI()` không nên được log nguyên dạng nếu path chứa dữ liệu nhạy cảm; ưu tiên route template từ handler mapping. Filter có thể chạy trước khi security context được thiết lập hoặc sau khi response đã commit, vì vậy không nên cố tự suy ra actor/object/tenant tại đây.

### 11.2. Lấy route template sau khi handler được match

Trong Spring MVC, route template có thể được lấy từ request attribute do `HandlerMapping` thiết lập, ví dụ `BEST_MATCHING_PATTERN_ATTRIBUTE`, sau khi dispatcher đã chọn handler. Cần xử lý trường hợp request bị từ chối trước khi route mapping hoàn tất hoặc không có handler. Có thể ghi `route="UNMATCHED"` cùng status/reason, không fallback sang raw URI nếu URI có thể chứa secret.

### 11.3. Security event tại authorization boundary

Service layer có đầy đủ thông tin về actor, object và tenant. Nên phát event ngay sau quyết định authorization, nhưng tránh tạo log cho phép trước khi thao tác thật sự thành công nếu event muốn mô tả outcome cuối cùng.

```java
public Order getOrder(UUID orderId, ApiPrincipal principal) {
    Order order = orderRepository
            .findByIdAndTenantId(orderId, principal.tenantId())
            .orElseThrow(OrderNotFoundException::new);

    AuthorizationDecision decision =
            orderAuthorization.canRead(principal, order);

    securityEventLogger.recordAccessDecision(
            principal.actorId(),
            principal.subjectId(),
            principal.tenantId(),
            "order.read",
            "order",
            order.getId(),
            decision);

    decision.requireGranted();
    return order;
}
```

Ví dụ này giả định `principal` đã được xác minh và repository đã giới hạn tenant. Trong hệ thống cần audit transaction chính xác, cân nhắc ghi audit event trong cùng transaction hoặc dùng transactional outbox để tránh trường hợp dữ liệu commit nhưng audit event bị mất, hoặc audit ghi thành công dù transaction rollback.

Không log toàn bộ entity `order`. Ghi object type/ID, action, tenant, decision và những thay đổi được policy cho phép.

### 11.4. MDC và context cleanup

Nếu dùng MDC để tự động gắn request ID, trace ID hoặc actor ID vào log, phải xóa context trong `finally` khi request kết thúc. Thread pool tái sử dụng thread; thiếu cleanup có thể làm log của request sau mang nhầm actor/tenant trước đó.

MDC/ThreadLocal không tự truyền an toàn qua `@Async`, executor, reactive pipeline hoặc message broker. Dùng context propagation có chủ đích; chỉ truyền các field cần thiết và xác minh nguồn. Với asynchronous task, lưu context trong message envelope đã được xác thực/ký hoặc metadata nội bộ đáng tin cậy, không dựa vào ThreadLocal còn sót.

## 12. Truyền actor/object/tenant qua nhiều service

Một request có thể đi qua gateway, BFF, domain service và data service. Mỗi service nên ghi actor trực tiếp của hop hiện tại và subject cuối nếu có delegation đã xác minh.

Ví dụ:

```text
Browser user-A
  -> API Gateway
  -> order-service
  -> document-service
```

Ở `order-service`:

```json
{
  "actor": {"type": "user", "id": "user-A"},
  "subject": {"type": "user", "id": "user-A"},
  "tenant": {"id": "tenant-1"},
  "action": "order.invoice.read",
  "object": {"type": "order", "id": "order-7"}
}
```

Ở `document-service`, actor trực tiếp có thể là workload `order-service`, còn subject là user A nếu delegated token/assertion hợp lệ:

```json
{
  "actor": {"type": "service", "id": "order-service"},
  "subject": {"type": "user", "id": "user-A"},
  "tenant": {"id": "tenant-1"},
  "action": "invoice.read",
  "object": {"type": "invoice", "id": "invoice-9"}
}
```

Không tin các header `X-Actor-Id`, `X-User-Id` hoặc `X-Tenant-Id` từ client bên ngoài. Gateway phải loại bỏ header giả mạo và thiết lập context từ identity đã xác minh. Downstream chỉ chấp nhận context qua trust boundary có xác thực, ví dụ signed token, mTLS workload identity hoặc message envelope được bảo vệ.

### 12.1. Queue và background job

Khi API tạo job chạy sau, actor/subject/tenant context có thể cần được giữ để audit. Message nên có:

- `initiated_by` hoặc actor ID đã xác minh.
- Subject/delegation reference nếu job thực hiện thay user.
- Tenant ID từ context tin cậy.
- Business action và object reference.
- Request/trace correlation ID.
- Thời điểm khởi tạo và job ID.

Worker cần xác minh nguồn message, quyền hiện tại và trạng thái nghiệp vụ theo policy. Không mặc định quyền của user tại thời điểm tạo job vẫn còn hiệu lực khi job chạy; với thao tác nhạy cảm, cần kiểm tra lại quyền hoặc lưu quyết định ủy quyền có thời hạn rõ ràng.

## 13. Privacy, retention và quyền truy cập log

Log chứa actor, object và tenant ID có thể là dữ liệu cá nhân hoặc dữ liệu kinh doanh nhạy cảm. Bảo vệ log như một tài sản dữ liệu:

- Phân loại field và xác định mục đích thu thập.
- Chỉ thu thập field cần thiết; không log payload theo mặc định.
- Mask/tokenize hoặc pseudonymize định danh khi có thể.
- Mã hóa khi truyền và khi lưu.
- Giới hạn quyền đọc theo vai trò và mục đích; audit việc truy cập log.
- Đặt retention theo loại log, nghĩa vụ pháp lý và nhu cầu điều tra.
- Xóa/ẩn danh dữ liệu khi hết mục đích lưu trữ, theo policy.
- Không dùng log production làm dữ liệu thử nghiệm mà không xử lý phù hợp.

Access log có thể có retention ngắn hơn audit log. Audit log cho thay đổi quyền hoặc giao dịch quan trọng có thể cần giữ lâu hơn và có kiểm soát toàn vẹn. Không giữ mọi request vô thời hạn chỉ vì dung lượng lưu trữ còn đủ.

### 13.1. Tính toàn vẹn và chống sửa log

Đối với audit event quan trọng, cân nhắc:

- Ghi vào kho append-only hoặc hệ thống có retention lock.
- Quyền ghi tách khỏi quyền đọc/quản trị.
- Đồng bộ thời gian và timestamp UTC.
- Hash chain hoặc chữ ký/batch digest để phát hiện sửa đổi nếu threat model yêu cầu.
- Transactional outbox để gắn audit event với commit nghiệp vụ.
- Sao lưu và kiểm tra khả năng phục hồi.

Hash chain không tự ngăn người có quyền xóa cả kho hoặc thay khóa; cần bảo vệ key, quyền quản trị và bản sao độc lập. Chọn mức bảo vệ theo rủi ro và yêu cầu audit.

## 14. Tìm kiếm và phát hiện bất thường

Khi schema ổn định, có thể tạo rule phát hiện:

- Một actor truy cập nhiều object thuộc nhiều tenant trong thời gian ngắn.
- Nhiều lần `authorization_decision=deny` trên cùng route hoặc nhiều object ID tuần tự.
- Service identity truy cập object ngoài phạm vi workload thông thường.
- Một actor thực hiện action nhạy cảm ngoài thời gian hoặc vị trí vận hành thường lệ.
- Một tenant có lượng export/download tăng đột biến.
- Một endpoint admin được gọi từ client hoặc workload không mong đợi.
- Log ghi `tenant_id` không khớp tenant của object đã resolve.
- Nhiều request không có actor/client identity tới endpoint cần authentication.

Rule cần tránh false positive do batch job, support operation hoặc traffic theo mùa. Kết hợp baseline, allowlist có thời hạn, owner và business context. Không tạo cảnh báo dựa trên một field đơn lẻ nếu field đó có thể bị caller kiểm soát.

### 14.1. Ví dụ truy vấn điều tra cross-tenant

Giả sử log đã chuẩn hóa trong bảng `api_security_events`:

```sql
SELECT
    actor_id,
    tenant_id,
    object_type,
    COUNT(*) AS denied_requests,
    COUNT(DISTINCT object_id) AS distinct_objects,
    MIN(event_time) AS first_seen,
    MAX(event_time) AS last_seen
FROM api_security_events
WHERE event_type = 'authorization.denied'
  AND reason_code IN ('TENANT_SCOPE_MISMATCH', 'OBJECT_SCOPE_DENIED')
  AND event_time >= :window_start
  AND event_time < :window_end
GROUP BY actor_id, tenant_id, object_type
HAVING COUNT(*) >= :threshold
ORDER BY denied_requests DESC;
```

Đây là truy vấn minh họa; schema và cú pháp phụ thuộc hệ thống lưu log. Cần giới hạn quyền truy cập kết quả, tránh hiển thị actor/object ID cho người không có thẩm quyền và xem xét cả request hợp lệ lẫn bị từ chối để hiểu hành vi.

## 15. Kiểm thử log cho API

Test cần xác minh log có đủ ngữ cảnh, dùng đúng nguồn dữ liệu và không chứa secret.

| Tình huống | Điều cần kiểm tra |
|---|---|
| Request thành công | Có route template, method, actor, subject, object, tenant, action, outcome và request ID phù hợp |
| Authentication thất bại | Actor được ghi anonymous/unknown; không lưu token/password |
| Authorization bị từ chối | Có actor, route, object/tenant nếu đã resolve an toàn, decision deny và reason code |
| Cross-tenant access | Tenant context tin cậy và mismatch được ghi nhận; không lộ dữ liệu tenant khác |
| Client gửi giả `X-Tenant-Id` | Log dùng effective tenant từ context xác minh, không tin header giả |
| Bulk operation | Ghi count/job reference có giới hạn, không log payload vô hạn |
| Exception | Có request ID, route, outcome; không có stack trace/secret trong response hoặc log public |
| Async job | Actor/subject/tenant/correlation được truyền có kiểm soát, không rò context giữa thread |
| Thread reuse | MDC được cleanup; request sau không mang actor/tenant của request trước |
| Log injection | Newline/control characters không tạo log record giả |
| Secret redaction | Token, cookie, password, API key và signed URL không xuất hiện |
| Schema compatibility | Consumer đọc được event version mới và field optional |
| Audit transaction | Rollback không để audit success sai; commit không làm mất audit bắt buộc |

### 15.1. Integration test kiểm tra structured log

Trong test Spring Boot, có thể dùng appender test hoặc log capture để xác minh key-value event. Ví dụ pseudo-test:

```java
mockMvc.perform(get("/api/orders/{id}", orderId)
        .with(user("user-A").authorities("order:read")))
    .andExpect(status().isOk());

assertThat(capturedEvents)
    .anySatisfy(event -> {
        assertThat(event.get("route"))
                .isEqualTo("/api/orders/{orderId}");
        assertThat(event.get("method")).isEqualTo("GET");
        assertThat(event.get("actor_id")).isEqualTo("user-A");
        assertThat(event.get("tenant_id")).isEqualTo("tenant-A");
        assertThat(event.get("object_type")).isEqualTo("order");
        assertThat(event.get("authorization_decision")).isEqualTo("allow");
    });
```

Đây là pseudo-test; cách capture log phụ thuộc logging backend. Test cần tạo principal/tenant context đúng với ứng dụng và xác minh object thuộc đúng tenant. Thêm assertion rằng event không chứa `Authorization`, cookie, password hoặc body nhạy cảm.

### 15.2. Kiểm tra log không làm lộ secret

Tạo request test có token giả, cookie giả, password marker và payload chứa chuỗi đánh dấu duy nhất. Sau request, quét toàn bộ captured log, trace và exception output để chắc chắn các marker bí mật không xuất hiện. Không chỉ kiểm tra message text; secret có thể nằm trong structured attribute hoặc nested exception.

## 16. Checklist triển khai

- [ ] Có schema structured logging với version và tên field thống nhất.
- [ ] Endpoint được ghi bằng route template, không phải raw URL/query nhạy cảm.
- [ ] HTTP method và business action được ghi riêng.
- [ ] Actor, subject, client và service identity được phân biệt.
- [ ] Actor/subject chỉ lấy từ principal hoặc delegation đã xác minh.
- [ ] Object type/ID được ghi theo policy; bulk reference có giới hạn.
- [ ] Tenant ID lấy từ context tin cậy và được đối chiếu với object.
- [ ] Requested tenant/object do caller gửi được đánh dấu untrusted nếu cần ghi.
- [ ] Có authorization decision, outcome và reason code rõ ràng.
- [ ] Request ID/trace ID được validate và truyền xuyên service an toàn.
- [ ] MDC/thread context được cleanup và propagation đúng cho async/reactive.
- [ ] Token, password, cookie, secret và payload nhạy cảm không được log.
- [ ] Structured logging chống log injection và giới hạn độ dài field.
- [ ] Log store có encryption, access control, retention và audit phù hợp.
- [ ] Audit event quan trọng có cơ chế bảo đảm tính toàn vẹn và gắn với transaction.
- [ ] Có alert cho deny bất thường, cross-tenant, object enumeration và service identity bất thường.
- [ ] Có test log cho success, deny, authentication failure, async context, injection và redaction.

## Kết luận

Log endpoint, method, actor, object và tenant tạo ngữ cảnh cần thiết để hiểu một API request đã đi đâu, do ai thực hiện và tác động tới tài nguyên thuộc phạm vi nào. Hãy ghi route template và business action ổn định; phân biệt actor trực tiếp với subject được đại diện; lấy object/tenant từ dữ liệu đã xác minh; và ghi authorization decision cùng outcome. Structured logging, correlation ID, context propagation và audit integrity giúp điều tra hiệu quả, trong khi allowlist field, redaction, quyền truy cập và retention ngăn log trở thành một nguồn rò rỉ dữ liệu mới.

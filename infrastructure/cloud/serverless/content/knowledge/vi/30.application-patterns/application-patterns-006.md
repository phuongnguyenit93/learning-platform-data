# Xây dựng backend serverless cho ứng dụng web và di động

Một ứng dụng web hoặc di động thường cần backend để xác thực người dùng, kiểm tra quyền, lưu dữ liệu, xử lý nghiệp vụ, nhận tệp tải lên, gửi thông báo và đồng bộ trạng thái giữa nhiều thiết bị. Với kiến trúc serverless, các chức năng backend được triển khai dưới dạng API, Java function, event handler và workflow do nền tảng cloud quản lý. Nhóm phát triển tập trung vào hợp đồng API, logic nghiệp vụ, dữ liệu và vận hành; nền tảng cung cấp khả năng thực thi, mở rộng và tích hợp dịch vụ theo cấu hình.

Serverless không có nghĩa là không cần thiết kế backend. Một ứng dụng vẫn cần ranh giới bảo mật, mô hình dữ liệu, authorization, kiểm soát tải, idempotency, quan sát hệ thống, quản lý chi phí và chiến lược triển khai. Nếu chỉ chuyển từng endpoint thành function mà không xem xét luồng nghiệp vụ, hệ thống có thể phát sinh quá nhiều lần gọi, dữ liệu không nhất quán hoặc chi phí khó dự đoán.

Trong module **CLOUD_SERVERLESS**, người học xây dựng Java function được kích hoạt bởi HTTP, message hoặc event, xử lý trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Bài này xây dựng một backend serverless cho cả web và mobile, từ kiến trúc tổng thể đến API, identity, dữ liệu, realtime, offline sync, bảo mật, kiểm thử và triển khai.

## 1. Mục tiêu và yêu cầu của backend web/mobile

Backend cần cung cấp một tập capability ổn định cho nhiều loại client:

- Web browser chạy trên desktop hoặc tablet.
- Ứng dụng native trên iOS/Android.
- Ứng dụng cross-platform.
- Admin portal hoặc internal tool.
- Partner integration hoặc webhook từ hệ thống khác.

Các client có đặc điểm khác nhau. Browser thường có kết nối tương đối ổn định và có thể dựa vào cookie/session. Mobile có mạng không ổn định, app có thể bị suspend, người dùng có thể offline và request có thể được gửi lại sau khi app khởi động. Một API backend tốt phải xử lý được các tình huống này mà không dựa vào giả định client luôn trực tuyến hoặc chỉ gửi request một lần.

Những capability thường gặp:

| Capability | Trách nhiệm backend |
|---|---|
| Identity | Đăng nhập, xác minh token, refresh/revoke session |
| Profile | Đọc và cập nhật thông tin người dùng |
| Authorization | Kiểm tra quyền theo user, tenant, resource và action |
| Business API | Xử lý đơn hàng, thanh toán, nội dung hoặc nghiệp vụ |
| Data access | Lưu, truy vấn, phân trang và bảo đảm consistency |
| File/media | Nhận upload, xác thực, xử lý và phân phối tệp |
| Async processing | Queue, event và workflow cho tác vụ dài |
| Realtime | Push event, WebSocket hoặc server-sent events |
| Notification | Gửi email, SMS hoặc mobile push |
| Offline sync | Đồng bộ thay đổi và giải quyết conflict |
| Observability | Log, metric, trace, audit và cảnh báo |
| Administration | Quản lý cấu hình, tenant và vận hành |

Không phải ứng dụng nào cũng cần mọi capability. Bắt đầu từ user journey và SLA thực tế, sau đó bổ sung thành phần khi có yêu cầu.

## 2. Kiến trúc tham chiếu

Một kiến trúc phổ biến đặt API gateway trước các Java function. Function gọi database, cache, object storage và service khác. Tác vụ dài được chuyển sang queue hoặc workflow; kết quả có thể được thông báo qua push hoặc realtime channel.

~~~mermaid
flowchart TD
    W[Web browser] --> EDGE[CDN / WAF]
    M[Mobile app] --> EDGE
    EDGE --> API[API Gateway]
    API --> AUTH[Identity provider / JWT validation]
    API --> F1[Java API functions]
    F1 --> DB[(Database)]
    F1 --> CACHE[(Cache)]
    F1 --> OBJ[(Object storage)]
    F1 --> Q[Queue / Event bus]
    Q --> F2[Worker functions]
    F2 --> WF[Workflow / orchestration]
    WF --> EXT[External services]
    F2 --> DB
    F2 --> OBJ
    F2 --> PUSH[Push / realtime service]
    PUSH --> W
    PUSH --> M
    F1 --> OBS[Logs / metrics / traces]
    F2 --> OBS
    API --> OBS
~~~

Các thành phần có thể là dịch vụ managed của một cloud provider hoặc sản phẩm tương đương. Sơ đồ mô tả trách nhiệm logic, không bắt buộc mỗi ô phải là một dịch vụ riêng. Với ứng dụng nhỏ, một vài function có thể đảm nhận nhiều use case có liên quan; khi tải, quyền hoặc vòng đời khác nhau, tách chúng thành các function/service riêng.

### Luồng request đồng bộ

1. Client gọi API qua HTTPS.
2. Gateway kiểm tra TLS, route, kích thước request và throttling.
3. Identity provider hoặc authorizer xác minh token/session.
4. Java function xác thực input và kiểm tra authorization ở cấp resource.
5. Function thực hiện transaction với database hoặc gọi dependency.
6. Function trả response theo API contract.
7. Gateway và ứng dụng phát telemetry có correlation ID.

### Luồng xử lý bất đồng bộ

1. Client gửi command hoặc yêu cầu tạo tác vụ.
2. API function xác thực và lưu trạng thái ban đầu.
3. Function gửi event vào queue hoặc khởi chạy workflow.
4. API trả 202 Accepted cùng operation ID.
5. Worker xử lý, cập nhật trạng thái và lưu kết quả.
6. Client poll operation status hoặc nhận push notification.
7. Client lấy kết quả qua API khi trạng thái hoàn tất.

Không giữ HTTP request mở trong thời gian dài chỉ để chờ xử lý video, báo cáo hoặc workflow kéo dài. Dùng operation resource và trạng thái bền vững để client có thể tiếp tục sau timeout hoặc app restart.

## 3. Chọn API Gateway và ranh giới backend

API gateway là entry point cho HTTP API. Gateway thường hỗ trợ route, TLS, authentication integration, throttling, request size limit, access logging và kết nối tới function. Một số nền tảng hỗ trợ REST, HTTP, WebSocket hoặc GraphQL gateway với feature và pricing khác nhau.

Các trách nhiệm nên đặt ở gateway:

- TLS termination và custom domain.
- Route và stage/version.
- Request size limit và throttling.
- CORS policy.
- Token validation nếu gateway hỗ trợ.
- WAF hoặc rule chống abuse.
- Access log và request correlation.
- Mapping đơn giản giữa HTTP request và backend.

Các trách nhiệm nên đặt ở backend:

- Business validation.
- Authorization theo resource/tenant.
- Transaction và consistency.
- Idempotency.
- Domain rule và side effect.
- Error mapping theo API contract.

Không dựa vào gateway để thay thế authorization trong domain. Một token hợp lệ chỉ chứng minh danh tính hoặc claims; nó không tự chứng minh user có quyền sửa mọi resource mà client gửi ID.

## 4. Chọn REST, GraphQL và Backend-for-Frontend

REST phù hợp với resource và command rõ ràng: GET profile, POST orders, PATCH preferences, GET operation status. Nó dễ cache, dễ quan sát và tương thích rộng với web/mobile.

GraphQL hữu ích khi client cần query nhiều resource theo hình dạng linh hoạt và có thể giảm over-fetching. Tuy nhiên, cần kiểm soát query depth, complexity, resolver fan-out, authorization ở từng field và caching. Một GraphQL request có thể kích hoạt nhiều backend operation; giới hạn HTTP request đơn thuần không đủ bảo vệ hệ thống.

Backend-for-Frontend (BFF) là lớp API tối ưu cho một loại client hoặc trải nghiệm. Có thể dùng khi web và mobile có nhu cầu response, authentication flow hoặc release cadence khác nhau. Không tạo BFF riêng cho từng client nếu nó chỉ chuyển tiếp request và làm tăng số endpoint cần vận hành.

| Lựa chọn | Khi phù hợp | Điểm cần quản lý |
|---|---|---|
| REST API dùng chung | Resource và use case tương đồng giữa web/mobile | Versioning và response compatibility |
| GraphQL | Client cần query linh hoạt, nhiều nguồn dữ liệu | Query cost, resolver authorization và caching |
| BFF | Client có UX, payload hoặc release needs khác nhau | Code duplication và ownership |
| WebSocket API | Cần kết nối hai chiều, cập nhật liên tục | Connection lifecycle và fan-out |
| Async operation API | Tác vụ dài hoặc có nhiều bước | Durable status, retry và polling |

## 5. Thiết kế API contract ổn định

API contract là thỏa thuận giữa client và backend. Nó cần mô tả:

- HTTP method và path.
- Request/response schema.
- Field bắt buộc, optional và default.
- Validation rules.
- Authentication và authorization.
- Error code và error body.
- Pagination/filter/sort.
- Idempotency semantics.
- Timeout và async behavior.
- Versioning và deprecation policy.

Ví dụ:

~~~http
POST /v1/orders
Authorization: Bearer <access-token>
Idempotency-Key: 8d7e1a4c-...
Content-Type: application/json

{
  "items": [
    {"productId": "P-100", "quantity": 2}
  ],
  "shippingAddressId": "ADDR-8"
}
~~~

Response thành công có thể là:

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/ORD-9001
Content-Type: application/json

{
  "id": "ORD-9001",
  "status": "PENDING",
  "createdAt": "2026-11-17T10:15:30Z"
}
~~~

Nếu thao tác cần xử lý lâu, API có thể trả:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/OP-3001
Retry-After: 3
Content-Type: application/json

{
  "operationId": "OP-3001",
  "status": "ACCEPTED",
  "statusUrl": "/v1/operations/OP-3001"
}
~~~

Không đưa internal stack trace, SQL message hoặc secret vào error response. Client cần một error code ổn định và correlation ID để hỗ trợ người dùng hoặc gửi yêu cầu hỗ trợ.

## 6. Authentication cho web và mobile

Authentication xác định client đang đại diện cho principal nào. Với web/mobile, thường dùng OpenID Connect (OIDC) hoặc OAuth 2.0 thông qua identity provider.

Các nguyên tắc:

- Dùng Authorization Code Flow với PKCE cho native/mobile public client.
- Browser app cần cân nhắc BFF và secure, HttpOnly, SameSite cookie để giảm rủi ro token theft.
- Không nhúng client secret trong mobile app hoặc SPA; mã client public có thể bị trích xuất.
- Access token nên có audience, issuer, expiry và scope phù hợp.
- Refresh token cần rotation/reuse detection nếu provider hỗ trợ.
- Logout/revoke cần có semantics rõ ràng; xóa token ở client không nhất thiết vô hiệu hóa token đã phát hành.
- Backend xác minh chữ ký, issuer, audience, expiry và claims theo policy.
- Không chấp nhận token chỉ vì decode được JWT payload.

### Access token và refresh token

Access token thường có lifetime ngắn để gọi API. Refresh token dùng để lấy access token mới và cần được bảo vệ kỹ hơn. Tránh lưu token dài hạn trong local storage của browser nếu có phương án an toàn hơn. Mobile nên dùng secure storage do hệ điều hành cung cấp.

Không tự xây dựng password, token issuance và cryptography nếu có thể dùng identity provider đã được kiểm chứng. Nếu backend tự quản lý identity, cần xử lý password hashing, MFA, recovery, brute-force defense, credential stuffing và session revocation một cách chuyên nghiệp.

## 7. Authorization và tenant isolation

Authentication không thay thế authorization. Sau khi xác minh principal, function cần kiểm tra người đó có quyền thực hiện action trên resource cụ thể hay không.

Một quyết định authorization có thể phụ thuộc:

- Subject: user, service hoặc role.
- Action: read, update, delete, approve.
- Resource: order, document, tenant hoặc project.
- Context: ownership, tenant, state, location hoặc risk.
- Policy: role, attribute hoặc relationship.

Ví dụ, user có role CUSTOMER vẫn chỉ được đọc đơn hàng thuộc account/tenant mà họ được phép truy cập. Không tin tenantId hoặc ownerId do client gửi mà chưa đối chiếu với claims và dữ liệu authoritative.

### Kiểm tra quyền trong từng request

1. Xác minh token ở gateway hoặc backend.
2. Lấy subject và tenant claims từ identity đã xác thực.
3. Tải resource bằng khóa có tenant scope.
4. Kiểm tra action được phép trên resource.
5. Thực hiện thay đổi trong transaction nếu có thể.
6. Ghi audit event cho hành động nhạy cảm.

Dùng deny-by-default. Mọi đường truy cập trực tiếp tới function, database, object storage hoặc queue cũng cần được kiểm soát bằng IAM/network policy; không giả định mọi request đều đi qua gateway.

## 8. Thiết kế Java function cho API

Java function xử lý HTTP nên tập trung vào một use case hoặc nhóm use case có cùng security, scaling và deployment boundary. Handler nên mỏng: parse request, xác thực context, gọi application service, map response. Business rule nằm trong domain/application layer để dễ unit test và tái sử dụng từ event consumer.

Ví dụ kiểu handler độc lập với cloud provider:

~~~java
public final class CreateOrderHandler {
    private final CreateOrderService service;
    private final RequestMapper mapper;
    private final ResponseMapper responses;

    public HttpResponse handle(HttpRequest request) {
        AuthenticatedPrincipal principal =
                request.authenticatedPrincipal();

        CreateOrderCommand command =
                mapper.toCommand(request.body());

        CreateOrderResult result =
                service.create(principal, command,
                        request.header("Idempotency-Key"));

        return responses.created(result);
    }
}
~~~

Đây là pseudocode; adapter thực tế sẽ phụ thuộc runtime/API Gateway integration. Handler không nên tin actor hoặc tenant lấy từ body. Dùng identity context do authorizer/middleware xác minh.

### Tái sử dụng execution environment an toàn

Có thể khởi tạo SDK client, serializer hoặc connection pool ở phạm vi class để tái sử dụng giữa invocation nếu runtime giữ execution environment. Nhưng:

- Không giữ user-specific state trong static field.
- Không lưu access token của một request để dùng cho request khác.
- Không giả định một instance chỉ xử lý một request tại một thời điểm nếu runtime có concurrency.
- Connection có thể stale sau thời gian idle; cần reconnect/retry có giới hạn.
- Không thực hiện side effect lúc class initialization nếu nó làm cold start hoặc deploy khó kiểm soát.

## 9. Chọn mô hình lưu trữ dữ liệu

Chọn database theo access pattern và transaction requirement, không chỉ theo nhãn serverless.

| Mô hình | Phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Managed relational database | Quan hệ, transaction, constraint, SQL phức tạp | Connection management, capacity và cold start kết nối |
| Serverless relational | Tải biến động, cần SQL/transaction | Scale behavior, min/max capacity và connection proxy |
| Key-value/document database | Lookup theo key, access pattern rõ, throughput cao | Partition key, index và query flexibility |
| Object storage | File, media, report, immutable artifact | Metadata/index ở database khác |
| Cache | Session/cacheable data, giảm latency | TTL, invalidation và không dùng làm source of truth |
| Search index | Full-text/search/filter chuyên biệt | Đồng bộ index và eventual consistency |

Dữ liệu nghiệp vụ có quan hệ phức tạp thường phù hợp với relational model. Dữ liệu event hoặc aggregate có access pattern đơn giản có thể phù hợp với document/key-value. Object storage phù hợp với nội dung lớn; database lưu metadata, owner, status và object reference.

Không lưu file lớn trực tiếp trong database hoặc HTTP response nếu object storage và direct upload phù hợp hơn.

## 10. Data model và transaction boundary

Một backend cần xác định aggregate và transaction boundary. Ví dụ, tạo order có thể cần lưu order header, line items, inventory reservation và outbox event. Nếu tất cả nằm trong một database hỗ trợ transaction, có thể commit các thay đổi nội bộ cùng nhau.

Không giả định transaction có thể trải qua database, queue, payment provider và email service. Với side effect bên ngoài, dùng saga/workflow, outbox/inbox và compensation.

Một flow tạo order:

1. Xác thực user và quyền mua.
2. Tạo order ở trạng thái PENDING.
3. Reserve inventory hoặc phát command.
4. Authorize payment.
5. Xác nhận order hoặc chuyển sang trạng thái cần xử lý.
6. Phát event để gửi notification.
7. Nếu bước sau thất bại, chạy compensation theo business rule.

Lưu state transition rõ ràng để client có thể đọc trạng thái nhất quán. Không dùng một boolean isComplete để mô tả workflow nhiều trạng thái.

## 11. Multi-tenancy và cách ly dữ liệu

Ứng dụng SaaS có thể phục vụ nhiều tenant. Cần xác định isolation model:

- Shared table với tenant key.
- Schema riêng cho tenant.
- Database riêng cho tenant.
- Account/project riêng cho tenant hoặc nhóm khách hàng có yêu cầu đặc biệt.

Shared table giảm chi phí vận hành nhưng yêu cầu mọi query/write đều có tenant scope. Dùng repository API nhận TenantContext đã xác thực, unique key có tenant dimension và database policy/row-level security khi phù hợp.

Không tạo tenant context từ header tùy ý. Gateway có thể chuyển claim đã xác minh nhưng function vẫn cần xác nhận tenant membership. Test cross-tenant access như một nhóm security test riêng.

## 12. Cache và phân phối nội dung

CDN có thể cache static asset, image derivative và response công khai. Cache backend có thể giảm database reads hoặc dependency calls.

Các điểm cần thiết kế:

- Cache key phải bao gồm các dimension ảnh hưởng đến response.
- Không cache private response trong shared cache nếu không partition đúng.
- TTL phù hợp với freshness requirement.
- Invalidation khi dữ liệu thay đổi.
- Cache stampede protection cho key nóng.
- Stale-while-revalidate nếu chấp nhận stale data.
- Không coi cache là nguồn dữ liệu authoritative.

Với web/mobile, static content nên được phân phối qua CDN khi phù hợp. API response cá nhân hóa cần cache policy rõ ràng; đặt Cache-Control sai có thể làm lộ dữ liệu giữa người dùng.

## 13. Upload tệp từ web/mobile

Không nên mặc định chuyển toàn bộ file lớn qua API Gateway và function. Pattern phổ biến là backend cấp upload session, client upload trực tiếp vào private object storage bằng URL/token có thời hạn và scope giới hạn.

Luồng upload:

1. Client gọi POST /uploads để xin upload session.
2. Backend xác thực user, quota, loại file được phép và giới hạn kích thước.
3. Backend tạo object key ngẫu nhiên trong vùng quarantine.
4. Backend trả URL upload ngắn hạn hoặc multipart upload instructions.
5. Client upload trực tiếp vào storage.
6. Client báo hoàn tất hoặc storage phát object-created event.
7. Backend xác minh object, checksum, size và owner.
8. Pipeline scan/validate rồi xử lý.
9. Metadata chuyển sang READY hoặc REJECTED.
10. Client lấy trạng thái và URL tải xuống có kiểm soát.

Không dùng filename do client gửi làm object key. Không tin MIME type, extension hoặc metadata client khai báo. Kiểm tra content signature/magic bytes và giới hạn decompression.

### Upload session

Một upload session có thể chứa:

- uploadId và owner/tenant.
- object key được server tạo.
- expected size và allowed content types.
- checksum algorithm/value nếu có.
- expiry và trạng thái.
- multipart upload ID nếu sử dụng.
- idempotency key và correlation ID.

URL ký trước là bearer capability: ai sở hữu URL có thể dùng quyền được cấp cho đến khi hết hạn hoặc bị thu hồi theo cơ chế của provider. Không ghi URL đầy đủ vào log; bảo vệ khỏi referrer leak và chỉ cấp quyền cho đúng object/method/TTL.

### Multipart và resume

Với file lớn hoặc mạng mobile không ổn định, multipart/resumable upload giúp gửi từng phần và tiếp tục sau khi kết nối gián đoạn. Backend cần quản lý:

- Part size và số part tối đa.
- Checksum từng part hoặc checksum tổng theo semantics của storage.
- Expiry và abort upload chưa hoàn tất.
- Complete operation idempotency.
- Cleanup orphaned multipart uploads.
- Giới hạn concurrent upload và tổng quota.

ETag không phải lúc nào cũng là MD5 của toàn bộ object, đặc biệt với multipart hoặc encryption. Dùng checksum semantics do storage provider tài liệu hóa.

## 14. Pipeline xử lý bất đồng bộ

Tệp upload xong chưa có nghĩa là an toàn hoặc sẵn sàng cho người dùng khác truy cập. Dùng queue/event để xử lý scan, metadata extraction, thumbnail, transcoding hoặc OCR.

~~~mermaid
flowchart TD
    A[Client requests upload session] --> B[API validates identity and quota]
    B --> C[Private quarantine object]
    C --> D[Object-created event]
    D --> E[Ingestion queue]
    E --> F[Validate size, type and checksum]
    F --> G[Malware / content scan]
    G -->|Accepted| H[Processing workflow]
    G -->|Rejected| R[Quarantine / reject]
    H --> I[Image / video / document workers]
    I --> J[Private derived objects]
    J --> K[Metadata and status update]
    K --> L[READY event]
    L --> M[Client status / notification]
~~~

Các stage nên có trạng thái bền vững, retry policy, timeout và DLQ. Worker phải idempotent vì event có thể được giao lại. Không public object hoặc trả download URL trước khi kiểm tra và xử lý xong theo policy.

## 15. Xử lý ảnh

Image processing thường gồm:

- Kiểm tra định dạng thực tế và decode thành công.
- Giới hạn width, height, pixel count và file size.
- Xoay theo EXIF orientation.
- Xóa hoặc kiểm soát EXIF metadata, đặc biệt GPS.
- Tạo thumbnail và các kích thước responsive.
- Chuyển định dạng theo client/browser support.
- Tối ưu quality và compression.
- Ghi metadata như dimensions, color profile và checksum.

Cần phòng decompression bomb: file nén nhỏ nhưng khi decode tạo bitmap rất lớn. Giới hạn pixel count, memory và thời gian xử lý. Dùng worker riêng cho tác vụ CPU/memory nặng thay vì để API function xử lý đồng bộ.

Derived object nên có key/version gắn với source object version và processor version. Khi thuật toán thay đổi, có thể tạo derivative mới mà không ghi đè bản cũ trong lúc client đang đọc.

## 16. Xử lý video và media dài

Video thường tốn compute, thời gian và storage hơn ảnh. Một pipeline có thể:

1. Kiểm tra container/codec và duration.
2. Trích xuất metadata và thumbnail.
3. Tạo renditions hoặc adaptive bitrate output.
4. Tạo caption/subtitle nếu có speech-to-text.
5. Phát hiện lỗi decode hoặc file bị cắt.
6. Ghi trạng thái processing và thời gian hoàn tất.
7. Phân phối qua CDN hoặc streaming origin.

Không xử lý video dài trong một function invocation nếu vượt timeout hoặc memory limit. Dùng managed transcoding service, container/job worker hoặc workflow chia bước. Theo dõi job state và hỗ trợ cancel khi user xóa hoặc thay thế media.

Nếu output gồm nhiều segment, manifest và thumbnail, chỉ công bố phiên bản hoàn chỉnh sau khi tất cả output cần thiết được xác minh. Không để client nhận manifest trỏ tới segment chưa upload xong.

## 17. Xử lý tài liệu và OCR

Document pipeline có thể thực hiện:

- Xác định file PDF, DOCX, XLSX, TXT hoặc định dạng được phép.
- Malware scanning.
- Kiểm tra file mã hóa/password-protected.
- Trích xuất text và metadata.
- OCR cho ảnh scan.
- Tách trang hoặc chia đoạn.
- Phân loại tài liệu và trích xuất field.
- Lưu kết quả có version và confidence.
- Đưa trường hợp confidence thấp vào human review.

Parser của PDF, office document và archive có bề mặt tấn công lớn. Chạy trong môi trường giới hạn quyền, memory, CPU, file descriptor, network egress và thời gian. Không để parser tải URL tùy ý từ document; điều đó có thể tạo SSRF.

Kết quả OCR/extraction có thể sai. Lưu provenance, model/processor version, page reference và confidence; không dùng extracted field làm dữ liệu authoritative cho quyết định quan trọng nếu chưa có validation.

## 18. Queue và event design

Event nên mô tả điều đã xảy ra hoặc command cần thực hiện, với schema version rõ ràng.

Ví dụ event:

~~~json
{
  "eventId": "evt-82c1",
  "eventType": "upload.accepted",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T10:15:30Z",
  "tenantId": "tenant-42",
  "uploadId": "upl-9001",
  "object": {
    "key": "quarantine/tenant-42/obj-random",
    "versionId": "v-17",
    "sizeBytes": 2457600,
    "checksum": "sha256:..."
  },
  "correlationId": "corr-31"
}
~~~

Không đưa nội dung file, access token hoặc URL ký trước vào event. Event mang object reference và metadata cần thiết; worker đọc object bằng IAM role có quyền tối thiểu.

Event contract cần định nghĩa compatibility. Thêm field optional thường dễ tương thích hơn đổi nghĩa field hiện tại. Nếu thay đổi semantics hoặc required field, tăng schema version và có migration plan.

## 19. Idempotency và xử lý duplicate

Queue/event thường cung cấp at-least-once delivery hoặc có thể retry sau timeout. Một event có thể được xử lý nhiều lần. Idempotency giúp cùng một operation không tạo side effect trùng.

Các khóa có thể dùng:

- eventId do producer tạo ổn định.
- uploadId + object version.
- business operation ID.
- client Idempotency-Key cho command HTTP.

Một inbox table có unique constraint trên eventId hoặc composite key có thể chặn duplicate. Worker nên ghi trạng thái và kết quả trong transaction nếu side effect nằm trong cùng database.

Không chỉ đánh dấu event đã xử lý trong memory. Function có thể bị terminate sau khi side effect commit nhưng trước khi acknowledge message. Khi event được giao lại, trạng thái bền vững mới giúp xác định có cần chạy lại hay không.

Với external service, truyền idempotency key nếu provider hỗ trợ. Nếu không, lưu external reference và thực hiện reconciliation trước khi retry thao tác có thể đã thành công.

## 20. Workflow cho tác vụ nhiều bước

Workflow phù hợp khi pipeline có nhiều stage, branching, timeout, retry, callback hoặc compensation.

Ví dụ document processing:

1. ValidateUpload.
2. ScanMalware.
3. ExtractMetadata.
4. DetectDocumentType.
5. RunOCR nếu cần.
6. ValidateExtractedFields.
7. StoreDerivedContent.
8. MarkReady.
9. NotifyOwner.

Mỗi step nên có input/output nhỏ, timeout và retry policy. Lưu object lớn trong storage; workflow state chỉ giữ object reference, IDs và metadata cần thiết. Tránh đưa toàn bộ binary payload vào workflow state vì giới hạn payload, chi phí và khả năng quan sát.

Workflow engine không tự bảo đảm side effect bên ngoài chỉ xảy ra một lần. Task cần idempotency; compensation cần business semantics rõ. Nếu workflow được khởi chạy lại sau lỗi, task đã commit không được tạo lại side effect.

## 21. Realtime updates: WebSocket, SSE và polling

Client cần biết trạng thái order, upload hoặc processing job có thể dùng nhiều cách:

| Cơ chế | Phù hợp | Trade-off |
|---|---|---|
| Polling | Đơn giản, tần suất thấp | Request lặp và độ trễ theo interval |
| Long polling | Server giữ request đến khi có update hoặc timeout | Quản lý connection và gateway timeout |
| Server-Sent Events | Server đẩy event một chiều đến browser | Client-to-server vẫn dùng HTTP riêng |
| WebSocket | Hai chiều, realtime | Connection lifecycle, auth refresh và fan-out |
| Mobile push | Thông báo khi app background/offline | Delivery không tức thời và payload hạn chế |

Polling cần backoff: bắt đầu ngắn sau khi submit, sau đó tăng interval đến giới hạn. Trả Retry-After để client tôn trọng backend. Không polling vô hạn nếu operation đã terminal.

WebSocket connection có thể bị ngắt khi mobile chuyển mạng hoặc app background. Client cần reconnect, authenticate lại và lấy snapshot trạng thái trước khi áp dụng event mới để tránh bỏ sót.

## 22. Push notification

Push notification phù hợp để báo cho mobile user biết có thay đổi cần xem. Backend lưu device token/registration theo user và thiết bị, quản lý token rotation, unsubscribe và invalid token.

Không đưa dữ liệu nhạy cảm vào notification payload nếu màn hình lock có thể hiển thị. Gửi notification chứa event type và reference; client gọi API đã xác thực để lấy nội dung.

Push provider không bảo đảm người dùng đã đọc hoặc app đã xử lý notification. Notification có thể bị delay, duplicate hoặc drop. Trạng thái nghiệp vụ phải được lưu ở backend; push chỉ là tín hiệu đánh thức client.

## 23. Offline-first và đồng bộ mobile

Mobile có thể tạo thay đổi khi offline. App nên lưu local operation queue và đồng bộ khi có kết nối.

Một sync request có thể chứa:

- operationId ổn định.
- entityId.
- baseVersion hoặc ETag.
- operation type.
- payload đã validate.
- client timestamp và device/session reference nếu cần.
- idempotency key.

Backend xác minh user, kiểm tra version và áp dụng conflict policy. Không tin client timestamp làm thứ tự authoritative vì đồng hồ thiết bị có thể sai.

### Conflict resolution

Các chiến lược thường gặp:

- Last-write-wins: đơn giản nhưng có thể ghi đè thay đổi quan trọng.
- Optimistic concurrency với version/ETag: từ chối cập nhật nếu base version cũ.
- Field-level merge: chỉ gộp field không xung đột.
- Domain-specific merge: phù hợp dữ liệu như giỏ hàng, checklist hoặc collaborative content.
- Human resolution: cần người dùng chọn khi dữ liệu không thể tự hợp nhất.

Không dùng một chiến lược cho mọi entity. Ví dụ, preference có thể last-write-wins, còn inventory hoặc payment cần transaction và invariant nghiêm ngặt.

### Delta sync

Thay vì tải lại toàn bộ dataset, backend có thể trả thay đổi sau sync cursor. Cursor phải ổn định, có expiry semantics và không làm lộ dữ liệu của tenant khác. Khi cursor hết hạn hoặc client quá cũ, cung cấp full resync có kiểm soát.

## 24. Pagination, filtering và search

API list cần pagination để tránh response lớn. Cursor pagination phù hợp dữ liệu thay đổi liên tục hơn offset pagination trong nhiều trường hợp.

Một response có thể chứa:

~~~json
{
  "items": [
    {"id": "ORD-1", "status": "READY"}
  ],
  "nextCursor": "opaque-cursor-value"
}
~~~

Cursor nên opaque và được ký hoặc tra cứu server-side; không để client tự sửa sort key hoặc tenant scope. Đặt giới hạn page size và whitelist filter/sort fields. Với search phức tạp, dùng search service hoặc index thay vì tạo query tùy ý trên database.

## 25. Rate limiting và bảo vệ backend

Gateway và backend cần giới hạn theo nhiều chiều:

- IP/network source.
- User/principal.
- Tenant/customer plan.
- API route và operation cost.
- Login attempt hoặc OTP destination.
- Upload size và concurrent upload.
- WebSocket connection/message.
- Background job admission.

Một global rate limit có thể không đủ: một tenant lớn có thể chiếm hết capacity. Dùng per-tenant quota và concurrency limit khi cần fairness. Đặt limit dựa trên downstream capacity và SLA.

Trả 429 Too Many Requests cùng Retry-After khi phù hợp. Client phải dùng exponential backoff với jitter, không retry đồng loạt. Với command có side effect, luôn dùng idempotency key.

## 26. Bảo mật API và dữ liệu

Các kiểm soát quan trọng:

- HTTPS/TLS cho mọi client.
- OIDC/OAuth flow đúng loại client.
- JWT validation đầy đủ hoặc session validation.
- Authorization theo resource và tenant.
- Input validation và output encoding.
- SQL/NoSQL injection protection bằng parameterized query.
- CORS allowlist cho browser origin.
- CSRF protection nếu dùng cookie authentication.
- XSS defense ở frontend và response handling.
- WAF, throttling và bot/abuse controls.
- Secret manager và IAM least privilege.
- Encryption at rest và in transit.
- Audit log cho hành động nhạy cảm.
- Không log token, password, secret hoặc raw sensitive payload.

CORS không phải authorization. CORS chủ yếu là browser enforcement; mobile client hoặc script có thể gọi API trực tiếp. Backend vẫn phải xác thực và kiểm tra quyền.

Nếu dùng cookie session cho browser, thiết lập Secure, HttpOnly, SameSite phù hợp và CSRF token/strategy. Nếu dùng bearer token, tránh lưu token lâu dài ở nơi JavaScript không đáng tin cậy có thể đọc.

## 27. Upload security và xử lý nội dung không tin cậy

Tệp do user upload là input không tin cậy. Các kiểm soát nên có:

- Allowlist content types và file size.
- Magic-byte/content inspection.
- Malware scan hoặc sandbox.
- Archive entry count, nesting depth và decompressed size limit.
- Parser chạy trong sandbox hoặc worker có quyền tối thiểu.
- Không execute macro/script hoặc render HTML tùy ý.
- Không cho parser truy cập network tùy ý.
- Tạo object key server-side.
- Lưu file ở private quarantine cho đến khi accepted.
- Kiểm tra ownership trước download.
- Content-Disposition và Content-Type an toàn khi serve.
- Lifecycle xóa file rejected/abandoned theo policy.

Nếu cung cấp preview, phục vụ qua origin/domain riêng hoặc cơ chế sandbox phù hợp để nội dung user upload không chạy trong origin có session cookie của ứng dụng.

## 28. Privacy và quản lý dữ liệu người dùng

Backend web/mobile thường xử lý profile, vị trí, thiết bị, file và hành vi người dùng. Cần xác định:

- Mục đích thu thập mỗi field.
- Data classification và sensitivity.
- Consent hoặc legal basis theo yêu cầu áp dụng.
- Data residency và cross-Region transfer.
- Retention và deletion lifecycle.
- Access logging và audit.
- Encryption/key ownership.
- Data export và account deletion workflow.
- Backup retention và cách xử lý dữ liệu đã xóa trong backup.
- Masking trong dev/test và log.

Không thu thập mọi dữ liệu chỉ vì có thể. Log cần tối thiểu hóa dữ liệu cá nhân. Với delete account, cần xử lý database, object, search index, cache, notification registration và downstream processor theo policy, đồng thời lưu audit evidence phù hợp mà không giữ lại dữ liệu đã phải xóa.

## 29. Reliability: timeout, retry và circuit breaker

Mỗi API/dependency cần timeout rõ. Timeout của client, gateway, function và downstream phải tương thích. Nếu gateway timeout trước khi function hoàn thành, client có thể retry dù operation đã commit.

Các nguyên tắc:

- Timeout ngắn cho request đồng bộ.
- Chuyển tác vụ dài sang async operation.
- Retry chỉ lỗi tạm thời.
- Exponential backoff và jitter.
- Retry budget theo operation.
- Circuit breaker hoặc bulkhead cho dependency không ổn định.
- Idempotency cho command.
- DLQ cho message không thể xử lý.
- Compensation cho workflow nhiều bước.
- Graceful degradation cho capability phụ.

Không retry lỗi validation, authorization hoặc schema invalid nếu không có thay đổi input. Retry storm có thể làm backend quá tải nặng hơn sự cố ban đầu.

## 30. Hiệu năng, cold start và concurrency

Cold start ảnh hưởng latency khi execution environment mới được tạo. Với Java, cần đo class loading, dependency initialization, framework startup, connection establishment và JIT warm-up.

Các cách tối ưu:

- Giữ dependency graph gọn.
- Dùng framework/startup mode phù hợp với runtime.
- Tái sử dụng client an toàn.
- Giảm reflection/scanning nếu không cần.
- Dùng artifact nhỏ và tránh initialize service không dùng.
- Đo p50/p95/p99 cold và warm.
- Cân nhắc provisioned/warm capacity cho route có latency objective nghiêm ngặt.
- Benchmark memory/CPU thay vì chọn cấu hình thấp nhất.

Concurrency phải được kiểm soát theo database connection, API quota và downstream capacity. Function scale nhanh hơn database có thể gây connection storm. Dùng reserved concurrency, queue buffering, connection proxy/pool và backpressure phù hợp.

## 31. Observability và correlation

Một user action có thể đi qua gateway, nhiều function, queue, workflow, database và push provider. Cần correlation ID hoặc trace context được truyền xuyên các thành phần.

Theo dõi:

- Request rate, error rate và latency p50/p95/p99.
- Authentication/authorization denial.
- Throttling và 429.
- Function duration, cold start, concurrency và throttles.
- Database connection, query latency và throttling.
- Queue depth, oldest message age, retry và DLQ.
- Workflow duration và failed state.
- Upload size, scan duration và processing status.
- Push delivery result và invalid device token.
- Cost per successful business operation.

Log structured JSON với requestId, traceId, tenant-safe reference, operationId và function version. Không đưa access token hoặc payload nhạy cảm vào trace baggage. Metric labels không nên dùng userId hoặc objectId có cardinality rất cao.

## 32. Chi phí và unit economics

Chi phí backend gồm API gateway, function invocation/duration, workflow transitions/execution, queue operations, database capacity/IO, storage GB-month, requests, egress, cache, WAF và observability.

Tính theo business outcome:

\[
CostPerSuccessfulOperation =
\frac{TotalBackendCost}{SuccessfulBusinessOperations}
\]

Ví dụ một lần upload thành công có thể tạo một API request xin URL, một hoặc nhiều storage operation, một event, vài queue operations, ba worker invocations, một workflow và một số log/trace. Chỉ đếm API request sẽ đánh giá thiếu.

Tối ưu:

- Upload trực tiếp vào object storage thay vì proxy binary qua function.
- Batch message khi phù hợp.
- Giảm polling và dùng callback/push.
- Lưu object lớn ngoài workflow state.
- Chọn storage lifecycle theo access pattern.
- Giảm retry/duplicate bằng idempotency.
- Giảm log volume nhưng giữ audit/security event.
- Đặt quota và TTL cho tài nguyên tạm.
- Đo cost per order/upload/user journey.

Không tối ưu chi phí bằng cách bỏ security scan, audit quan trọng hoặc giảm reliability dưới SLA.

## 33. Kiểm thử backend serverless

Kiểm thử nhiều tầng:

| Loại test | Mục tiêu |
|---|---|
| Unit test | Domain rule, validation, mapping và state transition |
| Contract test | Request/response schema, error semantics và API compatibility |
| Authorization test | User/tenant không truy cập resource ngoài quyền |
| Integration test | Database, queue, storage và identity adapter |
| Event test | Duplicate, out-of-order, malformed và replay |
| Workflow test | Retry, timeout, compensation và resume |
| Upload security test | File type giả, oversize, archive bomb và malware fixture an toàn |
| Mobile network test | Timeout, offline, reconnect và duplicate submit |
| Load test | Peak concurrency, throttling và downstream capacity |
| End-to-end test | User journey từ login đến business outcome |

Không chỉ test happy path. Test request timeout sau commit, token hết hạn, tenant mismatch, upload chưa hoàn tất, queue duplicate và worker crash giữa side effect với acknowledgement.

## 34. CI/CD và quản lý API version

Pipeline triển khai nên gồm:

1. Compile và unit test Java.
2. Static analysis và dependency/security scan.
3. Build artifact immutable.
4. Generate IaC plan và policy check.
5. Integration/contract test.
6. Deploy vào staging.
7. Smoke test và synthetic transaction.
8. Approval theo môi trường.
9. Canary hoặc gradual rollout.
10. Monitor error/latency và rollback nếu cần.

API change cần backward compatibility. Thêm optional field thường an toàn hơn xóa/đổi nghĩa field. Mobile app có thể tồn tại nhiều phiên bản ngoài thị trường trong thời gian dài; backend phải hỗ trợ client cũ theo deprecation policy.

Dùng API version trong path/header/schema tùy convention. Theo dõi client version để biết mức sử dụng trước khi ngừng API cũ. Feature flag giúp bật capability dần nhưng cần audit, owner và expiry để tránh flag tồn tại mãi.

## 35. Ví dụ Java: idempotent command cho web/mobile

Ví dụ dưới đây mô tả cách xử lý create order bằng idempotency key. Repository cần có unique constraint và transaction; đây là pseudocode, không phải adapter cho một database cụ thể.

~~~java
public CreateOrderResult create(
        AuthenticatedPrincipal principal,
        CreateOrderCommand command,
        String idempotencyKey) {

    if (idempotencyKey == null || idempotencyKey.isBlank()) {
        throw new ValidationException("Idempotency-Key is required");
    }

    String requestHash = canonicalHash(command);

    return transaction(() -> {
        IdempotencyRecord existing =
                idempotencyRepository.findForUpdate(
                        principal.subject(), idempotencyKey);

        if (existing != null) {
            if (!existing.requestHash().equals(requestHash)) {
                throw new IdempotencyConflictException();
            }
            return existing.resultAs(CreateOrderResult.class);
        }

        authorization.requireCanCreateOrder(principal, command);

        Order order = orderRepository.createPending(
                principal.subject(), command);

        outboxRepository.insert(
                OrderCreatedEvent.from(order));

        CreateOrderResult result =
                CreateOrderResult.accepted(order.id(), order.status());

        idempotencyRepository.insertCompleted(
                principal.subject(),
                idempotencyKey,
                requestHash,
                result);

        return result;
    });
}
~~~

Trong triển khai thực tế, record idempotency có thể cần trạng thái PROCESSING/COMPLETED, lease hoặc unique insert để xử lý hai request đồng thời. Business update, outbox và idempotency result cần transaction boundary rõ. Nếu workflow bất đồng bộ, lưu operation ID và trả cùng operation reference khi client retry.

Không dùng idempotency key toàn cục không có owner scope. Key nên được ràng buộc với principal/tenant và endpoint/operation để tránh collision hoặc replay chéo.

## 36. Ví dụ luồng tạo order hoàn chỉnh

~~~mermaid
sequenceDiagram
    participant C as Web/Mobile
    participant G as API Gateway
    participant F as Java API Function
    participant D as Database
    participant Q as Queue
    participant W as Worker/Workflow
    participant P as Push Service

    C->>G: POST /v1/orders + token + idempotency key
    G->>F: Authenticated request
    F->>D: Validate, authorize, create PENDING order
    F->>D: Save idempotency record and outbox
    F-->>G: 202 + operation/order ID
    G-->>C: Accepted
    Q->>W: OrderCreated event
    W->>D: Reserve inventory / update status
    W->>P: Notify client
    P-->>C: Status changed notification
    C->>G: GET /v1/orders/{id}
    G->>F: Authenticated read
    F->>D: Load tenant-scoped order
    F-->>C: Current order status
~~~

Luồng này thể hiện request nhanh trả operation/order ID, worker xử lý phần bất đồng bộ và client đọc trạng thái authoritative từ backend. Push chỉ báo có thay đổi; API GET vẫn là nguồn trạng thái chính.

## 37. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chuyển mọi binary qua API function | Tăng latency, memory và chi phí | Direct upload/download qua object storage |
| Tin tenantId từ client | IDOR và cross-tenant data leak | Derive tenant từ identity và kiểm tra resource |
| Chỉ xác thực ở gateway | Internal path có thể bypass authorization | Kiểm tra quyền trong domain/backend |
| Dùng token dài hạn trong app | Token theft có tác động lớn | OIDC/PKCE, secure storage và rotation |
| Trả 200 trước khi durable state được ghi | Client tưởng operation đã được nhận | Commit state/outbox trước response |
| Giữ HTTP request mở cho job dài | Timeout và retry không kiểm soát | 202 + operation status |
| Không có idempotency | Double submit tạo side effect trùng | Stable key và durable deduplication |
| Xử lý queue trong memory | Crash gây mất tiến độ | Durable state, retry và DLQ |
| Public file ngay sau upload | Nội dung độc hại hoặc chưa kiểm tra bị lộ | Quarantine, scan và controlled release |
| Dùng push làm source of truth | Client bỏ lỡ event sẽ stale | Lưu state backend và sync API |
| Không có offline conflict policy | Ghi đè dữ liệu người dùng | Version/ETag và domain merge |
| Cache private response sai key | Rò rỉ dữ liệu giữa user | Partition cache hoặc không cache |
| Không giới hạn query/list | Query tốn kém và response lớn | Pagination, filter allowlist và query budget |
| Function scale không giới hạn | Database connection storm | Concurrency cap và backpressure |
| Log toàn bộ request | Lộ token/PII và tăng cost | Structured logging, redaction |
| Mobile client cũ không tương thích | Lỗi sau backend deploy | Backward compatibility và deprecation |
| Retry mọi lỗi | Retry storm và chi phí tăng | Error classification, backoff và retry budget |

## 38. Quy trình xây dựng backend serverless

1. **Map user journey:** xác định web/mobile cần capability và SLA nào.
2. **Thiết kế API contract:** method, schema, error, pagination và versioning.
3. **Chọn identity flow:** OIDC/OAuth, session, token lifetime và refresh.
4. **Thiết kế authorization:** subject, tenant, resource, action và policy.
5. **Chọn data model:** database, object storage, cache và transaction boundary.
6. **Chọn execution boundary:** Java function cho HTTP, event consumer và workflow task.
7. **Thiết kế async:** queue, event schema, idempotency, retry và DLQ.
8. **Thiết kế file flow:** upload session, quarantine, scan, process và controlled delivery.
9. **Thiết kế realtime/offline:** polling, push, WebSocket, sync cursor và conflict resolution.
10. **Thiết kế security:** IAM, WAF, CORS/CSRF, encryption, privacy và audit.
11. **Thiết kế reliability:** timeout, backoff, concurrency, backpressure và compensation.
12. **Thiết kế observability:** correlation ID, metrics, trace và business outcome.
13. **Tính cost model:** cost per successful operation và peak scenario.
14. **Kiểm thử:** contract, authorization, duplicate, failure, mobile offline và load.
15. **Triển khai:** IaC, CI/CD, canary, API compatibility và rollback.
16. **Vận hành:** alert, runbook, quota review, cost review và deprecation.

## 39. Checklist production

- **API contract:** schema, error code, pagination, idempotency và versioning được tài liệu hóa.
- **Identity:** browser/mobile dùng auth flow phù hợp; token được xác minh đầy đủ.
- **Authorization:** kiểm tra quyền theo resource và tenant ở backend.
- **Gateway:** TLS, route, throttling, CORS, request size và access log được cấu hình.
- **Java functions:** handler stateless, dependency được tái sử dụng an toàn, timeout và concurrency có giới hạn.
- **Data:** transaction boundary, index, connection pool và backup được xác định.
- **Multi-tenant:** mọi query/write có tenant scope; cross-tenant tests pass.
- **Async:** queue/workflow có durable state, idempotency, retry, DLQ và replay plan.
- **Upload:** direct upload, signed URL TTL, quarantine, scan, checksum và cleanup.
- **Media/document:** processor có resource limit, sandbox, timeout và versioned output.
- **Realtime:** reconnect, auth refresh và snapshot resync được hỗ trợ.
- **Mobile offline:** operation ID, sync cursor và conflict policy được xác định.
- **Notification:** device token lifecycle và invalid token cleanup có quy trình.
- **Security:** secrets, encryption, WAF, abuse protection, CSRF/XSS và data minimization.
- **Privacy:** retention, export, deletion và data residency được xác định.
- **Reliability:** timeout, retry budget, backoff, circuit breaker và compensation đã được test.
- **Observability:** trace xuyên gateway/function/queue/workflow; alert theo business outcome.
- **Cost:** gateway, compute, workflow, queue, database, storage, network và telemetry có forecast.
- **CI/CD:** artifact immutable, IaC review, canary, smoke test và rollback.
- **Compatibility:** backend hỗ trợ phiên bản web/mobile đang được sử dụng theo deprecation policy.
- **Operations:** runbook cho incident, quota, DLQ, data restore và account recovery sẵn sàng.

## 40. Kết luận

Backend serverless cho web và mobile cần kết hợp API gateway, Java functions, identity provider, database, object storage, queue, workflow, realtime và notification theo nhu cầu nghiệp vụ. API đồng bộ phù hợp với thao tác nhanh; tác vụ dài nên chuyển sang async operation có ID và trạng thái bền vững. Upload trực tiếp vào object storage giúp giảm tải gateway/function, còn queue và workflow giúp xử lý media, document và các business process nhiều bước.

Những quyết định quan trọng nhất nằm ở API contract, authorization, tenant isolation, transaction boundary, idempotency, offline conflict resolution và khả năng quan sát. Mobile có thể retry sau timeout hoặc gửi lại thao tác sau khi reconnect; backend phải chịu được duplicate và trạng thái không chắc chắn. Push notification chỉ là tín hiệu, database/API mới là nguồn trạng thái authoritative. Tệp upload phải đi qua quarantine và validation trước khi được công bố.

Hãy bắt đầu từ user journey, chọn ranh giới function và data phù hợp, sau đó thiết kế bảo mật, reliability, cost và CI/CD ngay từ đầu. Một backend serverless tốt không chỉ scale theo traffic mà còn giữ được dữ liệu đúng, quyền truy cập đúng và trải nghiệm ổn định khi client offline, dependency lỗi hoặc workload tăng đột biến.

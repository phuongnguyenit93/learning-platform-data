# Kiểm thử cross-tenant access

> **Chương:** Multi-tenant  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Mô hình tin cậy và vòng đời token bảo mật; JWT, opaque token, access token, refresh token; kiểm tra claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại trong OAuth 2.0/OIDC.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **cross-tenant access** và vì sao đây là rủi ro nghiêm trọng trong hệ thống SaaS nhiều tenant.
2. Xác định nguồn tenant context đáng tin cậy, phân biệt tenant trong token đã xác minh với tenant do client tự gửi.
3. Thiết kế ma trận kiểm thử cho API, dữ liệu, thao tác CRUD, bulk operation, tìm kiếm, export, cache và tác vụ bất đồng bộ.
4. Kiểm tra sự kết hợp giữa **subject, tenant, audience, scope, role và resource ownership**.
5. Phát hiện lỗi IDOR/BOLA, tenant switching, cache leakage, connection pool contamination và nhầm tenant trong message/event.
6. Tự động hóa kiểm thử âm tính và kiểm thử cách ly tenant ở tầng API, service, database và các luồng tích hợp.

## 1. Cross-tenant access là gì?

Trong kiến trúc multi-tenant, một ứng dụng phục vụ nhiều tổ chức hoặc khách hàng trên cùng nền tảng. Mỗi tenant có không gian dữ liệu và quyền truy cập riêng. **Cross-tenant access** xảy ra khi một chủ thể thuộc tenant A có thể đọc, sửa, xóa, suy đoán hoặc thực hiện hành động trên tài nguyên thuộc tenant B mà không được chính sách cho phép.

Ví dụ:

- Công ty A và công ty B cùng sử dụng một hệ thống quản lý đơn hàng.
- Người dùng Alice thuộc tenant A có quyền xem đơn hàng của công ty A.
- Alice thay ID trong URL từ đơn hàng của A sang ID đơn hàng của B.
- Nếu API chỉ kiểm tra người dùng đã đăng nhập mà không kiểm tra tenant/ownership của đối tượng, API có thể trả dữ liệu của B.

~~~mermaid
flowchart LR
    A["Alice<br/>tenant A"] --> API["Orders API"]
    B["Bob<br/>tenant B"] --> API
    API --> DB[("Shared database")]
    API --> P["Tenant isolation policy"]
    P -->|Alice chỉ truy cập tenant A| RA["Orders của A"]
    P -->|Bob chỉ truy cập tenant B| RB["Orders của B"]
    A -.->|"Thử dùng order ID của B"| RB
    P -.->|"Phải từ chối"| X["403 / 404 theo policy"]
~~~

Rủi ro này có thể xuất hiện dù xác thực JWT hoàn toàn hợp lệ. Token chứng minh một danh tính hoặc client đã được issuer xác thực; nó không tự đảm bảo mọi truy vấn dữ liệu đều bị giới hạn đúng tenant.

### Phân biệt các lớp kiểm soát

| Lớp | Câu hỏi cần trả lời | Ví dụ kiểm soát |
|---|---|---|
| Authentication | Ai đang gọi? | Chữ ký JWT, introspection, mTLS client identity |
| Token validation | Token dành cho API nào và còn hiệu lực không? | iss, aud, exp, nbf, thuật toán |
| Tenant context | Chủ thể đang hoạt động trong tenant nào? | Claim tenant đã xác minh, membership, tenant binding |
| Authorization | Chủ thể có quyền thực hiện hành động nào? | Scope, role, permission, policy |
| Object-level authorization | Có được thao tác trên bản ghi cụ thể không? | Tenant ID, owner, relationship, resource state |
| Data isolation | Truy vấn có thể nhìn thấy dữ liệu tenant khác không? | Tenant predicate, schema/database isolation, RLS |

**Nguyên tắc:** Xác thực thành công không đồng nghĩa truy cập dữ liệu thành công. Mỗi request phải được ràng buộc với tenant context hợp lệ và mọi thao tác trên tài nguyên phải tuân theo chính sách tenant đó.

## 2. Xác định tenant context đáng tin cậy

Một hệ thống có thể nhận tenant context từ nhiều nguồn: access token, session, subdomain, route, header hoặc thông tin membership trong database. Không phải nguồn nào cũng có cùng mức độ tin cậy.

### Các nguồn tenant context

| Nguồn | Mức độ tin cậy | Cách xử lý |
|---|---|---|
| Claim tenant trong JWT đã xác minh | Có thể tin theo issuer và token profile | Kiểm tra chữ ký, issuer, audience, thời hạn, loại token và policy tenant |
| Metadata từ opaque token introspection | Có thể tin theo Authorization Server và kết nối introspection | Xác minh active, client, subject, audience và tenant metadata |
| Membership được truy vấn từ server-side identity store | Có thể dùng làm nguồn quyết định | Kiểm tra user/client còn thuộc tenant và membership còn hiệu lực |
| Subdomain như acme.example.com | Chỉ xác định tenant được yêu cầu | Resolve tenant server-side và kiểm tra caller được phép vào tenant đó |
| Header X-Tenant-Id do client gửi | Dữ liệu do client kiểm soát | Không dùng một mình để cấp quyền; phải đối chiếu membership và token context |
| Query parameter hoặc body tenantId | Dữ liệu đầu vào không tin cậy | Validate và ràng buộc với tenant context đã xác thực |
| Header do gateway tạo | Chỉ tin khi backend xác thực gateway và header đã được sanitize | Bảo vệ hop, xóa giá trị inbound giả, giới hạn đường bypass |

Một claim tenant trong JWT chỉ đáng tin sau khi token được xác minh đúng issuer, chữ ký, audience, thời gian và loại token. Nếu issuer cho phép một người dùng thuộc nhiều tenant, token cần biểu diễn rõ tenant context đang hoạt động hoặc hệ thống phải có bước chọn tenant và xác minh membership.

### Header không phải bằng chứng membership

Ví dụ request:

~~~http
GET /api/orders/ord-200 HTTP/1.1
Authorization: Bearer <access-token-cua-alice>
X-Tenant-Id: tenant-b
~~~

Backend không được tự động chuyển tenant context sang tenant B chỉ vì header có giá trị tenant-b. Server phải xác minh Alice có quyền hoạt động trong tenant B theo policy và token/session hiện tại. Nếu token được cấp riêng cho tenant A, yêu cầu này phải bị từ chối hoặc yêu cầu quy trình chuyển tenant có kiểm soát.

### Quy tắc resolve tenant

Một luồng xử lý tham khảo:

~~~text
resolveTenant(request, authenticatedPrincipal):
    requestedTenant = resolveFromRouteOrTrustedSelection(request)

    if token is tenant-bound:
        if requestedTenant != token.tenant:
            deny

    if token supports multiple tenants:
        if not membershipStore.isActive(
            authenticatedPrincipal.subject,
            requestedTenant
        ):
            deny

    return tenantContext(
        tenantId = requestedTenant,
        subject = authenticatedPrincipal.subject,
        actor = authenticatedPrincipal.actor
    )
~~~

Đây là pseudocode. Nguồn membership và cách chọn tenant phải phù hợp mô hình identity của hệ thống. Không được lấy subject, tenant hoặc role từ header không được xác thực.

## 3. Mối liên hệ giữa JWT, access token và tenant

Một access token có thể mang các claim như:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "alice",
  "aud": "orders-api",
  "tenant_id": "tenant-a",
  "scope": "orders.read orders.write",
  "exp": 1893456000,
  "jti": "token-123"
}
~~~

Đây là payload minh họa, không phải token sử dụng được. Resource server cần xác minh chữ ký, thuật toán được phép, issuer, audience, thời hạn và profile access token trước khi tin các claim.

### Những điều cần kiểm tra

- **iss:** token do Authorization Server được tin cậy phát hành.
- **aud:** token dành cho đúng resource server. Token dành cho Orders API không tự động hợp lệ ở Billing API.
- **exp/nbf:** token đang trong thời gian hợp lệ, với clock skew theo policy.
- **sub:** định danh chủ thể. Cần hiểu sub có thể là user hoặc client/service tùy loại grant.
- **tenant claim:** tenant context phải được issuer phát hành theo quy tắc rõ ràng; không mặc định mọi issuer dùng tên claim tenant_id.
- **scope/roles:** quyền được cấp trong token phải được ánh xạ đúng với tenant và resource.
- **jti hoặc token state:** nếu có cơ chế thu hồi/replay detection, kiểm tra theo profile triển khai.

JWT được ký không đồng nghĩa claim tenant luôn phản ánh membership hiện tại. Nếu user vừa bị xóa khỏi tenant, một JWT self-contained có thể còn hợp lệ đến exp. Hệ thống cần cân nhắc token TTL, membership revalidation, revocation/introspection hoặc versioning policy tùy yêu cầu thu hồi.

### Opaque token

Với opaque access token, API thường cần introspection hoặc một cơ chế tra cứu tin cậy để lấy thông tin active, subject, client, audience, scope và tenant metadata. Không giải mã chuỗi opaque hoặc suy tenant từ ký tự của token.

Kết quả introspection cũng cần được bảo vệ: xác thực resource server, kiểm tra trạng thái active và quản lý cache để thay đổi membership/revocation không bị trễ quá mức policy cho phép.

### Token exchange và tenant

Khi Orders Service đổi token để gọi Inventory API, Authorization Server cần giữ đúng tenant context và giới hạn quyền theo subject, actor, resource. Token mới có audience Inventory API và tenant phù hợp; không được để client yêu cầu tenant B chỉ bằng cách gửi tham số tenant=B nếu subject không có membership hợp lệ.

## 4. Xây dựng ma trận tenant để kiểm thử

Trước khi viết test, cần tạo dữ liệu đại diện cho nhiều tenant và nhiều kiểu chủ thể.

### Bộ dữ liệu kiểm thử mẫu

| Đối tượng | Tenant | Vai trò/quyền | Dữ liệu |
|---|---|---|---|
| Alice | tenant-a | orders.read, orders.write | order-a1, order-a2 |
| Alex | tenant-a | orders.read | order-a3 |
| Bob | tenant-b | orders.read, orders.write | order-b1 |
| Beth | tenant-b | tenant-admin | order-b2 |
| Service A | tenant-a | inventory.read | integration-a |
| Service B | tenant-b | inventory.read | integration-b |
| Platform auditor | platform | quyền audit có điều kiện | audit scope theo policy |

Tạo dữ liệu có ID khó đoán và dễ đoán để không phụ thuộc vào giả định ID ngẫu nhiên. Có thể dùng UUID, số tăng dần hoặc slug; authorization vẫn phải đúng bất kể khả năng đoán ID.

### Ma trận truy cập cơ bản

| Caller | Tài nguyên tenant A | Tài nguyên tenant B | Kết quả mong đợi |
|---|---|---|---|
| Alice, tenant A | order-a1 | order-b1 | Cho phép A; từ chối B |
| Alex, tenant A chỉ đọc | order-a1 | order-b1 | Cho phép đọc A; từ chối sửa A và mọi truy cập B |
| Bob, tenant B | order-a1 | order-b1 | Từ chối A; cho phép B theo quyền |
| Beth, tenant B admin | order-a1 | order-b2 | Từ chối A; cho phép B theo policy admin |
| Service A | inventory tenant A | inventory tenant B | Cho phép A; từ chối B |
| Platform auditor | theo phạm vi được cấp | theo phạm vi được cấp | Chỉ cho phép theo quyền platform audit rõ ràng |

Không nên giả định platform administrator mặc định được đọc mọi dữ liệu. Nếu có break-glass hoặc support access, cần quyền riêng, lý do, thời hạn, audit và quy trình phê duyệt phù hợp.

## 5. Kiểm thử object-level access: IDOR/BOLA

**IDOR (Insecure Direct Object Reference)** hoặc **BOLA (Broken Object Level Authorization)** xảy ra khi API sử dụng object ID do client gửi nhưng không kiểm tra caller có quyền với đối tượng đó hay không.

Ví dụ endpoint:

~~~http
GET /api/orders/order-b1
~~~

Alice có token tenant A nhưng thử thay ID sang order-b1 thuộc tenant B. API phải từ chối theo policy.

### Các thao tác phải thử

| Thao tác | Biến thể cross-tenant |
|---|---|
| GET detail | Đổi order ID sang bản ghi tenant khác |
| PUT/PATCH | Sửa trạng thái hoặc địa chỉ đơn hàng tenant khác |
| DELETE | Xóa resource của tenant khác |
| POST action | Hủy, approve, capture hoặc refund resource khác tenant |
| List/search | Bỏ tenant filter hoặc sửa filter tenant |
| Export/report | Export dữ liệu tenant khác qua job hoặc report ID |
| Download/upload file | Dùng file ID hoặc storage key của tenant khác |
| Bulk API | Trộn ID thuộc tenant A và B trong cùng request |
| Nested resource | Dùng order ID hợp lệ của A nhưng line-item ID của B |
| GraphQL | Đổi node ID, parent ID hoặc resolver argument để đọc tenant khác |

Kiểm tra cả đường đọc và đường ghi. Một endpoint GET có filter đúng không chứng minh PATCH/DELETE hoặc background export cũng an toàn.

### ID không thay thế authorization

Không dùng các biện pháp sau như kiểm soát duy nhất:

- UUID khó đoán.
- Ẩn ID trên giao diện.
- Kiểm tra tenant ở frontend.
- Chỉ xác thực người dùng đã đăng nhập.
- Kiểm tra role chung nhưng bỏ qua tenant/resource.
- Dựa vào URL có subdomain tenant mà không xác minh membership.

Mỗi service cần kiểm tra resource thuộc tenant nào và caller có quyền thực hiện action trên resource đó không.

## 6. Kiểm thử API và HTTP boundary

### Tenant switching

Nếu người dùng có nhiều tenant, hệ thống có thể cho phép chuyển tenant. Việc này phải đi qua quy trình được xác minh:

1. Client yêu cầu chuyển sang tenant B.
2. Server kiểm tra membership và trạng thái tenant B.
3. Server tạo session/token context mới hoặc cập nhật context theo thiết kế.
4. Request sau đó mang context tenant B đã được xác minh.
5. Các token/cache/context cũ không được dùng nhầm cho tenant mới.

Không cho phép đổi tenant bằng cách chỉ sửa header hoặc query parameter.

### Các trường hợp header và parameter

| Đầu vào | Điều cần kiểm tra |
|---|---|
| X-Tenant-Id: tenant-b | Có membership và tenant binding không? |
| Header tenant trùng lặp | Proxy/backend có chọn nhầm giá trị không? |
| Header khác chữ hoa/thường | Tên header HTTP không phân biệt hoa thường; xử lý phải nhất quán |
| tenantId trong JSON body | Không được ghi đè tenant context đã xác thực |
| tenant trong query string | Không dùng như bằng chứng quyền |
| tenant trong URL path | Resolve và kiểm tra membership |
| X-Forwarded-* | Chỉ tin proxy được cấu hình; không nhầm với tenant identity |
| Header identity do gateway tạo | Xóa giá trị inbound và xác thực gateway/backend hop |

### Kết quả 403 hay 404?

Có hai chính sách thường gặp:

- **403 Forbidden:** cho biết caller đã xác thực nhưng không có quyền truy cập.
- **404 Not Found:** có thể dùng để tránh tiết lộ resource có tồn tại ở tenant khác.

Chọn một hành vi nhất quán theo threat model. Dù dùng status nào, response body, timing, metadata, count hoặc error detail cũng không được làm lộ dữ liệu tenant khác.

## 7. Kiểm thử list, search, pagination và aggregate

Cross-tenant leak thường không chỉ xảy ra ở endpoint detail. Các API danh sách và báo cáo có thể vô tình trộn dữ liệu.

Các phép thử:

- Gọi list endpoint không có filter tenant do client gửi; server phải tự áp tenant context.
- Thay query parameter tenantId từ A sang B.
- Thử sort, filter, search và full-text query với dữ liệu có dấu hiệu nhận biết từng tenant.
- Kiểm tra tổng số bản ghi, count, facets, dashboard aggregate và thống kê.
- Kiểm tra pagination cursor/continuation token được tạo ở tenant A có dùng được ở tenant B không.
- Kiểm tra export file được sinh từ query tenant A có chứa dữ liệu tenant B không.
- Kiểm tra autocomplete, suggestion, lookup và endpoint báo cáo có cùng policy.

### Ví dụ dữ liệu kiểm thử

Tạo một giá trị dễ nhận biết riêng mỗi tenant:

- Tenant A: customer name = ALPHA-ONLY-CUSTOMER.
- Tenant B: customer name = BETA-ONLY-CUSTOMER.

Khi Alice tìm kiếm trong tenant A, response, count, facets, autocomplete và export không được chứa BETA-ONLY-CUSTOMER. Không chỉ kiểm tra kết quả đầu tiên; hãy kiểm tra mọi trang và mọi định dạng export.

## 8. Kiểm thử bulk operation và nested resource

Bulk endpoint thường nhận danh sách ID:

~~~http
POST /api/orders/bulk-cancel
Content-Type: application/json
Authorization: Bearer <token-tenant-a>

{
  "orderIds": ["order-a1", "order-b1"]
}
~~~

API cần có chính sách rõ ràng cho request trộn tenant:

- **Atomic reject:** từ chối toàn bộ request nếu có một ID ngoài tenant hiện tại.
- **Per-item result:** chỉ xử lý bản ghi được phép và trả kết quả từng item, không tiết lộ chi tiết resource ngoài tenant.
- **Partial success:** chỉ áp dụng nếu hợp đồng API quy định rõ, audit được từng item và không tạo side effect ngoài ý muốn.

Không tự động bỏ qua ID ngoài tenant rồi báo thành công toàn bộ nếu điều đó khiến caller hiểu sai kết quả.

Với nested resource, kiểm tra cả quan hệ cha-con. Ví dụ order-a1 thuộc tenant A nhưng line-item-b1 thuộc tenant B; API không được chỉ kiểm tra order cha rồi thao tác item con không thuộc order đó.

## 9. Cache, session và tenant context

Cache là một nguồn cross-tenant leakage phổ biến. Nếu cache key không chứa tenant context, request của tenant B có thể nhận response đã cache từ tenant A.

### Cache key an toàn

Không nên chỉ dùng:

~~~text
orders:list:user-123
~~~

Nếu user hoặc query context không đủ phân biệt tenant, key có thể va chạm. Một dạng thiết kế tốt hơn là:

~~~text
tenant:{tenantId}:subject:{subjectId}:orders:list:{queryHash}
~~~

Cache key thực tế còn phụ thuộc quyền, locale, filter, resource và policy. Không đưa raw token hoặc secret vào cache key/log.

### Các test bắt buộc cho cache

1. Alice tenant A đọc order-a1, sau đó Bob tenant B gọi cùng URL/query.
2. Đảo thứ tự: Bob đọc trước, Alice đọc sau.
3. Hai tenant dùng cùng user ID nội bộ nhưng khác tenant.
4. Hai tenant có cùng resource ID nếu hệ thống dùng ID theo namespace.
5. Tenant switching trong cùng session/browser.
6. Cache invalidation sau khi membership hoặc role thay đổi.
7. Token v1 hết hạn/revoke trong khi cached response còn tồn tại.
8. CDN, reverse proxy và application cache có phân biệt tenant không.

Cache phải cô lập theo security context. Nếu response phụ thuộc quyền, cache key hoặc cache policy cần phản ánh quyền đó. Đặc biệt cẩn thận với HTTP shared cache và header Vary; không giả định Vary tự giải quyết mọi ràng buộc authorization.

### Session và distributed context

- Không tái sử dụng session tenant A cho request tenant B nếu context chưa được đổi theo quy trình.
- Không lưu tenant context trong static mutable field dùng chung giữa thread.
- Khi dùng ThreadLocal, phải clear trong finally hoặc dùng cơ chế context propagation an toàn.
- Kiểm tra async executor, reactive context và coroutine có truyền đúng tenant context.
- Không dùng một global singleton tenant ID cho nhiều request đồng thời.

## 10. Kiểm thử database isolation và Row-Level Security

Ngay cả khi API đã kiểm tra tenant, database vẫn cần phòng thủ nhiều lớp nếu kiến trúc yêu cầu cách ly mạnh. Các chiến lược thường gặp:

- **Shared database, shared schema:** mọi bảng có tenant_id và truy vấn phải áp filter.
- **Shared database, schema per tenant:** kết nối/schema được resolve đúng tenant và không cho phép schema injection.
- **Database per tenant:** credential, connection routing, migration và backup phải ánh xạ đúng tenant.

### Kiểm tra tenant predicate

Một truy vấn nghiệp vụ cần ràng buộc tenant từ context đáng tin:

~~~sql
SELECT id, status, total
FROM orders
WHERE tenant_id = :tenant_id
  AND id = :order_id;
~~~

Không lấy tenant_id trực tiếp từ request body rồi truyền vào truy vấn như thể đã được xác thực. Giá trị tenant phải đến từ tenant context server-side đã resolve và authorize.

### PostgreSQL Row-Level Security minh họa

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

Ứng dụng có thể thiết lập context theo transaction:

~~~sql
BEGIN;
SELECT set_config('app.tenant_id', :verified_tenant_id, true);

SELECT id, status
FROM orders
WHERE id = :order_id;

COMMIT;
~~~

Đây là ví dụ minh họa. Cần hiểu đặc tính của PostgreSQL RLS và quyền database role:

- Superuser và role có quyền **BYPASSRLS** có thể bỏ qua policy; không dùng các role này cho ứng dụng thông thường.
- FORCE ROW LEVEL SECURITY giúp áp dụng policy với cả table owner trong nhiều tình huống, nhưng không biến superuser thành role bị giới hạn.
- Transaction-local setting phải được thiết lập cho từng transaction; không để tenant context rò sang connection tiếp theo trong pool.
- Nếu tenant setting bị thiếu hoặc rỗng, policy nên từ chối truy cập theo hướng fail closed.
- Không nối chuỗi SQL từ tenant input; dùng parameter binding.
- Kiểm tra cả SELECT, INSERT, UPDATE, DELETE, bulk update và các function/view có quyền đặc biệt.

### Test connection pool contamination

1. Request tenant A lấy connection từ pool, đặt tenant context và truy vấn.
2. Transaction kết thúc hoặc rollback.
3. Request tenant B nhận lại cùng connection.
4. Truy vấn không được tiếp tục dùng tenant A context.
5. Request thiếu tenant context phải bị từ chối, không được dùng context còn sót lại.

Test này đặc biệt quan trọng vì lỗi có thể chỉ xuất hiện khi connection được tái sử dụng hoặc request chạy đồng thời.

## 11. Kiểm thử background jobs, event và message queue

Một request có thể an toàn ở HTTP layer nhưng tạo ra message thiếu tenant context hoặc tin metadata không đáng tin.

Ví dụ Orders Service phát event:

~~~json
{
  "eventId": "evt-100",
  "tenantId": "tenant-a",
  "orderId": "order-a1",
  "requestedBy": "alice",
  "eventType": "OrderCreated"
}
~~~

Consumer phải xác minh nguồn event và ràng buộc tenant context với dữ liệu đã được phát hành bởi producer đáng tin. Không được tin tenantId chỉ vì nó có trong JSON message.

### Các tình huống cần test

- Producer tenant A phát event; consumer xử lý dữ liệu tenant A.
- Producer bị lỗi hoặc bị xâm nhập, cố gửi tenantId B trong event A.
- Consumer nhận message trùng lặp hoặc retry sau khi tenant membership thay đổi.
- Dead-letter queue và replay tool có giữ đúng tenant context.
- Scheduled job chạy cho nhiều tenant không giữ context giữa hai lần lặp.
- Batch export hoặc report job lưu tenant ID đã được server xác minh, không lấy từ tham số tùy ý.
- Event được chuyển qua nhiều service vẫn giữ actor/subject/audit context phù hợp.
- Một message có ID hợp lệ nhưng resource thuộc tenant khác phải bị từ chối.

### Context trong message

Nên có hợp đồng message rõ ràng: tenant identity, subject/actor nếu cần, correlation ID, event ID, version và producer identity. Consumer xác thực producer, kiểm tra tenant/resource relationship và áp policy trước khi thực hiện side effect.

Không nên chuyển nguyên access token người dùng vào message queue nếu không có thiết kế bảo mật rõ ràng. Có thể dùng service identity hoặc token exchange để consumer lấy token phù hợp với resource và thao tác; phải giới hạn lifetime, audience và scope.

## 12. Token exchange và multi-tenant boundary

Trong chuỗi microservices, token exchange có thể tạo token mới dành cho service đích. Với multi-tenant, token exchange còn phải giữ đúng tenant context.

Ví dụ Orders Service xử lý yêu cầu của Alice tenant A và cần gọi Inventory API:

~~~mermaid
sequenceDiagram
    participant U as Alice / tenant A
    participant O as Orders Service
    participant AS as Authorization Server
    participant I as Inventory API

    U->>O: Access token: sub=alice, tenant=A, aud=orders-api
    O->>AS: Exchange + client authentication<br/>audience=inventory-api<br/>scope=inventory.read
    AS->>AS: Validate subject, actor, tenant membership, policy
    AS-->>O: Token mới: tenant=A, aud=inventory-api
    O->>I: Bearer token mới
    I->>I: Validate iss, aud, exp, tenant, scope
    I-->>O: Chỉ dữ liệu tenant A
~~~

Các kiểm tra:

- Subject token có tenant context nào? Issuer có tin cậy không?
- Orders Service có quyền exchange token cho tenant đó không?
- Actor service có được phép hành động thay mặt subject không?
- Token mới có audience đúng Inventory API không?
- Scope được downscope và tenant binding có được giữ đúng không?
- Inventory API có kiểm tra resource tenant trùng token tenant không?
- Cache token exchange có phân biệt subject, actor và tenant không?

Không cho phép Orders Service lấy token tenant B chỉ bằng cách thêm tenantId=B vào request exchange. Authorization Server phải xác minh membership/delegation và giới hạn tenant theo policy.

## 13. Kiểm thử quyền đặc biệt và platform administrator

Một số hệ thống có platform support, auditor hoặc tenant administrator. Các quyền này dễ tạo ngoại lệ làm suy yếu tenant isolation.

### Tenant admin

Tenant admin của A chỉ quản trị tenant A. Thử đổi tenant path/header sang B và xác nhận bị từ chối, trừ khi user có membership và quyền riêng ở B.

### Platform support

Nếu có support access xuyên tenant, cần kiểm thử:

- Có role/permission riêng, không dùng role tenant admin thông thường.
- Phải có lý do và phạm vi tenant cụ thể.
- Thời hạn quyền ngắn và có thể thu hồi.
- Audit ai đã truy cập tenant nào, tài nguyên nào, thao tác gì.
- Break-glass yêu cầu quy trình xác thực mạnh hoặc phê duyệt theo policy.
- Không dùng support access để bypass toàn bộ authorization.
- Support token phải có audience/scope phù hợp và không được tái sử dụng ở API không liên quan.

### Background/system administrator

System job có thể cần xử lý nhiều tenant. Nên dùng workload identity và policy chuyên biệt, giới hạn operation, tenant set và thời gian. Không biến một service account toàn quyền thành credential mặc định cho mọi microservice.

## 14. Tự động hóa kiểm thử với Java và Spring Security

Ví dụ dưới đây minh họa test controller yêu cầu JWT có tenant claim. Giả sử endpoint đọc order phải ràng buộc tenant context với token đã xác thực.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class CrossTenantAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void userFromTenantACannotReadTenantBOrder() throws Exception {
        mvc.perform(get("/api/orders/order-b1")
                .with(SecurityMockMvcRequestPostProcessors.jwt()
                    .jwt(jwt -> jwt
                        .subject("alice")
                        .claim("tenant_id", "tenant-a")
                        .claim("scope", "orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void clientCannotSwitchTenantUsingHeader() throws Exception {
        mvc.perform(get("/api/orders/order-b1")
                .header("X-Tenant-Id", "tenant-b")
                .with(SecurityMockMvcRequestPostProcessors.jwt()
                    .jwt(jwt -> jwt
                        .subject("alice")
                        .claim("tenant_id", "tenant-a")
                        .claim("scope", "orders.read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là ví dụ minh họa. Cần có dữ liệu order-b1 thuộc tenant B và authorization layer thật sự kiểm tra tenant. Spring Security test postprocessor tạo Authentication test; nó **không kiểm tra chữ ký JWT thật**. Vì vậy phải bổ sung integration test cho decoder/JWKS hoặc introspection, issuer, audience, expiry và claim mapping.

Nếu policy dùng 404 để tránh tiết lộ sự tồn tại của resource, điều chỉnh assertion theo contract API. Quan trọng là không có dữ liệu hay side effect cross-tenant.

### Test service layer

Không chỉ test controller. Service method có thể được gọi từ scheduled job, message consumer hoặc một controller khác. Test service layer để đảm bảo mọi đường gọi đều yêu cầu tenant context hợp lệ và truy vấn dữ liệu luôn có tenant predicate.

### Test song song

Dùng hai request đồng thời với tenant A/B để phát hiện static context, ThreadLocal cleanup hoặc connection pool leakage. Kiểm tra cả kết quả, audit record và side effect; không chỉ status code.

## 15. Property-based và fuzz testing

Ngoài các test case cố định, có thể sinh nhiều tổ hợp subject, tenant, resource, role và action.

Các thuộc tính mong muốn:

1. Nếu resource thuộc tenant B và caller chỉ có tenant A, mọi thao tác bị từ chối.
2. Thay đổi resource ID không thể vượt qua tenant boundary.
3. Thay header/query/body tenant không thể ghi đè tenant context đã xác minh.
4. Thêm role không thuộc token hoặc membership không làm tăng quyền.
5. Token sai audience hoặc issuer không được chấp nhận.
6. Cache hit không thể trả response của tenant khác.
7. Sau revoke membership, request tiếp theo bị từ chối theo SLA thu hồi.
8. Mọi side effect chỉ ảnh hưởng resource thuộc tenant được phép.

### Các input nên fuzz

- Tenant ID rỗng, null, sai format, unicode confusable, khoảng trắng, encoding khác nhau.
- Duplicate headers, duplicate JSON properties và parameter trùng tên.
- ID của resource cha hợp lệ nhưng ID con thuộc tenant khác.
- Danh sách bulk chứa ID trùng, thiếu, không tồn tại và cross-tenant.
- Cursor pagination lấy từ tenant khác.
- Tenant context thiếu hoặc không nhất quán giữa JWT và route.
- Token có nhiều audience, scope trùng, claim tenant sai kiểu hoặc cấu trúc không hợp lệ.
- Race giữa tenant switching, refresh token, revoke membership và request đang chạy.

Fuzzing cần chạy trên dữ liệu thử nghiệm và có giới hạn để không tạo side effect thật.

## 16. Bộ kiểm thử cross-tenant end-to-end

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Token | JWT sai chữ ký, issuer hoặc audience | 401 hoặc từ chối xác thực |
| Tenant claim | Token tenant A nhưng request chọn B | Từ chối nếu chưa có quy trình chuyển tenant hợp lệ |
| Membership | User không còn thuộc tenant B | Từ chối theo policy cập nhật membership |
| Object | Đọc/sửa/xóa ID tenant khác | 403/404 nhất quán, không side effect |
| List/search | Query bỏ tenant filter | Không có dữ liệu/count của tenant khác |
| Bulk | Trộn resource A và B | Atomic reject hoặc per-item policy đã định |
| Nested resource | Parent A, child B | Từ chối |
| Export/file | Dùng report/file ID của tenant khác | Từ chối và không tạo file chứa dữ liệu khác |
| Cache | Tenant B nhận cache entry của A | Không xảy ra |
| Session | Switch tenant trong cùng browser | Context và token được cập nhật đúng |
| Database | Thiếu tenant context hoặc tái sử dụng connection | Fail closed, không đọc tenant cũ |
| Async | Message khai tenant khác producer/resource | Consumer từ chối hoặc cách ly |
| Token exchange | Đổi token sang tenant không được ủy quyền | Authorization Server từ chối |
| Admin | Tenant admin A truy cập B | Từ chối |
| Platform support | Truy cập theo break-glass | Chỉ cho phép đúng phạm vi, thời gian và audit |
| Revocation | Membership/token bị thu hồi | Không tiếp tục truy cập ngoài SLA |
| Concurrency | Request A/B đồng thời | Không rò context, response hoặc side effect |

## 17. Audit, response và thông tin không được rò rỉ

Khi một request cross-tenant bị từ chối, log cần đủ dữ liệu để điều tra mà không lưu credential nhạy cảm.

Thông tin audit có thể gồm:

- Timestamp và correlation/trace ID.
- Subject ID và actor/workload identity đã xác thực.
- Tenant context đã được server resolve.
- Resource tenant và resource ID theo mức phân loại dữ liệu.
- Action được yêu cầu và policy decision.
- Lý do từ chối ở dạng mã nội bộ.
- Client ID, issuer hoặc token ID nếu policy cho phép.

Không ghi raw access token, refresh token, client secret hoặc private key. Không trả stack trace, tên khách hàng khác, email, dữ liệu đơn hàng hoặc tenant ID nội bộ không cần thiết trong response công khai.

Response 403/404 cần nhất quán để tránh side-channel. Timing, pagination count, error message và metadata cũng có thể tiết lộ resource có tồn tại ở tenant khác.

## 18. Checklist trước khi đưa multi-tenant API vào production

- Tenant context đến từ nguồn nào? Có được xác minh và gắn với subject/client đã xác thực không?
- Token có đúng issuer, audience, thời hạn và loại access token không?
- User thuộc nhiều tenant được chuyển tenant qua quy trình nào?
- Tất cả GET/POST/PUT/PATCH/DELETE, bulk, nested, search và export có kiểm tra tenant không?
- Cache key, session, CDN và connection pool có cô lập tenant không?
- Background jobs, event consumers và scheduled jobs có xác minh tenant context không?
- Database có tenant predicate hoặc RLS phù hợp? Role ứng dụng có thể bypass RLS không?
- Token exchange có giữ subject, actor, audience, scope và tenant binding không?
- Membership revoke có hiệu lực trong thời gian bao lâu?
- Platform support/break-glass có phạm vi và audit rõ ràng không?
- Test suite có negative tests, concurrency tests và dữ liệu hai tenant độc lập không?
- Logs/traces/metrics có tránh tiết lộ token và dữ liệu tenant khác không?

## 19. Tổng kết

**Cross-tenant access testing** kiểm tra xem một chủ thể có thể vượt qua ranh giới dữ liệu và quyền của tenant khác hay không. Việc kiểm thử phải đi từ token và tenant context đến authorization trên từng đối tượng, truy vấn database, cache, session, background job và message queue.

Trong hệ thống token security, access token cần được xác minh đúng issuer, audience, thời hạn, scope và tenant context. Nhưng claim tenant chỉ là một phần của quyết định; service còn phải xác minh membership, actor, resource ownership và chính sách nghiệp vụ. Mọi dữ liệu đầu vào như header, path, query và body đều cần được đối chiếu với tenant context đã xác thực.

Một hệ thống multi-tenant an toàn phải bảo đảm **tenant A không thể đọc, sửa, xóa, tìm kiếm, export hoặc gây side effect trên dữ liệu tenant B**, kể cả khi request có token hợp lệ, resource ID đoán được, cache hit, request chạy đồng thời hoặc được xử lý qua luồng bất đồng bộ.

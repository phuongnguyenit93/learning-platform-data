# Tenant claim và tenant boundary

> **Chương:** Multi-tenant  
> **Phạm vi:** Token security fundamentals — xác thực, phân quyền, vòng đời access token/refresh token và ranh giới dữ liệu giữa các tenant.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `tenant claim` biểu diễn điều gì, nguồn nào được phép xác nhận claim và vì sao một claim trong JWT không tự động tạo ra quyền truy cập.
2. Phân biệt `tenant_id` với `sub`, `iss`, `aud`, `scope`, role, organization và tenant ID của nhà cung cấp danh tính.
3. Thiết kế quy tắc thực thi **tenant boundary** từ lúc kiểm tra token đến truy vấn dữ liệu, cache, tác vụ nền và lời gọi giữa các dịch vụ.
4. Nhận diện lỗi truy cập chéo tenant (cross-tenant access), đặc biệt khi API chỉ kiểm tra tài nguyên theo ID hoặc tin header do client cung cấp.
5. Xây dựng ca kiểm thử chứng minh người dùng của tenant A không thể đọc, sửa hay tạo dữ liệu thuộc tenant B.

## 1. Tenant, tenant claim và tenant boundary

Trong một ứng dụng SaaS nhiều khách hàng, **tenant** là miền cô lập bảo mật của một khách hàng/đơn vị sử dụng hệ thống. Ví dụ, công ty Alpha và công ty Beta cùng dùng ứng dụng quản lý đơn hàng nhưng dữ liệu, phân quyền và tác vụ của hai công ty phải tách biệt.

- **Tenant ID:** định danh ổn định của miền cô lập, chẳng hạn UUID của một tổ chức trong cơ sở dữ liệu ứng dụng.
- **Tenant claim:** thuộc tính do bên phát hành token đáng tin cậy gắn vào token hoặc trả về qua token introspection để biểu thị tenant mà token được cấp quyền hoạt động trong đó; ví dụ `tenant_id`.
- **Tenant context:** tenant đã được máy chủ xác lập cho một request/tác vụ sau khi xác thực và áp dụng quy tắc phân quyền.
- **Tenant boundary:** tập hợp các quy tắc bảo đảm request/tác vụ chỉ có thể thao tác trên tài nguyên thuộc tenant context được cho phép.

**Xác thực** trả lời “ai hoặc client nào đang gọi?”. **Phân quyền** trả lời “được làm hành động nào?”. **Tenant isolation** còn yêu cầu “được làm trên dữ liệu của tenant nào?”. Cả ba điều kiện đều cần đúng.

Giả sử Alice thuộc Alpha, Bob thuộc Beta. Alice có quyền `orders.read` không có nghĩa Alice được xem mọi đơn hàng trong toàn hệ thống. Quyền đọc phải được xét **trong tenant Alpha**, trên đơn hàng thuộc Alpha và theo chính sách truy cập tài nguyên cụ thể.

### Mô hình ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Người dùng / client"] --> AS["Authorization Server"]
    M["Membership và policy đáng tin cậy"] --> AS
    AS -->|"Access token có tenant_id"| API["Resource Server"]
    API --> V{"Xác thực token + kiểm tra audience, scope, tenant"}
    V -->|Hợp lệ| S["Service / authorization"]
    S --> Q["Truy vấn có tenant_id / RLS"]
    Q --> D[("Dữ liệu tenant")]
    V -->|Không hợp lệ| X["Từ chối"]
~~~

Ranh giới quan trọng nằm tại **resource server** và mọi nơi dữ liệu được truy cập. Chữ ký JWT chứng minh claim đến từ một issuer được tin cậy; chữ ký **không chứng minh** người gọi có quyền trên mọi tài nguyên có ID được truyền vào.

## 2. Tenant claim nằm ở đâu và có nghĩa gì?

Ví dụ payload của một **access token JWT** dành cho API quản lý đơn hàng (chỉ minh họa):

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "iat": 1900000000,
  "nbf": 1900000000,
  "exp": 1900000900,
  "tenant_id": "9f66a815-0e25-42c7-912f-23344e58ac85",
  "scope": "orders.read orders.write"
}
~~~

| Claim hoặc thuộc tính | Vai trò | Điều không được suy diễn |
| --- | --- | --- |
| `iss` | Xác định issuer đã phát hành token | Không có nghĩa issuer này được tin cho mọi API |
| `sub` | Xác định chủ thể (người dùng hoặc service principal) | Không đồng nghĩa với tenant ID |
| `aud` | Xác định resource/API mà token hướng tới | Không chứng minh quyền trên từng tenant hoặc đơn hàng |
| `exp`, `nbf`, `iat` | Giới hạn thời gian sử dụng token | Token chưa hết hạn vẫn có thể mang quyền đã bị thu hồi |
| `scope` | Diễn đạt các quyền thao tác được cấp cho token | `orders.read` không phải quyền đọc đơn của mọi tenant |
| `tenant_id` | Tenant đang hoạt động, theo quy ước do hệ thống định nghĩa | Chỉ đáng tin sau khi kiểm tra token và quy trình cấp claim |
| Role/permission | Vai trò/quyền nghiệp vụ gắn với chủ thể và tenant | `ADMIN` của tenant A không phải admin toàn hệ thống |

**Không có chuẩn chung bắt buộc mọi JWT đều có `tenant_id`.** Tên, định dạng và ngữ nghĩa claim là hợp đồng giữa bên phát hành và resource server. Nếu tích hợp một Identity Provider bên ngoài, claim `tid` có thể chỉ là định danh directory/tenant của chính Identity Provider, **không tự động tương đương tenant trong SaaS**. Ứng dụng phải ánh xạ danh tính bên ngoài sang tenant nội bộ thông qua cấu hình và membership đáng tin.

Với **opaque access token**, API không tự giải mã payload; nó gọi cơ chế introspection đáng tin cậy (hoặc một dịch vụ xác thực nội bộ) để lấy trạng thái `active` và thông tin tenant/scope/audience tương ứng. Dù token là JWT hay opaque, quy tắc tenant boundary vẫn giống nhau.

**ID token của OpenID Connect dùng để xác nhận phiên đăng nhập cho client; không dùng thay access token để gọi API.** Resource server phải kiểm tra access token được phát hành cho chính API đó.

### Ai được quyết định tenant claim?

Quy trình hợp lệ thường là:

1. Người dùng xác thực thành công.
2. Server kiểm tra người dùng thuộc tenant nào và còn quyền gì bằng nguồn membership/policy đáng tin.
3. Nếu người dùng thuộc nhiều tenant, họ chọn **active tenant**; server xác thực lựa chọn đó rồi mới cấp access token ràng buộc với tenant đã chọn.
4. Resource server kiểm tra token và sử dụng tenant đã xác thực để xử lý request.

Giá trị tenant trong form, query, URL, cookie hoặc header do client gửi chỉ là **lựa chọn/yêu cầu** cần được so khớp; nó không được tự nâng thành tenant context có thẩm quyền. Không phát hành claim chỉ bằng cách chép nguyên một `X-Tenant-ID` từ request khi chưa kiểm tra membership.

## 3. Bất biến bảo mật xuyên suốt request

Với thiết kế **mỗi access token gắn một active tenant**, đặt:

- `T_token`: tenant ID lấy từ access token **đã xác thực hợp lệ**.
- `T_request`: tenant được nêu trên route/header nếu API có trường đó.
- `T_resource`: tenant thực sự sở hữu dữ liệu được truy cập.

Yêu cầu tối thiểu cho một thao tác hợp lệ:

~~~text
token hợp lệ cho API
AND subject/client có quyền thao tác trong T_token
AND (request không chọn tenant khác OR T_request == T_token)
AND T_resource == T_token
AND chính sách quyền trên tài nguyên cho phép hành động
~~~

Ví dụ:

~~~http
GET /api/tenants/alpha/orders/ord-101
Authorization: Bearer <access-token-tenant-alpha>
~~~

Một request đổi đường dẫn thành `/tenants/beta/orders/ord-202` phải bị từ chối nếu token vẫn ràng buộc Alpha. Ngay cả khi route chứa Alpha, truy vấn đơn hàng vẫn cần ràng buộc `tenant_id = Alpha`; chỉ kiểm tra route rồi tìm `order_id` trên toàn bảng sẽ tạo lỗ hổng.

**Không bắt buộc phải đưa tenant vào URL.** API có thể dùng `/api/orders/{id}` và suy tenant từ token. Bất biến quan trọng là mọi thao tác xác lập tenant từ nguồn đã được kiểm chứng, và mọi tài nguyên đều bị lọc theo tenant đó.

### Trình tự xử lý ở resource server

1. **Kiểm tra token:** chữ ký JWT dựa trên khóa issuer đã cấu hình, thuật toán được cho phép, `iss`, `aud`, `exp` và `nbf`; với opaque token, kiểm tra phản hồi introspection từ kênh đáng tin cậy và trạng thái `active`.
2. **Kiểm tra claim:** `tenant_id` phải có, đúng kiểu/định dạng, thuộc miền tenant được API hỗ trợ; token không có tenant rõ ràng cần chính sách riêng, không tự mặc định sang tenant đầu tiên.
3. **Kiểm tra quyền:** scope, role/membership của chủ thể **trong tenant này**, quyền trên resource và các điều kiện nghiệp vụ.
4. **So khớp tenant ở request:** nếu URL/header/body chứa tenant, so khớp với tenant context hoặc áp dụng chính sách chuyển tenant rõ ràng.
5. **Truy cập dữ liệu theo tenant:** lọc tại tầng truy vấn và, nếu phù hợp, tăng cường bằng ràng buộc CSDL hoặc Row-Level Security (RLS).
6. **Giữ context qua các tầng:** cache, message, job, file/object storage và service nội bộ phải giữ được cùng boundary.

Phân biệt lỗi: **401** cho trường hợp chưa xác thực/token không hợp lệ; **403** cho token hợp lệ nhưng không có quyền. Với tài nguyên truy cập bằng ID, **404** có thể được dùng nhất quán cho tài nguyên không thuộc tenant để hạn chế lộ sự tồn tại của dữ liệu.

## 4. Ví dụ thực hiện với Java / Spring Security

Giả sử resource server đã cấu hình `oauth2ResourceServer().jwt()`, kiểm tra issuer và **audience = orders-api** bằng validator, đồng thời bật method security để kiểm tra scope. Ví dụ sau minh họa bước ràng buộc tenant của một endpoint; nó không thay thế toàn bộ cấu hình xác thực token.

~~~java
@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{orderId}")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    OrderDto getOrder(
            @PathVariable UUID tenantId,
            @PathVariable UUID orderId,
            @AuthenticationPrincipal Jwt jwt) {

        UUID tokenTenant = requireTenantId(jwt);
        if (!tokenTenant.equals(tenantId)) {
            throw new AccessDeniedException("Tenant mismatch");
        }

        // Service/repository luôn dùng tenant đã xác thực.
        return orderService.findByTenantIdAndId(tokenTenant, orderId)
                .orElseThrow(() ->
                    new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    private static UUID requireTenantId(Jwt jwt) {
        String raw = jwt.getClaimAsString("tenant_id");
        if (raw == null || raw.isBlank()) {
            throw new AccessDeniedException("Missing tenant_id");
        }
        try {
            return UUID.fromString(raw);
        } catch (IllegalArgumentException ex) {
            throw new AccessDeniedException("Invalid tenant_id");
        }
    }
}
~~~

Tầng repository cũng phải ràng buộc tenant:

~~~sql
SELECT id, tenant_id, amount, status
FROM orders
WHERE tenant_id = :tenantId
  AND id = :orderId;
~~~

Điểm then chốt của ví dụ:

- `@AuthenticationPrincipal Jwt` chỉ an toàn trong pipeline đã xác minh chữ ký/issuer/audience/thời hạn của access token. Đọc payload bằng cách decode Base64 rồi tin claim là sai.
- `@PreAuthorize` chỉ kiểm tra một **scope**; hệ thống còn phải có cơ chế xác nhận người dùng/service principal được cấp scope đó trong tenant và kiểm tra quyền trên từng đơn hàng khi nghiệp vụ yêu cầu.
- Hàm repository nhận tenant từ token đã xác thực, không lấy tenant tùy ý từ client.
- Thao tác **UPDATE/DELETE/INSERT** cũng phải kiểm tra tenant ở điều kiện ghi/khóa ngoại; chỉ bảo vệ GET là chưa đủ.
- Với người dùng thuộc nhiều tenant, lựa chọn active tenant cần được kiểm tra khi phát hành/đổi token; không tự động cấp quyền mọi tenant từ một claim role chung.

Nếu API dùng gateway, gateway có thể loại bỏ request không hợp lệ sớm, nhưng **dịch vụ xử lý dữ liệu vẫn phải thực thi boundary**. Một route được gateway bảo vệ chưa đủ để đảm bảo mọi service downstream chỉ truy cập đúng tenant.

## 5. Đặt tenant boundary ở tầng dữ liệu

### 5.1. Chặn truy cập chéo tenant trong mọi thao tác

Với bảng chia sẻ, đa số bảng nghiệp vụ cần cột `tenant_id`. Khi lấy, sửa hoặc xóa theo ID, luôn thêm điều kiện tenant tương ứng:

~~~sql
UPDATE orders
SET status = :newStatus
WHERE id = :orderId
  AND tenant_id = :tenantId;
~~~

Đối với quan hệ giữa hai bảng, có thể dùng khóa ngoại ghép để tránh gán dữ liệu tenant này cho tài nguyên tenant khác:

~~~sql
-- Ví dụ minh họa cho PostgreSQL.
ALTER TABLE projects
    ADD CONSTRAINT uq_projects_tenant_id_id
    UNIQUE (tenant_id, id);

ALTER TABLE orders
    ADD CONSTRAINT fk_orders_project_same_tenant
    FOREIGN KEY (tenant_id, project_id)
    REFERENCES projects (tenant_id, id);
~~~

Mô hình này giả định `orders.tenant_id`, `orders.project_id` và `projects.tenant_id` đã được khai báo, đồng thời quan hệ dữ liệu cho phép áp dụng khóa ngoại như trên. Cần thiết kế thêm quy tắc cho trường hợp `project_id` có thể `NULL`.

### 5.2. Row-Level Security là lớp tăng cường

Với PostgreSQL, ứng dụng có thể sử dụng RLS để buộc truy vấn chỉ thấy hàng thuộc tenant context:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_boundary ON orders
    USING (
        tenant_id = NULLIF(
            current_setting('app.tenant_id', true), ''
        )::uuid
    )
    WITH CHECK (
        tenant_id = NULLIF(
            current_setting('app.tenant_id', true), ''
        )::uuid
    );
~~~

Trong một **transaction** xử lý request đã xác thực, thiết lập tenant context bằng tham số an toàn trước khi chạy truy vấn nghiệp vụ:

~~~sql
SELECT set_config('app.tenant_id', :verifiedTenantId, true);
~~~

Tham số thứ ba `true` làm giá trị có phạm vi transaction. Khi không có tenant context, chính sách trên không trả hàng (fail closed). Cần bảo đảm cùng transaction/connection được dùng xuyên suốt thao tác; connection pool, asynchronous flow và quyền tài khoản CSDL phải được cấu hình cẩn thận. Role có `BYPASSRLS` hoặc quyền chủ sở hữu trong một số cấu hình có thể vượt RLS; vì vậy không nên coi RLS là lớp bảo vệ duy nhất.

RLS, truy vấn có điều kiện tenant và khóa ngoại ghép có thể bổ sung lẫn nhau; kiến trúc tách riêng database/schema cho mỗi tenant cũng cần boundary chính xác ở bước chọn kết nối/datasource.

## 6. Tenant boundary không dừng ở controller

| Thành phần | Rủi ro phổ biến | Cách bảo vệ |
| --- | --- | --- |
| URL, query, header | Tin `tenantId` do client tự nhập | Ràng buộc với token/membership đã xác thực |
| Repository/ORM | `findById(id)` lấy tài nguyên ở tenant khác | Query theo `(tenant_id, id)`; kiểm tra quan hệ ghép |
| Cache | Dùng key `order:{id}` chung, hoặc chia cache không có tenant | Dùng namespace/key tenant và kiểm tra quyền trước khi trả dữ liệu |
| File/object storage | Dùng object key của tenant khác | Kiểm tra tenant của metadata và phạm vi signed URL |
| Search/index | Bộ lọc tenant bị bỏ quên trong truy vấn tìm kiếm | Áp dụng tenant filter tại tầng tìm kiếm, kiểm thử cả export/report |
| Queue/job | Message thiếu tenant hoặc worker lấy tenant từ payload giả mạo | Gắn tenant context đáng tin, xác nhận nguồn message, thực thi quyền ở consumer |
| Service-to-service | Downstream tin header `X-Tenant-ID` mà không xác thực caller | Dùng danh tính service, token đúng `aud` và quyền tenant-scoped; xác thực ngữ cảnh được chuyển tiếp |
| Log/metrics | Ghi lẫn dữ liệu tenant hoặc lộ token | Ghi tenant ID cho audit có kiểm soát; che token/PII |
| Admin/support | Dùng “super-admin” để vô tình vượt kiểm tra tenant | Cơ chế truy cập đặc quyền riêng, audit đầy đủ, giới hạn phạm vi/thời gian |

Ví dụ, dù endpoint GET đã lọc đúng tenant, job xuất báo cáo chạy sau vài phút vẫn có thể làm rò rỉ dữ liệu nếu nó chỉ lưu `reportId` mà không lưu và xác minh tenant context. Tương tự, invalidation cache hoặc cập nhật search index phải dùng cùng khóa tenant với dữ liệu gốc.

Ở ranh giới giữa các service, token người dùng dành cho `orders-api` không mặc nhiên hợp lệ với `billing-api`; mỗi resource server phải kiểm tra `aud`. Nếu cần ủy quyền, dùng cơ chế token exchange/on-behalf-of phù hợp và giữ tenant cùng quyền hạn đã được xác thực. Service token vận hành không có người dùng cũng cần ràng buộc tenant hoặc chính sách đặc quyền rõ ràng; `client_credentials` không tự sinh quyền trên mọi tenant.

## 7. Đổi tenant, hết quyền và vòng đời token

Một người dùng có thể là thành viên của Alpha và Beta. Có hai cách thiết kế phổ biến:

- **Một active tenant trên mỗi access token:** người dùng chọn tenant, authorization server xác minh membership rồi cấp access token mới với `tenant_id` tương ứng. Cách này giúp resource server có một tenant context rõ ràng.
- **Token mang nhiều membership:** API có thể chấp nhận một tenant được client chọn nếu kiểm chứng tenant nằm trong tập đã được cấp và thỏa quyền tương ứng. Thiết kế này phức tạp hơn, đặc biệt khi scope/role khác nhau giữa các tenant; tuyệt đối không dùng một role chung để cấp quyền đồng loạt.

Với mô hình một active tenant, **đổi tenant không phải thao tác thay claim ở phía client**: JWT đã ký không thể được sửa hợp lệ, còn opaque token phải tham chiếu ngữ cảnh mới ở authorization server. Đổi tenant nên đi qua flow cấp token có kiểm tra membership và chính sách session/refresh token.

Membership có thể bị thu hồi trong khi JWT chưa hết hạn. Vì vậy cần kết hợp những biện pháp phù hợp với mức rủi ro: access token có TTL ngắn, refresh token được bảo vệ và rotation, thu hồi session/token khi cần, kiểm tra membership hiện hành với thao tác nhạy cảm, hoặc dùng token introspection/policy version. Khi thiết kế cache quyền, phải tính đến độ trễ hiệu lực của việc thu hồi.

Với refresh token, server phải gắn nó với chủ thể, client và session được cho phép; không chấp nhận tham số tenant mới để phát access token cho tenant mà chủ thể không thuộc về. Tenant bị khóa/xóa, quyền bị giảm hoặc người dùng rời tổ chức phải được phản ánh ở lần cấp token tiếp theo, kể cả khi refresh token cũ còn tồn tại.

## 8. Những lỗi thiết kế hay gặp

**Lỗi 1 — IDOR/BOLA qua ID tài nguyên.** API kiểm tra token và scope hợp lệ nhưng thực hiện `SELECT * FROM orders WHERE id = ?`. Kẻ gọi chỉ cần biết ID hợp lệ của tenant khác là có thể đọc dữ liệu. Sửa bằng cách buộc mọi truy vấn tài nguyên tenant-scoped gắn `tenant_id`, kiểm tra chính sách đối tượng và thử nghiệm truy cập chéo tenant.

**Lỗi 2 — Tin tenant từ header.** Gateway chuyển `X-Tenant-ID: beta` đến service và service dùng ngay giá trị đó. Nếu header do client có thể điều khiển hoặc service không xác thực nguồn, boundary bị phá. Sửa bằng cách xác lập context từ identity đã kiểm tra, loại bỏ header client giả mạo, dùng kết nối nội bộ tin cậy và xác minh claim/ủy quyền phù hợp.

**Lỗi 3 — Coi `scope`/`role` là quyền toàn hệ thống.** `ADMIN` thường có nghĩa “admin trong tenant A”, không phải “admin mọi tenant”. Role phải được gắn phạm vi, và resource server phải kiểm tra cả tenant lẫn đối tượng.

**Lỗi 4 — Dùng `tid` của Identity Provider làm tenant nội bộ.** Một directory có thể chứa nhiều tổ chức ứng dụng hoặc một tổ chức có nhiều directory. Cần định nghĩa ánh xạ và hợp đồng claim rõ ràng.

**Lỗi 5 — Chỉ bảo vệ đường đọc.** Endpoint ghi, bulk import, download, export, webhook, background task và file attachment đều là bề mặt truy cập cần tenant boundary.

**Lỗi 6 — Chỉ xác thực JWT mà bỏ qua `aud`.** Access token phát cho service A được gửi sang service B; nếu B chỉ kiểm tra chữ ký và `exp` có thể chấp nhận nhầm token. Mỗi API phải kiểm tra token được cấp cho chính mình.

**Lỗi 7 — Tenant context bị rò giữa request/job.** Lưu tenant trong biến global hoặc `ThreadLocal` mà không quản lý vòng đời có thể để request sau kế thừa tenant trước, nhất là khi thread pool tái sử dụng worker. Phải đặt, truyền và dọn context theo phạm vi request/transaction/job.

## 9. Bộ ca kiểm thử bắt buộc

Thiết lập tenant **A** và **B**, mỗi bên có người dùng và đơn hàng riêng; chuẩn bị access token hợp lệ cho A.

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Token A đọc đơn thuộc A, có scope phù hợp | Thành công theo quyền nghiệp vụ |
| Token A đọc/sửa/xóa đơn thuộc B dù biết ID | Từ chối; không rò rỉ dữ liệu |
| Token A gọi route `/tenants/B/...` | Bị từ chối do tenant mismatch |
| Token A gửi header `X-Tenant-ID: B` | Không thay đổi tenant context đã xác thực |
| Token không có `tenant_id`, sai kiểu hoặc không có quyền | Bị từ chối theo chính sách |
| Chỉnh payload `tenant_id` từ A sang B mà không có chữ ký hợp lệ | Token bị từ chối |
| Token có chữ ký hợp lệ nhưng sai `aud` hoặc hết hạn | Token bị từ chối |
| Token A có `orders.read` nhưng thiếu `orders.write` | Không thể cập nhật |
| Thành viên A bị thu hồi quyền và thử refresh/token mới | Không được cấp lại quyền A; token cũ xử lý theo chính sách thu hồi |
| Xuất báo cáo, cache, job, truy vấn search với dữ liệu A/B | Không có dữ liệu B xuất hiện trong kết quả A |
| Tạo order A tham chiếu project thuộc B | Vi phạm constraint hoặc bị chặn ở tầng nghiệp vụ |
| Lời gọi nội bộ thiếu identity/tenant scope đáng tin | Bị từ chối; không suy diễn “service nội bộ = toàn quyền” |

Nên kiểm thử cả truy vấn đơn lẻ, danh sách có phân trang, thao tác batch, thống kê/aggregate, export, xử lý bất đồng bộ và đường admin. Một ca kiểm thử “token hợp lệ nhưng ID tài nguyên thuộc tenant khác” đặc biệt quan trọng vì nó phát hiện lỗi bỏ qua tầng tenant dù xác thực JWT vẫn hoạt động đúng.

## 10. Bài tập ứng dụng

**Tình huống:** SaaS có hai tenant `alpha` và `beta`. Alice là admin của `alpha`. Endpoint `GET /orders/{id}` sử dụng `hasAuthority('SCOPE_orders.read')` nhưng repository gọi `findById(id)`, trong khi bảng `orders` có cột `tenant_id`.

1. Giải thích vì sao request với token Alice có thể vẫn gây rò rỉ dữ liệu của `beta`.
2. Viết lại hợp đồng repository để bắt buộc truyền tenant lấy từ token đã xác thực.
3. Nêu cách xử lý khi Alice chuyển sang `beta` nhưng hiện không có membership của tenant này.
4. Đề xuất hai ca kiểm thử tại API và một ca kiểm thử cho tác vụ export bất đồng bộ.

**Gợi ý đáp án:** `orders.read` chỉ cho phép loại thao tác, không định nghĩa sở hữu dữ liệu. Repository cần truy vấn `findByTenantIdAndId(tenantId, id)`; server từ chối yêu cầu chọn `beta` nếu membership không cho phép và không cấp token `tenant_id=beta`. Test nên dùng ID tài nguyên thật của tenant khác, kể cả với token có scope hợp lệ, và xác nhận export không chứa bản ghi ngoài tenant.

## Ghi nhớ

- **Tenant claim là dữ kiện phân quyền do nguồn tin cậy phát hành**, không phải tham số tùy ý do client quyết định.
- **Token hợp lệ là điều kiện cần**, chưa đủ để được truy cập tài nguyên: cần kiểm tra audience, scope/permission, active tenant và quyền trên đối tượng.
- **Tenant boundary phải có ở mọi đường truy cập dữ liệu**, kể cả database, cache, file, search, queue và các service downstream.
- **Chuyển tenant và thu hồi membership là vấn đề của vòng đời token**; phải thiết kế đồng bộ với authorization server và chính sách phiên.

### Đọc thêm

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OWASP API Security Top 10 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)

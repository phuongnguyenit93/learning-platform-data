# Tenant trong token có đáng tin không?

**Câu trả lời:** Có thể dùng thông tin tenant trong token làm **đầu vào đáng tin cậy có điều kiện** sau khi đã xác thực token và kiểm tra ý nghĩa của claim theo hợp đồng với bên phát hành. Tuy nhiên, `tenant_id` trong một token hợp lệ **không tự động chứng minh** người gọi hiện có quyền truy cập tenant đó, càng không chứng minh họ được phép đọc mọi dữ liệu của tenant. Quyết định cuối cùng phải kết hợp token, trạng thái thành viên/quyền hiện tại và ranh giới tenant của tài nguyên.

Bài học thuộc chủ đề **Multi-tenant** trong nền tảng bảo mật token: phân biệt nguồn gốc claim, xác thực JWT hoặc opaque token, sử dụng access token đúng mục đích, xác định tenant được phép truy cập và chống truy cập chéo tenant khi làm việc với OAuth 2.0/OIDC, API, cơ sở dữ liệu và dịch vụ nội bộ.

## 1. Bài toán: Một token đi qua nhiều tenant

Trong ứng dụng SaaS, **tenant** là một ranh giới cách ly nghiệp vụ và dữ liệu, chẳng hạn một công ty khách hàng hoặc một tổ chức. Một người dùng có thể thuộc nhiều tenant; một tenant có nhiều người dùng, vai trò và tài nguyên riêng.

Ví dụ:

- An là nhân viên của tenant `acme`, có quyền đọc hóa đơn ở `acme`.
- An cũng là khách mời của tenant `beta`, nhưng chưa được cấp quyền xem hóa đơn ở `beta`.
- API nhận yêu cầu `GET /tenants/beta/invoices/inv-73` kèm access token hợp lệ có `tenant_id: "acme"`.

Chữ ký token đúng **không có nghĩa** yêu cầu trên hợp lệ. Token đang ràng buộc phiên truy cập vào `acme`, trong khi URL yêu cầu tài nguyên của `beta`. API cần từ chối trước khi truy vấn tài nguyên của `beta`.

Phải phân biệt các khái niệm:

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| Authentication (xác thực) | Token do ai phát hành, đã được xác minh và đại diện cho chủ thể nào? |
| Tenant context (ngữ cảnh tenant) | Yêu cầu hiện nhắm tới tenant nào? Tenant đó được xác định bằng quy tắc nào? |
| Authorization (phân quyền) | Chủ thể hiện có quyền thực hiện hành động này trong tenant đó không? |
| Resource isolation (cách ly dữ liệu) | Tài nguyên đang truy cập có thực sự thuộc tenant được phép không? |

Chỉ khi cả bốn câu hỏi được giải quyết, hệ thống mới nên phục vụ yêu cầu.

## 2. Phân biệt nguồn thông tin tenant

`tenant_id` chỉ là tên claim thường gặp; không có quy định rằng mọi nhà cung cấp danh tính đều dùng claim này với cùng ý nghĩa. Có hệ thống dùng `org_id` hoặc `organization`, có hệ thống dùng tenant để chỉ miền danh tính của nhà phát hành chứ không phải tenant sở hữu dữ liệu ứng dụng. Hợp đồng token phải xác định rõ **ai phát hành, định danh tenant nào, cho API nào và có quyền biểu đạt điều gì**.

| Nguồn tenant | Có thể tin trực tiếp? | Cách sử dụng đúng |
| --- | --- | --- |
| `X-Tenant-Id`, URL, body, query, subdomain do client chọn | **Không** | Chỉ là tenant *được yêu cầu*; đối chiếu với quyền được cấp |
| Payload JWT chỉ mới Base64URL-decode | **Không** | Ai cũng có thể sửa chuỗi này trước khi token được xác minh |
| `tenant_id` trong JWT đã xác minh đầy đủ | **Có điều kiện** | Là phát biểu của issuer, trong đúng mục đích và thời hạn token |
| Tenant từ opaque token đã introspection thành công | **Có điều kiện** | Là metadata bên phát hành trả về cho token còn hiệu lực |
| Membership/role hiện hành từ hệ thống quản lý quyền | **Có điều kiện** | Dùng để quyết định có quyền trên tenant và hành động cụ thể |
| Tenant ID của bản ghi trong database | **Cần cưỡng chế** | So khớp khi truy vấn hoặc ghi; tránh IDOR và rò rỉ chéo tenant |

Điểm then chốt là **tin nguồn phát biểu** khác với **tin kết luận phân quyền**. Issuer có thể xác nhận token được cấp cho `acme`, nhưng quyết định một hóa đơn cụ thể có được đọc hay không vẫn thuộc về resource server.

## 3. JWT hợp lệ nói lên điều gì?

Ví dụ payload access token minh họa (đây là JSON đã giải mã, **không phải** token để tự tin tưởng):

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["invoice-api"],
  "iat": 1795400000,
  "nbf": 1795400000,
  "exp": 1795400900,
  "jti": "token-7f2a",
  "scope": "invoice:read",
  "tenant_id": "acme"
}
~~~

Resource server nhận access token này cần:

1. **Xác minh nguồn gốc và tính toàn vẹn:** kiểm tra chữ ký bằng khóa đáng tin cậy của issuer đã cấu hình; giới hạn thuật toán hợp lệ, xử lý `kid`/JWKS theo chính sách đáng tin cậy. Không chấp nhận `alg: none` hay khóa/URL khóa do token tự chỉ định mà không kiểm soát.
2. **Kiểm tra issuer:** `iss` thuộc tập nhà phát hành được API tin tưởng, và khóa xác minh gắn với đúng issuer đó. Token có chữ ký hợp lệ của một issuer khác vẫn có thể không hợp lệ cho API.
3. **Kiểm tra nơi nhận:** `aud` bao gồm `invoice-api`. Token hợp lệ cho `profile-api` không được dùng thay thế chỉ vì cùng hệ thống ký.
4. **Kiểm tra thời gian và trạng thái:** `exp` chưa hết, `nbf`/`iat` hợp lý theo chính sách và độ lệch đồng hồ cho phép; áp dụng kiểm tra thu hồi hoặc trạng thái phiên nếu kiến trúc yêu cầu.
5. **Kiểm tra loại và mục đích token:** đây là **access token** được API chấp nhận; không lấy ID token dành cho client OIDC hay refresh token làm bearer token cho API. Nếu hệ thống có phân biệt `typ`/token class, phải kiểm tra theo hợp đồng phát hành.
6. **Diễn giải claim theo hợp đồng:** `tenant_id` được issuer gán sau khi kiểm tra người dùng hoặc service có quyền chọn tenant đó, với định dạng ID ổn định và không mơ hồ.

Nếu tất cả đạt, API có thể tin rằng **issuer đã phát biểu**: access token này gắn với `sub=user-123`, `tenant_id=acme` và `scope=invoice:read` cho `invoice-api` tại thời điểm phát hành. API vẫn phải kiểm tra chính sách hiện hành, ví dụ membership đã bị vô hiệu hóa sau khi token được cấp.

> **Quy tắc:** Token hợp lệ là một **bằng chứng danh tính và các quyền được phát biểu**, không phải tấm vé bỏ qua kiểm tra phân quyền ở resource server.

## 4. Chuỗi kiểm tra từ token đến dữ liệu

~~~mermaid
flowchart TD
    A["Yêu cầu API và access token"] --> B{"Xác minh token: chữ ký hoặc introspection; issuer, audience, thời hạn, loại token"}
    B -->|Không đạt| C["401 Unauthorized"]
    B -->|Đạt| D["Lấy chủ thể và tenant được token ràng buộc"]
    D --> E{"Tenant yêu cầu có khớp tenant được phép?"}
    E -->|Không| F["403 Forbidden hoặc 404 theo chính sách"]
    E -->|Có| G{"Membership, role, scope và chính sách hiện còn hợp lệ?"}
    G -->|Không| F
    G -->|Có| H["Truy vấn tài nguyên có điều kiện tenant_id"]
    H --> I{"Tài nguyên thuộc đúng tenant?"}
    I -->|Không hoặc không tồn tại| J["404 Not Found"]
    I -->|Có| K["Trả dữ liệu được phép"]
~~~

Trong mô hình **token chỉ gắn một tenant**, API yêu cầu:

`requested_tenant == verified_token.tenant_id`

Trong mô hình một token được phép truy cập **nhiều tenant**, phép so sánh đơn giản này không đủ: API phải xác định tenant đang hoạt động, kiểm tra tenant đó thuộc tập được issuer/chính sách cho phép, kiểm tra membership/quyền **trên tenant cụ thể**, rồi truy vấn dữ liệu với tenant ấy. Với nghiệp vụ nhạy cảm, nên cân nhắc cấp access token ngắn hạn được ràng buộc một tenant cho mỗi lần chuyển ngữ cảnh để dễ kiểm toán và giảm nhầm lẫn.

Không được suy ra tenant được phép từ email domain, hostname, tên hiển thị tổ chức hoặc một header bất kỳ. Các giá trị này có thể dùng để định tuyến hoặc gợi ý giao diện, nhưng không thay thế phép kiểm tra quyền.

## 5. Áp dụng với Spring Security và truy vấn dữ liệu

Giả sử `invoice-api` được cấu hình làm OAuth 2.0 Resource Server, chỉ nhận access token hợp lệ từ issuer xác định, xác minh `aud=invoice-api` và ánh xạ scope thành authority dạng `SCOPE_invoice:read`. Ví dụ Java dưới đây tập trung vào **bước phân quyền sau khi token đã được xác minh**:

~~~java
@Service
public class InvoiceService {
    private final MembershipService membershipService;
    private final InvoiceRepository invoiceRepository;

    public InvoiceService(MembershipService membershipService,
                          InvoiceRepository invoiceRepository) {
        this.membershipService = membershipService;
        this.invoiceRepository = invoiceRepository;
    }

    @PreAuthorize("hasAuthority('SCOPE_invoice:read')")
    @Transactional(readOnly = true)
    public Invoice getInvoice(Jwt verifiedAccessToken,
                              String tenantFromPath,
                              String invoiceId) {
        // Jwt phải lấy từ SecurityContext sau khi Resource Server xác minh.
        String tenantFromToken = verifiedAccessToken.getClaimAsString("tenant_id");
        if (tenantFromToken == null || !tenantFromToken.equals(tenantFromPath)) {
            throw new AccessDeniedException("Tenant mismatch");
        }

        // Kiểm tra quyền hiện hành bằng nguồn dữ liệu có thẩm quyền.
        String subject = verifiedAccessToken.getSubject();
        if (!membershipService.canReadInvoices(subject, tenantFromToken)) {
            throw new AccessDeniedException("Tenant permission denied");
        }

        // Điều kiện tenant đi vào truy vấn; không fetch theo invoiceId rồi
        // mới hy vọng tầng ứng dụng sẽ lọc đúng.
        return invoiceRepository
                .findByIdAndTenantId(invoiceId, tenantFromToken)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }
}
~~~

Đây là ví dụ minh họa phần service; ứng dụng thực tế còn cần cấu hình `SecurityFilterChain`/`JwtDecoder`, kiểm tra issuer, audience, thời gian, policy thuật toán, xử lý lỗi và bật method security (`@EnableMethodSecurity`). Không tạo `Jwt` từ dữ liệu request hay tin vào payload tự decode rồi truyền vào method. Nếu ứng dụng hỗ trợ service account, hãy dùng chính sách riêng cho service principal thay vì giả định `sub` luôn là user ID.

Ở tầng lưu trữ, nguyên tắc quan trọng là mọi đường truy cập dữ liệu theo tenant đều phải ràng buộc bằng tenant được ủy quyền:

~~~sql
SELECT id, tenant_id, amount, currency
FROM invoices
WHERE id = :invoice_id
  AND tenant_id = :authorized_tenant_id;
~~~

Với lệnh `UPDATE`, `DELETE`, danh sách, tìm kiếm, export, báo cáo và background job cũng phải áp dụng cùng giới hạn. Nếu có PostgreSQL Row-Level Security (RLS), có thể dùng như lớp phòng vệ bổ sung, với cơ chế đặt tenant context trong transaction an toàn và kết nối được reset đúng cách. RLS không thay thế việc kiểm tra quyền nghiệp vụ.

### Vì sao kiểm tra token thôi vẫn thất bại?

Ví dụ mã nguy hiểm:

~~~java
// Token của acme hợp lệ nhưng invoiceId có thể thuộc beta.
return invoiceRepository.findById(invoiceId).orElseThrow();
~~~

Nếu ID hóa đơn có thể đoán hoặc rò rỉ, người dùng `acme` có thể truy cập hóa đơn `beta` dù `tenant_id` trong token hoàn toàn hợp lệ. Đây là biến thể của **Broken Object Level Authorization (BOLA/IDOR)**. Cần kiểm soát **đúng hành động trên đúng tài nguyên trong đúng tenant**, không chỉ kiểm soát đăng nhập.

## 6. Những tình huống dễ hiểu sai

### 6.1. Tenant trong URL khác tenant trong token

~~~http
GET /tenants/beta/invoices/inv-73 HTTP/1.1
Authorization: Bearer <access-token-bound-to-acme>
~~~

Với token một tenant, phải từ chối. Không lấy `beta` từ URL rồi ghi đè `tenant_id` trong security context; cũng không lấy `acme` trong token để ngầm thay URL mà không làm rõ ngữ nghĩa yêu cầu. Chính sách lỗi có thể trả `403` hoặc `404` nhằm giảm lộ thông tin, nhưng phải thống nhất.

### 6.2. Người dùng bị xóa khỏi tenant sau khi token phát hành

JWT vẫn có thể còn chữ ký và `exp` hợp lệ. Nếu quyền cần được thu hồi tức thì, chỉ đọc role/membership cũ từ JWT là không đủ. Các cách giảm cửa sổ rủi ro gồm access token ngắn hạn, kiểm tra membership/policy hiện tại ở API, phiên bản phân quyền (`membership_version` hoặc `authz_version`) và cơ chế vô hiệu hóa token/phiên khi cần. Việc dùng cache quyền phải có TTL và cơ chế invalidation tương ứng yêu cầu thu hồi.

### 6.3. Người dùng thuộc hai tổ chức

Một user `sub=user-123` có quyền khác nhau ở `acme` và `beta`. Scope `invoice:read` không có tenant context **không** đủ suy ra quyền đọc hóa đơn của cả hai. Thiết kế có thể chọn:

1. Phát access token theo tenant đang chọn, với `tenant_id` đã được kiểm tra tại thời điểm cấp.
2. Dùng token đa tenant nhưng có tập tenant/quyền được cấp được định nghĩa tường minh và xác thực riêng cho tenant đang yêu cầu.

Khi chuyển tổ chức trên giao diện, client phải xin quyền/ngữ cảnh hợp lệ tương ứng; đổi dropdown, URL hoặc header không tự làm token cũ có thêm quyền.

### 6.4. Chữ ký đúng nhưng sai issuer hoặc audience

Một JWT được ký hợp lệ cho `analytics-api` không trở thành token của `invoice-api`. Tương tự, tenant ID cùng tên do một issuer không tin cậy cấp không có ý nghĩa tại hệ thống của bạn. Cần ánh xạ rõ issuer, khóa, loại token, audience và namespace của tenant ID; không gộp các issuer chỉ vì claim có cùng tên.

### 6.5. Quản trị viên hoặc dịch vụ nội bộ truy cập nhiều tenant

Quyền hỗ trợ khách hàng, kiểm toán hoặc thao tác service-to-service phải có **quyền liên tenant được cấp tường minh**, giới hạn hành động, phạm vi tenant, mục đích và thời hạn; ghi audit cho các thao tác nhạy cảm. Không suy luận rằng token mang role `admin` hoặc scope `*` đương nhiên được đọc mọi tenant. Với client credentials, `sub` có thể là một client/service, không phải người dùng; cần chính sách riêng cho service identity và tenant mà dịch vụ được ủy quyền.

## 7. JWT, opaque token và các loại token trong multi-tenant

| Loại token | Xác minh gì? | Vai trò của tenant claim |
| --- | --- | --- |
| JWT access token | Chữ ký, issuer, audience, thời gian, loại token và chính sách hiệu lực | Claim đã xác minh biểu đạt tenant được issuer ràng buộc, nhưng API vẫn kiểm tra quyền hiện tại và tài nguyên |
| Opaque access token | Gọi introspection hoặc cơ chế kiểm tra đáng tin cậy; kiểm tra `active` và metadata đúng API | Tenant có thể lấy từ response introspection; vẫn phải xác thực quyền và tenant tài nguyên |
| OIDC ID token | Xác minh theo quy tắc OIDC tại client dự định nhận token | Dùng để biểu đạt thông tin xác thực đăng nhập cho client, **không thay access token để gọi API** |
| Refresh token | Được authorization server quản lý, kiểm tra và xoay vòng/thu hồi theo chính sách | Dùng xin access token mới, **không đưa thẳng cho resource API như bằng chứng phân quyền** |

Trong OAuth 2.0, token là một *bearer credential* nếu bất kỳ ai cầm token đều có thể sử dụng. Claim tenant không ngăn được **token theft/replay**: cần TLS, lưu trữ token an toàn, hạn sử dụng ngắn, refresh token rotation, phát hiện sử dụng lại và cân nhắc sender-constrained token (ví dụ mTLS hoặc DPoP) khi phù hợp. `jti` hữu ích cho audit hoặc cơ chế chống replay nếu hệ thống thực sự duy trì trạng thái tương ứng; chỉ có `jti` trong payload chưa tự ngăn replay.

## 8. Thiết kế vòng đời tenant claim

**Khi phát hành token:**

1. Xác thực user hoặc service theo quy trình phù hợp.
2. Nhận tenant mà client muốn làm việc như một **yêu cầu chọn ngữ cảnh**.
3. Authorization server kiểm tra tenant tồn tại, membership/quyền hoặc ủy quyền giữa dịch vụ và tenant còn hợp lệ.
4. Gắn tenant ID chuẩn từ nguồn tin cậy vào access token, quy định rõ `iss`, `aud`, `scope`, `exp` và loại token. Không sao chép nguyên giá trị client tự khai thành claim có thẩm quyền.
5. Ghi nhận phiên/ủy quyền để phục vụ audit, thay đổi quyền, thu hồi hoặc giới hạn tuổi thọ token theo rủi ro.

**Khi xử lý request:** resource server xác minh token theo `3`, kiểm tra tenant đang yêu cầu theo `4`, rồi kiểm tra quyền hiện tại và truy vấn dữ liệu có tenant predicate. Với opaque token, dùng thông tin introspection từ kênh đáng tin cậy thay vì tự giải mã chuỗi ngẫu nhiên.

**Khi đổi tenant:** yêu cầu lại access token tenant-bound hoặc chạy quy trình chọn tenant được hệ thống chấp nhận; không tái sử dụng nguyên token cũ như thể nó đã được chuyển quyền. **Khi thu hồi quyền:** thay đổi membership/policy và áp dụng cơ chế vô hiệu hóa hoặc kiểm tra lại phù hợp mức độ nhạy cảm. Nếu chỉ trông chờ JWT hết hạn, quyền đã thu hồi có thể còn được sử dụng đến `exp`.

## 9. Các bề mặt ngoài HTTP API dễ bị bỏ sót

- **Cache:** cache key phải chứa tenant ID đã được xác thực và các yếu tố quyền liên quan. Cache chỉ theo `invoiceId` có thể trả dữ liệu tenant khác.
- **Message queue và background job:** thông điệp chứa `tenant_id` là dữ liệu đầu vào; worker cần xác minh nguồn phát và ngữ cảnh ủy quyền của job, sau đó giới hạn truy vấn theo tenant.
- **Tìm kiếm, export, thống kê:** mọi query, index, object storage path và file tải xuống đều phải giữ ranh giới tenant; không chỉ endpoint `GET /invoice/{id}`.
- **Kết nối database dùng chung:** thread-local/connection/session tenant context phải được thiết lập và dọn sạch đúng vòng đời request/transaction để tránh rò tenant sang yêu cầu kế tiếp.
- **Audit và quan sát:** ghi subject, client ID, tenant đã được cấp, tenant được yêu cầu, hành động, kết quả và correlation ID theo quy định bảo mật. Tránh log access/refresh token nguyên văn hoặc dữ liệu nhạy cảm.
- **Mời khách, chuyển tổ chức, xóa tenant:** membership và các alias/domain thay đổi theo thời gian; ưu tiên tenant ID nội bộ ổn định thay vì suy quyền từ email hay tên tenant.

## 10. Checklist kiểm thử phân quyền tenant

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| JWT payload bị sửa `tenant_id` nhưng không ký lại hợp lệ | `401`, từ chối token |
| Token hết hạn, sai issuer, sai audience hoặc sai loại | `401`, từ chối token |
| Token hợp lệ cho `acme`, URL yêu cầu `beta` | Từ chối trước khi đọc dữ liệu `beta` |
| Token `acme`, hóa đơn ID thuộc `beta` | Không trả dữ liệu; query phải có tenant predicate |
| User hợp lệ nhưng đã rời `acme` | Từ chối khi chính sách yêu cầu quyền còn hiệu lực |
| User là viewer ở `acme`, admin ở `beta` | Quyền phải đúng từng tenant, không trộn vai trò |
| Có scope `invoice:read` nhưng không có membership tenant | Từ chối |
| ID token/refresh token gửi cho endpoint API | Từ chối theo chính sách token của resource server |
| Cache/job/export cùng một ID ở hai tenant | Không trả nhầm dữ liệu, không trộn ngữ cảnh |
| Service account không được cấp quyền tenant `beta` | Từ chối dù service token được ký hợp lệ |
| Quyền liên tenant đã được cấp tường minh | Chỉ cho phép đúng tenant, hành động và thời hạn được ủy quyền; có audit |

Kiểm thử nên bao gồm cả **negative cases** và trường hợp tài nguyên không tồn tại. Nếu dùng `404` để che giấu sự tồn tại tài nguyên, mã lỗi và thông báo không được vô tình tiết lộ tên, ID hoặc dữ liệu của tenant khác.

## 11. Tình huống tự kiểm tra

Một API đã xác minh thành công chữ ký, `iss`, `aud` và `exp` của JWT mang `sub=user-123`, `tenant_id=acme`, `scope=invoice:read`. Người dùng gọi `GET /tenants/acme/invoices/inv-900`. Có thể trả hóa đơn ngay không?

**Chưa.** API cần xác nhận user/service hiện còn được đọc hóa đơn trong `acme` và `inv-900` thực sự thuộc `acme`; chỉ truy vấn theo `id` là chưa đủ. Nếu token bị đánh cắp, chữ ký vẫn hợp lệ đối với kẻ cầm token, nên các biện pháp chống đánh cắp và phát lại vẫn quan trọng.

**Ghi nhớ:** `tenant_id` trong token đã được xác minh trả lời “**issuer nói yêu cầu này được ràng buộc tenant nào?**”. Phân quyền và cách ly dữ liệu mới trả lời “**chủ thể có được làm hành động này với tài nguyên này, trong tenant này, ngay bây giờ không?**”.

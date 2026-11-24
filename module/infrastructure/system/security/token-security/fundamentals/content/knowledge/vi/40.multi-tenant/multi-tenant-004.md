# Cross-tenant token rejection: từ chối token truy cập sai tenant

## 1. Bối cảnh và mục tiêu

Trong hệ thống **multi-tenant**, một ứng dụng phục vụ nhiều tổ chức (tenant) nhưng dữ liệu, quyền và ngữ cảnh bảo mật của mỗi tổ chức phải được cách ly. **Cross-tenant token rejection** là quy tắc từ chối yêu cầu khi token không được phép đại diện cho chủ thể truy cập vào **tenant đích** của tài nguyên, kể cả khi chữ ký token hợp lệ.

Ví dụ: một người dùng thuộc tenant A đăng nhập và nhận access token hợp lệ. Người đó sửa URL từ `/tenants/A/invoices/123` thành `/tenants/B/invoices/456`. API phải phát hiện đây là thao tác vượt ranh giới tenant và từ chối, kể cả khi access token của A có scope `invoices:read`.

Bài học nằm trong nền tảng **Security Token Security Fundamentals**: cần hiểu vòng đời token, JWT/opaque token, access token/refresh token, OAuth 2.0/OIDC, kiểm tra claims, scope, audience và phòng chống token bị đánh cắp hoặc phát lại. Với multi-tenant, thêm một bất biến quan trọng: **token hợp lệ về mật mã chưa đồng nghĩa với được truy cập tài nguyên của mọi tenant**.

Sau bài này, người học có thể:

- Phân biệt xác thực token với kiểm tra quyền đối với tenant đích.
- Thiết kế cơ chế xác định tenant đích từ dữ liệu có thẩm quyền ở phía máy chủ.
- Từ chối token sai issuer, audience, token type, tenant context hoặc quyền trên tài nguyên.
- Xử lý đúng các trường hợp nhiều issuer, người dùng thuộc nhiều tenant và truy cập liên tenant được ủy quyền rõ ràng.
- Kiểm thử để ngăn lỗi IDOR/BOLA, confused deputy, lẫn cache và phát lại token giữa tenant.

## 2. Ranh giới tin cậy: ba khái niệm thường bị nhầm

| Khái niệm | Ý nghĩa | Điều **không** được suy ra |
| --- | --- | --- |
| **Token hợp lệ** | API đã xác minh chữ ký hoặc introspection, issuer, audience, thời hạn và các điều kiện dành cho access token. | Không chứng minh người dùng được đọc tất cả dữ liệu mà API quản lý. |
| **Tenant context của token** | Tenant mà token được phát hành hoặc ràng buộc để sử dụng, theo hợp đồng claims của hệ thống. | Không nhất thiết là tenant sở hữu tài nguyên đang yêu cầu; claim `tid` của một nhà cung cấp có thể biểu thị tenant gốc của danh tính. |
| **Tenant sở hữu tài nguyên** | Tenant gắn với bản ghi/tệp/đơn hàng theo cơ sở dữ liệu hoặc quan hệ sở hữu do server kiểm soát. | Không được tin chỉ vì client gửi `tenantId` qua path, body, header hay query. |

Các thông tin thường gặp:

- `iss` (issuer): đơn vị phát hành token, phải thuộc tập issuer được API tin cậy; khi có nhiều issuer, khóa xác minh và chính sách phải gắn với issuer tương ứng.
- `aud` (audience): API/nhóm tài nguyên mà token hướng tới. Access token dành cho API X không được mặc nhiên dùng ở API Y.
- `sub` (subject): định danh chủ thể. Trong mô hình nhiều issuer, dùng cặp **`(iss, sub)`**, không dùng riêng `sub` như khóa người dùng toàn cục.
- `tenant_id`, `tid` hoặc `resource_tenant`: claim tenant **không có một tên hay ngữ nghĩa chuẩn chung cho mọi nhà cung cấp**. Chỉ sử dụng sau khi định nghĩa và kiểm tra hợp đồng phát hành token.
- `scope`/`scp`/`roles`: đặc quyền được gán trong một ngữ cảnh. Scope `documents:read` không tự cấp quyền đọc tài liệu của tenant khác.
- `exp`, `nbf`, `iat`, `jti`: thời gian hiệu lực và mã định danh token (nếu có); chúng hỗ trợ kiểm soát vòng đời, không thay thế kiểm tra tenant.

> **Bất biến cốt lõi:** với mỗi thao tác, hệ thống phải chứng minh được **chủ thể đã xác thực + ngữ cảnh tenant được chấp nhận + quyền cụ thể + tài nguyên thuộc tenant được phép truy cập**. Thiếu bất kỳ điều kiện nào thì từ chối theo mặc định.

## 3. Minh họa đường tấn công và điểm từ chối

Giả sử hệ thống có tenant A và B, cùng sử dụng `billing-api`:

```text
Client với access token của tenant A
          |
          | GET /tenants/B/invoices/456
          v
[1] Xác minh access token (issuer, chữ ký, aud, exp...)
          |  PASS: token của A hợp lệ
          v
[2] Tìm hóa đơn 456 trong kho dữ liệu
          |  ownerTenant = B
          v
[3] Đối chiếu path tenant với ownerTenant
          |  B = B -> PASS
          v
[4] Kiểm tra token có hiệu lực cho tenant B?
          |  token bound to A -> FAIL
          v
[5] TỪ CHỐI (403; hoặc 404 theo chính sách che giấu tài nguyên)
```

Lỗi dễ mắc nhất là dừng ở bước [1]. Một JWT được ký đúng chỉ chứng minh nội dung do issuer được tin cậy phát hành và chưa bị sửa; nó không tự chứng minh người gọi được phép truy cập tenant B.

**Cách tấn công tương tự:** đổi ID đơn hàng trong body, gửi `X-Tenant-Id: B`, sửa biến GraphQL `tenantId`, đọc tài liệu qua đường dẫn tải file, hoặc đưa job xử lý nền chạy dưới tenant B. Điểm kiểm soát phải áp dụng ở mọi đường vào truy cập tài nguyên, không chỉ một REST controller.

## 4. Quy trình kiểm tra an toàn theo thứ tự

### Bước 1 — Xác thực đúng loại access token

Với JWT access token, lớp resource server cần:

1. Chỉ chấp nhận thuật toán ký đã cấu hình; xác minh chữ ký với khóa thuộc issuer đáng tin và cơ chế xử lý `kid` an toàn. Không chấp nhận `alg=none` hoặc tự nạp JWKS từ URL do header token điều khiển.
2. Kiểm tra `iss` chính xác theo danh sách được tin cậy; trong hệ thống có nhiều issuer, ánh xạ issuer tới JWKS và chính sách tương ứng. Không tin một issuer mới chỉ vì token tự khai báo URL của nó.
3. Kiểm tra `aud` có chứa audience được cấu hình cho API hiện tại; kiểm tra `exp`, `nbf` và độ lệch thời gian hợp lý. Áp dụng `iat`/tuổi tối đa nếu chính sách yêu cầu.
4. Phân biệt **access token** với **ID token** và **refresh token**. ID token chứng minh kết quả đăng nhập cho client OIDC; refresh token dùng xin token mới tại authorization server. Không dùng hai loại này làm bearer access token cho API.
5. Kiểm tra các claims bắt buộc, định dạng tenant context và scope/role nền tảng theo hợp đồng issuer.

Nếu hệ thống dùng **opaque access token**, API thực hiện introspection với authorization server đáng tin, yêu cầu `active=true` và kiểm tra audience, issuer/ngữ cảnh phát hành, client, scope và tenant context theo dữ liệu được trả về. Chỉ thấy `active=true` chưa đủ để cấp quyền vào tenant đích.

**Kết quả:** có một danh tính/token đã được xác thực để đi tiếp. Thông tin token chưa phải quyết định cấp quyền tài nguyên.

### Bước 2 — Xác định tenant đích có thẩm quyền

Server nhận `/tenants/{tenantId}/documents/{documentId}`. `tenantId` trên URL có thể dùng làm **tham số lựa chọn tenant**, nhưng phải tra dữ liệu:

- `documents.tenant_id` là thuộc tính sở hữu lưu tại cơ sở dữ liệu;
- nếu `documentId` thuộc tenant B mà path ghi A, trả về lỗi, không cố truy cập theo tenant A;
- truy vấn kho dữ liệu nên luôn kèm tenant predicate, ví dụ `WHERE id = :id AND tenant_id = :authorizedTenant`, để có lớp bảo vệ ngay tại data access;
- nếu tenant được xác định từ subdomain, gateway hoặc header thì vẫn cần kiểm tra ánh xạ được tin cậy và đối chiếu với chủ sở hữu tài nguyên.

Không dùng dữ liệu mà client tự chọn như `X-Tenant-Id` để vượt kiểm tra. Với quan hệ lồng nhau (tenant → project → document), cần kiểm tra đúng chuỗi sở hữu, không chỉ một ID ở path.

### Bước 3 — Ràng buộc token và chủ thể với tenant đích

Có hai mô hình chính; cần chọn rõ mô hình trước khi viết validator:

| Mô hình | Điều kiện chấp nhận | Điểm cần thận trọng |
| --- | --- | --- |
| **Tenant-bound access token** (mặc định dễ kiểm soát) | Token được authorization server tin cậy phát hành **cho tenant đích**; claim như `resource_tenant` khớp tenant sở hữu tài nguyên; người dùng còn tư cách và quyền. | Không đồng nhất mọi claim `tid` của IDP với `resource_tenant`; claim phải có hợp đồng ngữ nghĩa rõ ràng. |
| **Ủy quyền liên tenant có chủ đích** (B2B/delegation) | Có grant/membership rõ ràng cho tenant đích, audience/scope phù hợp, chính sách tin cậy và các giới hạn tài nguyên được xác nhận ở phía server. | Token của A không được tự động dùng ở B chỉ vì cùng issuer hoặc người dùng có vai trò `admin` ở A. |

Một tài khoản có thể là thành viên của cả A và B. Điều đó **không đồng nghĩa** access token đang dùng cho A tự động có hiệu lực ở B. Thiết kế phổ biến là cho client **chuyển tenant bằng một bước cấp lại/trao đổi token**, nhận access token ràng buộc với B sau khi authorization server xác minh quyền. Với mô hình delegation khác, mọi ngoại lệ cũng phải biểu diễn thành grant minh bạch, giới hạn theo tenant đích và kiểm tra tại lúc sử dụng.

### Bước 4 — Kiểm tra quyền cụ thể trên tài nguyên

Sau khi tenant đã khớp, tiếp tục kiểm tra trạng thái thành viên, quyền sở hữu/chia sẻ tài nguyên và action được yêu cầu (ví dụ `invoices:read`, `invoices:write`). Phân quyền có thể kết hợp RBAC, ABAC và quan hệ chia sẻ.

**Quy tắc fail closed:** tenant không khớp, thiếu claim bắt buộc, thành viên bị thu hồi, grant hết hiệu lực hoặc không xác định được chủ sở hữu tài nguyên → từ chối. Không dùng giá trị mặc định như `public` hay tenant đầu tiên của tài khoản để “cứu” request thiếu ngữ cảnh.

## 5. Ví dụ Spring Security (Java) ở lớp ứng dụng

Giả định Spring Security Resource Server đã **xác minh JWT access token** với issuer, audience, chữ ký và thời hạn. Authorization server của ứng dụng phát hành claim riêng `resource_tenant` chứa UUID tenant đích, sau khi kiểm tra quyền chọn tenant. Đoạn Java dưới đây minh họa kiểm tra tại service; các interface repository và exception tài nguyên là thành phần ứng dụng cần hiện thực.

```java
public DocumentView readDocument(
        UUID tenantInPath,
        UUID documentId,
        Jwt verifiedAccessToken) {

    // Tra quyền sở hữu thật từ DB; không suy từ URL/header.
    Document document = documents.findById(documentId)
            .orElseThrow(DocumentNotFoundException::new);

    if (!document.tenantId().equals(tenantInPath)) {
        throw new DocumentNotFoundException();
    }

    UUID tokenTenant = requireTenantClaim(
            verifiedAccessToken, "resource_tenant");

    if (!document.tenantId().equals(tokenTenant)) {
        throw new AccessDeniedException("TENANT_MISMATCH");
    }

    // Subject có thể trùng giữa các issuer khác nhau.
    Identity identity = new Identity(
            verifiedAccessToken.getIssuer().toString(),
            verifiedAccessToken.getSubject());

    if (!memberships.isActive(identity, tokenTenant)
            || !permissions.canRead(identity, documentId, tokenTenant)) {
        throw new AccessDeniedException("ACCESS_DENIED");
    }

    return DocumentView.from(document);
}

private UUID requireTenantClaim(Jwt jwt, String claimName) {
    String value = jwt.getClaimAsString(claimName);
    if (value == null || value.isBlank()) {
        throw new AccessDeniedException("TENANT_CLAIM_MISSING");
    }

    try {
        return UUID.fromString(value);
    } catch (IllegalArgumentException exception) {
        throw new AccessDeniedException("TENANT_CLAIM_INVALID");
    }
}
```

Lưu ý khi triển khai thật:

- Chỉ truyền `Jwt` đã được resource server **xác minh**, không tự parse chuỗi JWT rồi coi các claims là đáng tin.
- `resource_tenant` là claim ứng dụng tự định nghĩa, không phải claim JWT/OIDC chuẩn. Issuer đáng tin phải chịu trách nhiệm ràng buộc claim đó với tenant được phép truy cập. Nếu không có claim này thì cần một cơ chế tenant authorization được định nghĩa rõ, thay vì tự đoán từ `tid`.
- Áp dụng kiểm tra trong service/data-access hoặc policy dùng chung để API REST, GraphQL, gRPC và background job không bỏ sót. Kết hợp truy vấn có `tenant_id` để giảm rủi ro IDOR/BOLA.
- Nếu membership/grant có thể bị thu hồi tức thời, không chỉ tin claims chứa quyền cũ cho đến khi hết `exp`; kiểm tra trạng thái hiện tại hoặc thiết kế TTL, revocation và cache invalidation phù hợp.
- Đường đi cho B2B/delegation là một **chính sách riêng** với grant có thể kiểm toán; ví dụ trên cố ý thực thi mô hình tenant-bound token nghiêm ngặt.

Một middleware kiểm tra `tokenTenant == pathTenant` vẫn có thể bỏ lọt dữ liệu nếu `documentId` thực tế thuộc tenant khác. Vì vậy phải kiểm tra cả **tenant sở hữu tài nguyên**.

## 6. Nhiều issuer, JWKS và OAuth 2.0/OIDC

Trong hệ thống SaaS, có thể gặp:

**Một issuer chung cho nhiều tenant:** cùng `iss` và tập khóa ký, nhưng authorization server phát hành access token ràng buộc `resource_tenant`. API xác minh token như thường lệ, sau đó so tenant đích và permission. Chữ ký dùng chung không khiến các tenant được truy cập chéo.

**Issuer riêng cho từng tenant:** API lưu danh sách issuer được tin và ánh xạ cấu hình/JWKS cho từng issuer. Khi nhận token từ issuer A yêu cầu tài nguyên B, có thể từ chối ở mức issuer-to-tenant policy, trước cả khi kiểm tra quyền chi tiết. Không dùng issuer URL do token tùy ý đưa vào để tự tạo trust mới.

**Liên kết danh tính B2B:** người dùng có thể đăng nhập bằng issuer của tổ chức gốc nhưng được cấp quyền tại tenant khách. Cần tách **home identity tenant** với **resource tenant**. Quyền khách phải đến từ quan hệ tin cậy và grant do tenant đích chấp thuận, không chỉ từ một claim `groups`/`roles` trong token của tổ chức gốc.

Đặc biệt:

- OAuth 2.0 scopes chỉ có ý nghĩa trong phạm vi audience và tenant context đã được ràng buộc.
- OIDC ID token thường có `aud` là **client ID**; không được dùng làm access token chỉ vì có `sub`, `email` hoặc `tid`.
- Với JWT access token theo RFC 9068, kiểm tra các quy tắc profile tương ứng (ví dụ kiểu token `at+jwt` nếu profile áp dụng). Các nhà cung cấp khác có thể dùng profile riêng và cần cấu hình đúng hợp đồng.
- Không cho phép thuật toán bất ngờ, khóa JWT từ issuer A xác minh token mạo danh issuer B, hay chấp nhận token từ một issuer không được onboarding.

## 7. Chống phát lại, thu hồi và lẫn ngữ cảnh tenant

Cross-tenant rejection cần đồng bộ với vòng đời token:

| Tình huống | Biện pháp |
| --- | --- |
| Người dùng chuyển từ tenant A sang B | Yêu cầu bước chọn/chứng thực quyền tenant B và cấp token có tenant context phù hợp; làm mới dữ liệu, permissions và giao diện theo B. |
| Access token của A bị đánh cắp | Token ngắn hạn, lưu trữ an toàn, HTTPS, kiểm soát audience/tenant; DPoP hoặc mTLS có thể giảm khả năng dùng token bị sao chép nếu triển khai phù hợp. Chúng **không** thay thế kiểm tra tenant. |
| Refresh token của A bị dùng khi đang thao tác trong B | Refresh token phải gắn với client, tài khoản và phiên/grant; server không phát hành access token cho B nếu chưa kiểm tra quyền B. Dùng rotation và revocation theo chính sách. |
| Xóa thành viên A/B hoặc hủy delegation | Hủy grant/phiên liên quan, làm mất hiệu lực token hoặc chấp nhận thời gian tồn tại tối đa được thiết kế; invalidate cache quyền và ghi nhận audit. |
| Cache trả dữ liệu của A cho B | Cache key phải chứa tenant sở hữu tài nguyên và ngữ cảnh phân quyền phù hợp; không chỉ dùng `documentId` hoặc `sub`. |
| Event/queue/job thiếu tenant | Đưa tenant context đáng tin vào job metadata, kiểm tra lại tại worker và truy vấn dữ liệu theo tenant; không lấy tenant từ payload tùy ý. |

Trong trình duyệt, bảo vệ refresh token và access token theo mô hình client (ví dụ backend-for-frontend và cookie `HttpOnly`/`Secure`/`SameSite` khi phù hợp), chống CSRF đối với xác thực qua cookie, và xóa trạng thái/cache khi chuyển tenant. Không ghi token đầy đủ vào log.

## 8. Tình huống dễ mắc và cách sửa

**Sai 1 — Chỉ kiểm chữ ký:** API trả 200 vì JWT ký hợp lệ, bất kể URL đang trỏ tenant nào. **Sửa:** thêm tenant authorization sau authentication và trước data access.

**Sai 2 — Tin `X-Tenant-Id`:** client gửi `X-Tenant-Id: B` để chọn dữ liệu B. **Sửa:** header chỉ là hint; kiểm tra token, policy và ownerTenant trong DB; nếu gateway cấp header thì phải đảm bảo loại bỏ header từ client và vẫn ủy quyền tại backend.

**Sai 3 — Cho scope thay quyền tenant:** token `documents:read` của A đọc tài liệu B. **Sửa:** đánh giá scope cùng audience, tenant context, membership/grant và ACL tài nguyên.

**Sai 4 — Dùng `tid` mà không hiểu nghĩa:** với IDP liên kết danh tính, `tid` có thể là tenant phát hành hoặc tenant gốc, khác tenant của tài nguyên. **Sửa:** định nghĩa riêng claim “tenant mà access token có hiệu lực” hoặc ánh xạ grant được server xác thực.

**Sai 5 — Quản trị tenant A thành quản trị toàn hệ thống:** role `admin` thuộc A bị áp dụng ở B. **Sửa:** phân biệt tenant admin, system admin và các quyền đặc biệt theo policy được cấp rõ, kiểm toán đầy đủ.

**Sai 6 — Chặn controller nhưng quên truy vấn trực tiếp:** endpoint A có guard, nhưng API tải file/GraphQL resolver/job vẫn truy xuất theo ID trần. **Sửa:** thực thi tenant predicate và policy tại lớp dùng chung; có thể dùng row-level security như lớp bảo vệ bổ sung nếu phù hợp.

## 9. Kiểm thử tối thiểu theo ma trận tenant

Chuẩn bị hai tenant A/B, người dùng `alice-A` và `bob-B`, tài liệu `doc-A` thuộc A và `doc-B` thuộc B, token đúng audience `documents-api`.

| Ca kiểm thử | Token và request | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ cùng tenant | Token A, đọc `/tenants/A/doc-A`, đủ quyền | Cho phép (ví dụ 200). |
| Truy cập chéo tenant | Token A, đọc `/tenants/B/doc-B` | Từ chối (403 hoặc 404 theo chính sách). |
| Giả mạo tenant ở path | Token A, đọc `/tenants/A/doc-B` | 404 hoặc từ chối; tuyệt đối không trả `doc-B`. |
| Scope đủ nhưng tenant sai | Token A có `documents:read`, đọc `doc-B` | Từ chối. |
| Người dùng thuộc cả A và B nhưng token A-bound | Token A, đọc `doc-B` | Từ chối, trừ khi có chính sách delegation rõ ràng cho chính token đó. |
| Token đúng tenant nhưng thiếu quyền | Token A không có `documents:read`, đọc `doc-A` | 403. |
| Audience khác | Token cấp cho `analytics-api` dùng ở `documents-api` | 401. |
| Issuer không tin cậy hoặc chữ ký sai | JWT do issuer lạ/mạo danh phát hành | 401. |
| ID token hoặc refresh token dùng tại API | Gửi nhầm loại token | 401. |
| Token hết hạn/chưa có hiệu lực | `exp` quá hạn hoặc `nbf` ở tương lai | 401. |
| Tenant context thiếu hoặc sai kiểu | JWT đã xác thực nhưng thiếu claim bắt buộc | Từ chối theo chính sách: 401 nếu validator coi token không hợp lệ; 403 nếu policy coi token không đủ quyền. |
| Thành viên vừa bị thu hồi | Token còn hạn, grant B không còn | Từ chối theo chính sách thu hồi đã thiết kế. |
| Delegation hợp lệ | Identity A có grant được B phê duyệt, token và quyền giới hạn B | Chỉ cho phép các hành động/tài nguyên nằm trong grant. |
| Lẫn cache hoặc job | Dùng cùng document ID qua tenant hoặc job thiếu tenant context | Không trả/chạy dữ liệu tenant khác. |

Cần test cả ba lớp: **validator token**, **tenant authorization policy** và **data-access isolation**. Với ứng dụng hỗ trợ đổi tenant, thêm integration test chuyển A → B → A, refresh token, revoke membership, key rotation và các request đồng thời để bắt lỗi cache/context bị tái sử dụng.

### Mã lỗi và audit

- **401 Unauthorized**: không có access token hợp lệ cho API (chữ ký, issuer, audience, thời hạn, token type...).
- **403 Forbidden**: token đã xác thực nhưng không có quyền ở tenant/tài nguyên đích.
- **404 Not Found**: có thể dùng để tránh tiết lộ tài nguyên của tenant khác; phải nhất quán và không tạo đường dò ID qua response/timing.

Log nên ghi request/correlation ID, issuer, subject định danh an toàn, token ID dạng đã được xử lý phù hợp (nếu có), tenant context, tenant đích, resource type, quyết định policy và lý do mã hóa như `TENANT_MISMATCH`. Không log nguyên bearer token, refresh token hay dữ liệu nhạy cảm.

## 10. Checklist thiết kế

- [ ] Mỗi API chỉ chấp nhận access token đúng issuer, signature/introspection, audience, thời hạn và token type.
- [ ] Tenant context của access token có định nghĩa rõ, do thực thể phát hành đáng tin thiết lập.
- [ ] Tenant đích được đối chiếu với chủ sở hữu tài nguyên do server quản lý.
- [ ] Quyền truy cập được đánh giá theo `(issuer, subject, tenant, action, resource)` và tình trạng grant hiện hành.
- [ ] Tenant A không thể đọc/ghi dữ liệu B bằng cách đổi URL, ID, header, body, query hoặc token từ issuer khác.
- [ ] B2B/delegation được mô hình hóa thành ngoại lệ có grant cụ thể, giới hạn phạm vi và có thể thu hồi.
- [ ] REST, GraphQL, gRPC, download, cache, message queue và background job cùng tuân thủ chính sách tenant.
- [ ] Kiểm thử lỗi, giám sát và log không làm lộ token hoặc tài nguyên của tenant khác.

**Ghi nhớ:** “JWT signature valid” là điểm bắt đầu của xác thực token. **Cross-tenant token rejection** chỉ hoàn tất khi API chứng minh token và chủ thể có quyền trên **tenant sở hữu tài nguyên cụ thể**; nếu không chứng minh được thì từ chối.

## Tài liệu đối chiếu

- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): phòng chống nhầm issuer/audience, thuật toán và các kiểu token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): yêu cầu dành cho JWT access token theo profile.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh trạng thái opaque token và metadata tại resource server.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ý nghĩa của ID token trong luồng OIDC.

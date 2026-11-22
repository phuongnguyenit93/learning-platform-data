# Claims tenant và ngăn rò rỉ quyền giữa các tổ chức

## 1. Vì sao ranh giới tenant phải được kiểm tra ở nhiều lớp?

Trong hệ thống multi-tenant, một nền tảng phục vụ nhiều tổ chức (tenant) trên cùng hạ tầng. Người dùng có thể thuộc một hoặc nhiều tổ chức; mỗi tổ chức có dữ liệu, thành viên, vai trò và chính sách riêng.

JWT thường mang danh tính chủ thể và một phần thông tin quyền. Hệ thống có thể thêm claim tenant để xác định ngữ cảnh tổ chức mà token được phát hành. Tuy nhiên, **claim tenant chỉ là đầu vào cho quyết định authorization; nó không tự tạo ra ranh giới cách ly dữ liệu**.

Rò rỉ quyền giữa các tenant xảy ra khi một request được xác thực đúng nhưng ứng dụng áp dụng sai ngữ cảnh tổ chức. Ví dụ:

- Người dùng thuộc Tenant A gửi token hợp lệ của mình nhưng thay ID hóa đơn thành ID của Tenant B.
- API nhận tenant_id từ request body hoặc header rồi dùng trực tiếp để truy vấn dữ liệu.
- Một dịch vụ nội bộ tin X-Tenant-ID do caller gửi mà không kiểm tra caller có quyền hoạt động trong tenant đó.
- Cache dùng resource ID làm key mà không đưa tenant vào key, khiến dữ liệu của A được trả cho B.
- Background job được tạo trong tenant A nhưng worker xử lý bằng context tenant B hoặc context mặc định.
- Một vai trò admin được hiểu là quyền toàn nền tảng dù thực tế chỉ là admin trong một tenant.

Bảo vệ đúng cần kết hợp xác minh JWT, kiểm tra membership, ràng buộc tenant với tài nguyên, authorization ở từng service và cách ly ở database/cache/queue. Một token có chữ ký hợp lệ vẫn có thể bị dùng sai tenant nếu các lớp này không nhất quán.

Bài học này thuộc chương **Ranh giới dịch vụ** của học phần **Security - JSON Web Token (JWT)** (SECURITY_TOKEN_SECURITY_JWT). Nội dung áp dụng cho kiến trúc multi-tenant và JWT/JOSE nói chung, không phụ thuộc Java, Spring Security hay framework cụ thể.

## 2. Tenant claim là gì?

Tenant claim là claim do hệ thống định nghĩa để biểu thị tenant context của token. JWT không quy định một claim tenant phổ quát có cùng ý nghĩa cho mọi sản phẩm.

Một số hệ thống dùng tên như:

- tenant_id
- org_id
- organization
- tid

Đây thường là custom/private claims theo profile của tổ chức. Hai hệ thống dùng cùng tên claim vẫn có thể hiểu khác nhau. Vì vậy, issuer và các resource server phải thống nhất tên, kiểu dữ liệu, nguồn cấp và ngữ nghĩa của claim.

### 2.1. Dùng định danh ổn định, không dùng tên hiển thị

Nên dùng tenant identifier ổn định, opaque và không mang ý nghĩa nghiệp vụ nhạy cảm, ví dụ tn_8f3a.... Không nên dùng tên tổ chức, email domain, tên khách hàng hoặc display name làm định danh bảo mật.

Tên hiển thị có thể thay đổi hoặc trùng nhau. Một tenant có thể đổi tên, sáp nhập hoặc đổi domain nhưng vẫn giữ cùng ID nội bộ.

Tenant ID không phải bí mật. Với JWS thông thường, payload chỉ được Base64url-encode nên người có token có thể đọc claim. Không đưa thông tin cá nhân hoặc bí mật vào claim tenant.

### 2.2. Claim tenant cần có hợp đồng rõ ràng

Một profile nên quy định:

- Tên claim và kiểu dữ liệu.
- Tenant ID được cấp bởi hệ thống nào.
- Claim chỉ tenant đang hoạt động hay danh sách tenant mà principal có membership.
- Claim có hiệu lực cho toàn bộ token hay chỉ một audience/service.
- Vai trò và scope có áp dụng trong tenant đó hay toàn nền tảng.
- Cách xử lý membership bị thu hồi, tenant bị khóa hoặc người dùng bị vô hiệu hóa.
- Cách version hóa khi thay đổi ngữ nghĩa claim.

Nếu nhiều tổ chức hoặc vendor cần trao đổi JWT, cân nhắc claim name có namespace collision-resistant theo profile đã thỏa thuận. Không mặc định một custom claim name là chuẩn chung.

## 3. Mô hình token tenant-scoped

Một cách thiết kế dễ kiểm soát là phát hành access token gắn với **một tenant context đang hoạt động**. Khi người dùng chuyển tenant, client yêu cầu token mới sau khi server xác minh membership trong tenant đích.

Ví dụ payload JWS:

```json
{
  "iss": "https://identity.example",
  "sub": "user-42",
  "aud": "billing-api",
  "iat": 1794859200,
  "nbf": 1794859200,
  "exp": 1794860100,
  "jti": "at-7d91c2",
  "client_id": "web-console",
  "tenant_id": "tn-8f3a",
  "scope": "invoice:read invoice:approve",
  "tenant_roles": ["billing-operator"],
  "token_use": "access"
}
```

Đây là ví dụ profile riêng, không phải tập claim bắt buộc của JWT. Các điểm quan trọng:

- iss xác định issuer được tin cậy.
- sub xác định principal theo namespace của issuer.
- aud giới hạn resource server được nhận token.
- exp, nbf và iat hỗ trợ kiểm tra thời gian.
- jti định danh token; bản thân nó không tự chống replay.
- tenant_id xác định tenant context của token.
- scope và tenant_roles chỉ có ý nghĩa trong tenant context được quy định.
- client_id có thể giúp phân biệt ứng dụng đang gọi, nhưng không thay thế danh tính subject hay authorization.

Với JWS, các claim này không được mã hóa. Nếu cần che giấu payload, có thể dùng JWE theo profile phù hợp, nhưng mã hóa không thay thế kiểm tra tenant authorization.

### 3.1. Một tenant trong mỗi access token

Token gắn với một tenant giúp giảm mơ hồ:

- Mỗi request có một tenant context rõ ràng.
- Role và scope được đánh giá trong cùng tenant.
- Cache và truy vấn có thể nhận tenant context từ token đã xác minh.
- Khi membership bị thay đổi, server có thể phát hành token mới cho tenant phù hợp.
- Dịch vụ downstream có thể nhận context cụ thể thay vì một danh sách quyền rộng.

Cách này không bắt buộc cho mọi hệ thống, nhưng thường đơn giản hơn token chứa quyền trên hàng trăm tenant.

### 3.2. Vì sao token chứa danh sách tenant có thể nguy hiểm?

Một token có tenant_ids: ["A", "B", "C"] có thể thuận tiện, nhưng tạo ra các câu hỏi khó:

- Người dùng có được phép thực hiện cùng một hành động ở tất cả tenant không?
- Vai trò của người dùng ở A có giống vai trò ở B không?
- Membership có thể bị thu hồi trước khi token hết hạn không?
- Danh sách lớn có làm token phình to và lộ quan hệ tổ chức không?
- Dịch vụ có vô tình hiểu danh sách membership là quyền truy cập mọi tài nguyên không?

Nếu phải dùng token nhiều tenant, nên biểu diễn membership và quyền theo từng tenant, giới hạn audience/scope và vẫn kiểm tra membership hiện tại khi hành động nhạy cảm. Không suy ra quyền admin toàn cục từ việc một tenant xuất hiện trong danh sách.

## 4. Phát hành token: chỉ cấp tenant context sau khi xác minh membership

Client có thể yêu cầu chuyển sang tenant cụ thể, nhưng không được tự quyết định claim tenant có thẩm quyền.

Một quy trình phát hành token nên:

1. Xác thực principal và client.
2. Nhận tenant được yêu cầu từ luồng chọn tenant.
3. Tra cứu membership hiện tại của principal trong tenant đó.
4. Kiểm tra tenant đang hoạt động, tài khoản không bị khóa và membership chưa bị thu hồi.
5. Xác định role/scope trong đúng tenant.
6. Kiểm tra client có được phép yêu cầu audience và scope đó không.
7. Phát hành token có tenant context đã xác minh, audience cụ thể và thời hạn phù hợp.

Không nhận tenant_id từ client rồi chép thẳng vào JWT. Việc client chọn tenant chỉ là yêu cầu; server phải quyết định yêu cầu đó có hợp lệ hay không.

### 4.1. Không nhầm membership với quyền

Membership chỉ cho biết principal có quan hệ với tenant. Nó không tự cấp quyền cho mọi hành động.

Ví dụ một người dùng có thể:

- Là tenant-admin trong Tenant A.
- Chỉ có invoice-reader trong Tenant B.
- Không có quyền trong Tenant C.

Issuer cần phát hành quyền theo tenant tương ứng. Không dùng một role toàn cục như admin nếu role đó thực chất chỉ có hiệu lực trong một tenant.

### 4.2. Chuyển tenant phải là một quyết định authorization

Khi người dùng chọn tenant B:

- Server xác minh người dùng có membership hợp lệ ở B.
- Server phát hành token mới có tenant_id = B và role/scope của B.
- Client thay token đang dùng theo quy trình an toàn.
- API chỉ nhận token mới cho các request tiếp theo.

Không sửa payload JWT ở client để thay tenant. Thay đổi claim sẽ làm chữ ký không hợp lệ; nếu hệ thống chấp nhận token sau khi client tự sửa thì đó là lỗi xác minh nghiêm trọng.

## 5. Xác minh token và thiết lập tenant context

Resource server phải xác minh token trước khi sử dụng bất kỳ claim nào làm căn cứ authorization.

### 5.1. Các bước xác minh

- Kiểm tra định dạng token và loại token endpoint chấp nhận.
- Verify chữ ký JWS hoặc authenticated decryption JWE theo policy.
- Chỉ chấp nhận thuật toán và key type trong allowlist.
- Chọn khóa từ trust store/JWKS đã cấu hình cho issuer tin cậy.
- Kiểm tra iss, aud, exp, nbf và loại token.
- Kiểm tra claim tenant có tồn tại, đúng kiểu và thuộc namespace hợp lệ.
- Tạo tenant context bất biến từ claims đã xác minh.
- Chỉ chuyển context này vào các lớp authorization và data access.

Không dùng token decode-only để lấy tenant_id. Không tin header X-Tenant-ID, query parameter, hostname hoặc body như nguồn xác thực tenant.

### 5.2. Request có tenant selector

Một API đôi khi cần nhận tenant selector, ví dụ người dùng chọn tenant trong URL hoặc header. Selector có thể giúp định tuyến, nhưng phải được so sánh với context đã xác minh.

Ví dụ:

```text
verified = verifyAccessToken(token, trustedPolicy)

tokenTenant = verified.claims.tenant_id
requestedTenant = request.path.tenantId

if requestedTenant != tokenTenant:
    reject()

authorizeWithinTenant(
    subject = verified.claims.sub,
    tenant = tokenTenant,
    action = "invoice:read"
)
```

Nếu token hỗ trợ nhiều tenant, thay phép so sánh đơn giản bằng membership check theo từng tenant và từng action. Không bao giờ coi giá trị selector do client gửi là bằng chứng client có quyền trong tenant đó.

### 5.3. Tenant context phải được truyền tường minh

Sau khi xác minh, service nên tạo một context chứa tối thiểu:

- Principal hoặc service identity.
- Tenant ID đã xác minh.
- Issuer và audience.
- Scope/role liên quan.
- Correlation/request ID.
- Các thuộc tính delegation cần thiết nếu có.

Context phải được tạo ở ranh giới xác thực và truyền qua các lớp theo hợp đồng rõ ràng. Tránh đọc tenant từ biến toàn cục, thread-local không được làm sạch, request header tùy ý hoặc giá trị mặc định.

Với xử lý bất đồng bộ, phải truyền tenant context cùng job/message đã được xác thực và kiểm tra lại tại consumer.

## 6. Ngăn IDOR/BOLA và truy cập chéo tenant

Một lỗi phổ biến là API xác minh token đúng nhưng chỉ truy vấn tài nguyên theo ID.

Ví dụ không an toàn:

```text
invoice = database.findInvoice(request.invoiceId)
return invoice
```

Nếu invoiceId thuộc Tenant B và người dùng của Tenant A biết ID đó, API có thể trả dữ liệu B dù token A hoàn toàn hợp lệ.

Đây là dạng IDOR/BOLA (Insecure Direct Object Reference / Broken Object Level Authorization).

Cách xử lý là ràng buộc truy vấn với tenant context đã xác minh:

```text
invoice = database.findInvoice(
    id = request.invoiceId,
    tenant_id = verifiedTenantContext.tenantId
)

if invoice is missing:
    rejectAsNotFound()

authorize(
    principal = verifiedPrincipal,
    tenant = verifiedTenantContext.tenantId,
    action = "invoice:read",
    resource = invoice
)

return invoice
```

Điểm quan trọng:

- Không chỉ kiểm tra tenant ở controller hoặc gateway rồi giả định mọi truy vấn phía sau an toàn.
- Mỗi thao tác đọc, sửa, xóa, export và quan hệ dữ liệu đều phải giữ tenant boundary.
- Không để một ID hợp lệ trong tenant khác trở thành quyền truy cập.
- Khi tạo resource, tenant ID phải lấy từ context đã xác minh hoặc từ quan hệ parent đã kiểm tra.
- Với update/delete, điều kiện tenant phải nằm trong chính thao tác dữ liệu hoặc transaction bảo vệ.

### 6.1. Ràng buộc tenant trong quan hệ dữ liệu

Giả sử một invoice thuộc tenant A và một customer thuộc tenant B. Nếu database chỉ kiểm tra customer_id tồn tại, ứng dụng có thể vô tình liên kết dữ liệu giữa hai tenant.

Nên bảo đảm quan hệ có tenant consistency, ví dụ:

- Khóa duy nhất gồm (tenant_id, resource_id) khi phù hợp.
- Foreign key hoặc constraint bảo đảm parent và child thuộc cùng tenant.
- Join có điều kiện tenant ở cả hai phía.
- Update/delete có điều kiện tenant.
- Không cho phép client tự gán tenant ID cho object con nếu không qua authorization.

### 6.2. Tenant boundary trong database

Có thể dùng nhiều lớp bảo vệ:

- Query luôn có điều kiện tenant_id.
- Repository/data access layer yêu cầu tenant context tường minh.
- Row-level security (RLS) nếu database hỗ trợ và phù hợp kiến trúc.
- Database role hạn chế quyền truy cập.
- Constraint bảo vệ quan hệ dữ liệu.
- Audit các truy vấn hoặc thao tác nhạy cảm theo tenant.

RLS có thể là lớp phòng thủ bổ sung, nhưng phải thiết lập tenant context an toàn cho mỗi transaction/connection và tránh rò rỉ context qua connection pool. Không dùng RLS như lý do bỏ kiểm tra authorization ở ứng dụng.

## 7. Phân biệt tenant role, global role và service role

Một trong những lỗi nguy hiểm nhất là diễn giải role mà không có phạm vi.

| Loại quyền | Ví dụ | Phạm vi |
| --- | --- | --- |
| Tenant role | tenant-admin, invoice-approver | Chỉ trong tenant được xác định |
| Platform role | platform-support, platform-security-admin | Toàn nền tảng hoặc các tenant được ủy quyền rõ |
| Service/workload role | billing-worker, report-exporter | Hành động service được phép thực hiện |
| Delegated role | Quyền service thực hiện thay mặt subject | Chỉ trong delegation và tenant context được cấp |

Nếu token có roles: ["admin"], resource server không biết admin đó là tenant admin hay platform admin trừ khi profile định nghĩa rõ.

Nên biểu diễn phạm vi rõ ràng, ví dụ:

```json
{
  "tenant_id": "tn-8f3a",
  "tenant_roles": ["tenant-admin"],
  "scope": "invoice:read invoice:approve"
}
```

Nếu có platform admin, dùng claim hoặc policy riêng, có namespace và điều kiện sử dụng rõ ràng. Không để tenant-admin ở A được hiểu là quyền admin ở B.

### 7.1. Hỗ trợ vận hành xuyên tenant

Nhân viên support hoặc platform operator đôi khi cần truy cập nhiều tenant. Đây là quyền đặc biệt, không nên mô phỏng bằng cách phát token có tenant_id = * cho mọi request thông thường.

Một luồng an toàn nên:

- Yêu cầu role platform riêng và xác thực mạnh hơn khi cần.
- Ghi rõ tenant mục tiêu, lý do và ticket/case.
- Cấp quyền tạm thời, scope hẹp và thời hạn ngắn.
- Ghi audit đầy đủ subject, actor, tenant, resource và action.
- Có thể yêu cầu phê duyệt hoặc step-up authentication cho dữ liệu nhạy cảm.
- Phân biệt hành động hỗ trợ với hành động thay mặt tenant user.

## 8. Tenant isolation giữa các service

Trong kiến trúc microservices, một request có thể đi qua API gateway, identity service, billing service, reporting service và storage service. Mỗi service phải hiểu và bảo vệ tenant context.

### 8.1. Không tin header nội bộ chỉ vì request đến từ mạng nội bộ

Một gateway có thể chuyển X-Tenant-ID cho downstream service. Header này chỉ đáng tin nếu:

- Gateway đã xác minh token và xác định tenant context.
- Client bên ngoài không thể tự đặt header có cùng tên để vượt qua gateway.
- Kết nối gateway-service được xác thực và bảo vệ.
- Downstream service chỉ tin header từ gateway identity được phép.
- Tenant context được gắn với principal/delegation và không thể bị thay đổi tùy ý.

Trong môi trường có service-to-service token, nên truyền tenant context bằng claim hoặc context được ký/ủy quyền theo profile, rồi downstream xác minh audience, caller identity và tenant authorization. Không chuyển nguyên access token của người dùng tới mọi service nếu token không được cấp cho audience đó.

### 8.2. Token exchange và delegation

Một service có thể cần gọi service khác với quyền hẹp hơn. Khi đó, dùng token exchange hoặc cơ chế delegation phù hợp để cấp token mới:

- Giữ nguyên tenant context đã được xác minh.
- Giới hạn audience vào downstream service.
- Giảm scope theo công việc cần làm.
- Ghi rõ actor/caller và subject thay mặt nếu giao thức hỗ trợ.
- Không nâng quyền chỉ vì service trung gian có quyền rộng hơn.
- Downstream service vẫn kiểm tra tenant và resource ownership.

Token exchange không tự bảo đảm tenant isolation; policy cấp token mới và kiểm tra ở downstream vẫn quyết định quyền thực tế.

### 8.3. Background jobs và message queues

Tenant context thường bị mất hoặc sai khi công việc chạy bất đồng bộ.

Một message/job nên chứa:

- Tenant ID đã xác minh tại thời điểm tạo.
- Subject hoặc service actor.
- Resource IDs cần xử lý.
- Job purpose và correlation ID.
- Token/delegation reference hoặc bằng chứng ủy quyền nếu cần.
- Thời điểm tạo và hạn xử lý.

Consumer phải xác minh producer, tenant context và quyền trên resource trước khi xử lý. Không dùng một tenant mặc định khi message thiếu tenant. Không cho payload message không tin cậy tự quyết định tenant.

Nếu job có thể chạy lâu, cần xem xét membership hoặc tenant status có thể đã thay đổi; revalidate theo độ nhạy của hành động.

## 9. Cache, search index, object storage và log cũng phải cách ly tenant

Tenant isolation không dừng ở database chính.

| Thành phần | Lỗi thường gặp | Cách phòng tránh |
| --- | --- | --- |
| Cache | Key chỉ chứa resource ID, không có tenant | Đưa tenant vào cache key và kiểm tra ownership khi đọc |
| Search index | Query không filter tenant hoặc filter do client tự đặt | Filter bằng tenant context đã xác minh; kiểm tra quyền ở document |
| Object storage | Dùng object key đoán được hoặc URL chia sẻ không ràng buộc tenant | Prefix/namespace theo tenant, policy và signed URL thời hạn ngắn |
| File export | Worker tạo file từ resource ID mà không kiểm tra tenant | Bind job với tenant và xác minh trước khi export |
| Message queue | Consumer xử lý message thiếu hoặc giả tenant context | Xác thực producer, schema, tenant và resource ownership |
| CDN | Cache response riêng tư theo URL nhưng không theo identity/tenant | Không cache dữ liệu nhạy cảm dùng chung; cấu hình cache key và policy phù hợp |
| Logs/analytics | Tenant hoặc user nhạy cảm bị lộ trong log rộng quyền | Tối thiểu hóa dữ liệu, kiểm soát truy cập và phân vùng theo policy |
| Metrics | Label tenant không kiểm soát gây lộ dữ liệu hoặc cardinality cao | Dùng ID phù hợp, giới hạn nhãn và quyền truy cập |

### 9.1. Cache key phải bao gồm tenant context

Không an toàn:

```text
cacheKey = "invoice:" + invoiceId
```

An toàn hơn:

```text
cacheKey = "tenant:" + verifiedTenantId + ":invoice:" + invoiceId
```

Tenant trong cache key phải đến từ context đã xác minh. Không lấy trực tiếp từ query parameter hoặc header không tin cậy.

Ngay cả cache key đã có tenant, vẫn cần kiểm tra authorization khi lấy dữ liệu. Cache partitioning là lớp cách ly dữ liệu, không phải quyết định quyền cuối cùng.

## 10. Tenant membership thay đổi và token cũ

JWT thường được xác minh offline. Sau khi issuer phát hành token, resource server có thể tiếp tục chấp nhận token cho tới khi hết hạn nếu chữ ký và claims còn hợp lệ.

Điều này tạo ra vấn đề khi:

- Người dùng bị loại khỏi tenant.
- Tenant bị khóa hoặc ngừng hoạt động.
- Role bị hạ từ admin xuống reader.
- Tài khoản bị khóa hoặc nhân viên rời tổ chức.
- Service integration bị thu hồi.

Các lựa chọn:

1. **Access token ngắn hạn:** giảm thời gian quyền cũ còn hiệu lực.
2. **Introspection hoặc authorization lookup:** kiểm tra trạng thái token/membership hiện tại với authorization server hoặc policy service.
3. **Membership/policy version:** token mang version; resource server so với version hiện tại khi hành động cần bảo đảm mới nhất.
4. **Revocation/denylist:** thu hồi token hoặc session cụ thể khi cần.
5. **Event-driven invalidation:** phát sự kiện cập nhật cache/policy tại các service, kèm cơ chế xử lý khi event bị trễ hoặc thất lạc.

Không có giải pháp hoàn hảo cho mọi hệ thống. Quyết định phụ thuộc độ nhạy dữ liệu, yêu cầu sẵn sàng và mức chấp nhận quyền cũ còn hiệu lực trong một khoảng thời gian.

### 10.1. Membership version

Ví dụ token mang:

```json
{
  "tenant_id": "tn-8f3a",
  "membership_version": 17,
  "exp": 1794860100
}
```

Khi role hoặc membership thay đổi, server tăng version hiện tại. Resource server so sánh version trong token với version hiện tại trước hành động nhạy cảm. Nếu khác nhau, token bị từ chối hoặc yêu cầu cấp lại.

Đây là custom mechanism cần đồng bộ và định nghĩa rõ. Nếu resource server chỉ dùng version đã cache lâu, việc tăng version không có tác dụng tức thời. Cần xác định TTL, invalidation và hành vi khi policy service không truy cập được.

## 11. Những lỗi thiết kế thường dẫn đến cross-tenant data leakage

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tin tenant_id do client gửi | Client tự chọn tenant khác | Dùng claim đã xác minh và kiểm tra membership |
| Chỉ verify chữ ký, không kiểm tra tenant/resource | Token hợp lệ truy cập object tenant khác | Tenant-scoped authorization tại mỗi thao tác |
| Dùng role admin không có phạm vi | Tenant admin thành platform admin | Tách tenant role và platform role |
| Token có danh sách tenant rộng, không kiểm tra quyền từng tenant | Quyền từ tenant này lan sang tenant khác | Token tenant-scoped hoặc kiểm tra membership/role theo tenant |
| Chỉ lọc tenant ở API gateway | Downstream có thể truy vấn sai tenant | Mỗi service tự enforce tenant boundary |
| Cache key không có tenant | Dữ liệu A được trả cho B | Tenant-aware cache key và authorization |
| Background job không bind tenant | Job xử lý sai dữ liệu | Context bất biến, kiểm tra tại consumer |
| Tenant membership bị thu hồi nhưng token còn dài hạn | Quyền cũ tồn tại | TTL ngắn, introspection/version/revocation |
| Join dữ liệu không kiểm tra tenant | Liên kết record giữa hai tổ chức | Constraint và tenant-aware joins |
| Support account dùng quyền wildcard | Truy cập toàn bộ dữ liệu không kiểm soát | Just-in-time access, scope hẹp và audit |

## 12. Mẫu kiểm tra authorization theo tenant

Một quyết định truy cập nên xét đồng thời principal, tenant, action và resource:

```text
function authorizeTenantResource(token, action, resourceId):
    claims = verifyTokenAndValidateClaims(token)

    tenantId = claims.tenant_id
    if tenantId is missing:
        reject()

    membership = membershipStore.get(
        subject = claims.sub,
        tenant = tenantId
    )

    if membership is inactive:
        reject()

    resource = resourceStore.get(
        id = resourceId,
        tenant = tenantId
    )

    if resource is missing:
        rejectAsNotFound()

    if not policyAllows(
        subject = claims.sub,
        tenant = tenantId,
        roles = membership.roles,
        scopes = claims.scope,
        action = action,
        resource = resource
    ):
        reject()

    return resource
```

Mã giả này nhấn mạnh rằng claim tenant không thay thế membership và resource ownership. Với một số hệ thống, membership có thể được cache hoặc nhúng vào token trong thời gian ngắn; khi đó phải chấp nhận và kiểm soát độ trễ thu hồi.

Không nên truy vấn resource toàn cục trước rồi chỉ kiểm tra tenant ở bước hiển thị. Truy vấn và thao tác thay đổi dữ liệu phải có tenant condition để giảm cả lỗi authorization lẫn side-channel tiết lộ sự tồn tại của resource.

## 13. Kiểm thử tenant isolation

Kiểm thử phải tập trung vào việc tenant A không thể đọc, sửa, xóa, export hoặc suy luận dữ liệu của tenant B.

### 13.1. Kiểm thử dương tính

- Thành viên hợp lệ của tenant A truy cập tài nguyên thuộc A theo scope/role được cấp.
- Tenant admin A thực hiện thao tác quản trị trong A.
- Người dùng có role thấp hơn chỉ thực hiện thao tác được cho phép.
- Người dùng có membership ở A và B chuyển tenant qua luồng được xác minh và nhận context tương ứng.
- Service được ủy quyền xử lý job trong tenant đã bind.

### 13.2. Kiểm thử âm tính

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Token tenant A yêu cầu resource thuộc B | Từ chối |
| Client đổi tenant_id trong body/header sang B | Không làm thay đổi tenant context đã xác minh |
| Token thiếu tenant claim tại endpoint yêu cầu tenant | Từ chối |
| Tenant không hoạt động hoặc membership đã bị thu hồi | Từ chối theo policy |
| Role admin ở A dùng để quản trị B | Từ chối |
| Token của audience service A gửi tới service B | Từ chối |
| Cache entry A được yêu cầu từ context B | Không trả dữ liệu A |
| Job tenant A bị sửa thành tenant B | Từ chối hoặc xác minh lại theo binding |
| Downstream nhận tenant header từ caller không tin cậy | Không dùng header làm căn cứ authorization |
| Resource con trỏ tới parent ở tenant khác | Constraint/authorization từ chối |
| Platform support truy cập tenant không có grant | Từ chối và audit |
| Membership version cũ dùng cho hành động yêu cầu policy mới nhất | Từ chối hoặc yêu cầu cấp token mới |

### 13.3. Kiểm thử nhiều lớp

Không chỉ kiểm thử endpoint HTTP. Cần kiểm thử:

- API gateway và từng downstream service.
- Repository/data access và truy vấn join.
- Database RLS/constraints nếu có.
- Cache, search, object storage và export.
- Queue consumer và background worker.
- Token exchange/delegation.
- Membership revocation và cache invalidation.

Một test chỉ chứng minh gateway chặn request chưa đủ nếu downstream service có thể được gọi trực tiếp.

## 14. Checklist thiết kế tenant claims và service boundaries

- [ ] Claim tenant có tên, kiểu dữ liệu và ngữ nghĩa được định nghĩa rõ.
- [ ] Tenant ID là định danh ổn định; không dùng tên hiển thị hoặc dữ liệu cá nhân.
- [ ] Token được phát hành sau khi server xác minh membership và trạng thái tenant.
- [ ] Access token ưu tiên gắn với một tenant context rõ ràng.
- [ ] Không để client tự quyết định tenant claim hoặc role trong token.
- [ ] Verify chữ ký/authenticated decryption, issuer, audience, thời hạn và token type trước khi dùng claims.
- [ ] Không dùng decode-only hoặc header không tin cậy để thiết lập tenant context.
- [ ] Tenant role, platform role và service role có phạm vi riêng.
- [ ] Mỗi thao tác đọc/ghi/xóa/export kiểm tra tenant và resource ownership.
- [ ] Truy vấn, join, constraint và database policy duy trì tenant consistency.
- [ ] Downstream service xác thực caller và tenant context; không tin header nội bộ một cách mặc định.
- [ ] Token exchange/delegation không mở rộng tenant hoặc scope ngoài quyền ban đầu.
- [ ] Background job và message được bind với tenant context bất biến.
- [ ] Cache key, search, object storage, CDN, log và export được partition theo tenant.
- [ ] Có chính sách membership revocation, token TTL, version hoặc introspection phù hợp.
- [ ] Quyền platform support xuyên tenant là quyền đặc biệt, có thời hạn và audit.
- [ ] Có test âm tính cho cross-tenant read/write, cache leak, job context và direct downstream access.

**Kết luận:** Tenant claim cho biết token đang hoạt động trong ngữ cảnh tổ chức nào, nhưng không tự bảo đảm cách ly dữ liệu. Server phải xác minh membership trước khi phát hành token, resource server phải xác minh token và kiểm tra tenant/resource ownership ở từng thao tác, còn các service, database, cache, queue và object storage phải duy trì cùng ranh giới. Dùng access token tenant-scoped, phân biệt tenant role với platform role, xử lý membership revocation và kiểm thử cross-tenant âm tính giúp ngăn quyền của một tổ chức lan sang tổ chức khác.

### Tài liệu tiêu chuẩn

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)

# Tenant resolution từ issuer và audience

## Mục tiêu

Trong hệ thống **multi-tenant**, một API có thể phục vụ nhiều tổ chức (tenant) nhưng phải giữ ranh giới xác thực, phân quyền và dữ liệu giữa các tổ chức. Sau bài này, bạn có thể:

- Giải thích vai trò của hai claim JWT: **issuer** (`iss`) và **audience** (`aud`), và vì sao từng claim riêng lẻ không luôn xác định được tenant.
- Thiết kế chính sách ánh xạ issuer/audience sang tenant cho access token của OAuth 2.0/OIDC.
- Phân biệt **chọn cấu hình xác thực** bằng thông tin chưa tin cậy với **xác định tenant đã xác thực** sau khi kiểm tra token.
- Phát hiện các lỗi dẫn đến chấp nhận token sai tenant, sai API, sai loại token hoặc sai nhà phát hành.
- Áp dụng tenant context nhất quán từ bước xác thực đến truy vấn dữ liệu và kiểm thử.

Bài học thuộc module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`: ngoài JWT, các nguyên tắc về access token, opaque token, claims, scope, audience, thu hồi và chống đánh cắp/phát lại vẫn áp dụng khi triển khai nhiều tenant.

## 1. Bài toán: API cần biết token thuộc tenant nào

Giả sử dịch vụ `orders-api` phục vụ hai công ty **Acme** và **Beta**:

- `acme.example.com` và `beta.example.com` định tuyến yêu cầu đến cùng cụm API.
- Mỗi công ty có người dùng, quyền hạn, đơn hàng và cấu hình riêng.
- API nhận `Authorization: Bearer <access_token>` và phải xác định **tenant nào được phép sử dụng token đó**, trước khi truy cập dữ liệu.

Các câu hỏi phải được giải quyết độc lập:

1. **Ai phát hành token?** — Claim `iss`.
2. **Token được phát hành cho dịch vụ nhận nào?** — Claim `aud`.
3. **Token gắn với tenant nào?** — Có thể suy ra bằng cấu hình issuer/audience hoặc cần thêm tenant claim đã xác thực.
4. **Chủ thể có quyền thực hiện hành động trên tenant đó không?** — Kiểm tra scope, role, quan hệ thành viên và chính sách dữ liệu.

Một token có chữ ký hợp lệ chưa đủ để cho phép truy cập dữ liệu tenant. Token còn phải đúng **nhà phát hành**, **dịch vụ nhận**, **tenant** và **quyền thực hiện thao tác**.

## 2. Hiểu chính xác `iss` và `aud`

Ví dụ payload JWT minh họa (chỉ là phần claims, không phải token hoàn chỉnh):

~~~json
{
  "iss": "https://login.example.test/realms/acme",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893459600
}
~~~

| Claim | Ý nghĩa | Điều **không** được suy luận |
| --- | --- | --- |
| `iss` (issuer) | Định danh nhà phát hành có trách nhiệm ký/phát hành token; thường là một URL/URI chính xác | Không mặc định bằng tenant ID; cùng issuer có thể phục vụ nhiều tenant |
| `aud` (audience) | Một hoặc nhiều định danh của bên nhận token; API phải thấy audience mà nó chấp nhận | Không mặc định là người dùng, tenant hoặc client đang gọi |
| `sub` (subject) | Định danh chủ thể trong ngữ cảnh issuer | Không bảo đảm duy nhất giữa các issuer; không thay thế tenant |
| `scope` / `roles` | Quyền hoặc phạm vi đã được cấp theo ngữ nghĩa của hệ thống phát hành | Không thay thế kiểm tra `aud`, tenant hoặc quyền trên bản ghi |
| `tid` / `tenant_id` | Claim chuyên biệt mà một số nhà cung cấp dùng để biểu thị tenant | Không có ở mọi nhà cung cấp và **chỉ đáng tin sau khi xác thực token** |
| `azp` / `client_id` | Có thể mô tả ứng dụng được ủy quyền hoặc client trong một số profile | Không phải bản thay thế cho `aud` của resource server |

Lưu ý:

- Theo biểu diễn JWT, `aud` có thể là **chuỗi** hoặc **mảng chuỗi**; thư viện JWT nên chuẩn hóa thành tập hợp để đối chiếu.
- So khớp `iss` theo **giá trị chính xác đã đăng ký**. Không dùng `startsWith` kiểu `https://login.example.test/` hoặc tự ghép URL từ giá trị không tin cậy.
- Claim trong payload có thể bị bất kỳ ai đọc và sửa trước khi ký/xác minh. **Đọc được claim chưa có nghĩa claim đáng tin.**
- Chữ ký hợp lệ chứng minh token được ký bằng một khóa được chấp nhận, nhưng vẫn cần kiểm tra rằng **khóa đó thuộc đúng issuer được tin cậy**.

### ID token khác access token

Trong OIDC, **ID token** chủ yếu hướng đến ứng dụng client (audience thường là client ID) để xác nhận sự kiện đăng nhập. **Access token** dành cho resource server/API. Không dùng ID token làm bearer access token chỉ vì JWT có `sub`, `iss` và chữ ký hợp lệ. Resource server phải kiểm tra loại token/profile được chấp nhận và audience của chính API. Với profile JWT access token có claim hay header nhận diện loại token, áp dụng ràng buộc đó theo hợp đồng với nhà phát hành.

## 3. Bốn mô hình ánh xạ issuer/audience → tenant

Không tồn tại một công thức duy nhất áp dụng cho mọi hệ thống OAuth 2.0/OIDC. Thiết kế tenant resolution phụ thuộc vào cách identity provider (IdP) phát hành token.

### Mô hình A — Issuer riêng cho từng tenant, audience API dùng chung

| Tenant | `iss` | `aud` |
| --- | --- | --- |
| Acme | `https://login.example.test/realms/acme` | `orders-api` |
| Beta | `https://login.example.test/realms/beta` | `orders-api` |

Nếu issuer được ràng buộc duy nhất với tenant, chính sách có thể ánh xạ:

~~~text
(iss = realms/acme, aud chứa orders-api) → tenant = acme
(iss = realms/beta, aud chứa orders-api) → tenant = beta
~~~

**Điều kiện:** Cả hai issuer phải nằm trong allowlist và được kiểm tra chữ ký/issuer/audience độc lập. Không lấy phần cuối đường dẫn URL `/realms/acme` làm tenant ID bằng cách cắt chuỗi tùy ý.

### Mô hình B — Issuer chung, audience riêng theo tenant

| Tenant | `iss` | `aud` |
| --- | --- | --- |
| Acme | `https://login.example.test` | `orders-api-acme` |
| Beta | `https://login.example.test` | `orders-api-beta` |

Audience được cấu hình để đại diện duy nhất cho tài nguyên của tenant, nên cặp `(iss, aud)` có thể chỉ ra tenant. Tuy vậy, audience thường đại diện cho **API**, nên phải chủ động thiết kế quy ước này; không tự coi mọi giá trị `aud` là tenant ID.

### Mô hình C — Issuer và audience đều phân biệt theo tenant

Ví dụ Acme có issuer `realms/acme` và audience `orders-api-acme`; Beta có issuer `realms/beta` và audience `orders-api-beta`.

Khi đó ánh xạ dùng **cặp đầy đủ** `(iss, aud)`. Token có issuer Acme nhưng audience Beta phải bị từ chối, dù cả hai giá trị riêng lẻ đều tồn tại trong allowlist.

### Mô hình D — Issuer và audience đều dùng chung

~~~text
Acme: iss = https://login.example.test; aud = orders-api
Beta: iss = https://login.example.test; aud = orders-api
~~~

Cặp `(iss, aud)` **không đủ thông tin** để phân biệt Acme và Beta. Hệ thống cần thêm thông tin đã xác thực, chẳng hạn:

- Claim `tid` / `tenant_id` do issuer đáng tin phát hành theo một hợp đồng đã định nghĩa;
- Quan hệ thành viên `(issuer, subject) → tenant` lưu ở phía server;
- Cơ chế chọn organization của nhà cung cấp, được kiểm tra lại với token và quyền thành viên.

Nếu một người dùng là thành viên của nhiều tenant, token có thể không chỉ ra tenant đang hoạt động. Khi ấy, hostname/path hoặc lựa chọn tenant trong request chỉ nêu **tenant được yêu cầu**; server phải kiểm tra chủ thể đã xác thực có quyền làm việc trong tenant đó. Không được chọn một tenant bất kỳ khi có nhiều kết quả khớp.

## 4. Ranh giới tin cậy: dùng claim chưa xác thực để định tuyến, không để cấp quyền

Một resource server multi-tenant thường cần đọc sơ bộ `iss` để biết nên dùng bộ khóa và chính sách xác thực nào. Đây là một **gợi ý định tuyến chưa tin cậy**, bởi client có thể tự sửa payload JWT.

~~~mermaid
flowchart TD
    A["Nhận Bearer access token"] --> B["Đọc gợi ý iss chưa xác thực"]
    B --> C{"Issuer có trong allowlist?"}
    C -- "Không" --> X["401: Từ chối token"]
    C -- "Có" --> D["Chọn cấu hình xác thực cố định của issuer"]
    D --> E["Kiểm tra chữ ký, thuật toán, iss, thời gian, loại token"]
    E --> F{"Token hợp lệ?"}
    F -- "Không" --> X
    F -- "Có" --> G["Đối chiếu aud với API và chính sách tenant"]
    G --> H{"Có đúng một tenant hợp lệ?"}
    H -- "Không" --> X
    H -- "Có" --> I["Đối chiếu tenant được yêu cầu và quyền truy cập"]
    I --> J{"Đủ quyền?"}
    J -- "Không" --> Y["403/404: Từ chối thao tác"]
    J -- "Có" --> K["Thiết lập tenant context đã xác thực"]
    K --> L["Truy vấn dữ liệu có ràng buộc tenant"]
~~~

Các kiểm tra cốt lõi:

1. **Issuer allowlist:** Chỉ chấp nhận issuer được quản trị viên đăng ký; dùng so khớp chính xác và cấu hình tin cậy phía server.
2. **Khóa và thuật toán:** Xác minh chữ ký bằng khóa từ JWKS/metadata đã cấu hình của issuer đó; giới hạn thuật toán được chấp nhận. Không tin URL `jku`/`x5u` do token tự chỉ định hoặc chấp nhận `alg=none`.
3. **Các claims bắt buộc:** Đối chiếu `iss` chính xác; `exp` và `nbf` (nếu có) với thời gian server, độ lệch đồng hồ nhỏ theo chính sách; kiểm tra `iat` và các ràng buộc vòng đời khi profile yêu cầu.
4. **Audience và loại token:** Audience phải chứa định danh **API hiện tại** được cho phép trong chính sách; token phải đúng loại mà API nhận.
5. **Tenant mapping:** Tìm tenant từ dữ liệu **đã xác thực** và registry tin cậy. Kết quả phải rõ ràng; không khớp hoặc khớp nhiều tenant mà không có cơ chế chọn/ủy quyền hợp lệ đều bị từ chối.
6. **Authorization:** Kiểm tra scope, role và quyền trên tài nguyên trong đúng tenant. Tenant resolution không tự cấp quyền đọc/ghi.

**Thứ tự quan trọng:** Có thể dùng `iss` chưa xác thực để *tra cứu một cấu hình có sẵn*, nhưng chỉ sau khi xác thực đầy đủ mới được dùng claims để *kết luận tenant và danh tính*. Đặc biệt không tải JWKS tùy ý từ URL lấy trực tiếp trong token hoặc xây endpoint discovery từ issuer chưa được cho phép, vì dễ gây SSRF và trust confusion.

## 5. Thiết kế registry và thuật toán xác định tenant

Một registry do server quản lý có thể chứa:

| Trường cấu hình | Ví dụ | Vai trò |
| --- | --- | --- |
| `tenantId` | `acme` | Khóa tenant nội bộ dùng cho phân vùng dữ liệu |
| `issuer` | `https://login.example.test/realms/acme` | Issuer chính xác đã được tin cậy |
| `acceptedAudiences` | `["orders-api"]` | Audience được phép cho API/tenant |
| `providerTenantId` | `acme-idp-id` hoặc rỗng | Điều kiện bổ sung nếu issuer/audience dùng chung |
| `jwks/discovery` | Endpoint cấu hình từ issuer tin cậy | Nguồn khóa xác minh có cache/rotation |
| `acceptedAlgorithms` | Ví dụ `RS256` | Danh sách thuật toán cụ thể theo nhà phát hành |

Tùy cách tích hợp, registry có thể lưu cấu hình issuer riêng, cấu hình resource audience riêng và ánh xạ tenant. Điểm quyết định là **mọi lựa chọn phải xuất phát từ cấu hình tin cậy**, không tạo tenant hoặc issuer mới chỉ vì token yêu cầu.

### Thuật toán mức khái niệm

~~~text
authenticate(request, bearerToken):
    hintedIssuer = parseUnverifiedIssuer(bearerToken)
    issuerPolicy = trustedIssuerRegistry.findExact(hintedIssuer)
    if issuerPolicy is absent:
        reject 401

    verified = verifyAccessToken(
        bearerToken,
        trustedKeys = issuerPolicy.keys,
        allowedAlgorithms = issuerPolicy.algorithms,
        expectedIssuer = issuerPolicy.issuer,
        validTime = true,
        requiredTokenProfile = issuerPolicy.accessTokenProfile
    )
    if verification fails:
        reject 401

    candidates = tenantRegistry.findWhere(
        tenant.issuer == verified.iss
        and intersects(tenant.acceptedAudiences, verified.aud)
        and tenant.additionalClaimsMatch(verified)
    )
    if candidates.size != 1:
        reject 401  // không được tự chọn tenant đầu tiên

    tenant = candidates.only()
    if !resourceServer.acceptsAudience(verified.aud, tenant):
        reject 401

    requestedTenant = trustedRouteResolver.lookup(request.host, request.path)
    if requestedTenant exists and requestedTenant != tenant.id:
        deny 403 or 404

    if !authorization.allows(verified.subject, tenant.id,
                              verified.scopes, request.operation):
        deny 403

    return AuthenticatedTenantContext(tenant.id, verified.subject)
~~~

Ở mô hình D, `additionalClaimsMatch` chỉ được xét **sau** khi `verified` đã qua bước xác thực. Nếu người dùng hợp lệ với nhiều tenant và phải chọn tenant tại request, thuật toán cần mở rộng để kiểm tra membership thay vì bắt buộc token gắn một tenant; sự lựa chọn của client không được thay thế phép kiểm tra quyền.

### Ví dụ Java: kiểm tra ánh xạ sau khi JWT đã được xác minh

Đoạn dưới minh họa lớp resolver ở **tầng sau JwtDecoder/AuthenticationManager**. Giả định decoder đã xác minh chữ ký, issuer, thời hạn, đúng loại access token và audience theo cấu hình. Các điều kiện bổ sung ở đây bảo vệ tenant routing; đoạn mã không tự thực hiện giải mã/xác minh JWT.

~~~java
record TenantPolicy(
    String tenantId,
    String issuer,
    Set<String> audiences,
    String providerTenantId  // null nếu issuer/audience đã đủ phân biệt
) {}

String resolveTenant(
    Jwt verifiedJwt,
    String requestedTenant,
    Collection<TenantPolicy> policies
) {
    String verifiedIssuer = verifiedJwt.getIssuer().toString();
    List<String> verifiedAudiences = verifiedJwt.getAudience();
    String providerTenantId = verifiedJwt.getClaimAsString("tid");

    List<TenantPolicy> matches = policies.stream()
        .filter(p -> p.issuer().equals(verifiedIssuer))
        .filter(p -> p.audiences().stream().anyMatch(verifiedAudiences::contains))
        .filter(p -> p.providerTenantId() == null
            || p.providerTenantId().equals(providerTenantId))
        .toList();

    if (matches.size() != 1) {
        throw new BadCredentialsException("Ambiguous or unknown tenant");
    }

    TenantPolicy tenant = matches.get(0);
    if (requestedTenant != null && !tenant.tenantId().equals(requestedTenant)) {
        throw new AccessDeniedException("Requested tenant mismatch");
    }

    return tenant.tenantId();
}
~~~

Trong Spring Security, `Jwt` là đối tượng claims sau khi `JwtDecoder` xác thực; cần cấu hình `OAuth2TokenValidator<Jwt>` để kiểm tra issuer và audience tương ứng. Ở hệ thống thật, `providerTenantId` và tên claim phải khớp đúng tài liệu IdP, còn quyền thành viên/role/scopes cần được đánh giá thêm trước khi cho truy cập dữ liệu.

**Lưu ý về trường hợp nhiều audience:** Nếu token liệt kê nhiều audience, hãy kiểm tra audience hợp lệ của API. Không suy ra tenant từ phần tử đầu tiên của mảng `aud` hoặc từ thứ tự trong danh sách. Nếu nhiều chính sách tenant cùng khớp, cần quy tắc bổ sung đã được xác thực hoặc từ chối vì mơ hồ.

## 6. Đối chiếu tenant trong request và cô lập dữ liệu

Ngay cả khi token đã được gắn tenant `acme`, người gọi vẫn có thể gửi:

~~~http
GET /tenants/beta/orders/123 HTTP/1.1
Host: api.example.test
Authorization: Bearer <token-for-acme>
~~~

Nếu hệ thống chỉ kiểm tra token hợp lệ và scope `orders:read`, rồi lấy `beta` trực tiếp từ path để truy vấn, nó có thể cho phép **cross-tenant data access**.

Cần phân biệt:

- **Authenticated tenant:** tenant đã được xác định từ token hợp lệ, registry và kiểm tra quyền.
- **Requested tenant:** tenant mà URL, hostname hoặc header của request yêu cầu.
- **Data tenant:** tenant ID bắt buộc dùng trong điều kiện tìm kiếm, cache key, message, audit và truy vấn database.

Thông thường, `requestedTenant` phải khớp `authenticatedTenant` hoặc được chấp nhận thông qua một chính sách chuyển tenant được kiểm soát rõ ràng. Mọi truy vấn dữ liệu cần gắn tenant ID đã được cấp quyền, ví dụ:

~~~sql
SELECT id, total_amount
FROM orders
WHERE tenant_id = :authenticated_tenant_id
  AND id = :order_id;
~~~

Không nên chỉ lọc `id = :order_id` rồi tin rằng mỗi ID luôn độc nhất toàn hệ thống. Với mô hình quản lý nhiều tổ chức, nếu quyền cho phép người dùng đổi tenant, hãy xác lập **tenant context cho mỗi request** sau phép kiểm tra membership và dùng nó thống nhất đến persistence layer. Không để tenant context của request trước rò rỉ qua thread pool, asynchronous job hoặc cache.

## 7. Những lỗi bảo mật thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chấp nhận mọi issuer miễn chữ ký xác minh được với một khóa nào đó | Token từ IdP không được phép có thể được chấp nhận | Registry issuer allowlist; khóa và chính sách gắn với đúng issuer |
| Dùng `iss` chưa xác minh để tải JWKS động | SSRF, tin nhầm khóa/issuer, tiêu tốn tài nguyên | Tra issuer chính xác trong allowlist trước khi lấy JWKS đã cấu hình |
| Chỉ kiểm tra `iss`, bỏ qua `aud` | Token dành cho API khác bị sử dụng tại orders-api | Audience validator dành riêng cho resource server |
| Chỉ kiểm tra `aud`, bỏ qua `iss` | Chấp nhận token từ issuer ngoài chính sách | Xác minh chữ ký và issuer theo cùng trust configuration |
| Ghép issuer Acme với audience Beta nhưng kiểm tra từng danh sách độc lập | Token trộn tenant có thể vượt qua xác thực | Kiểm tra **cặp/quan hệ** `(issuer, audience, tenant)` hợp lệ |
| Tin `tid` hoặc `X-Tenant-ID` trước khi xác thực | Giả mạo tenant hoặc truy cập chéo | Dùng claim đã xác minh; kiểm tra header/path như thông tin yêu cầu |
| Dùng ID token làm access token | Token dành cho client bị sử dụng tại API | Ràng buộc token type/profile và audience API |
| Gán tenant đầu tiên khi nhiều policy khớp | Quyền và dữ liệu có thể rơi vào tenant sai | Từ chối ambiguous mapping hoặc yêu cầu lựa chọn + kiểm tra membership |
| Chỉ dựa vào tenant context ở gateway | Microservice sau gateway có thể bỏ qua hoặc nhận header giả | Mỗi trust boundary xác minh context hoặc dùng cơ chế truyền danh tính đáng tin |
| Cache khóa theo `sub` đơn lẻ | Đụng định danh giữa issuer/tenant khác nhau | Khóa cache ít nhất theo issuer, tenant và subject khi phù hợp |

### Confused deputy và token substitution

Một API có thể trở thành **confused deputy** nếu dùng quyền truy cập dữ liệu của chính nó để phục vụ một token hợp lệ nhưng được phát hành cho API/tenant khác. Kiểm tra chữ ký không ngăn được tình huống này; cần ràng buộc `aud`, `iss`, tenant và scope/role theo cùng policy. Không dùng một token từ tenant A để gọi tài nguyên tenant B khi chưa có quy trình ủy quyền hoặc token exchange rõ ràng.

### Đánh cắp và phát lại token

Tenant resolution ngăn sử dụng token sai tenant, nhưng **không tự ngăn được token bị đánh cắp**. Với access token dạng bearer, ai giữ token có thể thử phát lại trong thời hạn hiệu lực. Cần kết hợp thời hạn ngắn, TLS, bảo vệ lưu trữ, kiểm soát scope, cơ chế thu hồi phù hợp và khi cần **sender-constrained tokens** (ví dụ DPoP hoặc mTLS). Với refresh token, dùng rotation, ràng buộc client và phát hiện reuse theo chính sách của authorization server. Không ghi access/refresh token nguyên văn vào log.

## 8. JWT và opaque token: cùng ràng buộc tin cậy, cách kiểm tra khác nhau

**JWT access token** cho phép resource server xác minh chữ ký và claims cục bộ bằng khóa công khai từ issuer đáng tin. Cần cập nhật JWKS có kiểm soát khi xoay khóa; không biến một lỗi tải khóa thành cơ chế bỏ qua xác minh. Với `kid` lạ, chỉ tìm trong tập khóa được cấp bởi issuer đúng và từ chối nếu không có khóa hợp lệ.

**Opaque access token** không mang claims JWT để API tự đọc. Resource server phải gửi token đến **introspection endpoint đã cấu hình và được tin cậy**, kiểm tra kết quả `active` và những trường issuer, audience, scope, tenant theo hợp đồng thực tế. Không gửi opaque token đến endpoint do client chỉ định và không suy tenant bằng cách đoán cấu trúc chuỗi token. Nếu introspection không trả đủ thông tin để phân biệt tenant, phải bổ sung cơ chế ánh xạ đã xác thực hoặc từ chối.

Cả hai hình thức đều cần xác định resource server nào được phép nhận token và tenant nào token được phép hoạt động; khác biệt chủ yếu nằm ở nơi kiểm tra hiệu lực và claims.

## 9. Kịch bản kiểm thử quan trọng

Giả sử chính sách:

~~~text
tenant=acme, iss=issuer-A, aud=orders-api
tenant=beta, iss=issuer-B, aud=orders-api
~~~

| Trường hợp | Kết quả mong đợi | Lý do |
| --- | --- | --- |
| Issuer A, `aud=orders-api`, chữ ký và thời hạn hợp lệ, gọi Acme, đủ scope | Cho phép nếu quyền trên tài nguyên đạt | Đúng issuer, audience, tenant và authorization |
| Issuer A, audience đúng, gọi đường dẫn Beta | Từ chối 403/404 | Token Acme không cấp quyền Beta |
| Issuer A, `aud=billing-api` | Từ chối 401 | Token dành cho API khác |
| Issuer không trong allowlist | Từ chối 401 | Nhà phát hành không được tin cậy |
| Issuer A nhưng chữ ký bằng khóa của B | Từ chối 401 | Khóa không thuộc đúng issuer |
| Issuer A, audience Beta trong mô hình audience riêng | Từ chối 401 | Cặp issuer/audience không nằm trong chính sách |
| Token hết hạn, chưa có hiệu lực hoặc `alg` không cho phép | Từ chối 401 | Kiểm tra token thất bại |
| Token hợp lệ nhưng thiếu `orders:write` khi sửa đơn hàng | Từ chối 403 | Xác thực đạt, quyền thao tác thiếu |
| Issuer/audience chung, không có claim/quan hệ phân biệt tenant | Từ chối vì không xác định rõ tenant | Không đoán tenant |
| `aud` là mảng nhiều giá trị, chứa audience API và không gây mơ hồ tenant | Xét tiếp các ràng buộc còn lại | Đối chiếu theo tập hợp và chính sách |
| ID token có chữ ký hợp lệ, audience của web client | Từ chối tại resource server | Sai loại token và audience API |

Về mã HTTP, `401` thường áp dụng cho bearer token thiếu/không hợp lệ; `403` dùng khi đã xác thực nhưng không đủ quyền. Với tài nguyên tenant cần che giấu sự tồn tại, ứng dụng có thể dùng `404` theo thiết kế bảo mật. Cách phản hồi cụ thể phải nhất quán với API và tránh tiết lộ thông tin tenant khác.

## 10. Checklist áp dụng vào production

1. **Đăng ký tenant có kiểm soát:** Lưu tenant ID, issuer chính xác, audience được chấp nhận và điều kiện claim bổ sung trong registry tin cậy.
2. **Cố định trust configuration:** Chỉ dùng discovery/JWKS từ issuer cho phép, giới hạn thuật toán, kiểm soát cache khóa và rotation.
3. **Xác minh token đầy đủ:** Kiểm tra chữ ký, `iss`, `aud`, thời gian, profile token và các ràng buộc bổ sung; không thay thế phép kiểm tra này bằng cách chỉ decode JWT.
4. **Giải quyết tenant rõ ràng:** Mapping phải xác định duy nhất hoặc dùng cơ chế chọn tenant có kiểm tra quyền. Từ chối trường hợp không khớp/mơ hồ.
5. **Kiểm tra authorization theo tenant:** Scope/role là điều kiện cần, còn phải kiểm tra chủ thể có quyền trên tenant và tài nguyên đang thao tác.
6. **Truyền tenant context an toàn:** Dùng context đã xác thực cho database, cache, job và gọi service khác; không dựa vào header do client tự gán.
7. **Quan sát và kiểm thử:** Ghi log issuer ID/tenant ID đã chuẩn hóa, lý do từ chối và correlation ID; che token, secret và dữ liệu nhạy cảm. Kiểm thử cả token hợp lệ lẫn các hoán đổi issuer, audience, tenant, key và token type.

## Ghi nhớ

- `iss` trả lời **ai phát hành**; `aud` trả lời **token dành cho ai nhận**. Hai claim này **không mặc nhiên là tenant ID**.
- Chỉ ánh xạ `(iss, aud) → tenant` khi cấu hình đủ xác định; issuer/audience dùng chung có thể cần claim hoặc quan hệ thành viên đã được xác thực.
- **Chọn bộ xác thực** từ gợi ý chưa tin cậy là bước kỹ thuật; **cấp tenant context** chỉ diễn ra sau xác minh và đối chiếu chính sách.
- Ranh giới multi-tenant chỉ được bảo đảm khi tenant resolution, authorization và truy vấn dữ liệu cùng dùng một tenant context được xác thực.

### Tài liệu tiêu chuẩn nên đối chiếu

- **RFC 7519 (JSON Web Token):** ngữ nghĩa các claim chuẩn như `iss`, `aud`, `exp`, `nbf`.
- **RFC 8725 (JWT Best Current Practices):** thực hành an toàn cho thuật toán, issuer/audience và các kiểu nhầm lẫn JWT.
- **RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens):** profile khi access token là JWT.
- **OpenID Connect Core:** ID token, audience và phân biệt vai trò của ứng dụng client với resource server.
- **RFC 7662 (OAuth 2.0 Token Introspection):** cách resource server kiểm tra hiệu lực và metadata của opaque token.

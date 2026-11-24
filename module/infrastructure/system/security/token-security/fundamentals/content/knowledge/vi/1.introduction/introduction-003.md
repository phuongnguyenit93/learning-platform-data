# Authentication và authorization liên quan ra sao?

Một người đăng nhập thành công vào hệ thống chưa chắc được xem mọi dữ liệu hoặc thực hiện mọi thao tác. Đây là lý do **authentication (xác thực)** và **authorization (phân quyền/kiểm soát truy cập)** luôn cần được phân biệt, đặc biệt trong hệ thống dùng access token, JWT, OAuth 2.0 và OpenID Connect (OIDC).

Hai câu hỏi cốt lõi là:

- **Authentication — Ai đang tương tác với hệ thống?** Hệ thống kiểm tra bằng chứng về danh tính của người dùng, ứng dụng hoặc dịch vụ.
- **Authorization — Chủ thể đó được phép làm gì, trên tài nguyên nào, trong hoàn cảnh nào?** Hệ thống đánh giá yêu cầu theo quyền được cấp và chính sách truy cập thực tế.

Ví dụ: Alice đăng nhập bằng tài khoản hợp lệ và nhận access token. API xác nhận token hợp lệ, nhưng Alice vẫn không được đọc hóa đơn của Bob. Xác thực đã thành công; quyết định phân quyền cho hóa đơn đó phải là **từ chối**.

## 1. Phân biệt hai khái niệm

| Khía cạnh | Authentication (AuthN) | Authorization (AuthZ) |
|---|---|---|
| Câu hỏi | Ai là chủ thể? Bằng chứng danh tính có hợp lệ không? | Chủ thể có quyền thực hiện hành động này trên tài nguyên này không? |
| Đầu vào thường gặp | Mật khẩu, passkey, MFA, chứng chỉ client, phiên đăng nhập; trong một số luồng là thông tin đã được bên phát hành token xác nhận | Chủ thể đã xác định, hành động, tài nguyên, scope, vai trò, quyền sở hữu, tenant và điều kiện chính sách |
| Kết quả | Một danh tính/ngữ cảnh chủ thể được xác nhận ở mức độ tin cậy nhất định, hoặc xác thực thất bại | Cho phép hoặc từ chối một yêu cầu cụ thể |
| Phạm vi | Đăng nhập vào ứng dụng, xác thực client với máy chủ cấp token, xác minh nguồn gốc token theo thiết kế hệ thống | Kiểm quyền gọi API, truy cập từng bản ghi, thao tác quản trị, quyền theo ngữ cảnh |
| Lỗi HTTP thường gặp ở API | **401 Unauthorized** khi không có thông tin xác thực hợp lệ | **403 Forbidden** khi đã có ngữ cảnh hợp lệ nhưng quyền không đủ |

**AuthN và AuthZ liên quan chặt chẽ nhưng không đồng nghĩa.** Trong nhiều API riêng tư, AuthN (hoặc việc xác minh access token đáng tin cậy) tạo ra ngữ cảnh chủ thể để AuthZ ra quyết định. Tuy vậy, tài nguyên công khai vẫn có thể được phép truy cập theo chính sách mà không cần đăng nhập; ngược lại, đã đăng nhập cũng không tự động có quyền.

Một quyết định AuthZ thường có đủ bốn thành phần:

1. **Principal (chủ thể):** Alice, ứng dụng thanh toán, hoặc một dịch vụ nội bộ.
2. **Action (hành động):** đọc, tạo, sửa, xóa, phê duyệt.
3. **Resource (tài nguyên):** hóa đơn số 42, tài khoản khách hàng, API quản trị.
4. **Context (ngữ cảnh):** tenant, thời điểm, quan hệ sở hữu, chính sách tổ chức, mức độ xác thực hoặc rủi ro.

Hỏi “Alice có quyền đọc hóa đơn không?” là chưa đủ. Câu hỏi chính xác là: “Alice có quyền đọc **hóa đơn 42 thuộc tenant A** tại thời điểm yêu cầu hay không?”.

## 2. Token đứng ở đâu giữa AuthN và AuthZ?

Một **security token** là thông tin do một bên phát hành đáng tin cậy cấp để chủ thể khác sử dụng trong một phạm vi nhất định. Token có thể mang hoặc tham chiếu tới các **claims** (thuộc tính được bên phát hành khẳng định), chẳng hạn danh tính chủ thể, đối tượng nhận token, thời hạn và scope.

Trong kiến trúc OAuth 2.0 thông dụng:

| Thành phần | Trách nhiệm chính |
|---|---|
| **Người dùng / resource owner** | Sở hữu dữ liệu hoặc quyền truy cập được bảo vệ; có thể tham gia bước xác thực và cấp phép |
| **Client** (web, mobile, backend) | Xin và sử dụng access token theo luồng được phép |
| **Authorization Server (AS)** | Xác thực người dùng/client theo cơ chế phù hợp, áp dụng chính sách cấp quyền, phát hành token |
| **Resource Server (RS)** | API tiếp nhận access token, kiểm tra token, rồi quyết định có cho phép truy cập tài nguyên không |
| **Identity Provider (IdP)** | Cung cấp dịch vụ danh tính/xác thực; trong thực tế có thể cùng hệ thống với AS |

**Ba việc cần nhìn tách biệt:**

1. **Xác thực tại AS/IdP:** Ví dụ Alice dùng passkey và MFA để đăng nhập. Đây là sự kiện xác thực danh tính.
2. **Xác minh access token tại API:** API kiểm tra token có thật sự do bên tin cậy cấp, còn hiệu lực và dành cho API này không. Với bearer token, API biết phía gọi **đang sở hữu một token hợp lệ**, nhưng điều đó không chứng minh người cầm token lúc này chắc chắn là Alice.
3. **Phân quyền tại API:** Dựa trên claims đã kiểm chứng và dữ liệu/chính sách của ứng dụng để quyết định Alice có được đọc hóa đơn 42 hay không.

### Ví dụ luồng đăng nhập rồi gọi API

Sơ đồ sau minh họa khái niệm với **Authorization Code + PKCE**. Chi tiết chuyển hướng qua trình duyệt, quản lý phiên và đồng ý cấp quyền được lược bớt.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Ứng dụng client
    participant AS as Authorization Server / IdP
    participant API as Resource Server (API)
    participant DB as Dữ liệu và chính sách
    U->>C: Muốn xem hóa đơn 42
    C-->>U: Chuyển hướng đăng nhập/cấp quyền
    U->>AS: Hoàn tất xác thực
    AS-->>C: Authorization code qua redirect
    C->>AS: Đổi code và code_verifier
    AS-->>C: Access token (+ ID token nếu dùng OIDC)
    C->>API: GET /invoices/42 với access token
    API->>API: Xác minh chữ ký hoặc introspection, iss, aud, exp...
    API->>DB: Kiểm scope, tenant, quyền sở hữu và chính sách
    DB-->>API: Thông tin để quyết định
    API-->>C: Trả dữ liệu hoặc từ chối
~~~

Điểm mấu chốt: **AS cấp token không thay API quyết định mọi quyền truy cập cụ thể.** AS có thể cấp scope đọc hóa đơn; API vẫn phải kiểm quyền trên từng hóa đơn và bảo đảm không vượt ranh giới tenant.

## 3. Phân biệt token dùng cho xác thực và token dùng cho truy cập

Tên gọi “token” dễ khiến các loại token bị dùng nhầm mục đích:

| Loại token | Mục đích | Bên sử dụng đúng | Lưu ý bảo mật |
|---|---|---|---|
| **Access token** | Cung cấp khả năng gọi tài nguyên/API trong phạm vi được cấp | Resource Server | Phải kiểm hạn sử dụng, bên phát hành, audience, phạm vi quyền và chính sách tài nguyên; không mặc định cho phép mọi hành động |
| **ID token (OIDC)** | Truyền thông tin về sự kiện xác thực và người dùng cho client | Client OIDC là bên nhận dự kiến | **Không dùng ID token làm access token** để gọi API |
| **Refresh token** | Xin access token mới mà không phải lặp lại toàn bộ luồng cấp token | Authorization Server khi client gửi yêu cầu làm mới | Không gửi đến resource API; cần lưu trữ chặt, giới hạn sử dụng, xoay vòng/thu hồi phù hợp |

**OAuth 2.0 chủ yếu là khung ủy quyền truy cập.** Nó xác định cách client nhận và sử dụng access token để tiếp cận tài nguyên. **OIDC xây trên OAuth 2.0** để thêm lớp xác thực người dùng và ID token; dùng OAuth 2.0 thuần túy không đồng nghĩa đã có một cơ chế đăng nhập chuẩn hóa cho client.

Một access token **có thể** là JWT hoặc opaque token:

- **JWT** có cấu trúc header, payload, signature; API có thể kiểm chữ ký và claims cục bộ nếu triển khai theo mô hình đó. Chữ ký bảo đảm tính toàn vẹn và xác nhận bên ký theo khóa đáng tin cậy, **không mã hóa hay che giấu nội dung payload**.
- **Opaque token** là chuỗi tham chiếu không có ý nghĩa trực tiếp đối với client/API. API có thể gọi endpoint **introspection** hoặc dùng cơ chế tra cứu đáng tin cậy để biết token còn hoạt động và có các thuộc tính nào.

**JWT/opaque** là cách biểu diễn hoặc xác minh; **access/ID/refresh** là vai trò sử dụng. Hai trục phân loại này khác nhau. Không thể kết luận một chuỗi là access token hợp lệ chỉ vì nó có hình dạng JWT.

## 4. Claims giúp xác lập ngữ cảnh, không tự tạo mọi quyền

Giả sử API quản lý hóa đơn nhận access token có payload JWT như sau (số liệu minh họa, không phải token có thể dùng trực tiếp):

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": "invoices-api",
  "iat": 1800000000,
  "exp": 1800003600,
  "scope": "invoice:read",
  "tenant_id": "tenant-a"
}
~~~

Các claim thường gặp có ý nghĩa:

| Claim | Giải thích | Cần kiểm tra hoặc hiểu đúng |
|---|---|---|
| **iss** (issuer) | Ai phát hành token | API chỉ chấp nhận issuer đã cấu hình tin cậy |
| **sub** (subject) | Chủ thể của token | Có thể là người dùng **hoặc** client/service tùy luồng; không tự suy ra là người dùng đã đăng nhập |
| **aud** (audience) | Bên được phép nhận token | Phải bao gồm API đích; token dành cho API A không được tự động dùng ở API B |
| **iat / nbf / exp** | Thời điểm phát hành / chưa có hiệu lực trước / hết hạn | Kiểm tra các giới hạn thời gian áp dụng; chỉ cho phép sai lệch đồng hồ nhỏ, có chủ đích |
| **scope** | Phạm vi quyền AS đã cấp | Chỉ là **một điều kiện**; scope đọc hóa đơn không mặc nhiên cho đọc mọi hóa đơn |
| **tenant_id** | Ranh giới tenant, nếu hệ thống tự định nghĩa claim này | Phải được phát hành từ nguồn đáng tin và đối chiếu tenant của dữ liệu thực |

Claim tùy biến như **tenant_id**, **roles** hay **permissions** không có cùng ngữ nghĩa ở mọi hệ thống. API phải thống nhất hợp đồng claims với AS, kiểm định token trước khi dùng chúng, và chỉ tin những thuộc tính đã được AS bảo đảm.

Khi nhận token, API cần kiểm theo cách phù hợp với định dạng và kiến trúc đã chọn:

1. **Nguồn gốc và tính toàn vẹn:** Với JWT, xác minh chữ ký bằng khóa của issuer được tin cậy, chỉ cho phép thuật toán dự kiến và xử lý xoay vòng khóa; với opaque token, tra cứu/introspect qua kênh an toàn.
2. **Mục đích sử dụng:** Đây có đúng là access token dành cho API này không? Kiểm **aud**, **iss**, loại/token profile khi áp dụng; không tiếp nhận ID token làm vé truy cập.
3. **Trạng thái và thời gian:** Token còn hiệu lực không (**exp**, **nbf**, trạng thái introspection, hoặc cơ chế thu hồi có hiệu lực ở kiến trúc đang dùng)?
4. **Phạm vi và chính sách:** Scope có phù hợp với endpoint không? Chủ thể có quan hệ hợp lệ với dữ liệu không? Có vượt tenant, tổ chức hoặc quy định nghiệp vụ không?

Chỉ sau khi các bước tin cậy cần thiết thành công mới được dựa vào **sub**, **scope** hay **tenant_id** để cấp quyền. Đọc payload JWT mà chưa xác minh chữ ký không phải là xác thực.

## 5. Ví dụ đầy đủ: đọc một hóa đơn

Client yêu cầu:

~~~http
GET /invoices/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...redacted...
~~~

Giả sử access token hợp lệ, có **sub=user-123**, **scope=invoice:read**, **tenant_id=tenant-a**. Bản ghi hóa đơn 42 lưu trong cơ sở dữ liệu có:

~~~json
{
  "id": 42,
  "ownerId": "user-456",
  "tenantId": "tenant-a",
  "total": 2500000
}
~~~

Token hợp lệ về mặt kỹ thuật; scope đọc hóa đơn cũng tồn tại. Nhưng **ownerId** khác **sub**. Nếu chính sách chỉ cho đọc hóa đơn của chính mình, API phải từ chối.

Mã giả dưới đây thể hiện **thứ tự kiểm tra**, không phải thư viện triển khai hoàn chỉnh:

~~~text
function readInvoice(request, bearerToken, invoiceId):
    token = validateAccessToken(
        bearerToken,
        expectedIssuer = "https://login.example.test",
        expectedAudience = "invoices-api",
        enforceTimeValidity = true
    )
    if token.invalid:
        return HTTP_401

    if not token.scopes.contains("invoice:read"):
        return HTTP_403

    invoice = database.findInvoice(invoiceId)
    if invoice == null:
        return HTTP_404

    if invoice.tenantId != token.claims.tenant_id:
        return HTTP_403_or_404_by_policy

    if invoice.ownerId != token.subject:
        if not policy.permits(token.subject, "invoice:read:any", invoice):
            return HTTP_403_or_404_by_policy

    return HTTP_200_with_invoice
~~~

Ở hệ thống nhiều tenant, nên giới hạn truy vấn dữ liệu theo tenant ngay từ lớp truy cập dữ liệu (kết hợp với kiểm chính sách) để giảm nguy cơ truy xuất chéo dữ liệu. Việc trả **404** thay **403** khi tài nguyên thuộc người khác có thể được chọn để tránh lộ việc tài nguyên tồn tại, nhưng không được thay cho kiểm quyền thực tế.

So sánh một số tình huống:

| Tình huống | Kiểm token (AuthN/ngữ cảnh tin cậy) | Phân quyền (AuthZ) | Kết quả thường gặp |
|---|---|---|---|
| Alice có scope đọc, hóa đơn thuộc Alice và đúng tenant | Đạt | Đạt | **200 OK** |
| Alice có scope đọc, hóa đơn thuộc Bob | Đạt | Từ chối do quyền sở hữu | **403** hoặc **404** theo chính sách |
| Alice không có scope đọc | Đạt | Từ chối do scope | **403 Forbidden** |
| Token đã hết hạn | Không đạt | Không thực hiện bằng dữ liệu token không đáng tin | **401 Unauthorized** |
| Token phát hành cho API khác (**aud** sai) | Không đạt | Không thực hiện | **401 Unauthorized** |
| Token hợp lệ cho tenant A nhưng hóa đơn thuộc tenant B | Đạt | Từ chối do ranh giới tenant | **403** hoặc **404** theo chính sách |
| Service có access token từ **client_credentials** | Có thể đạt | Kiểm **quyền của service** theo chính sách riêng, không mặc định xem là Alice | Phụ thuộc quyền được cấp |

**401 và 403 khác nhau:** API thường trả **401** khi thiếu hoặc sai thông tin xác thực (kèm thử thách **WWW-Authenticate** với bearer token). Nếu token hợp lệ nhưng thiếu scope/quyền, API thường trả **403**. Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

## 6. Scope, role và quyền trên dữ liệu giải quyết các bài toán khác nhau

**Scope** mô tả giới hạn quyền của token đã được cấp cho client (ví dụ **invoice:read**, **invoice:write**). **Role** như **ADMIN**, **ACCOUNTANT** thường mô tả vai trò trong một tổ chức. **Quyền trên đối tượng** trả lời ai được thao tác lên hóa đơn cụ thể.

Ba yếu tố có thể kết hợp:

~~~text
Permit(request) =
    valid_access_token
    AND has_required_scope
    AND role_or_business_permission_allows_action
    AND resource_belongs_to_allowed_tenant
    AND ownership_or_relationship_policy_allows_access
~~~

Đây là mô hình minh họa, không phải quy tắc bắt buộc cho mọi endpoint. Một API công khai có thể không yêu cầu token; một dịch vụ nội bộ có thể dùng quyền riêng của client. Điều quan trọng là chính sách cần chỉ rõ **chủ thể, tài nguyên và hành động**, thay vì xem “có token” hoặc “có role” như điều kiện đủ.

Ví dụ, **ADMIN** của tenant A không mặc nhiên là ADMIN của tenant B. Tương tự, **invoice:read** có thể cho phép gọi endpoint đọc hóa đơn nhưng vẫn cần đối chiếu người sở hữu; còn **invoice:read:any** chỉ có hiệu lực nếu chính sách của API thực sự định nghĩa và cho phép quyền rộng đó.

## 7. Quan hệ này thay đổi thế nào theo vòng đời token?

| Giai đoạn | Liên quan đến authentication | Liên quan đến authorization và rủi ro |
|---|---|---|
| **Phát hành** | AS/IdP xác thực người dùng hoặc client tùy grant type; xác định chủ thể | AS áp dụng chính sách phát hành, consent khi cần và giới hạn scope/audience/thời hạn |
| **Gửi token** | Client chứng minh đang nắm token; bearer token có thể bị dùng bởi bất kỳ ai đánh cắp được | TLS và bảo vệ nơi lưu token giúp tránh bị chiếm quyền truy cập |
| **API kiểm tra** | Resource Server xác minh token đáng tin và còn hiệu lực | API kiểm scope, tenant, role/quyền và dữ liệu thực tại mỗi yêu cầu cần bảo vệ |
| **Hết hạn / làm mới** | Access token hết hạn; refresh token (nếu có) gửi đến AS theo chính sách của client | AS có thể tái đánh giá quyền khi làm mới; quyền đã thay đổi có thể cần được phản ánh sớm hơn |
| **Đăng xuất / thu hồi** | Phiên đăng nhập ở IdP/client có thể kết thúc | Không được giả định mọi access token JWT đã phát hành lập tức mất hiệu lực; tùy cách xác minh, thời hạn và cơ chế thu hồi |

Một access token JWT tự kiểm chữ ký thường cho phép API xử lý mà không gọi AS cho mỗi yêu cầu. Đổi lại, khi người dùng bị khóa hoặc quyền bị gỡ giữa thời hạn token, API **không tự biết ngay** nếu không có cơ chế bổ sung, như token sống ngắn, kiểm trạng thái phiên/quyền, danh sách thu hồi hoặc kiến trúc token có introspection. Với opaque token được introspect, hiệu quả thu hồi còn phụ thuộc cách AS cập nhật trạng thái và thời gian cache của API.

**Refresh token** có giá trị đặc biệt vì có thể tạo ra access token mới. Hệ thống cần bảo vệ nơi lưu, ràng buộc với client, áp dụng cơ chế xoay vòng hoặc ràng buộc người gửi khi phù hợp và thu hồi khi phát hiện lạm dụng. Refresh token không phải quyền trực tiếp để đọc tài nguyên của resource server.

## 8. Những nhầm lẫn bảo mật thường gặp

**“Đăng nhập thành công nên được gọi mọi API.”** Sai. Đăng nhập chỉ giải quyết danh tính trong phạm vi xác thực. Mỗi API và tài nguyên vẫn cần chính sách phân quyền thích hợp.

**“JWT có chữ ký hợp lệ nghĩa là yêu cầu an toàn.”** Sai. JWT còn phải đúng **issuer**, **audience**, thời hạn, loại token và các điều kiện của API. Chữ ký không chứng minh người giữ bearer token là chủ thể hợp pháp ở thời điểm hiện tại.

**“Có scope đọc là đọc được mọi bản ghi.”** Sai. Scope không tự thay thế kiểm quyền sở hữu, tenant, quan hệ giữa các thực thể và những ràng buộc nghiệp vụ.

**“ID token là JWT nên có thể gửi đến API.”** Sai. ID token phục vụ client OIDC và có audience/phạm vi sử dụng khác; API cần access token dành cho chính API đó.

**“Đăng xuất hoặc đổi mật khẩu làm mọi access token mất hiệu lực ngay.”** Không nhất thiết. Khả năng vô hiệu hóa phụ thuộc chính sách vòng đời token và việc API có kiểm trạng thái thu hồi hay không.

**“OAuth 2.0 luôn chứng minh có người dùng đăng nhập.”** Sai. Grant **client_credentials** là ví dụ API nhận token cho **client/service**, không nhất thiết có người dùng cuối. Phân quyền phải dựa trên đúng danh tính client, không tự gán quyền của một user tưởng tượng.

### Bảo vệ ranh giới tin cậy

- Chỉ nhận access token từ **issuer** đã cấu hình; xác minh chữ ký/thuật toán/khóa hoặc introspection theo mô hình tin cậy.
- Kiểm **audience** để ngăn token được cấp cho dịch vụ khác bị dùng nhầm; phân biệt ID token và access token.
- Dùng **HTTPS/TLS**, bảo vệ token khỏi log, URL, mã JavaScript độc hại hoặc môi trường lưu trữ không phù hợp. Với ứng dụng trình duyệt, cân nhắc kiến trúc lưu token giảm bề mặt XSS và bảo vệ CSRF khi dùng cookie.
- Giảm tác hại khi access token bị đánh cắp bằng **thời hạn ngắn**, scope tối thiểu, giám sát và cơ chế thu hồi phù hợp. Sender-constrained token (ví dụ mTLS hoặc DPoP) có thể hạn chế việc tái sử dụng token bị lộ khi triển khai đúng.
- Kiểm quyền **trên từng đối tượng** và ranh giới tenant tại API/lớp dữ liệu. Không tin role, tenant hoặc user ID do client tự gửi nếu chưa được xác minh và đối chiếu.
- Tránh đưa bí mật hoặc thông tin cá nhân không cần thiết vào payload JWT, vì JWT có chữ ký thông thường **đọc được**, dù không thể sửa hợp lệ khi thiếu khóa ký.

## 9. Tự kiểm tra qua một tình huống

Một API dùng JWT chấp nhận mọi token có chữ ký đúng và có scope **orders:read**. Người dùng thuộc tổ chức A gọi **GET /organizations/B/orders/99** và nhận đơn hàng của tổ chức B.

**Câu hỏi:** Đăng nhập và kiểm chữ ký đều thành công. Hệ thống đang thiếu điều gì?

**Phân tích:**

1. Nếu API chưa kiểm **aud**, token dành cho dịch vụ khác cũng có nguy cơ được chấp nhận: thiếu bước xác minh mục đích sử dụng token.
2. Dù **aud** đúng, API vẫn phải kiểm tổ chức B có nằm trong quyền truy cập của chủ thể không: đây là **lỗ hổng phân quyền trên tài nguyên/tenant**.
3. Scope **orders:read** chỉ cho biết token có phạm vi đọc đơn hàng theo định nghĩa của hệ thống; nó **không** tự cho phép đọc đơn hàng của mọi tổ chức.

Khi thiết kế hoặc rà soát một endpoint dùng token, hãy lần lượt trả lời:

1. **Ai đã xác thực chủ thể, bằng cơ chế nào, tại thời điểm nào?**
2. **API tin token dựa vào điều gì: issuer, khóa/chữ ký hay introspection, audience, thời hạn và trạng thái?**
3. **Token đang đại diện cho người dùng hay client/service?**
4. **Scope/quyền nào cho phép hành động được yêu cầu?**
5. **Chính sách nào kiểm quyền trên chính bản ghi, tenant và điều kiện nghiệp vụ?**

Nếu chỉ trả lời được ba câu đầu, hệ thống đã có một phần ngữ cảnh tin cậy nhưng **chưa chứng minh được yêu cầu cụ thể nên được cho phép**. Đó là ranh giới quan trọng giữa authentication, xác minh token và authorization.

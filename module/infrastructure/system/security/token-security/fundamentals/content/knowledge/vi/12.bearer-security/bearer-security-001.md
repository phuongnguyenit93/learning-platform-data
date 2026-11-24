# Bearer token có thể dùng bởi bất kỳ ai giữ được token

Giả sử An đăng nhập một ứng dụng và nhận **access token** để đọc hóa đơn. Sau đó, một đoạn JavaScript độc hại đánh cắp chuỗi access token từ trình duyệt. Kẻ tấn công gửi chính chuỗi đó đến Invoice API bằng công cụ dòng lệnh. API có thể nhận ra request này **không phải do An trực tiếp gửi** chỉ bằng access token không?

**Thông thường là không.** Với **bearer token**, bên gửi chứng minh quyền sử dụng token bằng việc **xuất trình token**. Resource Server (RS) không mặc nhiên có một bằng chứng mật mã độc lập rằng người đang cầm token là chủ thể ban đầu. Nếu token còn hiệu lực, đúng audience, đúng scope và thỏa các điều kiện phân quyền, một kẻ đánh cắp token có thể gửi request như bên cầm token hợp pháp.

Điều này không có nghĩa **bất cứ chuỗi token nào** đều dùng được ở **mọi API**. “Ai giữ được token thì có thể dùng” phải hiểu là: **bất cứ ai có thể xuất trình một bearer token hợp lệ đều có khả năng sử dụng nó trong đúng phạm vi mà token và chính sách Resource Server cho phép**. Các điều kiện như chữ ký, issuer, audience, expiry, revocation, scope và quyền tài nguyên vẫn phải được kiểm tra.

Bài học trong chương **Bearer security**, module **Security Token Security Fundamentals**, tập trung vào mô hình tin cậy đó; liên hệ JWT và opaque token, OAuth 2.0/OIDC, access/refresh token, các đường rò rỉ và phát lại token, cùng những cách bảo vệ phù hợp. Trọng tâm không chỉ là “mã hóa token” mà là **không để token lọt vào tay người khác và giảm thiểu tác động nếu điều đó xảy ra**.

## 1. Bearer là cơ chế xuất trình, không phải một định dạng token

Thuật ngữ **bearer** chỉ **cách sử dụng thông tin xác thực**: ai xuất trình được bearer token hợp lệ có thể yêu cầu quyền truy cập mà không cần chứng minh thêm quyền sở hữu một khóa mật mã gắn với token. Đây là điểm khác biệt với **sender-constrained token**, nơi access token được ràng buộc với một khóa hoặc chứng chỉ và RS phải kiểm bằng chứng tương ứng.

Ba câu hỏi thường bị nhầm:

| Câu hỏi | Ví dụ | Câu trả lời |
|---|---|---|
| **Token dùng để làm gì?** | Access token, refresh token, ID token | Vai trò của token trong OAuth/OIDC |
| **Token được biểu diễn ra sao?** | JWT, opaque/reference token | Định dạng hoặc cách RS kiểm tra |
| **Ai được phép xuất trình token?** | Bearer hoặc sender-constrained | Cách chứng minh quyền sử dụng token |

Vì vậy:

- Một **JWT access token** có thể được sử dụng theo cách **bearer**.
- Một **opaque access token** cũng có thể được sử dụng theo cách **bearer**.
- JWT có chữ ký hợp lệ **không tự biến bearer token thành token ràng buộc người gửi**.
- Một access token có thể được thiết kế **sender-constrained** bằng mTLS hoặc DPoP khi Authorization Server (AS), client và RS hỗ trợ đúng chuẩn.
- **Refresh token** là thông tin xác thực dùng ở AS để xin access token mới; nếu bị đánh cắp, hậu quả có thể kéo dài hơn access token, nên cần ràng buộc, luân phiên hoặc cơ chế bảo vệ theo profile áp dụng.
- **OIDC ID token** nhằm truyền thông tin xác thực cho **client**, không phải bearer access token hợp lệ để gọi API nghiệp vụ.

**JWT vs opaque** trả lời cách đóng gói/xác minh; **bearer vs sender-constrained** trả lời cách chứng minh quyền sử dụng. Hai trục này **độc lập**.

## 2. Vì sao tên người dùng trong claim không chứng minh người gửi request?

Xét access token JWT minh họa:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user:an",
  "aud": "invoice-api",
  "client_id": "invoice-web",
  "scope": "invoice:read",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "token-5b13"
}
~~~

Sau khi RS xác minh token, nó có thể kết luận:

- `iss` là AS được tin cậy và token được bảo vệ tính toàn vẹn theo cơ chế hợp lệ.
- `sub` mô tả chủ thể An theo hợp đồng với issuer.
- `aud` cho biết token dành cho Invoice API.
- `scope` cho biết phạm vi chức năng đã cấp là `invoice:read`.
- `exp` cho biết thời điểm token hết hiệu lực.

Nhưng RS **không thể kết luận chỉ từ các claim này** rằng **kết nối HTTP hiện tại** do chính An hoặc thiết bị của An thực hiện. Một người có chuỗi bearer token đã bị lấy cắp có thể gửi nó bằng `curl`, script hoặc một ứng dụng khác.

`client_id` cũng không chứng minh người đang cầm bearer token chính là OAuth client hợp pháp. Nó mô tả client được AS cấp token theo profile, **không phải một chữ ký do client tạo cho từng request**. `jti` chỉ là định danh token; nếu không có kiểm soát trạng thái/nonce thích hợp, nó **không tự chặn phát lại**.

Đây là khác biệt giữa:

1. **Authentication/token validation:** API xác minh bằng chứng do AS phát hành.
2. **Authorization:** API kiểm scope, role, audience, tenant, owner và điều kiện nghiệp vụ.
3. **Proof of possession:** API kiểm người xuất trình token có sở hữu khóa/chứng chỉ ràng buộc với token không, **nếu hệ thống dùng sender-constrained token**.

Không được coi bước 1 hoặc 2 là bằng chứng tự động của bước 3.

## 3. Cách bearer token bị đánh cắp và phát lại

Trong OAuth 2.0 Bearer Token Usage (RFC 6750), cách truyền phổ biến là HTTP `Authorization` header:

~~~http
GET /api/invoices/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-redacted>
~~~

Token giống như một **năng lực truy cập có thể chuyển giao bằng chuỗi**. Nếu token bị lộ trước khi hết hạn hoặc bị thu hồi, attacker có thể:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as An
    participant B as Trình duyệt
    participant AS as Authorization Server
    participant X as Kẻ tấn công
    participant API as Invoice API
    U->>B: Đăng nhập
    B->>AS: Xin access token
    AS-->>B: Bearer token aud=invoice-api
    Note over B,X: XSS/log/extension độc hại làm lộ token
    B--xX: Token bị sao chép
    X->>API: Authorization: Bearer token đã đánh cắp
    API->>API: Xác minh token, aud, scope, quyền dữ liệu
    alt Token hợp lệ và policy cho phép
        API-->>X: Trả tài nguyên
    else Token bị từ chối/thu hồi/hết hạn hoặc sai quyền
        API-->>X: 401 / 403 / 404 theo chính sách
    end
~~~

Trong ví dụ trên, AS có thể chưa biết token đã bị sao chép; RS không mặc nhiên phân biệt request của An với request của X. Cần lưu ý **attacker không luôn đọc được mọi dữ liệu**: token chỉ có hiệu lực với audience và scope được cấp, và RS phải kiểm quyền trên từng tài nguyên cụ thể.

### Các nguồn rò rỉ thường gặp

| Nơi rò rỉ | Ví dụ | Cách giảm rủi ro |
|---|---|---|
| **XSS trong frontend** | Script độc hại đọc token trong JavaScript-accessible storage/memory | Chặn XSS, giảm quyền JS tiếp cận token, dùng BFF khi phù hợp, CSP như lớp bổ trợ |
| **Local storage/session storage** | Script chạy cùng origin đọc được token | Tránh lưu token dài hạn tại vùng JavaScript truy cập được khi không cần; đánh giá rủi ro cụ thể |
| **Log, APM, tracing, crash report** | Ghi nguyên header `Authorization` hoặc token response | Redact ở mọi tầng; không log access/refresh token |
| **URL/query string** | `?access_token=...` lọt vào history, proxy log, analytics, referrer hoặc màn hình chia sẻ | Dùng `Authorization: Bearer` header; không gửi token trong URL |
| **Reverse proxy/gateway** | Gateway hoặc downstream chép bearer token vào log | Hạn chế nơi token được relay; chỉ chuyển đến RS cần thiết, che dữ liệu nhạy cảm |
| **Ứng dụng di động** | Backup/thiết bị bị root, log debug, bộ nhớ không an toàn | Dùng storage được nền tảng hỗ trợ, giảm thời hạn token, cân nhắc binding |
| **Máy chủ, CI/CD hoặc backup** | Secret/token nằm trong file cấu hình, artefact build, dump | Secrets management, least privilege, TTL ngắn, kiểm log và quyền truy cập |
| **Phần mở rộng trình duyệt/malware** | Extension có quyền cao đọc nội dung hoặc dữ liệu ứng dụng | Giảm phạm vi token và quyền endpoint; không giả định CSP chặn được malware |
| **Lỗi SSRF/metadata/cloud** | Service bị ép truy cập endpoint cấp credential nội bộ rồi lộ token | Chặn SSRF, bảo vệ metadata và workload identity, hạn chế scope/audience |
| **Ứng dụng bên thứ ba** | Frontend gửi token vào SDK phân tích/telemetry | Không chia sẻ token với bên không cần biết; kiểm data-flow và dependency |

**HTTPS/TLS bảo vệ token trong quá trình truyền qua kênh được thiết lập đúng**, nhưng không chống việc token bị đọc từ log, XSS, máy chủ đã bị chiếm quyền hoặc nơi lưu trữ sai. Ngược lại, chỉ mã hóa dữ liệu ở ổ đĩa cũng không giúp nếu đoạn mã đang chạy được phép giải mã và gửi token đi.

## 4. Hậu quả phụ thuộc token bị mất thuộc loại nào

| Loại token | Được dùng ở đâu | Nếu bị đánh cắp | Cần nhớ |
|---|---|---|---|
| **Bearer access token** | Resource Server theo audience | Attacker có thể gọi API trong thời hạn/phạm vi token nếu RS chấp nhận | Giảm TTL, scope/audience, bảo vệ token và kiểm quyền tài nguyên |
| **Refresh token** | AS/token endpoint | Có thể xin access token mới khi grant còn hiệu lực, tùy cơ chế bảo vệ | Rotation/reuse detection hoặc sender-constraining theo loại client và chính sách |
| **OIDC ID token** | Client/relying party | Có thể làm lộ danh tính/claims, hoặc bị lạm dụng nếu client/API kiểm sai | Không dùng ID token như bearer access token ở API |
| **Authorization code** | Client đổi lấy token ở AS | Bị đánh cắp có thể bị thử đổi code | PKCE, liên kết client/redirect, thời hạn ngắn và single-use |
| **Client secret/private key** | Xác thực confidential client ở AS | Có thể hỗ trợ attacker xin token hoặc giả client trong phạm vi bị lộ | Bảo vệ/luân phiên khóa, dùng phương thức xác thực phù hợp |

Nếu **access token chỉ còn 3 phút**, khoảng thời gian khai thác có thể ngắn hơn token còn sống 24 giờ. Nhưng “3 phút” không phải an toàn tuyệt đối: một API cho phép chuyển tiền hoặc xuất toàn bộ dữ liệu có thể gây thiệt hại lớn chỉ trong vài giây. **Giới hạn thời gian token** cần kết hợp **giới hạn quyền, xác nhận giao dịch và kiểm soát lạm dụng tại RS**.

## 5. Token hợp lệ không đồng nghĩa quyền truy cập vô hạn

Ngay cả khi attacker có bearer token, RS vẫn phải xác minh:

| Điều kiện | Ví dụ thất bại | Phản hồi thường gặp |
|---|---|---|
| **Token/issuer đáng tin** | JWT giả chữ ký hoặc issuer lạ; opaque token inactive | **401 Unauthorized** |
| **Đúng loại token** | Gửi ID token hoặc refresh token thay access token | **401** |
| **Đúng audience** | Token `aud=profile-api` gọi `invoice-api` | **401** |
| **Còn hiệu lực** | `exp` đã qua, `nbf` ở tương lai, token đã thu hồi theo policy | **401** |
| **Scope/quyền chức năng** | Chỉ có `invoice:read` nhưng gọi endpoint `invoice:approve` | **403 Forbidden** |
| **Quyền đối tượng/tenant** | Token của An cố đọc hóa đơn thuộc tenant khác | **403** hoặc **404** theo chính sách |
| **Trạng thái/rủi ro nghiệp vụ** | Đơn hàng đã khóa hoặc giao dịch yêu cầu xác thực mới | Từ chối/step-up theo policy |

Một JWT có chữ ký đúng nhưng **`aud` sai** không thể được dùng ở API không phải bên nhận dự kiến. Một bearer token có `scope=invoice:read` không cho phép attacker tự nâng thành `invoice:delete` chỉ bằng việc sửa payload: chữ ký phải bị sai sau sửa đổi. Tuy nhiên, không vì thế mà coi token có chữ ký đúng là không thể bị đánh cắp.

Với **JWT tự xác minh**, thu hồi không phải lúc nào được RS biết ngay nếu không có kiểm trạng thái ngoài. Với **opaque token** hoặc JWT được introspect, AS có thể trả trạng thái `active`; tính kịp thời phụ thuộc cách cập nhật và cache. Điều quan trọng là **policy thu hồi của hệ thống thật sự ảnh hưởng đến quyết định chấp nhận token**.

### Mã giả tại Resource Server

~~~text
function readInvoice(request, invoiceId):
    context = validateAccessToken(
        bearer = request.authorizationHeader,
        trustedIssuer = "https://auth.example.test",
        expectedAudience = "invoice-api",
        expectedPurpose = "access"
    )
    if context.invalid:
        return HTTP_401

    if not context.grantedScopes.containsExactly("invoice:read"):
        return HTTP_403

    invoice = repository.findWithinAllowedTenant(
        invoiceId, context.verifiedTenant
    )
    if invoice == null:
        return HTTP_404

    if not policy.mayRead(
        subject = context.subject,
        actor = context.clientOrActor,
        invoice = invoice
    ):
        return HTTP_403_or_404_by_policy

    return HTTP_200_with_allowed_fields
~~~

Đây là **mã giả**: `verifiedTenant` và `clientOrActor` là ngữ cảnh do ứng dụng dựng từ nguồn đã kiểm chứng, không phải claim bắt buộc có trong mọi access token. Nếu API dùng **sender-constrained token**, bước `validateAccessToken` còn phải xác minh **proof của người gửi**; ví dụ ở trên chỉ mô tả bearer validation.

## 6. Bảo vệ bearer token trong trình duyệt

Không có một nơi lưu token phù hợp tuyệt đối cho mọi kiến trúc web. Cần hiểu những rủi ro khác nhau của **JavaScript-readable tokens**, **cookie chứa credential** và **Backend For Frontend (BFF)**.

### Mẫu A: JavaScript cầm access token

Một Single-Page Application (SPA) có thể nhận access token và gửi bằng header:

~~~http
GET /api/invoices HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-redacted>
~~~

Nếu token nằm trong `localStorage`/`sessionStorage`, script chạy cùng origin có thể đọc được. Nếu token chỉ nằm trong **memory**, không có tính bền vững qua reload nhưng script độc hại đang chạy cũng có thể lấy token hoặc tự gửi request bằng quyền của ứng dụng. **Lưu trong memory giảm một số đường rò rỉ chứ không chữa XSS**.

Các lớp bảo vệ nên có:

- Ngăn **XSS** bằng output encoding, không render HTML tùy ý, kiểm dependency và CSP phù hợp.
- Chỉ xin scope/audience cần dùng; giảm thời hạn access token.
- Tránh gửi token vào analytics, URL, log, `postMessage` tới origin không tin cậy.
- Bảo vệ luồng Authorization Code + **PKCE**; PKCE giảm rủi ro authorization code interception, **không** tự ràng buộc bearer access token đã cấp với client.
- Nếu có thể, cân nhắc **BFF** hoặc cơ chế sender-constraining theo kiến trúc.

### Mẫu B: BFF giữ token trên server

Với **Backend For Frontend**, trình duyệt giữ **session cookie** để gọi BFF, còn BFF lưu access token/refresh token phía server và gọi resource API:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as Backend For Frontend
    participant AS as Authorization Server
    participant API as Invoice API
    B->>F: Request với session cookie
    F->>AS: Authorization Code + PKCE, token endpoint
    AS-->>F: Access/refresh token
    Note over F: Token nằm phía server, không trao cho JS
    F->>API: Authorization: Bearer access token
    API-->>F: Kết quả theo scope và policy
    F-->>B: Dữ liệu ứng dụng
~~~

Session cookie nên dùng các thuộc tính phù hợp như **`Secure`, `HttpOnly`, `SameSite`**, đồng thời ứng dụng cần quản lý session, chống **CSRF**, kiểm origin khi cần và bảo vệ đăng xuất/rotation. **HttpOnly giúp ngăn JavaScript đọc cookie trực tiếp**, nhưng script độc hại chạy cùng origin vẫn có thể **thực hiện request thông qua trình duyệt** nếu chưa chặn XSS và quyền thao tác. BFF giảm tiếp xúc access/refresh token với frontend, **không tự xóa mọi nguy cơ chiếm phiên hay lạm dụng tác vụ**.

### CORS, CSRF và bearer header

**CORS không phải authorization**: nó kiểm các trường hợp JavaScript của origin khác được trình duyệt cho phép đọc phản hồi; không ngăn attacker dùng `curl` với bearer token đã đánh cắp.

**CSRF** đặc biệt liên quan khi trình duyệt tự gửi credential như **cookie**. Nếu API chỉ chấp nhận `Authorization` header do JavaScript chủ động thêm, một trang ngoài origin thường không thể tự động gắn token bị giữ kín, nhưng vẫn phải đánh giá CORS, XSS và cấu hình credential thực tế. Khi chuyển sang session cookie/BFF, **phải thiết kế CSRF defense**, không chỉ dựa vào `SameSite` trong mọi tình huống.

## 7. Bảo vệ token tại backend, gateway và trên đường truyền

Trong hệ thống nhiều service, access token có thể đi:

~~~text
Browser / Mobile
    -> Edge / API Gateway
    -> Resource Server A
    -> Downstream API B
~~~

Mỗi lần token xuất hiện ở một thành phần là một **điểm có thể bị ghi log hoặc lộ**. Cần xác định thành phần nào thực sự cần biết token và chỉ chuyển nó đến nơi cần.

### Nguyên tắc áp dụng

1. **Dùng TLS/HTTPS** trên đường truyền thích hợp, kiểm chứng endpoint và hạn chế downgrade; bảo vệ cả hop gateway–backend theo trust boundary.
2. **Không đặt bearer token trong URL**. Header `Authorization` là cách phổ biến cho OAuth bearer; với những giao thức đặc biệt, tuân thủ chuẩn và đánh giá rủi ro log/referrer riêng.
3. **Redact đầu cuối**: gateway access log, APM, tracing, exception, error report và debug dump không được ghi nguyên header `Authorization`, refresh token, authorization code hay client secret.
4. **Không relay bừa** token `aud=service-A` sang service B; B phải kiểm audience của B. Khi cần, dùng token exchange hoặc cơ chế cấp token downstream được AS hỗ trợ.
5. **Không tin identity header tự khai** như `X-User-Id` hoặc `X-Tenant-Id` nếu không có kênh tin cậy và cơ chế xác minh; loại bỏ header mạo danh từ client trước khi gateway thêm ngữ cảnh nội bộ.
6. **Khóa quyền đọc token trên server**; dùng secrets management, session store thích hợp, hạn chế quyền truy cập log, backup và snapshot.
7. **Mỗi RS tự thực thi quyền API**, gồm scope, tenant/owner/role và trạng thái; gateway không thay thế toàn bộ object-level authorization.

**Token relay không đổi audience**: gateway đổi host/path của HTTP request không làm `aud` của JWT tự đổi. Nếu cần một access token khác cho backend, issuer đáng tin phải cấp token mới hoặc hệ thống phải dùng bằng chứng nội bộ có trust contract riêng.

### IP address hoặc User-Agent có phải proof of possession?

Chỉ so sánh IP/User-Agent có thể giúp **đánh giá rủi ro**, nhưng không phải bằng chứng sở hữu khóa mật mã. IP có thể thay đổi do NAT, mạng di động, proxy; User-Agent dễ bị giả. Ràng buộc cứng vào IP thường gây từ chối nhầm mà vẫn không ngăn attacker đứng cùng mạng/proxy. Nếu cần ngăn kẻ giữ được **chuỗi token** dùng ở máy khác, nên xem xét sender-constrained token thực sự thay vì chỉ đoán theo metadata mạng.

## 8. Sender-constrained token: khi giữ chuỗi token chưa đủ

Bearer token truyền thống được dùng bằng **việc xuất trình chuỗi token**. Sender-constrained access token bổ sung điều kiện: **request còn phải có bằng chứng sở hữu khóa/chứng chỉ gắn với token**. Hai cơ chế tiêu biểu là **mTLS** (RFC 8705) và **DPoP** (RFC 9449).

| Đặc tính | Bearer token | mTLS certificate-bound token | DPoP-bound token |
|---|---|---|---|
| Bằng chứng cơ bản | Chuỗi access token | Access token **và** chứng chỉ client đúng binding khi gọi RS | Access token **và** DPoP proof ký bằng khóa tương ứng |
| Ràng buộc với | Không bắt buộc khóa sender | Client certificate public key/thông tin certificate theo cơ chế chuẩn | Public key của cặp khóa DPoP, thường qua `cnf.jkt` |
| Lấy cắp **chỉ token string** | Có thể dùng nếu token hợp lệ | Thông thường không dùng được nếu không có certificate/private key phù hợp | Thông thường không dùng được nếu không có private key phù hợp |
| Nếu attacker có cả khóa và token | Vẫn có thể lạm dụng | Bảo vệ ràng buộc bị phá | Bảo vệ ràng buộc bị phá |
| Đòi hỏi hạ tầng | TLS và Bearer token validation | Client-cert TLS & RS kiểm binding; proxy termination cần thiết kế | Client tạo proof, AS/RS cùng kiểm key binding; xử lý nonce/replay |

**Không được chỉ kiểm token có claim `cnf` rồi tự kết luận đã ràng buộc người gửi**. RS cần kiểm proof thực tế, phù hợp với cơ chế đã được phát hành.

### 8.1. mTLS certificate-bound access token

Khi AS phát hành access token gắn với chứng chỉ client, thông tin xác nhận (*confirmation*) có thể ràng buộc token với fingerprint của certificate, chẳng hạn `cnf.x5t#S256` theo profile. RS kiểm chứng TLS client certificate được dùng để gọi mình có khớp binding hay không.

Nếu gateway **kết thúc mTLS của client** rồi mở kết nối TLS khác đến backend bằng chứng chỉ gateway, backend không được tự coi certificate ở hop sau là certificate gốc của client. Có thể kiểm binding ngay tại gateway và chuyển ngữ cảnh nội bộ **được bảo vệ**, hoặc dùng một token/bằng chứng downstream khác phù hợp. **Forward một header tên chứng chỉ** do client tự gửi không phải xác minh mTLS an toàn.

### 8.2. DPoP — proof cho request cụ thể

Với **DPoP**, client sở hữu một cặp khóa và tạo JWT proof có chữ ký cho request. Một proof minh họa về **payload** (không phải JWT đầy đủ):

~~~json
{
  "jti": "proof-8f3",
  "htm": "GET",
  "htu": "https://api.example.test/invoices/42",
  "iat": 1800000001,
  "ath": "hash-of-access-token"
}
~~~

Các thành phần quan trọng:

- `htm`: HTTP method.
- `htu`: URI mục tiêu theo quy tắc canonicalization của DPoP.
- `iat`: thời điểm proof được tạo.
- `jti`: định danh proof phục vụ phát hiện phát lại trong cửa sổ chấp nhận.
- `ath`: giá trị Base64URL của SHA-256 hash access token theo quy tắc DPoP khi proof được dùng ở RS.
- `nonce`: có thể được AS/RS yêu cầu để tăng khả năng chống phát lại.

Client thường gửi:

~~~http
GET /invoices/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <dpop-bound-access-token-redacted>
DPoP: <signed-proof-jwt-redacted>
~~~

RS cần kiểm chữ ký proof, khóa công khai, binding với token, `htm`, `htu`, `iat`, `ath` và kiểm soát `jti`/nonce theo chuẩn và cấu hình. Nếu proof/token chỉ được kiểm một phần, attacker vẫn có thể lách ràng buộc. Khi proxy viết lại URL, các thành phần phải thống nhất URL bên ngoài được xác thực, **không** lấy `X-Forwarded-*` từ nguồn không tin cậy làm căn cứ.

**Cảnh báo quan trọng:** DPoP/mTLS giảm tác động nếu **chỉ chuỗi access token** bị đánh cắp. Nếu attacker chiếm được **cả private key**, hoặc chạy được mã trong chính client và ký request, bảo vệ này không đủ. DPoP cũng không biến token thành quyền được xem mọi bản ghi: issuer, audience, scope và authorization vẫn cần kiểm.

## 9. Giảm tác động của token bị đánh cắp

Vì không thể giả định hệ thống luôn ngăn được mọi rò rỉ, cần thiết kế nhiều lớp:

| Biện pháp | Mục đích | Giới hạn |
|---|---|---|
| **Access token TTL ngắn** | Thu hẹp cửa sổ sử dụng token bị lộ | Không ngăn hành động tức thời; TTL quá ngắn tăng tải refresh |
| **Scope tối thiểu** | Giới hạn thao tác có thể thực hiện | Không thay quyền trên từng đối tượng |
| **Audience hẹp** | Giới hạn API chấp nhận token | Không chặn attacker dùng tại đúng API đó |
| **Object/tenant authorization** | Ngăn vượt quyền ngang và chéo tenant | Không ngăn attacker hành động trong quyền của chủ thể bị chiếm |
| **Refresh token rotation/reuse detection** | Hạn chế khả năng duy trì phiên nếu token bị sao chép | Cần xử lý race, lưu trạng thái và phản ứng thu hồi |
| **Token revocation/introspection** | Ngừng chấp nhận token bị đánh cắp theo chính sách | JWT tự xác minh có thể không biết revocation ngay; phụ thuộc cache |
| **DPoP/mTLS** | Yêu cầu bằng chứng khóa ngoài token string | Không chống mất cả khóa hoặc mã độc trong client |
| **Reauthentication/step-up** | Tăng bảo đảm cho thao tác nhạy cảm | Cần ràng buộc hành động/thời điểm, không chỉ có access token |
| **Rate limit và fraud detection** | Giảm tốc độ rút dữ liệu/thao tác, phát hiện bất thường | Không thay token validation hoặc phân quyền |
| **Audit và phản ứng sự cố** | Xác định hành động bị lạm dụng, thu hồi và điều tra | Phải tránh ghi token vào log |

### Access token và refresh token cần chiến lược khác nhau

Access token thường sống ngắn hơn và được gửi đến RS. Refresh token thường có giá trị **duy trì khả năng lấy access token mới** và nên được bảo vệ mạnh tại client. Theo OAuth 2.0 Security Best Current Practice (RFC 9700), public client cần dùng các biện pháp như **sender-constrained refresh tokens hoặc refresh token rotation** để phát hiện/hạn chế lạm dụng, theo những quy tắc áp dụng.

**Refresh token rotation** phát hành refresh token mới và làm vô hiệu refresh token cũ ở lần refresh thành công. Nếu refresh token cũ được dùng lại, AS có thể phát hiện khả năng bị sao chép; chính sách phản ứng có thể thu hồi token family và yêu cầu đăng nhập lại. Client phải phối hợp các tab/luồng bằng **single-flight refresh** để giảm sử dụng đồng thời cùng token một cách không chủ ý.

Không được hiểu rotation là giải pháp chống đánh cắp **access token đang hoạt động**. Nếu attacker có access token còn hạn, RS có thể vẫn chấp nhận cho tới expiry/thu hồi theo chính sách.

## 10. Phát hiện và xử lý khi nghi token bị lộ

Khi phát hiện token có thể đã xuất hiện trong log, telemetry, trình duyệt bị XSS hoặc kho mã:

1. **Ngăn tiếp tục rò rỉ:** khóa hoặc sửa đường thu thập token (debug logging, SDK, XSS, proxy headers); tránh sao chép token sang thêm công cụ theo dõi sự cố.
2. **Xác định loại token và phạm vi:** bearer access token hay refresh token, issuer nào, audience/scope/tenant nào, thời hạn còn lại và có sender-constraining không.
3. **Thu hồi phù hợp:** revoke refresh token/phiên hoặc token family theo hỗ trợ AS; xử lý access token qua introspection, denylist, đổi khóa/claim version hoặc đợi expiry **theo chính sách và mức độ nghiêm trọng**. Không đổi khóa ký toàn hệ thống chỉ vì một access token lộ nếu hậu quả gián đoạn lớn hơn và có cơ chế thu hồi phù hợp.
4. **Rà soát hành động đáng ngờ:** kiểm audit dựa trên subject/client, resource, thời điểm, request ID, nguồn/thiết bị; phân biệt dữ liệu có bằng chứng và suy đoán.
5. **Buộc xác thực lại khi cần**, vô hiệu phiên, đổi client secret hoặc private key nếu **chúng** bị lộ; chỉ đổi mật khẩu người dùng nếu có lý do liên quan.
6. **Khắc phục nguyên nhân gốc:** sửa XSS, khóa log, chặn SSRF, bảo vệ nơi lưu, cấu hình least privilege và test hồi quy.

Nếu token đã bị đăng công khai, nên giả định **chuỗi token đã bị người khác sao chép**, dù đã xóa bài đăng/log sau đó. Thu hồi và rà soát phải dựa trên khả năng sử dụng thực tế của token, không chỉ dựa trên việc “đã xóa nơi lộ”.

### Revocation không đồng nghĩa xóa claim khỏi JWT

JWT đã ký chứa dữ liệu cố định; AS không thể thay đổi `exp`, `scope` hay `aud` trong chính chuỗi token đã phát hành mà vẫn giữ chữ ký cũ. Thu hồi là vấn đề **RS ngừng chấp nhận token** thông qua trạng thái/chiến lược kiểm, không phải chỉnh trực tiếp payload ở thiết bị của attacker. Opaque token thường hỗ trợ kiểm trạng thái tập trung dễ hơn, nhưng khả năng phản ứng vẫn tùy triển khai/cache.

## 11. Ví dụ cấu hình và kiểm soát ở API

Đối với **Spring Security 6.x** khi Invoice API nhận bearer JWT access token, có thể khai báo chức năng bằng authorities tương ứng với scope:

~~~java
@Configuration
@EnableMethodSecurity
class InvoiceApiSecurity {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                .hasAuthority("SCOPE_invoice:read")
            .requestMatchers(HttpMethod.POST, "/api/invoices/*/approve")
                .hasAuthority("SCOPE_invoice:approve")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Đây không phải cấu hình production đầy đủ.** Ứng dụng còn phải cấu hình **issuer và audience validator**, thuật toán/khóa tin cậy, đúng access-token profile, phương án thu hồi và CSRF nếu có loại credential cần bảo vệ; mapping `scope` sang `SCOPE_...` có thể được tùy biến. Bản thân đoạn mã trên **không bật DPoP hoặc mTLS token binding**; nếu muốn sender-constraining phải triển khai và xác minh proof riêng đúng chuẩn.

**Quan trọng:** Dù bearer token hợp lệ và có `invoice:read`, service vẫn phải kiểm quan hệ của subject với **từng hóa đơn**. Nếu attacker lấy token của An, attacker chỉ nên có thể truy cập **những gì An thực sự được phép truy cập**, không phải dữ liệu thuộc người khác hay tenant khác.

### Vì sao 401 và 403 khác nhau?

| Tình huống | Mã phổ biến | Diễn giải |
|---|---|---|
| Không có token hoặc token sai issuer/chữ ký/audience/hết hạn | **401 Unauthorized** | Không có bearer access token được RS chấp nhận |
| Token hợp lệ, thiếu scope chức năng | **403 Forbidden** | Không được phép thực hiện hành động theo scope |
| Token hợp lệ, đúng scope nhưng tài nguyên của tenant khác | **403** hoặc **404** theo chính sách | Không có quyền đối tượng |
| Token hợp lệ nhưng sender proof bắt buộc không đúng | Từ chối theo profile, thường **401** | Không đủ bằng chứng người gửi theo cơ chế binding |

Ví dụ bearer challenge cho token không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Không trả toàn bộ claims, bearer token, khóa ký hoặc danh sách tài nguyên nhạy cảm trong response lỗi. Nếu nhận token sai mục đích hoặc sai binding, áp dụng lỗi/challenge thích hợp với profile đang triển khai (ví dụ DPoP có quy tắc riêng), không áp dụng mù mẫu `Bearer` cho mọi trường hợp.

## 12. Những hiểu lầm dễ tạo lỗ hổng

| Nhận định | Đúng hay sai? | Giải thích |
|---|---|---|
| “JWT đã ký thì người khác cầm token cũng không dùng được.” | **Sai** | Chữ ký chống sửa token, không ràng buộc người gửi |
| “Opaque token an toàn hơn JWT trước người cầm token bị lộ.” | **Không tự động đúng** | Nếu đều là bearer, chuỗi token bị đánh cắp có thể bị dùng; opaque chỉ khác cách xác minh/quản trị |
| “`sub=user:an` chứng minh request đang đến từ thiết bị của An.” | **Sai** | `sub` mô tả subject, không phải sender proof |
| “`jti` đủ để ngăn replay.” | **Sai** | Cần state/nonce hoặc cơ chế proof phù hợp; bearer access token thường được dùng nhiều lần |
| “HTTPS ngăn mọi kiểu đánh cắp token.” | **Sai** | TLS không ngăn XSS, log hoặc máy bị chiếm quyền |
| “CORS chặn được attacker có bearer token gửi request bằng `curl`.” | **Sai** | CORS là cơ chế trình duyệt, không phải API authorization |
| “`HttpOnly` khiến XSS hoàn toàn vô hại.” | **Sai** | Script có thể vẫn thực hiện request bằng phiên cookie, dù không đọc cookie trực tiếp |
| “PKCE giúp access token sau khi cấp không thể bị dùng lại.” | **Sai** | PKCE bảo vệ đổi authorization code, không tự ràng buộc bearer access token |
| “Chỉ cần scope đúng, API không cần kiểm owner/tenant.” | **Sai** | Scope không thay object-level authorization |
| “Token bị lộ nhưng đã xóa log thì hết rủi ro.” | **Sai** | Attacker có thể đã sao chép trước khi log bị xóa |
| “DPoP làm token không thể bị lạm dụng trong mọi hoàn cảnh.” | **Sai** | Mất cả khóa hoặc client bị XSS/chạy mã độc vẫn có rủi ro |
| “Access token ngắn hạn giảm thời gian khai thác.” | **Đúng, nhưng chưa đủ** | Một request nhạy cảm vẫn có thể gây thiệt hại ngay lập tức |

## 13. Ma trận kiểm thử bearer token

Một bài kiểm thử tốt phải thử cả **token đúng nhưng bị gửi từ một client khác** để thấy giới hạn của bearer, đồng thời bảo đảm RS không chấp nhận token ngoài scope hoặc audience.

| Kịch bản | Cách kiểm thử | Kết quả kỳ vọng |
|---|---|---|
| **Bearer token hợp lệ từ client chính** | Gọi API đúng audience/scope và có quyền dữ liệu | Cho phép theo chính sách |
| **Sao chép bearer token sang máy khác** | Gửi nguyên token hợp lệ từ công cụ độc lập trong môi trường test | Có thể được chấp nhận nếu không có sender-binding/điều kiện khác; dùng để minh họa rủi ro |
| **Token hết hạn** | Dùng token sau `exp` | **401** |
| **Token bị thu hồi** | Revoke rồi gọi lại khi hệ thống đã cập nhật trạng thái | Từ chối theo chính sách thu hồi |
| **Token sai audience** | `aud=profile-api` tại Invoice API | **401** |
| **Thiếu scope** | `invoice:read` nhưng gọi phê duyệt | **403** |
| **Sai tenant/owner** | Có scope đọc nhưng truy cập ID không thuộc quyền | **403/404** |
| **JWT bị sửa payload** | Đổi `sub` hoặc `scope` mà không ký lại | **401** |
| **ID token thay access token** | Gửi OIDC ID token đến RS | Từ chối token sai mục đích |
| **Refresh token vào resource API** | Gửi refresh token bằng Bearer header | Từ chối |
| **Access token sender-bound nhưng thiếu proof** | Gửi chỉ token DPoP/mTLS mà không có khóa/bằng chứng phù hợp | Từ chối |
| **DPoP proof sai phương thức/URI** | Đổi `htm`, `htu` hoặc request | Từ chối theo profile |
| **DPoP proof phát lại** | Dùng lại proof `jti` trong cửa sổ kiểm | Từ chối khi cơ chế replay detection áp dụng |
| **Proxy viết log token** | Gửi request test rồi tra log được phép kiểm | Không chứa bearer/refresh token nguyên bản |
| **BFF với XSS/CSRF thử nghiệm** | Kiểm JS không đọc server token; thử request không hợp lệ CSRF | Không lộ token; hành động trái policy bị chặn |
| **Token exchange sai đích** | Dùng token dành cho API A tại API B | B từ chối nếu không có token/bằng chứng riêng cho B |
| **Nhiều request bằng token bị lộ** | Tạo lưu lượng test có kiểm soát | Rate limit/giám sát hoạt động theo yêu cầu; không bỏ phân quyền |

### Tình huống thực hành

Invoice API yêu cầu `aud=invoice-api` và `scope=invoice:read`. An có token còn 8 phút, được phép xem hóa đơn `INV-42` của tenant A. Một script XSS lấy access token từ trình duyệt và gửi đến kẻ tấn công.

~~~text
Token đã cấp:
  iss   = https://auth.example.test
  sub   = user:an
  aud   = invoice-api
  scope = invoice:read
  exp   = sau 8 phút

Attacker:
  GET /api/invoices/INV-42
  Authorization: Bearer <stolen-token-redacted>
~~~

**Câu 1: Nếu đây là bearer access token bình thường, API có thể trả hóa đơn cho attacker không?**

**Có thể có.** Nếu token vẫn hợp lệ và chính sách cho An đọc hóa đơn, chỉ việc thay người cầm token không làm chữ ký sai. Đây chính là rủi ro cốt lõi của bearer token.

**Câu 2: Attacker có thể đổi token sang `scope=invoice:delete` rồi dùng không?**

**Không** nếu RS xác minh chữ ký/issuer đúng. Sửa payload làm token không còn hợp lệ; nếu attacker chiếm được khóa ký tin cậy thì là sự cố nặng hơn.

**Câu 3: Attacker dùng token của Invoice API để gọi Payment API được không?**

**Không**, nếu Payment API kiểm audience `payment-api` đúng cách. Token hợp lệ ở Invoice API không phải token của mọi API.

**Câu 4: Nếu attacker dùng token đó đọc hóa đơn tenant B thì sao?**

API phải từ chối theo quyền đối tượng/tenant. Bearer token không thay thế kiểm quyền dữ liệu.

**Câu 5: Nếu token được ràng buộc DPoP và attacker chỉ đánh cắp access token string thì sao?**

Khi RS thực thi DPoP đúng chuẩn, attacker **không thể hoàn tất proof phù hợp** nếu không có private key tương ứng. Nhưng nếu script độc hại có thể điều khiển client để ký request hoặc đánh cắp khóa, vẫn có nguy cơ. Ngăn XSS và bảo vệ khóa vẫn là điều kiện quan trọng.

**Câu 6: Nếu giảm TTL xuống 60 giây là đủ chưa?**

**Chưa.** Attacker vẫn có thể khai thác trong 60 giây và hành động giá trị cao có thể hoàn tất rất nhanh. Cần thêm scope/audience tối thiểu, bảo vệ nơi lưu, step-up, quyền trên bản ghi, rate limit và phản ứng thu hồi phù hợp.

## 14. Checklist thiết kế trước khi đưa bearer token vào production

1. **Hiểu đúng loại credential:** Token này là access, refresh hay ID token; bearer hay sender-constrained; JWT hay opaque?
2. **Bảo vệ khi cấp phát:** Authorization Code + PKCE hoặc flow phù hợp, xác thực client/grant và scope/audience tối thiểu?
3. **Không lộ qua kênh truyền:** TLS đúng cấu hình; bearer token không nằm trong URL, log, telemetry hoặc SDK không cần biết?
4. **Lưu trữ đúng rủi ro:** SPA có giải pháp với XSS; BFF/session cookie có chống CSRF; mobile/server có storage và quyền truy cập phù hợp?
5. **Kiểm tại từng RS:** `iss`, chữ ký hoặc introspection, `aud`, `exp`, token profile/type, scope và revocation theo chính sách?
6. **Phân quyền nghiệp vụ:** Tenant, owner, role, trạng thái và field-level authorization được kiểm độc lập với scope?
7. **Bảo vệ token bị lộ:** TTL, audience/scope hẹp, rate limit, audit, step-up và kế hoạch thu hồi/đăng xuất?
8. **Quản lý refresh token:** Rotation hoặc sender-constraining khi cần, reuse detection và xử lý race nhiều tab/client?
9. **Xem xét proof of possession:** mTLS/DPoP nếu phù hợp, RS có thực thi ràng buộc; proxy có duy trì/chuyển bằng chứng đúng không?
10. **Kiểm token forwarding:** Gateway không relay token sai audience hoặc chuyển principal qua header không tin cậy?
11. **Kiểm thử tấn công:** Token bị sao chép, hết hạn, sai audience/scope, ID/refresh token dùng sai, DPoP sai proof, log leak và access chéo tenant?
12. **Chuẩn bị incident response:** Khi token bị lộ, ai có thể revoke token/phiên, kiểm audit và ngăn tái lộ nhanh chóng?

**Ghi nhớ:** Với **bearer token**, **việc sở hữu chuỗi token là căn cứ để sử dụng token**, không phải bằng chứng xác thực độc lập về người đang cầm nó. Chữ ký JWT xác minh nguồn phát hành/tính toàn vẹn; opaque introspection xác minh trạng thái/ngữ cảnh; `aud` và `scope` giới hạn đích nhận và quyền; **không biện pháp nào trong số đó tự ngăn token bị sao chép và dùng lại tại đúng API**. Vì vậy phải bảo vệ token ở mọi điểm xuất hiện, cấp quyền tối thiểu, kiểm quyền ở RS, và cân nhắc **sender-constrained token** khi mức rủi ro yêu cầu.

### Chuẩn tham khảo

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** khái niệm bearer, cách gửi access token và mối đe dọa/bảo vệ.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** access token, refresh token, client, AS và RS.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `sub`, `aud`, `exp` và JWT Claims Set.
- **RFC 7662 — OAuth 2.0 Token Introspection:** tra trạng thái/ngữ cảnh opaque/reference token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế thu hồi token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** dùng JWT làm OAuth access token theo profile.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** access token ràng buộc chứng chỉ.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** token ràng buộc khóa, proof, token hash và replay.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth, giảm lạm dụng bearer token và refresh token.
- **OpenID Connect Core 1.0:** phân biệt ID token (cho client) với access token (cho API).

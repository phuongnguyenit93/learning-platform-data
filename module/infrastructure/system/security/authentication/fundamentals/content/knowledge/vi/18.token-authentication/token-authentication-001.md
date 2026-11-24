# Token là gì?

> **Chương:** Token authentication  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Khái niệm token trong xác thực và ủy quyền, các loại token, cấu trúc claim, cách phát hành và xác minh, vòng đời, lưu trữ, thu hồi và phòng chống replay.

## 1. Token là gì?

**Token** là một giá trị dữ liệu được hệ thống phát hành hoặc tạo ra để đại diện cho một trạng thái, quyền hoặc bằng chứng trong một ngữ cảnh xác định. Trong hệ thống xác thực, token thường được cấp sau khi người dùng hoặc dịch vụ đã chứng minh danh tính. Client gửi token trong các yêu cầu tiếp theo để dịch vụ nhận diện chủ thể và đánh giá quyền truy cập.

Ví dụ, sau khi người dùng đăng nhập thành công, hệ thống có thể cấp access token. Khi client gọi API, nó gửi token trong header Authorization. API kiểm tra token có hợp lệ, được cấp bởi bên tin cậy, dành cho API đó, còn hạn và có phạm vi quyền phù hợp hay không.

Token giúp không phải gửi lại mật khẩu ở mọi request. Tuy nhiên, token thường trở thành **credential có thể sử dụng để truy cập**. Nếu kẻ tấn công lấy được một bearer token còn hiệu lực, họ có thể dùng nó như người sở hữu token cho đến khi token hết hạn hoặc bị thu hồi, trừ khi có cơ chế ràng buộc người gửi hoặc thiết bị.

Token không phải một định dạng duy nhất. Nó có thể là chuỗi ngẫu nhiên không mang cấu trúc công khai (opaque token), hoặc một cấu trúc có các trường dữ liệu/claim như JWT. Token có thể dùng cho xác thực, ủy quyền, khôi phục, xác minh email, chống CSRF hoặc các mục đích khác. **Ý nghĩa của token phụ thuộc vào giao thức, nơi phát hành, nơi nhận và cách server xác minh.**

### Kết quả học tập

Sau bài này, người học có thể:

- Giải thích token và vai trò của nó trong xác thực, ủy quyền và duy trì phiên.
- Phân biệt opaque token, JWT, access token, ID token và refresh token.
- Đọc các claim quan trọng như issuer, subject, audience, expiry và scope.
- Thiết kế cách phát hành, lưu trữ, truyền, xác minh, làm mới và thu hồi token.
- Nhận diện rủi ro bearer token, replay, token substitution, lộ token và xác minh sai.
- Chọn cơ chế token phù hợp với ranh giới tin cậy và tài nguyên được bảo vệ.

## 2. Token nằm ở đâu trong luồng xác thực?

Token thường xuất hiện **sau bước xác minh credential**. Người dùng có thể đăng nhập bằng mật khẩu, MFA, passkey hoặc nhà cung cấp danh tính. Khi các điều kiện xác thực đạt, hệ thống tạo trạng thái phiên hoặc phát hành token. Client dùng kết quả đó để truy cập tài nguyên.

~~~mermaid
flowchart LR
    U["Người dùng"] --> C["Client"]
    C -->|"Credential / passkey / MFA"| A["Dịch vụ xác thực"]
    A -->|"Xác minh danh tính và trạng thái"| P{"Đạt chính sách?"}
    P -->|"Không"| D["Từ chối"]
    P -->|"Có"| T["Phát hành session hoặc token"]
    T --> C
    C -->|"Token trong request"| R["Resource server / API"]
    R --> V{"Token hợp lệ và đúng audience?"}
    V -->|"Không"| X["401"]
    V -->|"Có"| Z{"Có quyền trên tài nguyên?"}
    Z -->|"Không"| F["403"]
    Z -->|"Có"| O["Thực hiện hành động"]
~~~

Token giúp truyền ngữ cảnh đã xác thực hoặc quyền được cấp giữa các thành phần. Nó không làm mất nhu cầu kiểm tra ở server. API vẫn cần xác minh token và phân quyền cho từng tài nguyên/hành động.

### Ba câu hỏi phải tách biệt

1. **Token này đại diện cho ai hoặc điều gì?** Xác định subject, client, service hoặc phiên.
2. **Token này được dùng ở đâu và để làm gì?** Kiểm tra issuer, audience, loại token, scope và thời hạn.
3. **Chủ thể có được phép thực hiện hành động cụ thể không?** Áp dụng authorization tại resource server.

Một token có chữ ký hợp lệ không đồng nghĩa người cầm nó là chủ tài khoản ban đầu; với bearer token, quyền sử dụng thường thuộc về bên đang sở hữu token. Chữ ký cũng không tự chứng minh API được gọi là đúng audience hoặc hành động được phép.

## 3. Token và session khác nhau thế nào?

**Session** là trạng thái làm việc đã được hệ thống ghi nhận cho một chủ thể sau xác thực. **Token** là một cách mang hoặc tham chiếu đến thông tin về trạng thái/quyền đó. Một session có thể được đại diện bằng cookie chứa session ID; token cũng có thể là mã tham chiếu đến session phía server.

| Đặc điểm | Session phía server | Token tự chứa (ví dụ JWT) |
|---|---|---|
| Trạng thái | Server lưu trạng thái phiên | Một phần claim nằm trong token |
| Mỗi request | Server tra session hoặc cache | Server xác minh token; có thể không cần tra DB cho mọi claim |
| Thu hồi | Có thể vô hiệu hóa session ngay khi trạng thái được cập nhật | Khó thu hồi tức thời nếu token tự chứa và không có kiểm tra trạng thái bổ sung |
| Kích thước | Cookie thường chỉ mang session ID | Token có thể lớn do chứa nhiều claim/chữ ký |
| Tác động khi lộ | Người khác có thể chiếm session | Người khác có thể dùng bearer token trong phạm vi của nó |

JWT không tự động tốt hơn session. Lựa chọn phụ thuộc khả năng mở rộng, yêu cầu thu hồi, kiến trúc dịch vụ, độ nhạy tài nguyên và cách bảo vệ client.

### Cookie session cũng là một token theo nghĩa rộng

Cookie có thể chứa một session identifier ngẫu nhiên. Giá trị đó không nhất thiết chứa thông tin người dùng; server dùng nó để tra trạng thái phiên. Vì trình duyệt tự gửi cookie theo quy tắc domain/path/SameSite, cần bảo vệ CSRF và cấu hình Secure, HttpOnly, SameSite phù hợp.

## 4. Opaque token và token có cấu trúc

### Opaque token

Opaque token là chuỗi thường không mang ý nghĩa có thể đọc trực tiếp ở client. Server tra cứu token hoặc dùng introspection để biết token đại diện cho chủ thể nào, còn hạn hay không và có quyền gì.

Ưu điểm:

- Không để lộ claim trực tiếp cho client chỉ bằng cách giải mã chuỗi.
- Server có thể thay đổi trạng thái và thu hồi token qua kho dữ liệu hoặc introspection.
- Định dạng nội bộ có thể thay đổi mà client không cần hiểu cấu trúc.

Hạn chế:

- Resource server có thể cần gọi authorization server hoặc kho trạng thái để kiểm tra.
- Cần thiết kế cache/introspection để cân bằng hiệu năng và độ trễ thu hồi.
- Nếu kho token hoặc endpoint introspection gặp sự cố, các dịch vụ phụ thuộc có thể bị ảnh hưởng.

### Token có cấu trúc: JWT

**JWT (JSON Web Token)** là định dạng biểu diễn các claim dưới dạng JSON. JWT thường được dùng trong dạng JWS có chữ ký hoặc MAC; cũng có thể được mã hóa theo JWE.

JWT dạng JWS phổ biến có ba phần Base64URL, ngăn cách bằng dấu chấm:

~~~text
header.payload.signature
~~~

- **Header:** mô tả loại token và thuật toán bảo vệ, có thể có key ID.
- **Payload:** chứa claim như issuer, subject, audience, expiry, scope.
- **Signature:** bảo vệ tính toàn vẹn và xác thực nguồn phát hành theo khóa/thuật toán đã chọn.

Base64URL chỉ là cách mã hóa biểu diễn, **không phải mã hóa bí mật**. Bất kỳ ai có JWT dạng JWS đều có thể đọc header và payload. Không đưa mật khẩu, số định danh nhạy cảm, bí mật hoặc dữ liệu riêng tư không cần thiết vào payload.

### Chữ ký không phải mã hóa

| Cơ chế | Bảo vệ điều gì? | Có che nội dung payload không? |
|---|---|---|
| JWS ký số hoặc MAC | Tính toàn vẹn và nguồn phát hành theo khóa tin cậy | Không |
| JWE mã hóa | Tính bí mật, cùng các thuộc tính toàn vẹn theo thuật toán/mode | Có, với bên không có khóa giải mã |
| Base64URL | Cách biểu diễn dữ liệu | Không |

Nếu cần giữ bí mật claim, hãy cân nhắc không đưa dữ liệu đó vào token, dùng opaque token hoặc dùng cơ chế mã hóa phù hợp. Không tự mã hóa payload bằng một phép biến đổi tùy biến.

## 5. Các loại token thường gặp

| Loại | Mục đích | Ai thường sử dụng? |
|---|---|---|
| **Access token** | Truy cập API/resource server theo scope và audience | Client gửi đến API |
| **ID token** | Truyền kết quả xác thực người dùng cho OpenID Connect client | OIDC relying party/client |
| **Refresh token** | Xin access token mới mà không yêu cầu người dùng đăng nhập lại ngay | Client gửi đến authorization server |
| **Session token/identifier** | Tham chiếu đến phiên đăng nhập | Browser hoặc ứng dụng gửi đến server |
| **Password reset token** | Cho phép thực hiện một lần đặt lại mật khẩu theo mục đích | Luồng khôi phục |
| **Email verification token** | Xác minh quyền kiểm soát địa chỉ email | Luồng kích hoạt/xác minh |
| **CSRF token** | Ràng buộc request với ngữ cảnh trình duyệt để giảm CSRF | Client gửi theo cơ chế ứng dụng |
| **Service/workload token** | Đại diện workload hoặc dịch vụ khi gọi API | Service-to-service |

Không sử dụng một token cho nhiều mục đích chỉ vì định dạng giống nhau. Token reset mật khẩu không được dùng để gọi API dữ liệu; ID token không được tự động chấp nhận như access token; refresh token không được gửi đến resource server.

## 6. Access token, ID token và refresh token

Ba loại token thường gặp trong OAuth 2.0/OpenID Connect có mục đích khác nhau.

### Access token

Access token đại diện cho quyền truy cập được cấp cho client để gọi một resource server. API cần kiểm tra token được phát hành cho chính nó, còn hiệu lực và có scope/permission phù hợp.

Ví dụ request:

~~~http
GET /v1/profile
Authorization: Bearer <access-token>
~~~

Access token có thể là opaque hoặc JWT. Resource server phải biết cách xác minh đúng loại token theo cấu hình của authorization server.

### ID token

ID token thuộc OpenID Connect, truyền thông tin về kết quả xác thực cho client/RP. Nó thường chứa subject, issuer, audience, thời điểm phát hành và thời điểm hết hạn; có thể có claim về phương thức hoặc mức xác thực.

ID token **không phải access token**. API không được nhận ID token làm bằng chứng truy cập chỉ vì nó có chữ ký hợp lệ. Audience của ID token thường là OIDC client; resource server có audience và chính sách riêng.

### Refresh token

Refresh token được client dùng với authorization server để xin access token mới. Nó thường có tuổi thọ dài hơn access token và do đó là tài sản có giá trị cao.

Biện pháp bảo vệ:

- Lưu trong vùng bảo vệ phù hợp của ứng dụng; không đưa vào URL, log hoặc analytics.
- Với ứng dụng công khai, sử dụng refresh token rotation hoặc cơ chế sender-constrained theo khả năng giao thức.
- Phát hiện refresh token cũ được sử dụng lại sau khi đã xoay vòng.
- Thu hồi khi đăng xuất, đổi credential, phát hiện chiếm quyền hoặc người dùng hủy grant theo chính sách.
- Giới hạn scope, client và thời hạn; không gửi refresh token đến resource server.

### So sánh nhanh

| Câu hỏi | Access token | ID token | Refresh token |
|---|---|---|---|
| Dùng ở đâu? | Resource server/API | OIDC client/RP | Authorization server |
| Mục đích | Truy cập tài nguyên | Thông tin xác thực người dùng | Xin token mới |
| Audience | API/resource tương ứng | Client OIDC | Theo chính sách authorization server/client |
| Có gửi cho mọi API không? | Chỉ API đúng audience | Không | Không |
| Có cần bảo vệ bí mật? | Có | Có | Rất cao |

## 7. Các claim quan trọng

JWT payload có thể chứa các claim chuẩn và claim riêng. Claim chỉ đáng tin sau khi token được xác minh đúng nguồn, chữ ký, loại và ngữ cảnh.

| Claim | Ý nghĩa | Câu hỏi kiểm tra |
|---|---|---|
| **iss (issuer)** | Bên phát hành token | Có đúng authorization server được tin cậy không? |
| **sub (subject)** | Chủ thể được token đại diện | Subject này được hiểu trong phạm vi issuer nào? |
| **aud (audience)** | Bên nhận dự kiến | Token có dành cho API/client hiện tại không? |
| **exp (expiration)** | Thời điểm hết hạn | Token còn hiệu lực không? |
| **nbf (not before)** | Chưa được sử dụng trước thời điểm này | Đã đến thời điểm hợp lệ chưa? |
| **iat (issued at)** | Thời điểm phát hành | Token có quá cũ hoặc bất thường không? |
| **jti (JWT ID)** | Định danh token | Có dùng để phát hiện/revoke/replay theo thiết kế không? |
| **scope** | Phạm vi quyền được cấp | Scope có đủ và có bị rộng quá không? |
| **client_id** | Ứng dụng client liên quan | Client này có được phép dùng grant không? |
| **acr / amr** | Ngữ cảnh/mức hoặc phương thức xác thực trong OIDC | Chính sách có yêu cầu phương thức/mức xác thực cụ thể không? |
| **auth_time** | Thời điểm người dùng xác thực | Có cần xác thực lại vì phiên quá cũ không? |

### Issuer và subject phải được hiểu cùng nhau

Subject không nhất thiết là một định danh toàn cục. Hai issuer khác nhau có thể phát hành cùng giá trị sub cho hai người khác nhau. Vì vậy, khi liên kết danh tính liên kết, thường cần xem cặp **issuer + subject** và xác minh token theo đúng giao thức.

Không tự động ghép tài khoản chỉ vì email trong claim trùng nhau. Email có thể thay đổi, được tái cấp hoặc chưa được xác minh; cần kiểm tra trạng thái xác minh và chính sách liên kết.

### Audience là ranh giới rất quan trọng

Token dành cho API A không được mặc nhiên chấp nhận ở API B. Nếu nhiều API chỉ kiểm tra chữ ký và thời hạn mà không kiểm tra audience, token có thể bị sử dụng chéo dịch vụ (token substitution/confused deputy).

API phải kiểm tra audience đúng theo cấu hình, kể cả khi token do cùng một issuer phát hành. Với claim aud dạng mảng, áp dụng đúng quy tắc của giao thức và thư viện đã chọn.

## 8. Bearer token và sender-constrained token

### Bearer token

Bearer token là token mà bên sở hữu nó có thể sử dụng mà không cần chứng minh thêm quyền kiểm soát một khóa riêng hoặc thiết bị. Đây là mô hình đơn giản và phổ biến, nhưng token bị đánh cắp có thể bị replay.

Ví dụ, kẻ tấn công lấy access token từ log hoặc bộ nhớ client rồi gửi request đến API. Nếu token còn hạn, đúng audience và không bị thu hồi, API có thể chấp nhận request.

### Sender-constrained token

Sender-constrained token gắn quyền sử dụng token với một khóa hoặc bằng chứng từ client. Kẻ tấn công chỉ lấy được token nhưng không có khóa tương ứng sẽ khó sử dụng nó.

Các hướng triển khai có thể gồm:

- **mTLS-bound access token:** token gắn với chứng chỉ client; resource server kiểm tra chứng chỉ của kết nối và ràng buộc tương ứng.
- **DPoP (Demonstrating Proof of Possession):** client tạo proof ký bằng khóa riêng, gắn với request và token theo quy tắc giao thức.

Sender-constraining giảm rủi ro token bị sao chép đơn thuần, nhưng không giải quyết mọi tình huống. Nếu thiết bị/client và khóa riêng bị chiếm, kẻ tấn công vẫn có thể tạo bằng chứng hợp lệ. Cần dùng triển khai chuẩn và thư viện được duy trì, không tự thiết kế giao thức proof.

## 9. Token được phát hành như thế nào?

Token nên được phát hành bởi một thành phần có thẩm quyền sau khi kiểm tra credential, trạng thái tài khoản, client và chính sách cấp quyền.

Một quy trình khái niệm:

1. Client bắt đầu luồng xác thực/ủy quyền phù hợp.
2. Authorization server xác minh người dùng hoặc workload.
3. Server kiểm tra redirect URI, client, consent, scope và điều kiện MFA/step-up nếu có.
4. Server phát hành token với audience, thời hạn và quyền tối thiểu.
5. Token được chuyển về client qua kênh/response đúng giao thức.
6. Client lưu token theo cách phù hợp và gửi access token đến resource server.
7. Resource server xác minh token và kiểm tra quyền tài nguyên.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>C: Khởi tạo đăng nhập
    C->>AS: Authorization request
    AS->>AS: Xác thực người dùng / MFA / consent
    AS-->>C: Authorization result theo flow
    C->>AS: Đổi code hoặc yêu cầu token theo flow
    AS-->>C: Access token và có thể refresh token
    C->>RS: API request với access token
    RS->>RS: Xác minh token và authorization
    RS-->>C: Dữ liệu hoặc lỗi
~~~

Đây là sơ đồ tổng quát. Với ứng dụng web/mobile công khai, thường dùng Authorization Code Flow với PKCE theo hướng dẫn OAuth/OIDC hiện hành. Không dùng implicit flow cũ cho ứng dụng mới; không tự xây giao thức chuyển token bằng query string tùy biến.

## 10. Xác minh token tại resource server

Token chỉ có ý nghĩa khi bên nhận kiểm tra đúng điều kiện. Với JWT ký số, quy trình thường gồm:

1. Nhận token từ vị trí được quy định, thường là Authorization header.
2. Giới hạn kích thước và kiểm tra định dạng trước khi xử lý.
3. Xác định đúng loại token và thuật toán được phép từ cấu hình tin cậy.
4. Chọn khóa xác minh từ tập khóa tin cậy, không tải khóa tùy ý từ URL do token cung cấp.
5. Xác minh chữ ký hoặc MAC.
6. Kiểm tra issuer, audience, thời hạn exp, nbf và các điều kiện thời gian liên quan.
7. Kiểm tra scope, client, subject, trạng thái tài khoản hoặc trạng thái token theo yêu cầu.
8. Kiểm tra quyền của subject trên tài nguyên và hành động cụ thể.
9. Chỉ thực hiện thao tác sau khi mọi kiểm tra đạt.

### Không tin header thuật toán do token tự chọn

JWT header là dữ liệu đầu vào không tin cậy cho đến khi xác minh hoàn tất. Server phải dùng allowlist thuật toán đã cấu hình, kiểm tra kiểu token và chọn khóa từ nguồn đáng tin cậy. Không chấp nhận thuật toán không bảo vệ hoặc để token tự quyết định nguồn khóa.

Nếu dùng JWKS, endpoint lấy khóa phải được cấu hình từ issuer đáng tin cậy. Trường kid chỉ là gợi ý chọn khóa trong tập đã tin cậy; không nối kid thành đường dẫn file hoặc URL tùy ý.

### Ví dụ kiểm tra logic

~~~typescript
async function authorizeApiRequest(request) {
  const token = readBearerToken(request);
  if (!token) return { status: 401 };

  const claims = await trustedTokenVerifier.verify(token, {
    issuer: TRUSTED_ISSUER,
    audience: THIS_API_AUDIENCE,
    allowedAlgorithms: ["RS256", "ES256"],
    requiredClaims: ["sub", "exp"],
  });

  if (!claims) return { status: 401 };
  if (!hasRequiredScope(claims, "reports:read")) {
    return { status: 403 };
  }

  const resource = await loadRequestedReport(request);
  if (!await canReadReport(claims.sub, resource)) {
    return { status: 403 };
  }

  return { status: 200, resource };
}
~~~

Đây là pseudocode. Các thuật toán trong allowlist chỉ là ví dụ; cấu hình thực tế phải phù hợp issuer và thư viện. Hàm verify phải kiểm tra chữ ký, issuer, audience, thời hạn và loại token. Không tự giải mã payload rồi tin claim mà không xác minh chữ ký/MAC.

### Opaque token và introspection

Với opaque token, resource server có thể gọi endpoint introspection của authorization server để nhận trạng thái active, subject, scope, audience và metadata liên quan. Endpoint phải được bảo vệ; resource server cần xác thực khi gọi introspection. Nếu cache kết quả, thời gian cache quyết định độ trễ thu hồi.

## 11. Lưu trữ và truyền token an toàn

Token thường có quyền truy cập tương đương credential. Cách lưu phụ thuộc loại client và kiến trúc.

| Nơi lưu | Rủi ro | Hướng giảm thiểu |
|---|---|---|
| URL/query string | Lộ qua history, log, referrer, analytics | Không đặt token trong URL |
| Browser localStorage | JavaScript cùng origin có thể đọc; XSS có thể lấy token | Cân nhắc BFF và cookie an toàn; giảm XSS |
| Cookie | CSRF nếu trình duyệt tự gửi; cấu hình sai domain/path | Secure, HttpOnly, SameSite và CSRF protection phù hợp |
| Mobile secure storage | Thiết bị root/jailbreak, backup hoặc malware | Keychain/Keystore và chính sách thiết bị |
| Server secret store | Quyền đọc rộng, backup hoặc log lộ | Secret manager/KMS, least privilege, audit |
| Log/tracing/error report | Token có thể bị sao chép và sử dụng | Redaction, không log token, hạn chế dữ liệu |

Access token nên được gửi qua HTTPS trong Authorization header hoặc cơ chế chuẩn tương đương. Không gửi token qua query string. Không ghi toàn bộ Authorization header vào log.

### Browser và cookie

Cookie phiên/token có thể dùng Secure, HttpOnly và SameSite phù hợp. HttpOnly giảm khả năng JavaScript đọc cookie nhưng không ngăn XSS thực hiện request dưới phiên người dùng; SameSite giúp giảm CSRF nhưng không thay thế mọi kiểm soát CSRF. Lựa chọn cookie hay bearer token phụ thuộc kiến trúc web, BFF, CORS và threat model.

### Ứng dụng mobile

Lưu refresh token trong vùng bảo vệ của nền tảng như Keychain/Keystore theo thiết kế ứng dụng. Không nhúng token dài hạn trong binary, resource hoặc file cấu hình. Kiểm tra deep link/callback, backup và logging để tránh lộ token.

## 12. Thời hạn, làm mới và thu hồi token

### Expiration

Token nên có thời hạn phù hợp với giá trị tài nguyên và khả năng thu hồi. Access token thường ngắn hạn hơn refresh token. Token khôi phục hoặc xác minh email thường chỉ dùng một lần và có thời hạn ngắn.

Không chọn thời hạn chỉ vì thuận tiện. Thời hạn quá dài tăng cửa sổ sử dụng nếu token bị lộ; quá ngắn có thể tạo nhiều lần refresh và làm tăng độ phức tạp vận hành.

### Refresh token rotation

Với rotation, mỗi lần sử dụng refresh token, authorization server cấp token mới và vô hiệu hóa token cũ theo chính sách. Nếu token cũ đã bị dùng lại, hệ thống có thể phát hiện dấu hiệu replay/chiếm quyền và thu hồi cả nhóm token liên quan.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    C->>AS: Gửi refresh token R1
    AS->>AS: Kiểm tra R1 còn active và thuộc client
    AS->>AS: Thu hồi R1, tạo R2
    AS-->>C: Access token mới + refresh token R2
    Note over C,AS: Nếu R1 được gửi lại sau rotation, phát hiện reuse theo chính sách
~~~

Client phải xử lý đồng thời và retry cẩn thận. Hai request refresh cùng lúc có thể làm token cũ bị dùng lại ngoài ý muốn; cần cơ chế đồng bộ, idempotency hoặc chính sách grace phù hợp mà không tạo cửa sổ replay quá rộng.

### Revocation

Token có thể bị thu hồi khi người dùng đăng xuất, đổi mật khẩu, thay đổi yếu tố xác thực, bị đình chỉ, hủy consent hoặc khi phát hiện rủi ro. Cách thu hồi phụ thuộc loại token:

- Opaque token: đánh dấu inactive trong kho token hoặc introspection.
- JWT tự chứa: thời hạn ngắn, denylist/jti, token version, kiểm tra trạng thái phiên/tài khoản hoặc cơ chế tương đương.
- Refresh token: thu hồi token hoặc token family; yêu cầu đăng nhập/ủy quyền lại.
- Session cookie: hủy session ở server và thay session identifier khi cần.

JWT có chữ ký hợp lệ không tự biến mất khi người dùng đăng xuất. Nếu API chỉ kiểm tra chữ ký và exp, token có thể tiếp tục được chấp nhận đến khi hết hạn. Thiết kế phải cân bằng giữa xác minh stateless và nhu cầu thu hồi nhanh.

## 13. Replay, token theft và các rủi ro thường gặp

| Rủi ro | Cách xảy ra | Kiểm soát |
|---|---|---|
| Bearer token theft | Token lộ trong log, XSS, malware, URL hoặc backup | Lưu trữ an toàn, redaction, TLS, thời hạn ngắn, thu hồi |
| Replay | Kẻ tấn công gửi lại token/request đã lấy | Challenge/nonce, sender-constraining, idempotency cho thao tác |
| Wrong audience | Token của API A bị dùng ở API B | Kiểm tra aud chính xác |
| Token substitution | Dùng ID token ở nơi cần access token hoặc nhầm loại token | Kiểm tra typ, issuer, audience và mục đích |
| Algorithm confusion | Server chấp nhận thuật toán/khóa không phù hợp | Allowlist thuật toán, cấu hình khóa tin cậy |
| Key confusion / kid abuse | Token điều khiển việc chọn khóa hoặc nguồn khóa | JWKS cố định theo issuer, kid chỉ tra trong tập tin cậy |
| Long-lived refresh token theft | Kẻ tấn công duy trì quyền truy cập | Rotation, reuse detection, revoke family |
| Claim overtrust | API tin role/scope mà không kiểm tra tài nguyên | Authorization server-side theo object/action |
| Token in logs | Tracing/log lưu Authorization header | Redaction ở gateway, app, APM và support tooling |
| Clock/expiry mistakes | Bỏ qua exp/nbf hoặc lệch thời gian lớn | Đồng bộ thời gian, clock skew nhỏ và có giới hạn |

### Replay và nonce

Token bearer thường có thể được dùng nhiều lần trong thời hạn. Với một số thao tác nhạy cảm, hệ thống có thể dùng nonce hoặc challenge một lần, ràng buộc với request/giao dịch. Server lưu trạng thái đã sử dụng và từ chối replay. Cần xác định rõ cửa sổ thời gian, retry và tính idempotent để không nhầm request hợp lệ được gửi lại do mạng lỗi với tấn công.

### JWT không phải lúc nào cũng cần chứa nhiều claim

Claim dư thừa làm token lớn, tăng dữ liệu lộ khi token bị đọc và có thể trở nên lỗi thời khi quyền thay đổi. Chỉ đưa thông tin cần thiết; dữ liệu nhạy cảm hoặc thay đổi nhanh nên được tra từ server hoặc dùng token opaque/introspection phù hợp.

## 14. Token và authorization: scope chưa đủ

Scope mô tả phạm vi quyền được cấp ở mức giao thức hoặc API. Ví dụ scope reports:read có thể cho phép đọc nhóm API báo cáo, nhưng không nhất thiết cho phép đọc mọi báo cáo thuộc mọi tenant.

Resource server vẫn cần kiểm tra:

- Subject thuộc tenant nào?
- Resource có thuộc tenant hoặc phạm vi quản lý của subject không?
- Hành động cụ thể có được phép không?
- Trạng thái tài khoản và quyền có thay đổi sau khi token được cấp không?
- Token có được cấp cho client và API đúng không?

Ví dụ, token có scope reports:read vẫn không được phép đọc báo cáo của khách hàng khác nếu quan hệ sở hữu hoặc chính sách tenant không cho phép. Một claim role=admin cũng cần được xác minh nguồn và đánh giá theo chính sách hiện hành.

**Authentication** xác định danh tính hoặc bằng chứng của chủ thể; **authorization** quyết định hành động trên tài nguyên. Token có thể mang thông tin phục vụ cả hai nhưng không thay thế bước kiểm tra của server.

## 15. Ví dụ thực tế: ứng dụng báo cáo

**Bối cảnh:** Nhân viên đăng nhập vào ứng dụng báo cáo bằng passkey. Ứng dụng dùng OIDC để nhận token và gọi API báo cáo. API chỉ cho phép nhân viên xem báo cáo thuộc phòng ban của họ.

### Luồng

1. Browser chuyển người dùng đến authorization server theo OIDC Authorization Code Flow với PKCE.
2. Người dùng xác thực bằng passkey; server kiểm tra WebAuthn assertion.
3. Authorization server trả authorization code cho callback URI đã đăng ký.
4. Client đổi code theo flow và nhận ID token, access token; có thể nhận refresh token tùy chính sách.
5. Client xác minh ID token theo yêu cầu OIDC để thiết lập ngữ cảnh đăng nhập.
6. Client gửi access token đến API báo cáo.
7. API xác minh chữ ký/opaque token, issuer, audience, thời hạn và scope.
8. API tra quyền của subject trên báo cáo cụ thể rồi trả dữ liệu hoặc từ chối.

### Ví dụ request

~~~http
GET /api/reports/quarterly
Authorization: Bearer <access-token>
~~~

API không được dùng ID token thay cho access token. API cũng không được tin phòng ban do client gửi; phải xác định từ claim đã được xác minh hoặc dữ liệu phân quyền server-side phù hợp.

### Nếu access token bị lộ

- Thu hồi phiên/refresh token hoặc grant liên quan theo khả năng.
- Đánh giá request được thực hiện bằng token trong thời gian nghi lộ.
- Kiểm tra nơi token bị lộ: browser storage, extension, log, tracing hoặc thiết bị.
- Rút ngắn thời hạn và cân nhắc sender-constrained token cho API có rủi ro cao.
- Yêu cầu xác thực lại bằng passkey nếu cần; kiểm tra thay đổi phương thức khôi phục và quyền.

Đổi mật khẩu hoặc đăng xuất ở giao diện không tự động thu hồi mọi access token nếu hệ thống không có cơ chế tương ứng.

## 16. Checklist thiết kế token

- [ ] Mục đích token được xác định rõ: access, ID, refresh, session, recovery hay CSRF.
- [ ] Client và server phân biệt token bearer với sender-constrained token.
- [ ] Issuer và audience được kiểm tra theo cấu hình tin cậy.
- [ ] Chữ ký/MAC được xác minh bằng thuật toán và khóa nằm trong allowlist.
- [ ] JWT payload không bị xem như dữ liệu bí mật chỉ vì đã Base64URL.
- [ ] Kiểm tra exp, nbf, loại token và claim cần thiết.
- [ ] ID token không được dùng thay access token.
- [ ] Refresh token được bảo vệ, rotation và phát hiện reuse khi phù hợp.
- [ ] Token không xuất hiện trong URL, log, analytics hoặc error report.
- [ ] Cookie/browser/mobile storage có kiểm soát phù hợp với threat model.
- [ ] Có chiến lược expiry, logout, revocation và xử lý tài khoản bị đình chỉ.
- [ ] Scope không thay thế authorization theo tenant, tài nguyên và hành động.
- [ ] Challenge/nonce và cơ chế idempotency được dùng đúng nơi cần chống replay.
- [ ] Key rotation/JWKS được quản lý từ nguồn tin cậy; kid không điều khiển URL tùy ý.
- [ ] Có kiểm thử token hết hạn, sai issuer/audience, sai chữ ký, replay, nhầm loại và thu hồi.

## Ghi nhớ

Token là một giá trị đại diện cho danh tính, quyền hoặc trạng thái trong một ngữ cảnh cụ thể. Opaque token tham chiếu trạng thái phía server; JWT có cấu trúc claim và thường được ký, nhưng chữ ký không che nội dung. Access token dành cho API, ID token dành cho OIDC client và refresh token dành cho authorization server.

Token hợp lệ vẫn phải đúng issuer, audience, thời hạn, loại và phạm vi; API tiếp tục kiểm tra quyền trên tài nguyên cụ thể. Vì token có thể trở thành bearer credential, hãy bảo vệ nơi lưu trữ và truyền, giới hạn thời hạn, có cơ chế rotation/revocation và chống replay phù hợp.

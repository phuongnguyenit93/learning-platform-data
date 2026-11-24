# Issuer confusion — Nhầm lẫn nhà phát hành token

## 1. Issuer confusion là gì và nguy hiểm ở đâu?

Trong mô hình **OAuth 2.0/OpenID Connect (OIDC)**, một hệ thống thường phải phối hợp nhiều vai trò: **authorization server (AS)** phát hành token, **client** nhận và sử dụng token, **resource server (RS)** bảo vệ API, còn **OpenID Provider (OP)** cung cấp danh tính qua OIDC. Khi có nhiều nhà cung cấp danh tính, nhiều tenant hoặc nhiều môi trường, hệ thống cần biết **chính xác nhà phát hành nào được tin cậy trong từng giao dịch**.

**Issuer confusion (nhầm lẫn nhà phát hành)** xảy ra khi ứng dụng không xác định hoặc không kiểm tra đúng nguồn phát hành của token hay phản hồi ủy quyền. Hệ thống có thể chấp nhận một token đến từ AS không được phép, liên kết một danh tính với sai nhà phát hành, hoặc gửi authorization code và thông tin nhạy cảm đến token endpoint của AS khác.

Hai nhóm tình huống tiêu biểu:

1. **Token issuer confusion:** API hoặc ứng dụng chấp nhận JWT/ID token của issuer khác issuer được phép, hoặc lấy khóa xác thực từ nguồn do token chưa được xác thực chỉ định.
2. **Authorization server mix-up:** một OAuth client làm việc với nhiều AS nhưng nhầm phản hồi authorization thuộc AS nào, dẫn đến trao đổi code tại sai token endpoint hoặc gắn kết quả đăng nhập với sai nhà phát hành.

Không phải mọi lỗi issuer confusion đều do JWT. **Opaque token**, kết quả introspection, callback OAuth và cơ chế định tuyến đa tenant cũng có thể làm phát sinh sự nhầm lẫn tương tự.

**Mục tiêu của bài học:** xác lập chuỗi tin cậy theo issuer, hiểu vai trò của claim **iss**, biết cách kiểm tra response issuer trong OAuth/OIDC và triển khai xác minh token ở client/resource server mà không để dữ liệu chưa được tin cậy tự chọn bên xác thực nó.

## 2. Issuer, audience, subject và nơi phát hành token

### 2.1. Claim iss có ý nghĩa gì?

Trong JWT, claim **iss** (issuer) mô tả thực thể đã phát hành token. Với một hệ thống dùng OIDC, giá trị issuer thường là một định danh URL HTTPS do OpenID Provider công bố. Ví dụ:

~~~json
{
  "iss": "https://login.example.test/tenant-a",
  "sub": "user-724",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1795400000,
  "exp": 1795400300
}
~~~

Ở ví dụ này:

- **iss = https://login.example.test/tenant-a:** token tuyên bố được phát hành bởi nhà phát hành của tenant A.
- **sub = user-724:** định danh chủ thể **trong ngữ cảnh issuer đó**.
- **aud = orders-api:** đối tượng nhận token được chỉ định.
- **scope = orders:read:** phạm vi quyền đã cấp.
- **iat, exp:** thời điểm phát hành và hết hạn; phải được kiểm tra theo chính sách.

**Đọc được iss không đồng nghĩa tin được iss.** Payload JWT chỉ là dữ liệu có thể giải mã trước khi kiểm tra chữ ký. Kẻ tấn công có thể tự tạo một JWT với bất kỳ iss nào. Việc API chấp nhận token phải dựa trên chuỗi tin cậy đã được cấu hình và chữ ký được kiểm tra bằng **khóa của issuer được phép**, sau đó xác minh các claims khác.

### 2.2. Phân biệt các khái niệm thường bị đánh đồng

| Thông tin | Câu hỏi nó trả lời | Kiểm tra bảo mật tương ứng |
|---|---|---|
| **iss** | Ai tuyên bố đã phát hành token? | Có phải issuer được phép; giá trị có khớp issuer đã cấu hình không? |
| **aud** | Token được phát hành để ai nhận? | API/client hiện tại có nằm trong audience hợp lệ không? |
| **sub** | Chủ thể được nhận diện là ai? | Diễn giải subject trong phạm vi issuer; ánh xạ đúng tài khoản/tenant |
| **azp/client_id** | Client nào được ủy quyền hoặc có liên quan? | Kiểm tra theo loại token và chính sách |
| **scope/roles/permissions** | Token cho phép hành động nào? | Đánh giá quyền trên từng API hoặc tài nguyên |
| **jti** | Định danh token riêng biệt là gì? | Hỗ trợ kiểm toán, denylist hoặc phát hiện reuse nếu có trạng thái |
| **kid** trong JWT header | Dùng khóa nào trong tập khóa ứng viên? | Chỉ tra cứu khóa **thuộc issuer đang xác minh**; kid không phải danh tính issuer |

Kiểm tra iss **không thay thế** kiểm tra aud. Chẳng hạn hai issuer đều cấp token có aud = orders-api, nhưng API chỉ cho phép issuer dành cho môi trường production. Token do issuer staging phát hành vẫn phải bị từ chối dù audience trùng khớp.

Cần phân biệt định dạng token:

- **JWT access token:** resource server xác minh chữ ký và các claims. Trong **JWT access token profile RFC 9068**, iss là một trong các claims bắt buộc; RS còn phải kiểm tra audience và các điều kiện khác.
- **OIDC ID token:** client xác minh danh tính người dùng theo OIDC; phải kiểm tra iss và aud dành cho **client_id** cùng các điều kiện liên quan như nonce khi áp dụng. ID token **không tự động là access token** để gọi API.
- **Opaque access token:** token không cần chứa claims có thể đọc trực tiếp. RS thường dùng introspection hoặc trạng thái đáng tin cậy từ AS, và phải ràng buộc kết quả với **AS được phép** cho API/tenant tương ứng.
- **Refresh token:** chỉ được đổi tại token endpoint phù hợp, trong phạm vi client/phiên và nhà phát hành đã cấp; không dùng làm chứng thực tại resource server.

Trong chuẩn JWT tổng quát (RFC 7519), không phải mọi ứng dụng JWT đều bắt buộc có iss. Tuy nhiên, khi một giao thức hoặc chính sách yêu cầu xác thực issuer — ví dụ OIDC ID token hoặc JWT access token theo RFC 9068 — thiếu iss là lỗi cần từ chối, không được tự gán issuer mặc định.

## 3. Hai đường tấn công chính

### 3.1. Chấp nhận token của issuer không đáng tin cậy

Giả sử API Orders chấp nhận JWT. Kẻ tấn công vận hành một AS riêng có khóa ký **K_attacker** và phát hành token:

~~~json
{
  "iss": "https://attacker-idp.example.test",
  "sub": "admin",
  "aud": "orders-api",
  "scope": "orders:read orders:write",
  "exp": 1795403600
}
~~~

Token có thể có chữ ký hợp lệ **theo khóa của kẻ tấn công**. API vẫn phải từ chối vì issuer không thuộc tập issuer được cho phép. Lỗi xuất hiện nếu API:

1. Chỉ kiểm tra rằng JWT có **chữ ký hợp lệ bởi một khóa nào đó** mà không ràng buộc khóa với issuer được tin cậy.
2. Tự tải JWKS từ URL được suy ra từ claim iss hoặc header jku/x5u trong token chưa xác thực.
3. Tin mọi issuer có thể discovery qua Internet, hoặc tự thêm issuer mới vào danh sách tin cậy dựa trên request.
4. Dùng cùng một bộ khóa chung cho nhiều issuer nhưng không kiểm tra iss sau khi xác thực chữ ký.

Một biến thể tinh vi hơn: kẻ tấn công đặt **iss = https://login.example.test/tenant-a** trong JWT tự ký, rồi cung cấp header jku trỏ tới JWKS của mình. Nếu API tải và chấp nhận khóa đó, nó đã cho phép token tự quyết định nguồn xác thực chữ ký. Chữ ký lúc này **hợp lệ với khóa sai**, chứ không hợp lệ với khóa issuer tin cậy.

~~~mermaid
flowchart TD
    A[Kẻ tấn công tạo JWT với iss tùy ý] --> B[API đọc iss hoặc jku chưa xác thực]
    B --> C{API có danh sách issuer và JWKS tin cậy?}
    C -- Không --> D[Tải khóa theo dữ liệu token]
    D --> E[Chữ ký khớp khóa của kẻ tấn công]
    E --> F[Nguy cơ chấp nhận token giả]
    C -- Có --> G[Chỉ chọn issuer đã cho phép]
    G --> H[Chỉ dùng khóa của issuer đó]
    H --> I{Chữ ký và claims hợp lệ?}
    I -- Không --> J[Từ chối]
    I -- Có --> K[Tiếp tục kiểm tra audience và quyền]
~~~

### 3.2. Authorization server mix-up trong luồng đăng nhập

Một OAuth client có thể tích hợp **nhiều AS** — chẳng hạn AS_A là nhà cung cấp nội bộ, AS_B là IdP bên ngoài. Nếu client dùng chung một callback cho cả hai mà không ràng buộc mỗi giao dịch với issuer dự kiến, kẻ tấn công có thể khiến client hiểu sai authorization response đến từ AS nào.

Một kịch bản khái niệm:

1. Client có thể làm việc với **AS_A đáng tin cậy** và **AS_B do kẻ tấn công kiểm soát**.
2. Kẻ tấn công khiến người dùng/ứng dụng bắt đầu một phiên mà client ghi nhớ là với AS_B, trong khi trình duyệt nhận authorization code từ AS_A qua một đường chuyển hướng bị thao túng.
3. Callback nhận **code do AS_A cấp** nhưng client vẫn cho rằng phiên thuộc AS_B.
4. Nếu client chọn token endpoint từ lựa chọn ban đầu hoặc tham số không được kiểm tra, nó có thể gửi **code của AS_A đến token endpoint AS_B**, đồng thời làm lộ các tham số liên quan như code_verifier tùy triển khai.
5. Kẻ tấn công có thể lợi dụng dữ liệu bị lộ; phạm vi khai thác cụ thể còn phụ thuộc ràng buộc code với client, redirect URI, PKCE, xác thực client và hành vi của AS.

Đây là **mix-up attack**, được mô tả trong hướng dẫn bảo mật OAuth. Vấn đề gốc là client **không chứng minh được authorization response thuộc đúng AS đã chọn cho giao dịch hiện tại**.

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant C as OAuth Client
    participant A as AS_A hợp lệ
    participant B as AS_B độc hại
    C->>C: Tạo state, lưu expected_issuer = AS_B
    U->>A: Luồng authorization bị điều hướng đến AS_A
    A-->>U: Redirect về callback với code_A và issuer_A
    U->>C: code_A, state, iss=issuer_A
    C->>C: So iss với expected_issuer
    alt Xác minh issuer đúng
        C-->>U: Từ chối, không gửi code_A cho AS_B
    else Thiếu xác minh issuer
        C->>B: Gửi code_A đến token endpoint sai
        B-->>C: Phản hồi tùy ý hoặc thu thập dữ liệu
    end
~~~

**state**, **PKCE** và kiểm tra redirect URI vẫn rất quan trọng nhưng giải quyết những điều kiện khác nhau. Không nên xem việc có state hoặc PKCE là lý do để bỏ ràng buộc issuer. Để chống mix-up, client nhiều AS cần kiểm tra **issuer của authorization response**, chẳng hạn theo RFC 9207, hoặc sử dụng biện pháp phân biệt AS được tiêu chuẩn cho phép như **redirect URI riêng theo AS**.

## 4. Thiết lập ranh giới tin cậy cho issuer

### 4.1. Danh sách issuer cho phép phải có nguồn đáng tin cậy

Một resource server hoặc OAuth client nên có cấu hình được quản trị trước:

~~~yaml
trustedIssuers:
  - issuer: "https://login.example.test/tenant-a"
    jwksUri: "https://login.example.test/tenant-a/.well-known/jwks.json"
    allowedAudiences:
      - "orders-api"
    environment: "production"
  - issuer: "https://partners.example.test"
    jwksUri: "https://partners.example.test/keys"
    allowedAudiences:
      - "partners-api"
    environment: "production"
~~~

Ví dụ chỉ là cấu trúc minh họa, **không phải định dạng YAML chuẩn của một thư viện cụ thể**. Trong hệ thống thật, các URL và audience phải lấy từ cấu hình/metadata đã được kiểm chứng và được quản lý như một danh sách tin cậy.

Các nguyên tắc:

- Tạo **allowlist** issuer đúng với API, ứng dụng, tenant và môi trường triển khai.
- Với từng issuer, pin **issuer identifier**, metadata/discovery endpoint và nguồn **JWKS** tương ứng.
- Khi dùng OIDC Discovery hoặc OAuth Authorization Server Metadata, xác thực trường **issuer** trong metadata theo định danh issuer đã dự kiến; đừng tin metadata trả về một issuer khác chỉ vì HTTPS thành công.
- **Không** phát sinh địa chỉ tải JWKS bằng cách ghép đường dẫn trực tiếp từ iss/jku/x5u do token chưa xác thực cung cấp.
- Không nhận issuer tùy ý từ query parameter, HTTP header hoặc dữ liệu tenant do client khai rồi lập tức coi đó là **bên được tin cậy**.
- Khi nhiều issuer cùng được cho phép, giới hạn rõ issuer nào có quyền phát hành token cho **audience, chức năng và tenant cụ thể**. Cho phép issuer ở cấp hệ thống chưa có nghĩa nó được phép truy cập mọi tài nguyên.

**Discovery động** có thể được sử dụng trong hệ thống thực tế, nhưng quy trình quyết định **issuer mới có được tin cậy hay không** phải độc lập với token/request chưa xác thực và phải có điều kiện phê duyệt, ràng buộc tenant hoặc cơ chế onboarding đáng tin cậy.

### 4.2. So sánh issuer chính xác

Với OIDC và metadata OAuth, issuer identifier là giá trị giao thức cần so khớp theo quy tắc của giao thức. Nên dùng **so sánh chính xác với giá trị issuer được cấu hình**, không dùng:

- Kiểm tra tiền tố chuỗi, ví dụ bắt đầu bằng https://login.example.test.
- So sánh domain con gần giống hoặc một phần hostname.
- Coi mọi URL có cùng host là cùng issuer, bỏ qua path/tenant.
- Tự bỏ dấu / ở cuối, thay chữ hoa/chữ thường trong path, đổi URL encoding hoặc sửa issuer để hai giá trị khác nhau trở thành bằng nhau mà không có quy tắc giao thức cho phép.
- Chấp nhận một alias chưa được khai báo như một issuer có quyền tương đương.

Ví dụ:

| Issuer từ token/response | Issuer dự kiến | Kết luận |
|---|---|---|
| https://login.example.test/tenant-a | https://login.example.test/tenant-a | Khớp issuer; còn phải kiểm tra chữ ký, audience, quyền |
| https://login.example.test/tenant-b | https://login.example.test/tenant-a | **Từ chối:** khác tenant/path |
| https://login.example.test/tenant-a/ | https://login.example.test/tenant-a | **Từ chối** nếu identifier chuẩn đã khai báo khác nhau |
| https://login.example.test.attacker.test/tenant-a | https://login.example.test/tenant-a | **Từ chối:** khác host |
| https://evil.example.test | https://login.example.test/tenant-a | **Từ chối:** issuer không được phép |
| Issuer bị thiếu | Issuer bắt buộc | **Từ chối:** thiếu thông tin cần xác thực |

Khi thay đổi domain, tenant path hoặc cấu hình issuer, hãy triển khai chuyển đổi **có kiểm soát**. Việc tự thêm alias rộng rãi để xử lý lỗi cấu hình có thể mở đường cho token từ môi trường hoặc nhà phát hành khác.

### 4.3. Khóa ký phải nằm trong ngữ cảnh issuer

JWT header có thể chứa **kid** để xác định một khóa trong tập khóa. Kid **không phải giá trị duy nhất toàn cầu**. Hai issuer khác nhau có thể cùng dùng kid = key-1 nhưng khóa thực tế hoàn toàn khác nhau.

Khóa cache nên được chọn trong **JWKS của issuer đã cho phép**, tương đương định danh **(issuer, kid)** cùng các điều kiện khóa/thuật toán. Không tìm kid trong “một kho toàn cục” rồi dùng khóa đầu tiên trùng tên.

Phải áp dụng chính sách thuật toán, key type và key use phù hợp; từ chối alg = none trong luồng yêu cầu JWT ký, và tránh nhầm lẫn thuật toán đối xứng/bất đối xứng. Header **jku** hoặc **x5u** trong token không được tự ý trở thành URL tải khóa cho request hiện tại; nguy cơ bao gồm thay thế khóa và **SSRF**.

**Luân chuyển khóa** (key rotation) cho cùng một issuer là tình huống bình thường: token cũ có thể còn hợp lệ với khóa cũ trong giai đoạn chuyển đổi. Tuy nhiên, việc issuer cập nhật JWKS **không có nghĩa** có thể bỏ so khớp issuer hoặc chấp nhận khóa mới từ một địa chỉ do client tự chỉ định.

## 5. Quy trình xác minh JWT access token ở resource server

### 5.1. Thứ tự kiểm tra an toàn

Đối với một API nhận JWT access token từ nhiều AS:

1. **Xác định tập issuer được phép** từ cấu hình tin cậy của resource server và ngữ cảnh endpoint/tenant.
2. **Phân tích token ở chế độ chưa tin cậy** nếu cần lấy iss để chọn cấu hình xác minh. Giới hạn kích thước và cấu trúc token; không thực hiện nghiệp vụ từ claims chưa được xác thực.
3. **Từ chối issuer không thuộc allowlist**, không tự gọi HTTP đến URL lấy từ iss của token.
4. **Xác minh chữ ký** bằng khóa được lấy từ JWKS tin cậy của đúng issuer, kiểm tra thuật toán và header.
5. **Đọc claims đã được xác minh**, so khớp iss với issuer dự kiến và kiểm tra thời gian (exp/nbf; iat theo chính sách).
6. **Kiểm tra aud, kiểu token, scope/quyền, client hoặc các ràng buộc liên quan**, rồi áp dụng phân quyền nghiệp vụ và cách ly tenant.
7. Nếu có **sender-constrained token**, kiểm tra cnf và bằng chứng sở hữu khóa/chứng chỉ; nếu cần, kiểm tra nonce, jti của proof chống replay.
8. Xem xét **thu hồi**: JWT tự chứa không tự mất hiệu lực chỉ vì người dùng logout; dùng thời hạn sống, denylist, introspection hoặc chính sách riêng khi hệ thống yêu cầu.

~~~mermaid
flowchart TD
    A[Nhận JWT access token] --> B[Đọc iss để định tuyến, dữ liệu chưa xác thực]
    B --> C{iss có trong allowlist phù hợp?}
    C -- Không --> X[Từ chối]
    C -- Có --> D[Chọn cấu hình và JWKS của issuer đó]
    D --> E{Chữ ký, thuật toán và thời gian hợp lệ?}
    E -- Không --> X
    E -- Có --> F{iss đã xác thực khớp chính xác?}
    F -- Không --> X
    F -- Có --> G{aud và token type phù hợp?}
    G -- Không --> X
    G -- Có --> H{scope, tenant, binding và trạng thái hợp lệ?}
    H -- Không --> X
    H -- Có --> I[Cho phép nghiệp vụ tương ứng]
~~~

Việc định tuyến theo iss chưa xác thực **chỉ an toàn khi khóa lựa chọn được giới hạn vào allowlist đóng**. Một client có thể gửi iss giả để chọn cấu hình bất kỳ trong danh sách, nhưng nếu chữ ký không xác minh được bằng khóa của issuer đó thì phải bị từ chối.

### 5.2. Giả mã theo phong cách Java

~~~java
// Pseudocode: bỏ qua chi tiết xử lý ngoại lệ, HTTP và cấu hình thư viện.
final Map<String, TrustedIssuer> trusted = loadTrustedIssuersFromConfiguration();

AccessPrincipal verifyAccessToken(String rawJwt, ApiContext api) {
    String candidateIss = parseUnverifiedIssuerWithLimits(rawJwt);
    TrustedIssuer issuer = trusted.get(candidateIss);

    if (issuer == null || !api.allowsIssuer(issuer.identifier())) {
        throw unauthorized();
    }

    // Decoder có JWKS cố định theo issuer, thuật toán cho phép,
    // và validator issuer/thời gian. Không tải khóa theo jku trong JWT.
    VerifiedJwt jwt = issuer.decoder().verify(rawJwt);

    if (!issuer.identifier().equals(jwt.issuer())) {
        throw unauthorized();
    }
    if (!jwt.audience().contains(api.requiredAudience())) {
        throw unauthorized();
    }
    if (!api.acceptsAccessTokenType(jwt.tokenType())) {
        throw unauthorized();
    }
    if (!api.permissionsSatisfied(jwt.scopes())) {
        throw forbidden();
    }
    if (!api.tenantAllowsIssuerAndSubject(jwt.issuer(), jwt.subject())) {
        throw forbidden();
    }

    return new AccessPrincipal(jwt.issuer(), jwt.subject(), jwt.scopes());
}
~~~

Các kiểu **TrustedIssuer**, **VerifiedJwt** và hàm giả trong ví dụ có mục đích diễn giải, không phải API Java/Spring Security sẵn có. Với Spring Security, có thể dùng các **JwtDecoder** được tạo từ danh sách issuer đáng tin cậy rồi định tuyến tới decoder phù hợp; từng decoder vẫn cần validator dành cho **iss, aud, thời gian và token type** theo chính sách của API. Hãy kiểm tra chính xác validator mặc định của phiên bản thư viện đang chạy, đặc biệt phần **audience** và **token type**.

Một cấu hình chỉ có “signature valid” hoặc chỉ có “trusted issuer” là chưa đủ. Hệ thống cần đồng thời trả lời: **ai phát hành, ký bằng khóa nào, phát hành cho ai, còn hiệu lực hay không, và được phép làm gì**.

### 5.3. Với opaque token và token introspection

Opaque token không có payload JWT để đọc iss. Vì thế RS cần xác định **AS/introspection endpoint tin cậy** từ cấu hình, tuyến API hoặc ngữ cảnh ủy quyền phù hợp, rồi gọi endpoint đó bằng kênh và thông tin xác thực được bảo vệ.

Đối với phản hồi introspection (RFC 7662), **active = true chỉ cho biết đánh giá hiệu lực từ AS đã hỏi**. RS còn phải xác nhận đây là đúng AS mà API cho phép, rồi kiểm tra audience/resource, scope, client/subject, hạn dùng và ràng buộc khác theo metadata có sẵn. Không nên giả định mọi AS đều trả về claim iss trong phản hồi introspection; **danh tính của endpoint được xác thực** cũng là một phần của ranh giới tin cậy.

Nếu có nhiều AS:

- Không cho token opaque tự quyết định địa chỉ introspection thông qua đoạn text chưa xác thực.
- Không gửi mọi token nhận được đến một AS tùy ý để thử tới khi có active = true.
- Cần chính sách **rõ ràng** về AS nào có thể phát hành token cho API/tenant nào và cơ chế chọn endpoint không tạo đường vòng quyền truy cập.
- Cách ly cache kết quả introspection theo **AS, token identifier/digest và ngữ cảnh** liên quan; tránh dùng lại kết quả active của một AS cho issuer khác.

## 6. Xác minh OIDC ID token để tránh nhầm nhà cung cấp danh tính

Trong OIDC, **ID token** là JWT chứa thông tin xác thực phiên đăng nhập. OIDC client (relying party) cần xác minh:

1. **iss** đúng **issuer identifier** đã được dự kiến cho phiên đăng nhập.
2. Chữ ký theo **khóa tin cậy của đúng OP/issuer**, với thuật toán được cấu hình cho client.
3. **aud** chứa **client_id của chính ứng dụng**. Nếu có nhiều audience, kiểm tra các quy tắc liên quan đến **azp** theo OIDC.
4. **exp, iat**, và những điều kiện thời gian theo giao thức/chính sách.
5. **nonce** khi request dùng nonce và profile/flow yêu cầu; so khớp nonce với phiên đăng nhập đã lưu.
6. Các yêu cầu khác của flow tương ứng, chẳng hạn at_hash/c_hash khi áp dụng, cũng như ràng buộc kết quả với giao dịch ban đầu.

Ví dụ: client cho phép login bằng **OP_Corp** hoặc **OP_Partner**. Cả hai có thể phát hành ID token với **sub = 12345**. Nếu hệ thống chỉ lưu sub làm khóa tài khoản, người của Partner có thể bị ánh xạ nhầm sang tài khoản Corp.

Định danh ngoài hệ thống nên được lưu theo cặp:

~~~text
external_identity_key = (issuer, subject)

("https://corp-login.example.test", "12345")
    !=
("https://partner-login.example.test", "12345")
~~~

**Email** không phải khóa thay thế đáng tin cậy cho cặp (iss, sub). Hai OP có thể cung cấp cùng email, email có thể thay đổi và mức bảo đảm xác minh email khác nhau. **Account linking** giữa nhiều issuer nên là quy trình có xác thực và sự đồng ý thích hợp, không tự nối danh tính chỉ vì chuỗi email giống nhau.

Đừng dùng **ID token** để gọi resource server như access token chỉ vì nó có iss, chữ ký hợp lệ và claim sub. Audience của ID token thường dành cho OIDC client; resource server phải đòi access token hợp lệ cho API. Đây cũng là một dạng **token substitution/cross-JWT confusion**, khác với nhưng thường xuất hiện cùng issuer confusion.

## 7. Phòng chống authorization server mix-up trong OAuth client nhiều AS

### 7.1. Gắn giao dịch authorization với issuer dự kiến

Khi bắt đầu đăng nhập, client nên lưu một bản ghi giao dịch ở nơi có thể xác minh tính toàn vẹn, gắn với **state** và phiên trình duyệt phù hợp:

~~~json
{
  "state": "<RANDOM_OPAQUE_STATE>",
  "expected_issuer": "https://login.example.test/tenant-a",
  "authorization_endpoint": "https://login.example.test/tenant-a/authorize",
  "token_endpoint": "https://login.example.test/tenant-a/token",
  "redirect_uri": "https://app.example.test/oauth/callback/tenant-a",
  "code_verifier": "<PKCE_SECRET>",
  "nonce": "<OIDC_NONCE_IF_USED>",
  "expires_at": "<SHORT_LIVED_TRANSACTION_EXPIRY>"
}
~~~

Bản ghi trên là **minh họa cấu trúc dữ liệu phía client**. Không gửi code_verifier hoặc nonce bí mật ra client theo cách làm lộ chúng. State phải đủ ngẫu nhiên, khó đoán, liên kết với phiên và có vòng đời ngắn; một state hợp lệ không cho phép tự ý đổi issuer đã ghi từ trước.

Khi callback đến:

1. Đối chiếu **state** với giao dịch đang chờ và phiên hiện tại; từ chối nếu không khớp, hết hạn hoặc đã dùng.
2. Xác định **expected_issuer** từ giao dịch đã lưu, **không** lấy từ tham số issuer do request tùy ý cung cấp.
3. Nếu AS hỗ trợ **OAuth 2.0 Authorization Server Issuer Identification (RFC 9207)**, đọc tham số **iss** trong authorization response, giải mã theo quy tắc tham số giao thức và so sánh chính xác với expected_issuer.
4. Nếu thiếu hoặc sai iss trong luồng đã yêu cầu hỗ trợ RFC 9207, **từ chối trước khi đổi code**.
5. Trao đổi authorization code **chỉ với token endpoint đã gắn với issuer dự kiến** từ cấu hình tin cậy. Gửi đúng redirect_uri và PKCE code_verifier đã lưu.
6. Khi nhận token response, tiếp tục kiểm tra ID token/token theo issuer, audience, nonce, thời gian và các quy tắc OAuth/OIDC tương ứng.
7. Hoàn tất giao dịch chỉ một lần, dọn dữ liệu nhạy cảm và không ghi authorization code/token vào log.

~~~mermaid
flowchart TD
    A[Client bắt đầu login] --> B[Lưu state và expected_issuer]
    B --> C[Browser nhận authorization response]
    C --> D{state khớp giao dịch?}
    D -- Không --> X[Từ chối, dừng luồng]
    D -- Có --> E{iss response đúng expected_issuer?}
    E -- Không --> X
    E -- Có --> F[Gửi code tới token endpoint của issuer đã lưu]
    F --> G[Kiểm tra token/ID token từ issuer dự kiến]
    G --> H{Claims và binding hợp lệ?}
    H -- Không --> X
    H -- Có --> I[Hoàn tất đăng nhập]
~~~

**RFC 9207** giải quyết trường hợp AS có hỗ trợ tham số iss trong authorization response. Trong một hệ thống nhiều AS có AS không hỗ trợ, cần áp dụng biện pháp phòng chống mix-up khác được tiêu chuẩn chấp nhận, chẳng hạn **redirect URI khác biệt cho từng AS** và đối chiếu callback với issuer đã cấu hình. Chỉ dựa vào một callback chung và bỏ qua issuer vì “AS này không trả iss” là một rủi ro cần xử lý.

Nếu authorization response được bảo vệ bằng **JARM** hoặc flow OIDC cung cấp issuer trong response theo định dạng khác, việc kiểm tra issuer cần theo đúng đặc tả của cơ chế ấy. Không nhầm **iss trong JWT ID token nhận từ token endpoint sau đó** với bằng chứng issuer ở **authorization response trước khi gửi code**: nếu gửi code nhầm trước, kiểm tra ID token ở bước sau có thể đã quá muộn.

### 7.2. Vì sao state, PKCE và issuer identification phải đi cùng nhau?

| Cơ chế | Vấn đề chính giải quyết | Điều nó không tự giải quyết |
|---|---|---|
| **state** có ràng buộc phiên | CSRF và liên kết authorization response với giao dịch | Không tự chứng minh AS nào thực sự phát hành authorization response |
| **PKCE** | Giảm khả năng dùng authorization code bị chặn nếu không có code_verifier | Không thay thế ràng buộc issuer; gửi code và verifier đến nhầm endpoint vẫn là nguy cơ |
| **iss trong authorization response** (RFC 9207) | Xác định AS phát hành authorization response để chống mix-up | Không thay xác minh ID token, access token hay quyền |
| **Redirect URI riêng theo AS** | Giúp xác định luồng thuộc AS nào khi được cấu hình và kiểm tra đúng | Không thay kiểm tra token và các ràng buộc giao dịch |
| **nonce trong OIDC** | Ràng buộc ID token với yêu cầu xác thực có nonce | Không thay kiểm tra issuer trước khi đổi code |

Đây là các lớp kiểm tra bổ sung theo từng ranh giới tin cậy, không phải các lựa chọn “có một là đủ tất cả”.

## 8. Issuer confusion trong hệ thống đa tenant và đa môi trường

### 8.1. Tenant A và Tenant B chia sẻ API

Giả sử hệ thống có hai tenant:

~~~text
Issuer A: https://identity.example.test/tenant-a
Issuer B: https://identity.example.test/tenant-b

Cả hai đều có thể phát hành JWT với:
  sub = "u-100"
  aud = "billing-api"
~~~

Nếu API dùng duy nhất sub = u-100 để tìm hồ sơ, một người ở tenant B có thể bị ánh xạ vào tài khoản của tenant A. **Chữ ký JWT có thể hợp lệ**, iss có thể nằm trong allowlist toàn hệ thống và aud cũng có thể khớp, nhưng **phân quyền theo tenant vẫn sai**.

Định danh và kiểm tra nên có cấu trúc:

~~~text
principal = (iss, sub)
tenant_mapping = resolveAuthorizedTenant(iss, sub, trustedClaims)
resource_access = policyCheck(principal, tenant_mapping, resource.tenant)
~~~

Không tin tham số tenantId do client gửi để quyết định danh tính issuer nếu nó mâu thuẫn với token đã xác minh. Với API đa tenant, cần ràng buộc issuer, client, audience, tenant và quyền trên tài nguyên tùy theo mô hình nghiệp vụ.

### 8.2. Trộn issuer staging và production

Môi trường staging có thể dùng khóa thật, cùng tên audience hoặc tài khoản giả được cấp quyền cao. Nếu API production cho phép issuer staging vì “chung domain công ty”, staging token có thể hoạt động ngoài ý muốn trong production.

Khuyến nghị:

- Cấu hình allowlist issuer riêng cho **dev/staging/production**; kiểm tra cả audience riêng nếu có thể.
- Không tái sử dụng khóa riêng và secret giữa các môi trường.
- Không tự fallback sang issuer staging khi discovery/JWKS của production gặp lỗi.
- Kiểm tra cấu hình được triển khai và metadata thực tế, đặc biệt sau khi đổi domain, tenant hoặc nhà cung cấp danh tính.

### 8.3. Ứng dụng có nhiều client/OP

Một ứng dụng có thể đăng ký **client_id khác nhau cho mỗi OP**, mỗi bên với redirect URI, scope và thuật toán ký riêng. Không nên dùng một cấu hình “client chung” rồi mặc định ID token từ OP bất kỳ dùng được cho mọi phần của ứng dụng. Luồng đăng nhập cần giữ **(issuer, client_id, redirect_uri, transaction)** nhất quán, và tài khoản được ánh xạ từ (issuer, subject) sau khi xác minh.

## 9. Sai sót triển khai phổ biến và cách khắc phục

| Sai sót | Vì sao có thể bị khai thác | Cách sửa |
|---|---|---|
| Kiểm tra chữ ký JWT bằng khóa lấy từ URL trong iss/jku chưa xác thực | Token tự lựa chọn bên xác minh mình | Chỉ dùng JWKS đã cấu hình/được discovery từ issuer được phép |
| Chấp nhận mọi JWT có chữ ký hợp lệ từ bất kỳ IdP | Khóa của IdP lạ có thể ký token tự cấp quyền | Allowlists issuer có phạm vi theo API/client/tenant |
| So khớp iss bằng startsWith hoặc host chung | Cho phép lookalike domain hoặc tenant path khác | So sánh chính xác issuer identifier |
| Không kiểm tra aud | Token cấp cho client/API khác bị dùng chéo | Kiểm tra audience đích theo token type |
| Dùng kid làm cache key toàn cục | Hai issuer có thể dùng trùng kid | Scope khóa và cache theo issuer |
| Bỏ qua typ/token_use của token | Nhầm ID token hoặc refresh token với access token | Xác minh loại token theo profile/hợp đồng xác thực |
| Ánh xạ tài khoản chỉ theo sub/email | Có thể đụng định danh giữa các issuer | Khóa danh tính theo (iss, sub), account linking có kiểm soát |
| OAuth client đa AS chỉ kiểm tra state | Không chắc callback thực sự đến từ AS nào | RFC 9207 iss hoặc biện pháp chống mix-up phù hợp |
| Chọn token endpoint từ tham số callback | Có thể gửi authorization code đến nơi kẻ tấn công kiểm soát | Dùng endpoint đã ràng buộc với giao dịch tin cậy |
| Chỉ nhìn active = true khi introspection opaque token | Quên kiểm tra đúng AS/audience/tenant | Ràng buộc endpoint tin cậy và kiểm tra quyền, resource |
| Bỏ qua issuer do muốn “hỗ trợ migration” | Mở rộng tập nhà phát hành không kiểm soát | Kế hoạch migration issuer cụ thể, có thời hạn và giám sát |
| Xử lý lỗi bằng cách chấp nhận token “tạm thời” | Hạ cấp kiểm tra bảo mật khi AS/JWKS lỗi | Fail closed, cache khóa hợp lệ theo chính sách và cảnh báo |

## 10. Kiểm thử nhằm phát hiện issuer confusion

Hãy kiểm thử cả những trường hợp **chữ ký token hợp lệ** nhưng nguồn phát hành hoặc cách sử dụng sai. Chỉ thử “JWT bị sửa payload nên chữ ký sai” sẽ bỏ sót lớp lỗi issuer.

### 10.1. Các ca kiểm thử resource server

1. **Positive:** JWT từ issuer A, chữ ký do khóa A, aud đúng, còn hạn, scope đúng, tenant được phép → cho truy cập.
2. **Untrusted issuer:** JWT từ issuer B không nằm trong allowlist dù được B ký hợp lệ và aud đúng → từ chối.
3. **Spoofed iss:** token khai iss = A nhưng được ký bằng khóa B → từ chối.
4. **Malicious jku/x5u:** token khai URL JWKS do kẻ tấn công kiểm soát → không tự tải URL, từ chối nếu không có chữ ký hợp lệ từ A.
5. **kid collision:** issuer A và B có cùng kid nhưng khác khóa; decoder không dùng khóa của B cho token khai A.
6. **Wrong audience:** token từ A ký đúng nhưng aud dành cho inventory-api, không phải orders-api → từ chối.
7. **Wrong token type:** OIDC ID token dành cho client không được chấp nhận như access token của API.
8. **Missing issuer:** token thiếu iss trong profile yêu cầu issuer → từ chối.
9. **Issuer lookalike:** issuer có path tenant khác, dấu / khác hoặc domain mạo danh → từ chối.
10. **Cross-tenant subject:** (A, u-100) và (B, u-100) được phân biệt và không dùng chung quyền/tài nguyên.
11. **Environment isolation:** token từ staging không truy cập được resource server production.
12. **JWKS rotation:** khóa của A luân chuyển theo chính sách vẫn chỉ được chọn từ JWKS của A, không nới issuer allowlist.
13. **Opaque token:** introspection qua AS phù hợp, kiểm tra active và thông tin audience/scope; không chấp nhận do một AS khác báo active.

### 10.2. Các ca kiểm thử OAuth/OIDC client

1. Luồng login với AS_A có state và response issuer khớp → tiếp tục tới đúng token endpoint A.
2. Callback có **state A** nhưng **iss B** → từ chối **trước khi gọi token endpoint**.
3. Callback thiếu iss trong cấu hình yêu cầu RFC 9207 → từ chối.
4. Callback chứa state không tồn tại, hết hạn, dùng lại hoặc không thuộc phiên → từ chối.
5. Client không gửi code của A tới token endpoint B ngay cả khi có query parameter cố tình đổi issuer/token_endpoint.
6. Với AS không hỗ trợ response iss, xác minh cơ chế **redirect URI riêng theo AS** hoạt động và callback không bị tráo AS.
7. ID token của issuer B nhưng giao dịch dự kiến A → từ chối dù chữ ký B hợp lệ.
8. ID token đúng issuer nhưng aud khác client_id hoặc nonce không khớp → từ chối.
9. Hai OP cùng phát hành sub giống nhau → không đăng nhập nhầm tài khoản.
10. Error callback và token exchange failure không ghi code, code_verifier, ID token hay access token vào log.

**Gợi ý kiểm thử tích hợp:** dựng hai AS giả lập với issuer và JWKS tách biệt, hai JWT có cùng kid hoặc cùng sub, rồi quan sát xem request từ issuer không được phép có bị loại trước bước cấp quyền hay không. Với callback OAuth, ghi nhận số lần token endpoint được gọi để chứng minh rằng trường hợp **iss mismatch** không làm rò rỉ authorization code.

## 11. Giám sát, phản ứng sự cố và thiết kế log

Các sự kiện hữu ích:

- **token_issuer_untrusted:** token khai một issuer ngoài danh sách được phép.
- **token_issuer_mismatch:** iss trong token đã xác minh không khớp issuer đã chọn.
- **jwt_signature_invalid:** chữ ký không hợp lệ với khóa của issuer dự kiến.
- **token_audience_mismatch** hoặc **token_type_mismatch:** token phát hành sai đối tượng/kiểu sử dụng.
- **oauth_authorization_issuer_mismatch:** authorization response có iss khác issuer giao dịch.
- **oidc_id_token_issuer_mismatch:** ID token không đúng OP dự kiến.
- **cross_tenant_access_denied:** issuer/subject không được phép truy cập tenant đích.
- **trusted_issuer_configuration_changed:** thay đổi allowlist/metadata/JWKS được kiểm soát.

Log nên có mã sự kiện, timestamp, request/transaction ID, issuer **đã được phép hoặc giá trị issuer được xử lý an toàn**, API/audience, tenant định danh nội bộ và nguyên nhân từ chối. Giới hạn độ dài và ký tự lạ khi log một iss chưa xác thực để tránh log injection. **Không log raw token, authorization code, code_verifier, private key hay toàn bộ nội dung JWT.**

Nếu phát hiện API đã tin một issuer lạ, cần xác định khoảng thời gian lỗi cấu hình tồn tại, đánh giá token đã được chấp nhận, khóa truy cập hoặc phiên bị ảnh hưởng, sửa trust configuration, thu hồi khi có thể và rà soát dữ liệu. Với mix-up, cần kiểm tra khả năng authorization code hoặc PKCE verifier đã được gửi đến endpoint sai; các token phát hành sau đó có thể cần thu hồi theo chính sách. Một hệ thống chỉ kiểm tra JWT cục bộ có thể chưa thu hồi ngay access token đã cấp nếu thiếu denylist/introspection; cần lưu ý thời gian sống còn lại.

## 12. Những ngộ nhận cần tránh

**“JWT đã có chữ ký hợp lệ thì issuer tự nhiên đáng tin.”** Sai. Chữ ký chỉ có ý nghĩa khi xác thực bằng **khóa thuộc issuer được cho phép**; token do một IdP lạ ký vẫn có thể mang chữ ký hợp lệ.

**“iss là URL HTTPS nên có thể tin issuer đó.”** Sai. HTTPS chỉ bảo vệ kết nối tới máy chủ xác định, không cho phép một website bất kỳ tự gia nhập tập AS đáng tin cậy.

**“Chỉ cần kiểm tra aud.”** Sai. aud trả lời token cấp cho ai, còn iss xác định nhà phát hành. Cả hai đều cần đúng.

**“Hai issuer có cùng sub hoặc email thì là cùng một người.”** Sai. sub có phạm vi theo issuer; liên kết tài khoản đa OP cần quy trình đáng tin cậy riêng.

**“Có state và PKCE nên không thể gặp AS mix-up.”** Sai. state và PKCE là các cơ chế quan trọng nhưng không thay việc nhận diện AS phát hành **authorization response** trong client nhiều AS.

**“Có thể kiểm tra ID token iss sau khi đổi authorization code để chống mọi mix-up.”** Sai. Nếu code đã bị gửi đến token endpoint sai thì kiểm tra ở bước sau có thể không ngăn được rò rỉ.

**“Dùng cache JWKS toàn hệ thống chỉ cần kid là đủ.”** Sai. kid không duy nhất giữa issuer; khóa cần có ngữ cảnh issuer.

**“Opaque token không có iss nên không phải lo issuer confusion.”** Sai. Địa chỉ introspection, identity của AS trả lời và chính sách audience/tenant vẫn phải được xác minh.

## 13. Tự kiểm tra kiến thức

1. Vì sao một JWT có iss đúng và chữ ký **hợp lệ theo khóa của kẻ tấn công** vẫn không được chấp nhận?
2. Kiểm tra iss khác với kiểm tra aud và scope ở điểm nào?
3. Trong một API đa tenant, vì sao subject chỉ nên được ánh xạ theo **(issuer, subject)**?
4. Lấy JWKS URL từ header jku chưa xác thực tạo ra nguy cơ gì?
5. OAuth client hỗ trợ nhiều AS có thể làm lộ authorization code như thế nào khi bị mix-up?
6. Tham số **iss trong authorization response** của RFC 9207 giúp chặn lỗi ở thời điểm nào?
7. Vì sao kiểm tra ID token sau khi gọi token endpoint có thể quá muộn để ngăn mix-up?
8. Với opaque token, làm sao RS biết phản hồi introspection đến từ AS được tin cậy?
9. Cần thiết kế kiểm thử gì để phát hiện cùng một kid được hai issuer sử dụng?
10. Vì sao issuer staging có chữ ký hợp lệ không nên được API production chấp nhận?

**Ghi nhớ:** Một token hoặc authorization response chỉ có giá trị trong **ngữ cảnh issuer được xác định từ nguồn tin cậy**. Hãy ràng buộc issuer vào giao dịch trước khi đổi code, xác minh JWT bằng khóa của đúng issuer, so khớp iss và aud, kiểm tra token type/scope, rồi áp dụng cách ly tenant và phân quyền trên tài nguyên. Khi có nhiều AS hoặc OP, chính những ràng buộc ngữ cảnh này quyết định việc hệ thống có chống được issuer confusion hay không.

## Tài liệu tham khảo

- **RFC 7519 — JSON Web Token (JWT):** định nghĩa claim iss, sub, aud và claims JWT.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** metadata của authorization server và issuer identifier.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** xác định AS phát hành authorization response để phòng chống mix-up.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo mật OAuth, đặc biệt bảo vệ client dùng nhiều AS khỏi mix-up.
- **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens:** cấu trúc và kiểm tra JWT access token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** xác thực trạng thái và metadata của opaque token.
- **OpenID Connect Core 1.0 và OpenID Connect Discovery 1.0:** xác minh ID token, issuer và metadata OpenID Provider.


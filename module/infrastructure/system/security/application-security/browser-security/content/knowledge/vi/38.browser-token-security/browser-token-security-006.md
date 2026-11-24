# Token audience: giới hạn token cho đúng API nhận

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích audience (aud) là định danh resource server mà token được phát hành để sử dụng.
2. Phân biệt aud với issuer, subject, client_id, scope và authorized party.
3. Phân biệt audience của OAuth access token với audience của OpenID Connect ID token.
4. Kiểm tra aud dạng chuỗi hoặc mảng và so khớp chính xác với resource identifier đã cấu hình.
5. Hiểu rủi ro token substitution, token forwarding và confused deputy khi nhiều API dùng chung token.
6. Thiết kế việc cấp token theo từng resource bằng resource indicator và chính sách của authorization server.
7. Xác minh audience cùng chữ ký, issuer, thời hạn, loại token và các claim bắt buộc.
8. Xử lý cả JWT access token và opaque access token qua introspection.
9. Hiểu giới hạn của audience trong browser: aud giảm phạm vi sử dụng token nhưng không ngăn XSS đánh cắp hoặc sử dụng token tại đúng API.
10. Kiểm thử token đúng/sai audience và theo dõi lỗi an toàn trong môi trường staging.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Trong bảo mật token phía browser, audience giúp giới hạn resource server được phép chấp nhận token, qua đó giảm nguy cơ một token phát hành cho API này bị dùng nhầm hoặc bị chuyển tiếp sang API khác.

## 1. Audience giải quyết vấn đề gì?

Một hệ thống thường có nhiều API:

    Browser application
          |
          +------> Orders API
          |
          +------> Billing API
          |
          +------> Profile API

Người dùng đăng nhập một lần có thể nhận access token để gọi nhiều dịch vụ. Nếu mọi API đều chấp nhận cùng một token mà không kiểm tra token được phát hành cho ai, token có thể bị dùng ở nơi ngoài mục đích ban đầu.

Ví dụ:

1. Browser lấy access token để đọc đơn hàng.
2. Token bị gửi nhầm tới Billing API do cấu hình frontend hoặc gateway sai.
3. Billing API chỉ kiểm tra chữ ký và thời hạn, không kiểm tra audience.
4. Billing API có thể chấp nhận token vốn chỉ dành cho Orders API.

Audience claim giải quyết ranh giới người nhận: token phải chỉ rõ resource server hoặc nhóm resource server được phép chấp nhận nó. Mỗi API kiểm tra token có audience phù hợp với chính API đó hay không.

### Audience không phải quyền thao tác

Audience trả lời:

**Token này được phát hành cho resource server nào?**

Scope trả lời:

**Token này được phép thực hiện những hành động nào trong resource?**

Ví dụ:

    aud   = https://orders-api.example.test
    scope = orders.read orders.write

Token được dành cho Orders API, với các quyền đọc và ghi đơn hàng. Billing API không nên chấp nhận token đó chỉ vì token có chữ ký hợp lệ hoặc chứa một scope tên gần giống.

## 2. Những claim cần phân biệt

Các claim thường xuất hiện trong token có ý nghĩa khác nhau:

| Claim | Ý nghĩa | Câu hỏi được trả lời |
| --- | --- | --- |
| iss | Issuer, bên phát hành token | Ai phát hành token? |
| sub | Subject, chủ thể mà token nói tới | Token đại diện cho ai hoặc thực thể nào? |
| aud | Audience, resource server/người nhận dự kiến | Token dành cho ai nhận? |
| client_id | OAuth client đã yêu cầu hoặc được gắn với token | Ứng dụng client nào yêu cầu token? |
| scope | Tập quyền hoặc hành động được cấp | Token được làm gì? |
| exp | Thời điểm hết hạn | Token còn hiệu lực về thời gian không? |
| nbf | Thời điểm bắt đầu có hiệu lực | Token đã được phép sử dụng chưa? |
| iat | Thời điểm phát hành | Token được tạo khi nào? |
| jti | Mã định danh token | Có thể nhận diện token cụ thể nào? |
| azp | Authorized party trong ngữ cảnh OpenID Connect | Bên nào được ủy quyền sử dụng ID token? |

Không dùng một claim để thay thế claim khác. Một token có sub hợp lệ và scope phù hợp vẫn phải bị từ chối nếu aud không dành cho API nhận request.

### Audience khác origin của browser

Origin là bộ ba scheme, host và port của document browser:

    https://app.example.test

Audience là định danh resource server do authorization server và API thống nhất:

    https://orders-api.example.test

Hai giá trị có thể trùng hoặc khác nhau tùy kiến trúc. Audience cũng có thể là một URI identifier không phải URL người dùng mở trực tiếp. Không suy luận aud từ window.location.origin và không tự tạo audience bằng cách nối chuỗi hostname.

API phải dùng resource identifier canonical đã cấu hình, so sánh theo đúng quy ước của issuer. Không tự lowercase, bỏ slash cuối hoặc chuẩn hóa URI tùy tiện nếu hệ thống phát hành token không định nghĩa phép chuẩn hóa đó.

## 3. aud trong JWT có dạng gì?

Theo JSON Web Token (JWT), aud có thể là một StringOrURI hoặc một mảng StringOrURI:

    {
      "iss": "https://identity.example.test/",
      "sub": "user-123",
      "aud": "https://orders-api.example.test",
      "exp": 1790000000
    }

Hoặc:

    {
      "iss": "https://identity.example.test/",
      "sub": "user-123",
      "aud": [
        "https://orders-api.example.test",
        "https://reporting-api.example.test"
      ],
      "exp": 1790000000
    }

Trong JWT, giá trị audience có tính phân biệt chữ hoa/chữ thường theo quy tắc StringOrURI. API cần so khớp với identifier đã đăng ký và được cấu hình chính xác.

### Audience dạng chuỗi

Nếu aud là chuỗi:

    "aud": "https://orders-api.example.test"

Orders API chỉ chấp nhận khi giá trị này bằng audience kỳ vọng của nó.

### Audience dạng mảng

Nếu aud là mảng, token được định danh cho các audience được liệt kê. Resource server có thể kiểm tra audience của chính mình có nằm trong tập đó hay không, theo profile token và chính sách hệ thống.

Tuy nhiên, mảng audience rộng làm tăng số resource server có thể sử dụng cùng token. Ưu tiên token dành riêng cho từng API nếu kiến trúc cho phép. Chỉ phát hành multi-audience token khi có lý do rõ ràng và mọi resource server trong danh sách đều được tin cậy ở cùng mức cần thiết.

### JWT chung và JWT access token profile

Trong JWT tổng quát, aud không phải claim bắt buộc cho mọi loại JWT. Nhưng access token profile hoặc hợp đồng token của hệ thống có thể yêu cầu aud. Ví dụ JWT Profile for OAuth 2.0 Access Tokens (RFC 9068) yêu cầu audience trong access token theo profile đó.

API không được tự bỏ qua aud chỉ vì thư viện JWT cho phép claim này vắng mặt. Hãy xác định profile token được chấp nhận và từ chối token thiếu audience khi profile yêu cầu.

## 4. Access token và ID token có audience khác nhau

Đây là điểm rất quan trọng trong hệ thống dùng OpenID Connect.

### Audience của access token

Access token được cấp để client gọi resource server. Vì vậy, aud xác định API hoặc resource mà access token dành cho.

Ví dụ:

    {
      "iss": "https://identity.example.test/",
      "sub": "user-123",
      "aud": "https://orders-api.example.test",
      "client_id": "shop-web",
      "scope": "orders.read",
      "exp": 1790000000
    }

Orders API là resource server nhận token và phải kiểm tra audience của mình.

### Audience của ID token

ID token được authorization server phát hành cho OpenID Connect client để client xác minh danh tính người dùng. Trong ID token, aud phải chứa client_id của OIDC client nhận token theo quy tắc OpenID Connect.

Ví dụ:

    {
      "iss": "https://identity.example.test/",
      "sub": "user-123",
      "aud": "shop-web",
      "exp": 1790000000
    }

Ở đây shop-web là client ứng dụng, không phải Orders API.

### Không gửi ID token tới API như access token

ID token và access token phục vụ hai mục đích khác nhau:

| Đặc điểm | ID token | Access token |
| --- | --- | --- |
| Người nhận | OIDC client | Resource server/API |
| Audience thường là | client_id | Resource identifier/API |
| Mục đích | Xác nhận kết quả đăng nhập và thông tin xác thực người dùng | Cho phép truy cập resource theo quyền được cấp |
| Dùng làm bearer credential gọi API | Không | Có, theo token profile |

Nếu API chấp nhận ID token chỉ vì chữ ký hợp lệ, API có thể bị token substitution. Kẻ tấn công có thể đưa token được phát hành cho client vào API mà API không phải người nhận dự kiến.

Resource server phải xác định rõ loại access token được chấp nhận, kiểm tra audience resource và các claim theo profile. Không dùng ID token thay access token.

### azp không thay thế aud

Trong OpenID Connect, azp (authorized party) chỉ ra client được ủy quyền sử dụng ID token trong một số tình huống. Khi ID token có nhiều audience, client cần áp dụng các quy tắc kiểm tra azp của OpenID Connect.

azp không phải claim audience của API. Không dùng azp để bỏ qua kiểm tra aud và không coi client_id là resource server.

## 5. Scope, role và audience phối hợp thế nào?

Một access token hợp lệ cần đồng thời đúng người nhận và đúng quyền.

Ví dụ:

    {
      "iss": "https://identity.example.test/",
      "sub": "user-123",
      "aud": "https://orders-api.example.test",
      "scope": "orders.read",
      "exp": 1790000000
    }

Orders API kiểm tra:

1. Token được phát hành bởi issuer tin cậy.
2. Chữ ký hợp lệ và thuật toán được phép.
3. Audience chứa đúng Orders API.
4. Token còn hiệu lực và chưa tới thời điểm nbf.
5. Loại token đúng với access token profile của API.
6. Scope có orders.read.
7. User có quyền đọc đúng đơn hàng cụ thể.

Audience không tự cấp orders.read. Scope cũng không khiến token dành cho Billing API trở thành token hợp lệ cho Orders API.

### Ví dụ ma trận audience và scope

| Token | Audience | Scope | Orders API |
| --- | --- | --- | --- |
| A | Orders API | orders.read | Chấp nhận cho thao tác đọc nếu các kiểm tra khác đạt |
| B | Orders API | orders.write | Chấp nhận cho thao tác ghi nếu các kiểm tra khác đạt |
| C | Billing API | orders.read | Từ chối vì sai audience |
| D | Orders API | billing.pay | Không đủ quyền cho thao tác đọc/ghi đơn hàng |
| E | Orders API | orders.read | Vẫn từ chối nếu token hết hạn hoặc chữ ký sai |

Sau khi xác minh token, backend vẫn cần kiểm tra ownership, tenant và policy ở cấp đối tượng. Scope orders.read không tự cho phép user đọc đơn hàng của tenant khác.

## 6. Audience restriction khi cấp token

Audience phải được quyết định ở authorization server hoặc token issuer dựa trên resource mà client được phép truy cập.

### Resource indicator

OAuth 2.0 Resource Indicators (RFC 8707) định nghĩa tham số resource để client chỉ rõ resource server mà nó muốn lấy token.

Ví dụ request tới authorization server:

    POST /oauth/token
    Content-Type: application/x-www-form-urlencoded

    grant_type=authorization_code
    &code=AUTHORIZATION_CODE
    &redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback
    &client_id=shop-web
    &resource=https%3A%2F%2Forders-api.example.test

Authorization server kiểm tra resource có được đăng ký hoặc được policy cho phép hay không. Server sau đó có thể phát token với audience tương ứng.

Không được mù quáng copy giá trị resource do client gửi thành aud. Issuer phải xác minh resource identifier, client được phép yêu cầu resource đó và user consent/scope tương ứng.

### Token riêng cho từng API

Ví dụ client cần gọi Orders và Billing:

    Token A:
      aud = https://orders-api.example.test
      scope = orders.read

    Token B:
      aud = https://billing-api.example.test
      scope = invoices.read

Frontend hoặc BFF phải gửi đúng token đến đúng API. Nếu gửi Token A tới Billing API, Billing API từ chối do audience không khớp.

Token riêng theo resource giảm tác động nếu một API bị cấu hình sai hoặc token bị lộ ở một luồng tích hợp.

### Gửi token tới đúng API từ browser

Ví dụ gửi access token tới đúng API qua Authorization header:

    const response = await fetch(
      "https://orders-api.example.test/api/orders",
      {
        headers: {
          Authorization: "Bearer " + ordersAccessToken
        }
      }
    );

Không đưa token vào query string, fragment, URL điều hướng hoặc tên resource. Không log Authorization header trong frontend. Browser DevTools vẫn có thể hiển thị request của người dùng đang kiểm thử; vì vậy chỉ dùng token test khi debug và không chia sẻ ảnh/chụp log chứa credential.

### Không dùng audience quá rộng

Ví dụ:

    "aud": [
      "https://orders-api.example.test",
      "https://billing-api.example.test",
      "https://admin-api.example.test"
    ]

Token này có thể được chấp nhận bởi nhiều resource server. Nếu một API ít bảo vệ hơn bị xâm nhập, token rộng có thể làm tăng phạm vi ảnh hưởng.

Chỉ dùng multi-audience khi các resource thực sự cần cùng token và có trust boundary tương đương. Không đưa admin API vào audience chỉ để giảm số lần xin token.

## 7. Resource server phải xác minh audience

Mỗi API cần biết audience identifier chính xác của chính nó. Giá trị này lấy từ cấu hình tin cậy, không lấy từ request hoặc từ claim chưa xác minh.

Ví dụ cấu hình:

    EXPECTED_ISSUER=https://identity.example.test/
    EXPECTED_AUDIENCE=https://orders-api.example.test

Luồng xử lý:

    Nhận Authorization: Bearer <token>
                 |
                 v
    Xác minh định dạng và token profile
                 |
                 v
    Xác minh chữ ký bằng key tin cậy
                 |
                 v
    Kiểm tra issuer, audience, thời hạn, token type
                 |
                 v
    Kiểm tra scope/role và quyền object
                 |
                 v
    Cho phép hoặc từ chối request

Không giải mã JWT rồi tin claim ngay. Payload JWT chỉ là dữ liệu được mã hóa Base64URL, không phải bằng chứng tính xác thực. Phải xác minh chữ ký hoặc dùng cơ chế introspection đáng tin cậy trước khi tin claim.

JWT ký (JWS) không đồng nghĩa với JWT mã hóa. Payload của access token thường có thể được đọc bởi bất kỳ ai có token. Không đưa password, private key, dữ liệu thanh toán hoặc bí mật nội bộ vào claim với giả định rằng chữ ký sẽ che giấu nội dung.

### Kiểm tra aud chính xác

Pseudo-code:

    function hasExpectedAudience(aud, expectedAudience) {
      if (typeof aud === "string") {
        return aud === expectedAudience;
      }

      if (Array.isArray(aud)) {
        return aud.some((value) =>
          typeof value === "string" &&
          value === expectedAudience
        );
      }

      return false;
    }

Hàm này chỉ minh họa phép kiểm tra audience. Nó không xác minh chữ ký, issuer, thời hạn hoặc token type. Không dùng riêng hàm này để xác thực JWT.

### Không chuẩn hóa audience tùy tiện

Tránh:

- Chỉ so sánh hostname rồi bỏ qua scheme hoặc port.
- Dùng endsWith() hoặc contains().
- Bỏ slash cuối nếu issuer không quy định.
- Tự decode và sửa claim trước khi xác minh chữ ký.
- Chấp nhận mọi aud nếu claim thiếu.
- Dùng audience lấy từ query parameter hoặc request header làm giá trị kỳ vọng.

Audience là định danh có ngữ nghĩa do issuer và resource server thống nhất. So sánh theo exact identifier.

## 8. Xác minh JWT đầy đủ, không chỉ aud

Audience chỉ là một bước trong validation. Resource server cần kiểm tra token theo profile đã thống nhất.

Các bước thường gồm:

1. Chỉ chấp nhận thuật toán chữ ký trong allowlist cấu hình.
2. Xác minh chữ ký bằng public key thuộc issuer tin cậy.
3. Kiểm tra iss chính xác.
4. Kiểm tra aud có chứa resource identifier kỳ vọng.
5. Kiểm tra exp và nbf với clock skew nhỏ, có giới hạn.
6. Kiểm tra token type/profile, ví dụ JWT access token theo RFC 9068.
7. Kiểm tra claim bắt buộc như client_id, sub, iat hoặc jti nếu profile yêu cầu.
8. Kiểm tra scope/role.
9. Kiểm tra quyền trên tài nguyên cụ thể.

### Không tin key URL từ token

Không tự động tải key từ jku hoặc x5u do token header tùy ý chỉ định. Lấy JWKS từ issuer đã cấu hình hoặc metadata đã xác minh. Kiểm tra kid trong tập key tin cậy và từ chối khi không tìm được key phù hợp.

### Algorithm allowlist

Không để token tự quyết định thuật toán được chấp nhận. Cấu hình rõ thuật toán phù hợp với issuer, không chấp nhận alg=none và tránh algorithm confusion giữa HMAC và asymmetric signature.

### Token type và substitution

Nếu API chấp nhận JWT access token theo RFC 9068, kiểm tra profile và typ theo yêu cầu, thường là at+jwt ở JOSE header. Token type là một phần của validation; nó không thay thế audience.

Không chấp nhận một JWT bất kỳ chỉ vì issuer ký hợp lệ. Một issuer có thể phát hành nhiều loại JWT cho nhiều mục đích khác nhau.

## 9. Opaque access token và introspection

Không phải access token nào cũng là JWT. Authorization server có thể phát hành opaque token, tức chuỗi không mang claim JWT mà resource server không thể tự giải mã.

Ví dụ:

    Authorization: Bearer 7c3f...opaque-value

Resource server có thể gọi introspection endpoint theo RFC 7662 qua kênh server-to-server được xác thực:

    POST /oauth/introspect
    Content-Type: application/x-www-form-urlencoded

    token=OPAQUE_ACCESS_TOKEN

Response minh họa:

    {
      "active": true,
      "iss": "https://identity.example.test/",
      "sub": "user-123",
      "aud": ["https://orders-api.example.test"],
      "client_id": "shop-web",
      "scope": "orders.read",
      "exp": 1790000000
    }

Resource server phải kiểm tra active, audience và các trường cần thiết theo hợp đồng với issuer. Không trả introspection credential cho browser và không gọi introspection trực tiếp từ SPA.

Nếu authorization server không trả aud, resource server cần một hợp đồng khác đã được xác minh để biết token dành cho resource nào. Không tự suy ra audience từ việc token đang được gửi tới endpoint.

### Cache introspection

Có thể cache kết quả introspection trong thời gian ngắn để giảm tải, nhưng phải cân bằng với khả năng revoke token. Cache dài làm chậm hiệu lực thu hồi. Với thao tác nhạy cảm, cân nhắc revalidation hoặc TTL ngắn theo threat model.

## 10. Token forwarding và confused deputy

Một lỗi phổ biến trong kiến trúc nhiều API là service A nhận token dành cho A rồi chuyển tiếp token đó tới service B.

Ví dụ:

    Browser
       |
       | token aud=orders-api
       v
    Orders API
       |
       | forward nguyên token
       v
    Billing API

Billing API phải từ chối vì token không dành cho Billing API.

### Vì sao forwarding nguy hiểm?

- Token có thể mang scope rộng hơn service B cần.
- Service B có thể vô tình chấp nhận token không dành cho nó.
- Service A có thể trở thành confused deputy, dùng quyền của user ở sai resource.
- Log hoặc tracing ở nhiều service làm tăng nơi token có thể bị lộ.
- Khi token bị đánh cắp, phạm vi ảnh hưởng lớn hơn nếu nhiều API cùng chấp nhận.

### Cách xử lý đúng

Khi Orders API cần gọi Billing API:

1. Orders API xác thực request và user context.
2. Backend xin token mới dành cho Billing API qua client credentials, token exchange hoặc cơ chế delegation phù hợp.
3. Authorization server kiểm tra policy và phát token có aud là Billing API.
4. Billing API xác minh issuer, audience và quyền.
5. Service chỉ chuyển tiếp context tối thiểu cần thiết, không chuyển nguyên bearer token nếu token đó không dành cho resource đích.

OAuth Token Exchange (RFC 8693) có thể dùng trong một số kiến trúc để đổi token theo actor/subject và resource đích. Việc exchange vẫn phải có policy rõ ràng; không phải cơ chế tự động biến token thành quyền cao hơn.

## 11. Audience và browser application

Browser thường không tự xác minh token để quyết định quyền truy cập thật. Resource server mới là nơi thực thi audience validation.

### SPA gọi nhiều API

Một SPA có thể cần token cho nhiều resource:

    SPA
      |
      +-- token for Orders API --> Orders API
      |
      +-- token for Billing API --> Billing API

Client nên yêu cầu token đúng resource theo authorization server hỗ trợ. Không lấy token của API A rồi dùng cho API B.

Frontend có thể đọc claim để hiển thị trạng thái hoặc hỗ trợ UX, nhưng không được coi việc decode aud ở JavaScript là bằng chứng token hợp lệ. Người dùng có thể sửa code client, và payload chưa xác minh không đáng tin cậy. Resource server phải tự xác minh token và audience trên mọi request.

### Audience không bảo vệ token khỏi XSS

Nếu XSS đánh cắp token dành cho Orders API, audience vẫn hợp lệ tại Orders API. Audience chỉ khiến Billing API từ chối token đó; nó không ngăn attacker sử dụng token tại resource được chỉ định.

Các lớp giảm rủi ro khác:

- Ngăn XSS bằng output encoding, CSP và Trusted Types.
- Hạn chế token có thời hạn ngắn và scope tối thiểu.
- Tránh lưu bearer token lâu dài trong localStorage/sessionStorage.
- Cân nhắc Backend-for-Frontend (BFF) giữ token phía server và dùng cookie session HttpOnly, Secure, SameSite phù hợp.
- Với SPA cần gọi API trực tiếp, giữ token trong memory khi có thể và giảm thời gian tồn tại.
- Dùng sender-constrained token như DPoP khi kiến trúc và browser client hỗ trợ.

Giữ token trong memory giảm thời gian lưu bền vững nhưng XSS đang chạy vẫn có thể đọc token hoặc gọi API thay người dùng. BFF cũng không thay thế phòng XSS và CSRF.

### Audience không phải CORS

Hai cơ chế kiểm soát khác nhau:

| Cơ chế | Câu hỏi |
| --- | --- |
| CORS | JavaScript từ origin nào được browser cho đọc response cross-origin? |
| Token audience | Resource server nào được phép chấp nhận token? |

API có thể cho phép CORS từ app.example.test nhưng vẫn phải từ chối access token sai audience. Ngược lại, token đúng audience không làm browser tự cho phép JavaScript đọc response nếu CORS không hợp lệ.

Không dùng CORS thay audience validation, và không dùng aud thay authorization hoặc CORS.

## 12. Sender-constrained token và giới hạn của audience

Audience restriction giới hạn resource server nhận token, nhưng bearer token vẫn có thể được người khác sử dụng nếu bị đánh cắp và gửi tới đúng resource server.

Với bearer token:

- Ai sở hữu token có thể thử dùng token trong thời gian token còn hiệu lực.
- Resource server kiểm tra chữ ký/audience/scope nhưng không nhất thiết biết người gửi có phải client ban đầu hay không.

### DPoP

Demonstrating Proof of Possession (DPoP) ràng buộc token với một public key của client. Client gửi DPoP proof cho request; resource server xác minh proof và binding tương ứng.

Trong token có thể có claim cnf chứa thumbprint của key. Resource server phải xác minh DPoP proof theo RFC 9449, gồm method, URI, thời gian, jti, access-token hash khi áp dụng và nonce nếu server yêu cầu.

DPoP không thay audience. Token vẫn phải dành cho đúng resource server. DPoP cũng không ngăn XSS đang chạy trong browser sử dụng key hoặc thực hiện request thay người dùng nếu attacker kiểm soát execution context.

### Mutual TLS

Với client có khả năng quản lý certificate, OAuth mTLS có thể ràng buộc token với certificate của client. Resource server kiểm tra certificate phù hợp với confirmation claim.

Đây thường là lựa chọn cho backend/service hoặc môi trường quản lý thiết bị; không phải giải pháp mặc định cho mọi browser SPA.

### Kết hợp các lớp

    Token validation:
      signature + issuer + audience + time + type + scope
                         |
                         v
      sender constraint (DPoP hoặc mTLS nếu dùng)
                         |
                         v
      authorization theo user, tenant và object

Mỗi lớp xử lý một loại rủi ro khác nhau. Không bỏ qua audience chỉ vì đã dùng DPoP hoặc mTLS.

## 13. Lỗi audience và phản hồi API

Khi token không dành cho resource server hiện tại, API phải từ chối request.

Ví dụ:

    HTTP/1.1 401 Unauthorized
    WWW-Authenticate: Bearer error="invalid_token"

Không trả chi tiết nhạy cảm như danh sách audience nội bộ, tên service chưa công khai hoặc claim của token trong response client.

### Phân biệt 401 và 403

| Trường hợp | Phản hồi thường dùng |
| --- | --- |
| Token thiếu, sai chữ ký, hết hạn hoặc sai audience | 401 Unauthorized, invalid_token |
| Token hợp lệ cho API nhưng thiếu scope/quyền | 403 Forbidden, insufficient_scope hoặc lỗi authorization phù hợp |
| User không có quyền với object cụ thể | 403 hoặc 404 theo chính sách chống dò tìm tài nguyên |

Không tiết lộ lý do chi tiết cho attacker. Log nội bộ có thể ghi mã nguyên nhân như invalid_audience, invalid_issuer hoặc insufficient_scope mà không ghi token thô.

### Không redirect token sai audience

Không tự động chuyển token sai audience tới một API khác hoặc thử nhiều audience cho tới khi một API chấp nhận. Điều đó che giấu lỗi routing và có thể tạo token confusion.

Client cần yêu cầu token đúng resource từ authorization server.

## 14. Logging và xử lý token an toàn

Audience validation giúp xác định resource nhận token, nhưng log và telemetry vẫn có thể làm lộ token.

Không ghi:

- Authorization header nguyên vẹn.
- JWT hoặc opaque token.
- Refresh token, DPoP private key hoặc client secret.
- Ticket tạm thời có thể dùng để xác thực.
- Query string chứa credential.

Có thể ghi metadata tối thiểu:

- Kết quả validation.
- Mã lỗi như invalid_audience.
- Issuer identifier đã cấu hình.
- Resource server identifier nội bộ.
- Client ID hoặc subject dạng pseudonymous theo chính sách log.
- JTI hoặc fingerprint token nếu có nhu cầu điều tra và kiểm soát retention.
- Correlation ID của request.

JTI và fingerprint vẫn có thể liên kết hoạt động của người dùng; chỉ lưu khi có mục đích, giới hạn truy cập và thời hạn retention.

Khi phát hiện token gửi nhầm API:

1. Từ chối token tại resource server nhận sai audience.
2. Xác định client, service hoặc gateway đã gửi sai token.
3. Kiểm tra token có bị API sai audience chấp nhận do thiếu validation hay không.
4. Nếu token có khả năng bị lộ, revoke hoặc chờ hết hạn theo khả năng của issuer.
5. Sửa resource mapping và token acquisition.
6. Kiểm tra log/APM có lưu token thô không và redaction nếu cần.
7. Thêm regression test cho API nhận token sai audience.

## 15. Ví dụ kiểm tra audience trong API

Pseudo-code cho resource server:

    const expectedIssuer = "https://identity.example.test/";
    const expectedAudience = "https://orders-api.example.test";

    async function authenticateRequest(request) {
      const token = readBearerToken(request);
      if (!token) {
        throw unauthorized("missing_token");
      }

      const verified = await verifyJwtSignature(token, {
        trustedIssuer: expectedIssuer,
        allowedAlgorithms: ["RS256"]
      });

      const claims = verified.payload;

      if (claims.iss !== expectedIssuer) {
        throw unauthorized("invalid_issuer");
      }

      if (!hasExpectedAudience(claims.aud, expectedAudience)) {
        throw unauthorized("invalid_audience");
      }

      if (!isValidTimeWindow(claims.exp, claims.nbf)) {
        throw unauthorized("invalid_token_time");
      }

      if (verified.header.typ !== "at+jwt") {
        throw unauthorized("invalid_token_type");
      }

      return claims;
    }

Đây là pseudo-code, không phải thư viện JWT hoàn chỉnh. Hàm verifyJwtSignature phải xác minh chữ ký bằng JWKS tin cậy, xử lý kid, issuer và thuật toán theo cấu hình. isValidTimeWindow phải xử lý exp/nbf theo profile, clock skew nhỏ và claim bắt buộc. Kiểm tra typ at+jwt chỉ phù hợp khi issuer phát hành theo JWT access token profile tương ứng; không áp dụng máy móc cho mọi access token.

Sau authenticateRequest(), middleware authorization tiếp tục kiểm tra scope, role, tenant và quyền đối với object.

### Không tự viết thuật toán JWT

Trong production:

- Dùng thư viện JWT/OAuth đã được duy trì.
- Cấu hình issuer và JWKS endpoint tin cậy ngoài token.
- Khóa thuật toán theo cấu hình.
- Kiểm tra đầy đủ claim theo profile.
- Xử lý key rotation và cache JWKS an toàn.
- Không log token thô khi có exception.

## 16. Thực hành kiểm thử audience

Chỉ sử dụng token giả hoặc token test trong môi trường local/staging. Không dán access token thật vào website debug JWT công khai hoặc chia sẻ token qua chat/log.

### Bước 1 — Chuẩn bị hai resource server

Tạo hai API test:

    Orders API:
      expectedAudience = https://orders-api.example.test

    Billing API:
      expectedAudience = https://billing-api.example.test

Dùng cùng issuer test nhưng audience khác nhau.

### Bước 2 — Lấy token cho Orders API

Yêu cầu authorization server cấp token cho resource Orders API bằng cơ chế resource indicator hoặc mapping đã cấu hình.

Kiểm tra payload sau khi token đã được xác minh trong môi trường test:

    aud = https://orders-api.example.test
    scope = orders.read

### Bước 3 — Gọi đúng API

Gửi token tới Orders API:

    GET /api/orders
    Authorization: Bearer ORDERS_TEST_TOKEN

Kết quả mong đợi: token được chấp nhận nếu chữ ký, issuer, thời hạn, token type, scope và quyền object đều hợp lệ.

### Bước 4 — Gửi nhầm sang Billing API

Gửi cùng token tới Billing API:

    GET /api/invoices
    Authorization: Bearer ORDERS_TEST_TOKEN

Kết quả mong đợi: Billing API trả 401 invalid_token do audience không khớp. Không được tự fallback sang Orders API hoặc bỏ qua aud.

### Bước 5 — Kiểm tra ID token substitution

Dùng ID token của OIDC client test gọi Orders API.

Kết quả mong đợi: Orders API từ chối vì ID token không phải access token dành cho Orders resource. Kiểm tra cả token type/profile và audience.

### Bước 6 — Kiểm tra negative cases

- aud bị thiếu.
- aud là chuỗi sai.
- aud là mảng không chứa API hiện tại.
- aud chứa nhiều resource không được policy cho phép.
- issuer sai.
- chữ ký sai hoặc alg không được phép.
- token hết hạn hoặc chưa tới nbf.
- token đúng audience nhưng thiếu scope.
- token đúng audience/scope nhưng user không có quyền object.
- opaque token introspection trả active=false hoặc aud sai.

Không chỉnh payload JWT rồi kỳ vọng token vẫn hợp lệ; sửa claim mà không ký lại phải làm chữ ký thất bại.

### Ma trận kiểm thử

| Ca kiểm thử | Token/điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Đúng resource | aud là Orders API | Orders API tiếp tục kiểm tra scope và quyền |
| Sai resource | aud là Billing API | Orders API từ chối 401 |
| Thiếu aud | Token không có audience trong profile yêu cầu | Từ chối |
| aud sai kiểu | aud là number/object | Từ chối |
| aud dạng mảng hợp lệ | Mảng có Orders API và profile cho phép | Có thể chấp nhận theo policy |
| aud mảng quá rộng | Chứa nhiều resource ngoài nhu cầu | Cảnh báo/không cấp theo least privilege |
| ID token | Token dành cho OIDC client | API từ chối |
| Issuer sai | iss không khớp | Từ chối |
| Chữ ký sai | Token bị sửa payload | Từ chối |
| Hết hạn | exp đã qua | Từ chối |
| Chưa hiệu lực | nbf ở tương lai ngoài clock skew | Từ chối |
| Thiếu scope | Audience đúng, scope không đủ | 403 hoặc lỗi authorization |
| Không có object permission | Scope đúng nhưng object thuộc user khác | Từ chối |
| Opaque token active=false | Introspection báo inactive | Từ chối |
| Opaque token sai aud | Introspection aud không có resource hiện tại | Từ chối |
| Forward token sai resource | Orders token gửi Billing API | Billing API từ chối |

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ xác minh chữ ký và exp | Token hợp lệ vẫn có thể dành cho API khác | Kiểm tra aud theo resource server |
| Bỏ qua aud khi claim thiếu | Chấp nhận token không có người nhận rõ ràng | Yêu cầu audience theo token profile |
| Dùng scope thay audience | Token của API khác có thể bị chấp nhận | Kiểm tra cả aud và scope |
| Nhầm client_id với aud | Chấp nhận token dành cho client thay vì resource | Phân biệt client và resource server |
| Gửi ID token tới API | Token substitution | API chỉ chấp nhận access token profile phù hợp |
| Dùng azp thay aud | Sai người nhận token | Áp dụng đúng quy tắc OIDC và OAuth |
| Chấp nhận mọi audience trong mảng | Mở rộng nơi token được dùng | Multi-audience chỉ khi có policy rõ |
| So khớp hostname bằng suffix | Origin/resource giả có thể lọt | So khớp exact configured identifier |
| Tự tạo aud từ request Host | Client/proxy có thể tác động giá trị kỳ vọng | Dùng audience cố định trong cấu hình tin cậy |
| Forward nguyên token qua mọi service | Confused deputy và token reuse | Xin token mới cho resource đích |
| Nghĩ aud ngăn XSS đánh cắp token | Attacker vẫn dùng token ở API đúng audience | Phòng XSS, BFF, token ngắn hạn và sender constraint |
| Nghĩ CORS thay audience | API có thể chấp nhận token sai resource | CORS và aud xử lý hai ranh giới khác nhau |
| Chỉ kiểm tra aud ở gateway | Downstream service có thể nhận token sai | Mỗi resource server xác minh token theo policy |
| Decode JWT rồi tin claim | Payload không được xác minh | Verify chữ ký và profile trước khi tin claim |
| Ghi token vào log để debug | Credential bị lộ qua log/APM | Redact token, log mã lỗi và correlation ID |

## 18. Câu hỏi củng cố

**Câu 1.** Audience của access token xác định điều gì?

**Giải đáp:** Resource server hoặc nhóm resource server được phép chấp nhận token. API phải kiểm tra audience có chứa định danh của chính nó hay không.

**Câu 2.** aud khác scope như thế nào?

**Giải đáp:** aud xác định người nhận token; scope xác định hành động/quyền được cấp tại resource đó.

**Câu 3.** Audience của ID token thường là gì?

**Giải đáp:** OIDC client_id của client nhận ID token. API không được dùng ID token thay access token.

**Câu 4.** JWT aud có thể là mảng không?

**Giải đáp:** Có. JWT cho phép aud là chuỗi hoặc mảng StringOrURI. Resource server phải kiểm tra theo profile và policy đã thống nhất.

**Câu 5.** Audience có nhất thiết bằng origin của SPA không?

**Giải đáp:** Không. Audience là resource identifier của API; origin là định danh document browser. Hai giá trị có thể khác nhau.

**Câu 6.** Nếu Orders API nhận token dành cho Billing API thì nên làm gì?

**Giải đáp:** Từ chối token vì sai audience. Client hoặc service cần xin token dành cho resource đích.

**Câu 7.** Audience có ngăn token bị đánh cắp và dùng tại đúng API không?

**Giải đáp:** Không. Audience chỉ giới hạn resource chấp nhận token. Cần token ngắn hạn, phòng XSS, BFF hoặc sender-constrained token để giảm rủi ro replay.

**Câu 8.** Opaque token được kiểm tra audience thế nào?

**Giải đáp:** Resource server gọi introspection endpoint đáng tin cậy và kiểm tra audience/metadata theo hợp đồng với authorization server.

## 19. Tổng kết

Audience xác định resource server được phép chấp nhận access token. Mỗi API phải so khớp aud với resource identifier canonical đã cấu hình, đồng thời kiểm tra chữ ký, issuer, thời hạn, token type, scope và quyền ở cấp đối tượng. Audience không thay thế scope, client_id, sub hoặc authorization.

Không nhầm audience của access token với ID token: ID token dành cho OIDC client, còn access token dành cho resource server. Khi một ứng dụng gọi nhiều API, ưu tiên token riêng cho từng resource; không forward token của API này sang API khác. Với opaque token, dùng introspection và kiểm tra audience theo hợp đồng với issuer.

Trong browser, audience không ngăn XSS đánh cắp token hoặc sử dụng token tại đúng API. Kết hợp audience restriction với token ngắn hạn, scope tối thiểu, phòng XSS, BFF hoặc sender-constrained token khi phù hợp. CORS kiểm soát quyền đọc response cross-origin; audience kiểm soát resource server chấp nhận token. Hai cơ chế độc lập và đều cần cấu hình đúng.

## Tài liệu tham khảo

1. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claim aud, iss, sub và quy tắc JWT.
2. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và validation claims.
3. [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): tham số resource và audience restriction khi cấp token.
4. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): audience của ID token, client_id và azp.
5. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection cho opaque access token.
6. [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): đổi token cho resource và actor trong kiến trúc nhiều dịch vụ.
7. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token bằng proof-of-possession.
8. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0 hiện hành.

# UserInfo endpoint

> **Chương:** OpenID Connect  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Cách ứng dụng lấy các claim về người dùng từ UserInfo endpoint trong OpenID Connect, sử dụng access token đúng mục đích, kiểm tra subject, quản lý scope và bảo vệ dữ liệu danh tính.

## 1. UserInfo endpoint là gì?

**UserInfo endpoint** là một protected resource được định nghĩa trong OpenID Connect (OIDC). Ứng dụng (Relying Party — RP/client) gọi endpoint này bằng **access token** để lấy các claim về End-User đã xác thực, chẳng hạn tên hiển thị, email hoặc số điện thoại nếu nhà cung cấp danh tính cho phép chia sẻ.

UserInfo thường được dùng sau khi client hoàn tất luồng OIDC và nhận được ID token cùng access token. ID token cung cấp thông tin xác thực cần thiết để client thiết lập phiên đăng nhập; UserInfo có thể cung cấp thêm thuộc tính hồ sơ hoặc dữ liệu cập nhật hơn theo scope, consent và chính sách của OpenID Provider (OP).

Ví dụ: nhân viên đăng nhập vào ứng dụng quản lý dự án thông qua IdP công ty. Ứng dụng xác minh ID token, sau đó dùng access token gọi UserInfo endpoint để lấy tên, email và ảnh đại diện. Ứng dụng dùng subject ổn định để liên kết tài khoản, còn email/tên hiển thị chỉ phục vụ liên hệ và giao diện theo chính sách.

UserInfo endpoint **không phải endpoint đăng nhập**, không nhận mật khẩu và không thay thế authorization endpoint hoặc token endpoint. Nó là một tài nguyên được bảo vệ, trả về các claim mà client được phép nhận.

### Kết quả học tập

Sau bài này, người học có thể:

- Giải thích vai trò của UserInfo endpoint trong OIDC và phân biệt nó với authorization, token và discovery endpoint.
- Tìm UserInfo endpoint từ metadata của issuer tin cậy.
- Gọi endpoint bằng access token qua HTTPS.
- Hiểu quan hệ giữa scope, consent và các claim được trả về.
- Kiểm tra subject trong UserInfo khớp với subject của ID token.
- Xử lý response JSON hoặc JWT, lỗi token, cache và dữ liệu cá nhân an toàn.

## 2. UserInfo nằm ở đâu trong OIDC?

OIDC bổ sung lớp xác thực người dùng trên OAuth 2.0. Một client thường tương tác với các endpoint sau:

| Endpoint | Vai trò |
|---|---|
| **Authorization endpoint** | Bắt đầu luồng đăng nhập/ủy quyền, điều phối xác thực người dùng và consent |
| **Token endpoint** | Đổi authorization code hoặc thực hiện grant phù hợp để nhận token |
| **UserInfo endpoint** | Trả về các claim về End-User khi client trình access token hợp lệ |
| **Discovery endpoint** | Công bố metadata của OpenID Provider, bao gồm các endpoint và khả năng hỗ trợ |
| **JWKS URI** | Cung cấp tập khóa công khai để client xác minh chữ ký token do OP phát hành |
| **Revocation endpoint** | Thu hồi token nếu OP hỗ trợ theo giao thức/cấu hình |

### Luồng tổng quát

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as OIDC Client / RP
    participant OP as OpenID Provider
    participant UI as UserInfo endpoint
    U->>C: Bắt đầu đăng nhập
    C->>OP: Authorization request
    OP->>U: Xác thực / MFA / consent
    U-->>OP: Hoàn tất xác thực
    OP-->>C: Authorization code qua redirect
    C->>OP: Token request + PKCE verifier
    OP-->>C: ID token + access token
    C->>C: Xác minh ID token
    C->>UI: GET UserInfo + access token
    UI->>UI: Xác minh access token và scope
    UI-->>C: Claims về End-User
    C->>C: So sánh sub với ID token sub
    C-->>U: Thiết lập trải nghiệm đăng nhập
~~~

Sơ đồ mô tả một luồng phổ biến dùng Authorization Code Flow với PKCE. Chi tiết grant, loại client và việc cấp refresh token phụ thuộc cấu hình OP. UserInfo là bước tùy chọn khi ứng dụng cần thêm claims; client không cần gọi nó nếu các claim cần thiết đã có trong ID token và chính sách cho phép.

## 3. Tìm endpoint từ OpenID Provider metadata

Client không nên tự đoán URL UserInfo hoặc ghép endpoint từ tên miền người dùng nhập. OIDC Discovery cung cấp metadata của issuer, thường được công bố tại:

~~~text
https://id.example.com/.well-known/openid-configuration
~~~

Metadata có thể chứa các trường:

- **issuer:** định danh chính xác của OpenID Provider.
- **authorization_endpoint:** endpoint bắt đầu đăng nhập.
- **token_endpoint:** endpoint cấp token.
- **userinfo_endpoint:** endpoint lấy UserInfo.
- **jwks_uri:** endpoint chứa khóa công khai.
- **end_session_endpoint:** endpoint logout nếu được công bố.
- Các danh sách thuật toán, grant type, response type và khả năng khác.

### Quy trình lấy metadata an toàn

1. Bắt đầu từ issuer đã được tổ chức cấu hình hoặc đăng ký trước.
2. Lấy discovery document qua HTTPS và xác minh chứng thư TLS.
3. Kiểm tra trường issuer trong metadata khớp chính xác issuer đã tin cậy.
4. Kiểm tra userinfo_endpoint được công bố và sử dụng HTTPS.
5. Lưu metadata theo chính sách cache và cập nhật của nhà cung cấp.
6. Khi khóa hoặc endpoint thay đổi, cập nhật từ nguồn issuer tin cậy và ghi nhận thay đổi.

Không lấy issuer tùy ý từ query string, token chưa xác minh hoặc dữ liệu do người dùng kiểm soát rồi tải discovery document. Cách làm đó có thể tạo SSRF hoặc cho phép client tin một OP giả. Với hệ thống multi-tenant, mỗi issuer cần được đăng ký, kiểm tra và liên kết với tenant/client theo chính sách rõ ràng.

### Ví dụ metadata rút gọn

~~~json
{
  "issuer": "https://id.example.com",
  "authorization_endpoint": "https://id.example.com/authorize",
  "token_endpoint": "https://id.example.com/token",
  "userinfo_endpoint": "https://id.example.com/userinfo",
  "jwks_uri": "https://id.example.com/.well-known/jwks.json"
}
~~~

Đây là dữ liệu minh họa, không phải metadata của một nhà cung cấp thực. Ứng dụng phải dùng giá trị từ metadata đã xác minh, không hardcode các URL ví dụ này.

## 4. Gọi UserInfo endpoint bằng access token

Client gọi UserInfo bằng access token được cấp trong OIDC flow. Cách truyền bearer token thông dụng là HTTP Authorization header:

~~~http
GET /userinfo HTTP/1.1
Host: id.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

OIDC UserInfo endpoint hỗ trợ request bằng HTTP GET và POST. Dù dùng phương thức nào, access token phải được gửi theo cơ chế Bearer token được giao thức quy định và toàn bộ kết nối phải dùng TLS.

### Ví dụ response JSON

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "sub": "user-824",
  "name": "Lan Nguyen",
  "preferred_username": "lan.nguyen",
  "email": "lan.nguyen@example.com",
  "email_verified": true,
  "picture": "https://id.example.com/photos/user-824"
}
~~~

Response minh họa. Nhà cung cấp chỉ trả về các claim được phép theo scope, consent, dữ liệu sẵn có và chính sách của họ. Client không được giả định mọi claim đã yêu cầu chắc chắn sẽ xuất hiện.

### Dùng đúng loại token

- **Access token:** dùng để gọi UserInfo endpoint.
- **ID token:** dùng để client xác minh kết quả xác thực; không gửi thay access token.
- **Refresh token:** chỉ gửi đến token endpoint theo grant phù hợp; không gửi đến UserInfo.
- **Authorization code:** chỉ đổi tại token endpoint; không dùng như bearer credential.

ID token có thể là JWT đã ký, nhưng điều đó không làm nó trở thành access token. Hai token có audience và mục đích khác nhau.

## 5. Access token được xác minh như thế nào?

UserInfo endpoint là protected resource. OpenID Provider phải xác minh access token trước khi trả claim. Cách xác minh phụ thuộc loại token và kiến trúc của OP:

- Với opaque access token, endpoint có thể tra cứu trạng thái trong kho token hoặc dùng cơ chế introspection nội bộ.
- Với JWT access token, OP/resource component xác minh chữ ký hoặc MAC, issuer, audience theo profile phát hành, thời hạn, scope và trạng thái cần thiết.
- Nếu token bị thu hồi, hết hạn, sai issuer/audience hoặc không có quyền truy cập UserInfo, request phải bị từ chối.

Không được chỉ decode JWT payload rồi tin các claim. Không dùng thuật toán hoặc khóa do token tự chọn; verifier phải dựa trên cấu hình và khóa tin cậy của OP.

### Client cần làm gì với access token?

Client nhận access token từ token endpoint và dùng nó đúng resource. Client không nhất thiết phải đọc hoặc giải mã access token; access token có thể opaque. Client nên:

1. Lưu token trong vùng bảo vệ phù hợp với loại ứng dụng.
2. Gửi token chỉ đến UserInfo endpoint đã xác minh.
3. Không đưa token vào URL, log, analytics hoặc error report.
4. Xử lý lỗi hết hạn/thu hồi theo flow token, không lặp vô hạn.
5. Không dùng cùng token cho API khác nếu audience/scope không cho phép.

### Audience và mục đích

Không có quy tắc rằng mọi access token phải có cùng một audience hoặc định dạng. OP có thể cấp token được chấp nhận tại UserInfo theo hợp đồng của nó. Resource server phải kiểm tra đúng profile và chính sách phát hành, không áp dụng một giả định chung từ một nhà cung cấp khác.

## 6. Claim sub: ràng buộc danh tính bắt buộc

Claim **sub (subject)** là định danh chủ thể trong phạm vi issuer. UserInfo response phải chứa sub. Client phải kiểm tra giá trị sub trong UserInfo **khớp chính xác** với sub trong ID token đã được xác minh cho cùng một luồng xác thực.

Đây là kiểm tra bảo mật cốt lõi. Nếu hai giá trị không khớp, client phải coi UserInfo response không hợp lệ và không sử dụng các claim trong response để cập nhật hồ sơ hoặc liên kết tài khoản.

### Vì sao cần so sánh?

Giả sử ID token đã xác minh đại diện cho user-824, nhưng UserInfo response lại trả sub=user-991. Nếu client bỏ qua khác biệt, dữ liệu hồ sơ của một người khác có thể bị gắn vào phiên hiện tại. Đây là lỗi liên kết danh tính nghiêm trọng.

### Không dùng email thay cho sub

Email có thể thay đổi, được tái cấp, chưa xác minh hoặc trùng trong các hệ thống khác nhau. Subject phải được hiểu trong phạm vi issuer:

~~~text
identity_key = (issuer, subject)
           = (iss, sub)
~~~

Nếu cùng một sub được phát hành bởi hai issuer khác nhau, không được mặc nhiên xem là cùng người. Tương tự, email trùng nhau không phải bằng chứng đủ để tự động ghép hai tài khoản.

### Public và pairwise subject

OP có thể sử dụng subject identifier kiểu public hoặc pairwise. Với pairwise subject, cùng một người có thể nhận giá trị sub khác nhau ở các client/sector khác nhau để giảm khả năng các RP liên kết hoạt động của người dùng với nhau.

Vì vậy:

- Không giả định sub giống nhau trên mọi ứng dụng.
- Không tự suy ra danh tính toàn cục từ một subject pairwise.
- Dùng mapping do tổ chức quản lý nếu cần liên kết nhiều ứng dụng, với cơ sở pháp lý và kiểm soát phù hợp.

## 7. Scope và các claim UserInfo

Scope OIDC xác định nhóm thông tin mà client yêu cầu. Việc cấp scope không có nghĩa mọi thuộc tính đều chắc chắn được trả về; OP có thể áp dụng consent, chính sách riêng tư, mức xác minh và khả năng dữ liệu.

| Scope | Nhóm claim thường liên quan | Ví dụ |
|---|---|---|
| **openid** | Subject | sub |
| **profile** | Thông tin hồ sơ | name, given_name, family_name, nickname, preferred_username, picture, locale, zoneinfo |
| **email** | Email | email, email_verified |
| **address** | Địa chỉ | address |
| **phone** | Số điện thoại | phone_number, phone_number_verified |

### Scope không phải quyền API tùy ý

Các scope OIDC này mô tả nhóm claim về người dùng, không phải quyền truy cập nghiệp vụ như payments:write hoặc admin. Không dùng profile làm bằng chứng người dùng có quyền xem hồ sơ nhạy cảm trong ứng dụng.

### Ví dụ yêu cầu scope

~~~text
scope=openid profile email
~~~

Yêu cầu trên thể hiện client muốn xác thực OIDC và nhận các claim hồ sơ/email được OP cho phép. OP có thể yêu cầu consent hoặc chỉ trả một phần thuộc tính. Ứng dụng cần hoạt động đúng khi một claim tùy chọn vắng mặt.

### Claims request parameter

OIDC hỗ trợ claims request parameter để client diễn đạt các claim cụ thể cần trong ID token hoặc UserInfo, cùng một số yêu cầu như essential theo đặc tả. Đây là cơ chế yêu cầu chi tiết hơn scope; OP vẫn quyết định dựa trên khả năng, consent và chính sách.

Không yêu cầu dữ liệu nhạy cảm chỉ vì API cho phép. Client cần giải thích mục đích, tối thiểu hóa thuộc tính và không biến việc thiếu một claim tùy chọn thành lỗi xác thực nếu chính sách không yêu cầu.

## 8. Những claim phổ biến

UserInfo có thể trả nhiều claim chuẩn. Ví dụ:

| Claim | Ý nghĩa | Cách dùng thận trọng |
|---|---|---|
| **sub** | Định danh subject | Dùng làm khóa liên kết cùng issuer |
| **name** | Tên đầy đủ | Hiển thị; không dùng làm định danh |
| **given_name, family_name** | Tên và họ | Có thể thay đổi hoặc thiếu |
| **preferred_username** | Tên đăng nhập ưu tiên | Không mặc định duy nhất/toàn cục |
| **picture** | URL ảnh đại diện | Không tải hoặc hiển thị như nguồn tin cậy tuyệt đối |
| **locale, zoneinfo** | Ngôn ngữ/khu vực thời gian | Dùng cho trải nghiệm, không dùng phân quyền |
| **email** | Địa chỉ email | Có thể thay đổi |
| **email_verified** | OP xác nhận email theo chính sách của họ | Không thay thế kiểm soát sở hữu mailbox trong mọi quy trình |
| **phone_number** | Số điện thoại | Dữ liệu cá nhân; hạn chế lưu và hiển thị |
| **phone_number_verified** | Trạng thái xác minh số điện thoại | Hiểu theo phương thức và thời điểm OP xác minh |
| **address** | Đối tượng địa chỉ | Có thể chứa dữ liệu cá nhân nhạy cảm |

### Claim có thể thay đổi

Tên, email, ảnh đại diện, số điện thoại và địa chỉ có thể thay đổi theo thời gian. ID token thường phản ánh trạng thái tại thời điểm xác thực; UserInfo có thể trả dữ liệu mới hơn khi được gọi. Ứng dụng cần xác định thuộc tính nào được đồng bộ, thuộc tính nào do người dùng tự quản lý và thuộc tính nào cần nguồn dữ liệu nội bộ có thẩm quyền.

Không ghi đè dữ liệu hồ sơ cục bộ một cách mù quáng mỗi lần gọi UserInfo. Ví dụ, ứng dụng có thể cho người dùng tự chọn tên hiển thị riêng; nếu UserInfo trả name mới, cần chính sách đồng bộ rõ ràng.

## 9. Response format và xác minh

UserInfo response thường là JSON. Tùy đăng ký client và khả năng OP, response cũng có thể được ký hoặc mã hóa theo cấu hình giao thức.

### JSON response

Khi response là JSON, client nhận các claim qua TLS và phải:

- Đảm bảo request đến đúng UserInfo endpoint từ metadata tin cậy.
- Gửi access token đúng issuer/resource.
- Xử lý status code và Content-Type đúng.
- Kiểm tra sub bắt buộc và khớp ID token.
- Kiểm tra kiểu dữ liệu claim trước khi sử dụng.
- Không tin claim để cấp quyền vượt quá mapping đã định.

JSON response không có chữ ký độc lập theo mặc định. Tính tin cậy dựa trên TLS, endpoint đã cấu hình và việc OP xác minh access token. Nếu threat model yêu cầu response được ký, dùng chế độ ký theo OIDC registration/configuration thay vì tự thêm một trường signature tùy biến.

### Signed hoặc encrypted UserInfo response

Nếu OP trả UserInfo dưới dạng JWT đã ký:

1. Xác minh chữ ký bằng khóa tin cậy của OP.
2. Kiểm tra iss và aud theo cấu hình OIDC/client.
3. Kiểm tra thời hạn và các điều kiện token response liên quan.
4. Kiểm tra sub khớp ID token đã xác minh.
5. Chỉ sau đó mới sử dụng các claim.

Nếu response được mã hóa, client phải giải mã theo khóa và thuật toán đã đăng ký; nếu response vừa ký vừa mã hóa, thực hiện đúng thứ tự xử lý theo cấu hình và đặc tả. Không coi việc giải mã thành công là bằng chứng chữ ký hợp lệ.

### Kiểu dữ liệu

Một số claim là string, boolean hoặc object lồng nhau. Ví dụ email_verified là boolean; address là object với các trường như street_address, locality, region, postal_code và country. Client cần xác thực schema, xử lý trường thiếu và không giả định mọi giá trị luôn có.

## 10. Ví dụ tích hợp phía client

Ví dụ sau mô tả một backend RP đã có ID token và access token từ OIDC flow:

~~~typescript
async function loadUserInfo(accessToken, idTokenClaims, providerMetadata) {
  const endpoint = providerMetadata.userinfo_endpoint;
  if (!endpoint || !endpoint.startsWith("https://")) {
    throw new Error("Trusted HTTPS UserInfo endpoint is required");
  }

  const response = await fetch(endpoint, {
    method: "GET",
    headers: {
      "Authorization": "Bearer " + accessToken,
      "Accept": "application/json",
    },
    redirect: "error",
  });

  if (response.status === 401) {
    throw new Error("Access token is invalid, expired, or revoked");
  }
  if (response.status === 403) {
    throw new Error("Access token lacks permission for UserInfo");
  }
  if (!response.ok) {
    throw new Error("UserInfo request failed");
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.toLowerCase().includes("application/json")) {
    throw new Error("Unexpected UserInfo response format");
  }

  const userInfo = await response.json();
  if (typeof userInfo.sub !== "string" || userInfo.sub.length === 0) {
    throw new Error("UserInfo response has no valid subject");
  }
  if (userInfo.sub !== idTokenClaims.sub) {
    throw new Error("UserInfo subject does not match ID token subject");
  }

  return userInfo;
}
~~~

Đây là pseudocode minh họa. Trong triển khai thực tế, providerMetadata phải đến từ issuer đã đăng ký và được xác minh; cần kiểm tra URL đầy đủ bằng thư viện URL, không chỉ dựa vào startsWith. Xử lý response JWT nếu OP cấu hình dạng đó. Không ghi access token hoặc toàn bộ response có dữ liệu cá nhân vào log.

### Nếu gọi từ browser SPA

SPA có thể gọi UserInfo trực tiếp nếu OP cho phép CORS từ origin đã đăng ký. Cần:

- Allowlist chính xác origin của client; không bật wildcard một cách tùy tiện.
- Không lưu refresh token hoặc access token dài hạn trong nơi JavaScript dễ bị XSS đọc.
- Cân nhắc Backend-for-Frontend (BFF) để backend giữ token và browser chỉ dùng cookie session an toàn.
- Không coi CORS là cơ chế xác thực hoặc authorization; client ngoài browser vẫn có thể gọi endpoint.

## 11. Xử lý lỗi

UserInfo endpoint có thể từ chối request vì token sai, hết hạn, bị thu hồi hoặc không có scope cần thiết.

| HTTP status | Ý nghĩa thường gặp | Hành động của client |
|---|---|---|
| **200 OK** | Request hợp lệ, trả claims | Kiểm tra format và sub, sau đó dùng claim theo chính sách |
| **400 Bad Request** | Request sai định dạng hoặc tham số không hợp lệ | Kiểm tra cách gọi và cấu hình client |
| **401 Unauthorized** | Access token thiếu, sai, hết hạn hoặc không hợp lệ | Thực hiện refresh/re-auth theo flow; không lặp vô hạn |
| **403 Forbidden** | Token hợp lệ nhưng thiếu quyền/scope theo chính sách | Yêu cầu scope/consent phù hợp nếu cần |
| **429 Too Many Requests** | Bị giới hạn tần suất nếu OP áp dụng | Backoff và tuân thủ Retry-After |
| **5xx** | Lỗi phía OP hoặc hạ tầng | Retry có giới hạn, exponential backoff và quan sát trạng thái |

### Bearer error

Với OAuth Bearer token, response 401 có thể kèm WWW-Authenticate để mô tả lỗi như invalid_token; 403 có thể biểu thị insufficient_scope. Client không nên dựa vào chuỗi lỗi chi tiết để suy luận tài khoản có tồn tại hay không.

### Không refresh vô hạn

Nếu UserInfo trả 401, client có thể dùng refresh token để xin access token mới khi grant còn hợp lệ. Nếu refresh thất bại hoặc token family đã bị thu hồi, yêu cầu người dùng xác thực lại. Không lặp request UserInfo vô hạn bằng cùng access token đã bị từ chối.

## 12. Cache, tính mới và quyền riêng tư

UserInfo có thể chứa dữ liệu cá nhân. Response nên được bảo vệ khỏi cache ngoài ý muốn; OP thường dùng các chỉ thị như Cache-Control: no-store và Pragma: no-cache theo khuyến nghị OIDC.

Client cần xem xét:

- Không cache response chứa thông tin nhạy cảm vào shared proxy hoặc CDN.
- Nếu cần cache nội bộ, giới hạn thời gian, phạm vi người dùng và quyền truy cập.
- Xóa cache khi logout, unlink account hoặc nhận thông báo thay đổi theo chính sách.
- Không lưu dữ liệu nhiều hơn mục đích nghiệp vụ.
- Giới hạn quyền truy cập log, audit và backup có chứa claims.

### Tối thiểu hóa dữ liệu

Chỉ yêu cầu scope cần thiết. Một ứng dụng hiển thị lịch có thể chỉ cần sub, name hoặc preferred_username; không cần địa chỉ nhà hay số điện thoại. Việc yêu cầu email, phone hoặc address cần mục đích rõ ràng và tuân thủ chính sách riêng tư áp dụng.

### UserInfo không phải nguồn dữ liệu bất biến

Claim có thể thay đổi hoặc bị OP ngừng cung cấp. Ứng dụng nên phân loại:

- **Định danh liên kết:** issuer + subject; không thay đổi chỉ vì email đổi.
- **Thuộc tính hiển thị:** tên, ảnh, locale; có thể đồng bộ theo chính sách.
- **Thuộc tính liên hệ:** email, phone; cần quy trình xác minh và cập nhật.
- **Thuộc tính phân quyền:** group, department hoặc role; chỉ tin khi có hợp đồng nguồn dữ liệu và mapping rõ ràng.

Không dùng một claim hồ sơ đơn lẻ làm bằng chứng đủ để cấp quyền đặc quyền.

## 13. Các lỗi bảo mật thường gặp

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| Gửi ID token thay access token | Sai mục đích và audience; vi phạm mô hình OIDC | Chỉ dùng access token gọi UserInfo |
| Không kiểm tra sub | Có thể gắn claim của người khác vào phiên hiện tại | So sánh chính xác với ID token đã xác minh |
| Ghép tài khoản bằng email | Email thay đổi, tái cấp hoặc chưa xác minh | Dùng issuer + sub và quy trình liên kết có kiểm soát |
| Tin endpoint từ input người dùng | SSRF hoặc OP giả | Discovery từ issuer allowlist và xác minh metadata |
| Không xác minh TLS | Có thể bị nghe lén hoặc giả mạo endpoint | HTTPS và xác minh certificate |
| Log Authorization header | Access token có thể bị đánh cắp | Redact header ở app, proxy, tracing và APM |
| Giả định mọi claim đều có | Gây lỗi hoặc quyết định sai khi claim vắng mặt | Xử lý trường tùy chọn và chính sách fallback |
| Tin claim email_verified như bằng chứng vĩnh viễn | Trạng thái có thể cũ hoặc không đủ cho nghiệp vụ | Xác minh lại khi hành động yêu cầu kiểm soát mailbox |
| Dùng profile claim để phân quyền | Thuộc tính hồ sơ không tự tạo quyền | Authorization server-side theo resource/action |
| Cache response quá lâu | Dữ liệu cũ hoặc lộ qua shared cache | Cache có giới hạn và chỉ thị no-store phù hợp |
| Không xử lý response JWT theo cấu hình | Có thể bỏ qua chữ ký/mã hóa bắt buộc | Tuân thủ client registration và xác minh JWT |
| Gọi UserInfo sau logout bằng token cũ | Token có thể vẫn còn hiệu lực | Thu hồi/expiry token và xóa session theo chính sách |

## 14. Tình huống thực hành: ứng dụng quản lý dự án

**Bối cảnh:** Công ty dùng OIDC để nhân viên đăng nhập vào ứng dụng quản lý dự án. Ứng dụng cần subject, tên hiển thị và email công việc. OP hỗ trợ các scope openid, profile và email.

### Thiết kế luồng

1. RP khởi tạo Authorization Code Flow với PKCE, state và nonce.
2. Người dùng xác thực tại OP bằng passkey hoặc MFA theo chính sách.
3. RP đổi authorization code và nhận ID token cùng access token.
4. RP xác minh ID token: chữ ký, issuer, audience, thời hạn và nonce.
5. RP lấy userinfo_endpoint từ discovery metadata đã xác minh.
6. RP gửi access token qua Authorization header đến UserInfo.
7. RP xác minh response có sub và sub khớp ID token.
8. RP liên kết tài khoản theo (iss, sub).
9. RP cập nhật tên/email theo chính sách hồ sơ; không dùng email làm khóa chính.
10. RP kiểm tra quyền dự án ở dữ liệu nội bộ trước khi hiển thị hoặc thay đổi tài nguyên.

### Nếu UserInfo trả sub khác ID token

RP phải từ chối toàn bộ response và ghi nhận sự kiện bảo mật ở mức không chứa token. Không cập nhật tên, email hoặc mapping tài khoản. Điều tra issuer, token, cache và thư viện OIDC; không cố “sửa” bằng cách tìm tài khoản có email trùng.

### Nếu email không có trong response

Nếu email không phải claim bắt buộc cho việc đăng nhập, RP vẫn có thể tạo phiên dựa trên danh tính đã xác minh và yêu cầu người dùng cung cấp/xác minh email theo quy trình riêng khi tính năng cần. Không từ chối xác thực chỉ vì một claim tùy chọn vắng mặt.

## 15. Kiểm thử UserInfo endpoint

Kiểm thử trong môi trường được phép với issuer và tài khoản thử nghiệm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Access token hợp lệ, đúng quyền | Trả claims theo scope/consent |
| Không có Authorization header | Từ chối request |
| Token sai hoặc hết hạn | 401, không trả claims |
| Token bị thu hồi | Từ chối theo trạng thái token |
| Token không được phép gọi UserInfo | Từ chối theo chính sách |
| Gửi ID token thay access token | Không được chấp nhận như access token |
| sub UserInfo khác ID token | Client từ chối response và không cập nhật mapping |
| Claim email vắng mặt | Client xử lý theo chính sách, không lỗi xác thực ngoài ý muốn |
| email_verified là false | Không coi email đã xác minh |
| Discovery issuer không khớp cấu hình | Client từ chối metadata |
| UserInfo endpoint dùng HTTP không mã hóa | Client từ chối |
| Redirect sang endpoint khác | Client không gửi bearer token ngoài endpoint tin cậy |
| Response có Content-Type ngoài cấu hình | Client từ chối hoặc xử lý theo format đã đăng ký |
| Signed UserInfo JWT có chữ ký sai | Client từ chối |
| Signed UserInfo JWT có audience sai | Client từ chối |
| Response chứa claim lạ hoặc kiểu dữ liệu sai | Client xử lý an toàn, không dùng để cấp quyền |
| UserInfo response bị cache ngoài ý muốn | Kiểm tra và sửa cache policy |
| Token xuất hiện trong log | Redaction phải ngăn lộ secret |

## 16. Checklist thiết kế UserInfo endpoint

- [ ] UserInfo được hiểu là protected resource, không phải endpoint đăng nhập.
- [ ] Endpoint được lấy từ discovery metadata của issuer đã tin cậy.
- [ ] Metadata issuer khớp chính xác cấu hình; UserInfo endpoint dùng HTTPS.
- [ ] Client gọi bằng access token, không dùng ID token hoặc refresh token.
- [ ] Bearer token chỉ được gửi trong Authorization header qua TLS.
- [ ] Access token được OP xác minh theo đúng issuer, audience, thời hạn và scope.
- [ ] Client kiểm tra sub trong UserInfo khớp chính xác với ID token đã xác minh.
- [ ] Identity mapping dùng (iss, sub), không tự động ghép tài khoản bằng email.
- [ ] Scope/claims được tối thiểu hóa; xử lý claim tùy chọn vắng mặt.
- [ ] Claim hồ sơ không tự động trở thành quyền truy cập nghiệp vụ.
- [ ] JSON/JWT response được xử lý theo format đã đăng ký và xác minh đúng.
- [ ] Không log token, không đặt token trong URL và không cache dữ liệu cá nhân ngoài ý muốn.
- [ ] Xử lý 401/403, refresh, retry và rate limit có giới hạn.
- [ ] Browser SPA dùng CORS allowlist; cân nhắc BFF và bảo vệ token khỏi XSS.
- [ ] Kiểm thử mismatch sub, issuer sai, endpoint giả, token hết hạn và response sai định dạng.

## Ghi nhớ

UserInfo endpoint là protected resource của OIDC, cho phép client lấy các claim về End-User bằng **access token**. Client tìm endpoint từ metadata của issuer tin cậy, gọi qua HTTPS và chỉ yêu cầu các scope/claim cần thiết.

Kiểm tra quan trọng nhất ở phía client là sub trong UserInfo phải khớp chính xác sub của ID token đã xác minh. Dùng cặp (iss, sub) để liên kết danh tính; không dùng email làm khóa mặc định. Bảo vệ access token, xử lý claim như dữ liệu có thể thay đổi, giới hạn cache và tiếp tục kiểm tra authorization ở ứng dụng.

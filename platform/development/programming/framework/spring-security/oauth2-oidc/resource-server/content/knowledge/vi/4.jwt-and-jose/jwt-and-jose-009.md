# Registered claims, public claims và claims riêng của hệ thống

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, Access Token có thể được biểu diễn dưới dạng **JSON Web Token (JWT)**. JWT chứa các **claim**: những cặp tên–giá trị thể hiện thông tin về chủ thể, bên phát hành, đối tượng nhận token, thời hạn, quyền truy cập và các dữ liệu đã được hệ thống định nghĩa.

Không phải claim nào cũng có cùng nguồn gốc hoặc cùng ý nghĩa. Theo [RFC 7519, mục 4](https://www.rfc-editor.org/rfc/rfc7519#section-4), tên claim được chia thành ba nhóm: **Registered Claim Names**, **Public Claim Names** và **Private Claim Names**. Phân loại này giúp các bên thống nhất tên, tránh xung đột và xác định claim nào cần kiểm tra. Tuy nhiên, **việc có claim trong JWT không tự động chứng minh token hợp lệ hoặc người gọi có quyền**: Resource Server phải xác thực token và áp dụng chính sách cụ thể.

## 1. Claim nằm ở đâu trong JWT?

JWT dạng **JWS compact serialization** thường có cấu trúc:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(SIGNATURE)
        Phần 1              Phần 2              Phần 3
~~~

Ví dụ JSON của **JOSE Header**:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026",
  "typ": "at+jwt"
}
~~~

Ví dụ JSON của **JWT Claims Set**:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

Trong đó:

- **alg**, **kid**, **typ** thuộc **JOSE Header**, không phải payload claims. **alg** chỉ thuật toán chữ ký được khai báo; **kid** giúp chọn khóa xác minh; **typ** giúp xác định kiểu đối tượng/token khi profile yêu cầu.
- **iss**, **sub**, **aud**, **exp**, **iat** là các **registered claims** quen thuộc.
- **scope** là một claim được dùng trong ngữ cảnh OAuth 2.0/JWT Access Token profile; nó **không thuộc danh sách bảy registered claims gốc của RFC 7519**.
- **tenant_id** là tên claim riêng do hệ thống ví dụ tự quy ước; không mặc nhiên là tên chuẩn chung.

Các JSON trên chỉ nhằm giải thích cấu trúc; chúng không phải một JWT đã ký hợp lệ. **Base64url là cách mã hóa dữ liệu thành chuỗi, không phải mã hóa bảo mật (encryption)**. Nếu JWT chỉ được ký dưới dạng JWS, người có token có thể đọc payload, dù không thể sửa hợp lệ nếu không có khóa ký.

> **Điểm cốt lõi:** “Claim được ghi trong token” mô tả một dữ liệu do token mang theo; “claim được tin cậy để ra quyết định” đòi hỏi Resource Server xác minh token, đúng ngữ cảnh, đúng audience, đúng issuer và đúng quy tắc nghiệp vụ.

## 2. Ba nhóm tên claim trong RFC 7519

| Nhóm | Đặc điểm | Cách dùng | Ví dụ |
| --- | --- | --- | --- |
| **Registered Claim Names** | Các tên đã được RFC 7519 định nghĩa với ngữ nghĩa chung. | Dùng để biểu diễn thông tin chuẩn như issuer, audience và thời hạn. | **iss**, **sub**, **aud**, **exp**, **nbf**, **iat**, **jti**. |
| **Public Claim Names** | Các tên do cộng đồng hoặc một hệ thống định nghĩa để dùng rộng rãi; cần **đăng ký tên trong IANA JWT Claims Registry** hoặc sử dụng **tên chống xung đột** (collision-resistant name). | Giúp nhiều thành phần trao đổi claim mà giảm nguy cơ trùng tên mang ý nghĩa khác nhau. | **https://claims.example.test/tenant_id** (minh họa namespace thuộc tổ chức kiểm soát). |
| **Private Claim Names** | Tên do các bên phát hành và tiêu thụ JWT **tự thỏa thuận**; tên không đảm bảo duy nhất toàn cầu. | Phục vụ dữ liệu nghiệp vụ của một hệ thống hoặc nhóm ứng dụng. | **tenant_id**, **roles**, **permissions**, **department_code**. |

**Registered**, **public** và **private** ở đây nói về **tên và phạm vi quy ước**, không nói về mức bí mật của giá trị:

- Một **public claim** không có nghĩa nội dung được phép công khai cho người ngoài.
- Một **private claim** không có nghĩa nội dung được mã hóa hoặc mặc nhiên bí mật.
- Một **registered claim** không có nghĩa giá trị được framework kiểm tra trong mọi trường hợp.

RFC 7519 cố ý không bắt buộc mọi JWT có đủ bảy registered claims. **Một profile cụ thể** như OIDC ID Token hoặc JWT Access Token mới quy định những trường nào bắt buộc và cần kiểm tra ra sao.

### 2.1. “Được định nghĩa trong tiêu chuẩn” khác “thuộc bảy registered claims gốc”

Nhiều tiêu chuẩn và hệ thống còn dùng các tên claim khác:

- OIDC định nghĩa các claim liên quan đăng nhập như **auth_time**, **nonce**, **acr**, **amr** và các claim hồ sơ như **name**, **email**, **email_verified**.
- OAuth 2.0 Access Token profile dạng JWT (RFC 9068) định nghĩa cách biểu diễn các claim dành cho Resource Server, bao gồm những tên như **client_id** và **scope**.
- Nhà cung cấp có thể dùng **scp**, **realm_access**, **groups**, **roles** hoặc tên có namespace tùy thiết kế.

Một số claim từ tiêu chuẩn mở rộng có thể đã được đăng ký trong **IANA JWT Claims Registry**. Vì vậy, cách gọi chính xác hơn là: **bảy registered claims gốc của RFC 7519** và **các claim được định nghĩa/đăng ký bởi profile mở rộng**. Không nên cho rằng mọi claim ngoài bảy tên đầu tiên đều “private”, cũng không nên tin rằng một tên quen thuộc luôn có cùng kiểu dữ liệu ở mọi nhà phát hành.

## 3. Bảy registered claims trong RFC 7519

### 3.1. Bảng tổng quan

| Claim | Tên đầy đủ | Giá trị điển hình | Ý nghĩa thực tế |
| --- | --- | --- | --- |
| **iss** | Issuer | Chuỗi, thường là HTTPS URL của Authorization Server | Ai phát hành JWT? |
| **sub** | Subject | Chuỗi định danh chủ thể | JWT đang nói về ai/cái gì? |
| **aud** | Audience | Chuỗi **hoặc mảng chuỗi** | JWT dành cho bên nhận nào? |
| **exp** | Expiration Time | **NumericDate** | Kể từ thời điểm nào JWT không còn được chấp nhận? |
| **nbf** | Not Before | **NumericDate** | Sớm nhất từ lúc nào JWT được chấp nhận? |
| **iat** | Issued At | **NumericDate** | JWT đã được phát hành khi nào? |
| **jti** | JWT ID | Chuỗi định danh JWT | Mã định danh riêng của token, có thể hỗ trợ theo dõi/kiểm soát phát lại. |

### 3.2. **iss** — Issuer

~~~json
{
  "iss": "https://idp.example.test/realms/training"
}
~~~

**iss** xác định bên phát hành JWT. Trong Spring Security JWT Resource Server, **issuer-uri** thường dùng để khai báo bên phát hành đáng tin cậy:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/training
~~~

Resource Server phải xác minh **iss** theo cấu hình tin cậy; **không** lấy tùy ý URL **iss** của một token chưa xác minh rồi tự động tin cậy mọi issuer mà client gửi. Khi nhiều tenant có issuer riêng, hệ thống cần cơ chế chọn issuer đã được kiểm soát và giới hạn bởi danh sách nguồn phát hành tin cậy.

### 3.3. **sub** — Subject

~~~json
{
  "sub": "user-123"
}
~~~

**sub** biểu diễn chủ thể của JWT. Trong OIDC ID Token, nó là định danh người dùng mà OpenID Provider phát hành cho Relying Party theo quy tắc OIDC. Trong JWT Access Token, nó có thể đại diện người dùng hoặc một chủ thể khác tùy grant và profile phát hành; chẳng hạn luồng máy với máy không có người dùng đang tương tác.

Đừng dùng **sub** đơn lẻ làm định danh toàn cầu của mọi tài khoản: giá trị **sub** cần được diễn giải **trong ngữ cảnh issuer**, thường kết hợp **(iss, sub)** khi liên kết với người dùng nội bộ. Đặc biệt, **email** có thể thay đổi hoặc không được xác minh, nên không mặc định thay thế cho **sub**.

### 3.4. **aud** — Audience

~~~json
{
  "aud": "orders-api"
}
~~~

Hoặc:

~~~json
{
  "aud": ["orders-api", "reports-api"]
}
~~~

**aud** cho biết JWT dành cho bên nhận nào. Theo RFC 7519, audience có thể là **một chuỗi** hoặc **mảng chuỗi**; API phải xử lý đúng cả hai dạng. Tại Resource Server tên **orders-api**, việc kiểm tra chỉ chấp nhận token có audience dành cho **orders-api** giúp ngăn **token substitution**: dùng token dành cho ứng dụng khác để gọi API này.

Ví dụ: OIDC **ID Token** thường có **aud** chứa **client_id** của web client; JWT **Access Token** dành cho API cần audience tương ứng Resource Server. Cả hai có thể được ký bởi cùng một issuer, nhưng không vì vậy mà API nên nhận ID Token làm Bearer Access Token.

### 3.5. **exp** — Expiration Time

~~~json
{
  "exp": 1893456000
}
~~~

**exp** là thời điểm hết hạn. Theo ngữ nghĩa RFC 7519, token **không được chấp nhận vào hoặc sau thời điểm exp**, trừ mức chênh lệch đồng hồ nhỏ được validator cho phép. Giá trị phải là **NumericDate**, không phải chuỗi ngày tháng tự do.

Một số lỗi phổ biến:

- Nhầm **giây** với **mili-giây**, khiến thời gian hiệu lực bị sai nghiêm trọng.
- Chỉ decode payload rồi kiểm tra **exp**, bỏ qua chữ ký hoặc issuer.
- Dùng token đã hết hạn rồi kỳ vọng Resource Server tự làm mới token; **refresh token** thuộc trách nhiệm và luồng của OAuth 2.0 Client, không phải mặc định của API.

### 3.6. **nbf** — Not Before

~~~json
{
  "nbf": 1893452400
}
~~~

**nbf** đặt thời điểm **sớm nhất** token có thể được chấp nhận. Một token chưa đến **nbf** phải bị từ chối theo ngữ nghĩa claim, có thể xét mức clock skew nhỏ được cấu hình. Một số hệ thống bỏ qua claim này khi không có, nhưng nếu có thì validator cần xử lý đúng theo profile.

### 3.7. **iat** — Issued At

~~~json
{
  "iat": 1893452400
}
~~~

**iat** cho biết thời điểm JWT được phát hành. Claim này hữu ích cho việc tính tuổi token hoặc chính sách “chỉ nhận token mới”. **iat không đồng nghĩa exp**; bản thân có iat không đặt ra thời hạn hết hiệu lực. Hệ thống cũng không nên tự giả định “cứ có iat là token hợp lệ”.

### 3.8. **jti** — JWT ID

~~~json
{
  "jti": "order-access-b97c0f41"
}
~~~

**jti** là định danh token do issuer cấp; giá trị nên có xác suất trùng rất thấp theo quy tắc của JWT. Nó có thể được sử dụng cho cơ chế:

- Chống phát lại (**replay prevention**) với yêu cầu **một lần sử dụng**.
- Danh sách từ chối (**denylist**) để hỗ trợ vô hiệu hóa token cụ thể.
- Liên kết hoạt động của token trong một hệ thống kiểm soát chặt chẽ.

**Chỉ có jti trong payload không tự ngăn replay**. API phải có trạng thái lưu trữ hoặc cơ chế xác minh riêng nếu muốn từ chối một **jti** đã được sử dụng. Với Access Token Bearer thông thường được dùng nhiều lần trong thời hạn, việc “chỉ cho phép jti sử dụng một lần” thường không phù hợp nếu không được thiết kế ngay từ đầu.

### 3.9. NumericDate và đồng hồ

**exp**, **nbf** và **iat** sử dụng **NumericDate**: số giây tính từ **1970-01-01T00:00:00Z**, không tính giây nhuận theo định nghĩa của RFC. NumericDate có thể là số nguyên hoặc số không nguyên; hệ thống thường phát hành số nguyên. Ví dụ:

~~~json
{
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
~~~

Token minh họa này có khoảng hiệu lực danh nghĩa **một giờ**, nếu các điều kiện khác đều hợp lệ. Resource Server cần có đồng hồ được đồng bộ; **clock skew** nhỏ có thể bù sai lệch giờ hệ thống nhưng không nên kéo dài một cách tùy tiện thời hạn token.

## 4. Public claims: đặt tên để nhiều hệ thống hiểu giống nhau

RFC 7519 cho phép các bên định nghĩa claim mới để dùng công khai hoặc trao đổi với nhiều bên. Để tránh va chạm, tên claim mới nên đi theo một trong hai hướng:

1. **Đăng ký tên và ngữ nghĩa** tại **IANA JSON Web Token Claims Registry**, qua quy trình đăng ký phù hợp.
2. Sử dụng **collision-resistant name** do đơn vị định nghĩa kiểm soát; chẳng hạn tên có namespace dựa trên một domain do tổ chức sở hữu.

Ví dụ ứng dụng muốn biểu diễn định danh tổ chức (tenant) khi chia sẻ Access Token cho nhiều API:

~~~json
{
  "https://claims.example.test/tenant_id": "tenant-42",
  "https://claims.example.test/account_tier": "enterprise"
}
~~~

Đây là **tên claim dạng chuỗi**, không bắt buộc là URL đang tồn tại hay endpoint để API gọi. Điểm chính là phần namespace gắn với domain tổ chức kiểm soát, giảm nguy cơ bên khác tình cờ định nghĩa tên trùng mà mang nghĩa khác. Ví dụ dùng domain **example.test** chỉ để minh họa.

Không dùng namespace của domain không thuộc quyền kiểm soát của hệ thống phát hành. Cũng đừng tự đặt một tên “có vẻ chuẩn” rồi giả định mọi Authorization Server sẽ hiểu. Với claim trao đổi giữa nhiều đối tác, nên công bố tài liệu rõ:

| Trường định nghĩa | Ví dụ |
| --- | --- |
| Tên claim | **https://claims.example.test/tenant_id** |
| Kiểu JSON | **string** |
| Ý nghĩa | ID của tenant mà token được cấp quyền truy cập |
| Phạm vi giá trị | Các tenant do nhà phát hành quản lý |
| Có thể thiếu? | Không, đối với profile API nhiều tenant này |
| Quy tắc xác minh | Phải khớp tenant trong đường dẫn/tài nguyên và quyền của chủ thể |
| Nguồn phát hành | Chỉ Authorization Server tin cậy được phép gắn claim |
| Phiên bản/tương thích | Quy ước duy trì ổn định; có quy trình đổi schema |

“Tên chống xung đột” chỉ bảo đảm **khả năng phân biệt tên**, không có tác dụng tự động bảo vệ dữ liệu. API vẫn phải kiểm tra chữ ký, issuer, audience và tính hợp lệ của giá trị.

## 5. Private claims: giao kèo nội bộ giữa issuer và Resource Server

Các nhóm phát triển thường cần mang dữ liệu miền nghiệp vụ trong JWT:

~~~json
{
  "tenant_id": "tenant-42",
  "roles": ["ORDER_READER", "ORDER_EDITOR"],
  "permissions": ["order:read", "order:edit"],
  "department_code": "SALES"
}
~~~

Những tên như **tenant_id**, **roles**, **permissions**, **department_code** có thể là **private claim names** nếu các bên tự thỏa thuận mà không đăng ký hoặc đặt tên theo cơ chế tránh xung đột. Chúng thuận tiện trong một hệ thống do cùng nhóm quản lý, nhưng đi kèm các giới hạn:

- **Không có kiểu dữ liệu và ngữ nghĩa tự động thống nhất.** Một issuer có thể phát hành **roles** là mảng chuỗi, issuer khác có thể là chuỗi chứa dấu cách hoặc object lồng nhau.
- **Tên dễ va chạm.** Hai sản phẩm cùng đặt **tenant_id** nhưng định nghĩa tenant khác nhau.
- **Không tự gắn với quyền truy cập.** Claim **roles: ["ADMIN"]** không có nghĩa user được quản trị mọi API; phải xác định ADMIN thuộc ứng dụng, tenant và phạm vi nào.
- **Không tự bí mật.** JWT ký số có thể giải mã payload; không đặt dữ liệu nhạy cảm quá mức vào claims.
- **Có thể cũ trước khi token hết hạn.** Nếu vai trò hoặc tenant membership thay đổi giữa hai lần cấp token, một Access Token còn sống có thể mang quyền cũ nếu kiến trúc không có cơ chế cập nhật hoặc kiểm soát thu hồi.

Tên private claim nên được mô tả thành **contract** giữa Authorization Server và Resource Server. Tối thiểu cần xác định tên, JSON type, miền giá trị, điều kiện thiếu/null, ai được phát hành, chính sách xác thực, thời hạn cập nhật và cách version khi đổi nghĩa.

### 5.1. Vì sao không cho client tự gửi claim để API tin?

Ví dụ HTTP request sau **không** tạo ra quyền quản trị:

~~~http
GET /api/admin/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
X-User-Role: ADMIN
~~~

Header **X-User-Role** do client tùy ý gửi không phải claim đã được Authorization Server bảo vệ bằng chữ ký. Nếu API cần role, nó phải lấy role từ **Access Token đã xác thực** hoặc một nguồn chính sách tin cậy khác, đồng thời đối chiếu với tài nguyên và tenant thực tế.

Kể cả role nằm trong JWT đã ký hợp lệ, API vẫn cần kiểm tra **token dành cho chính API**, **issuer** được tin cậy và **ngữ nghĩa của role** mà issuer đã thống nhất với API.

## 6. Phân biệt claims trong OIDC ID Token và OAuth 2.0 Access Token

Một điểm dễ nhầm trong chủ đề **JWT và JOSE** là JWT không tự mang nhãn “dùng cho login” hay “dùng cho API” chỉ nhờ việc có **sub** và **email**. Cần xem **token profile**, **audience** và mục đích phát hành.

### 6.1. ID Token của OIDC Client

Payload ID Token minh họa:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1893452400,
  "exp": 1893456000,
  "auth_time": 1893452000,
  "nonce": "nonce-created-by-client",
  "email": "user@example.test",
  "email_verified": true
}
~~~

OIDC Client sử dụng ID Token để xử lý kết quả đăng nhập theo quy tắc OIDC, bao gồm xác minh chữ ký, issuer, audience, thời hạn và **nonce** khi yêu cầu. Các trường hồ sơ như email có thể xuất hiện tùy scope, claims request và chính sách của nhà cung cấp.

**email_verified: true** chỉ phản ánh thông tin xác minh địa chỉ email theo nhà phát hành; **không phải quyền truy cập API**. **sub** là định danh đáng tin cậy hơn email cho liên kết tài khoản trong ngữ cảnh issuer.

### 6.2. JWT Access Token dành cho Resource Server

Payload JWT Access Token minh họa:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "jti": "access-6a45d9",
  "client_id": "orders-web",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-42"
}
~~~

API **orders-api** xác minh Access Token và chỉ cho phép hành động tương ứng scope, tenant và chính sách. Trong nhiều hệ thống, Spring Security tự ánh xạ scope từ **scope** hoặc **scp** thành authority có tiền tố **SCOPE_**, ví dụ **SCOPE_orders.read**. Spring Security **không** tự hiểu rằng claim riêng **tenant_id**, **roles** hoặc **permissions** phải dẫn đến quyền gì nếu ứng dụng chưa định nghĩa quy tắc.

**Hai token có thể cùng issuer và sub nhưng audience khác nhau.** Không gửi ID Token vào **Authorization: Bearer** thay Access Token; Resource Server phải kiểm tra JWT được phát hành cho tài nguyên mà nó bảo vệ. Các profile đặc thù còn có thể yêu cầu kiểm tra **typ**, chẳng hạn **at+jwt** trong RFC 9068; trường này thuộc JOSE Header, không phải payload.

### 6.3. Một số tên claim hay gặp và cách đọc đúng

| Claim | Ý nghĩa điển hình | Điều cần nhớ |
| --- | --- | --- |
| **scope** | Danh sách quyền OAuth 2.0, thường là chuỗi cách nhau bởi dấu cách. | Không thuộc bảy registered claims gốc của RFC 7519; ý nghĩa phụ thuộc profile phát hành. |
| **scp** | Một cách biểu diễn scope được một số nhà cung cấp sử dụng. | Kiểm tra schema của issuer; không giả định kiểu luôn giống **scope**. |
| **client_id** | Client được cấp token theo profile áp dụng. | Có thể giúp định danh client, nhưng không thay thế **aud** của Resource Server. |
| **azp** | Authorized party theo OIDC, dùng trong các trường hợp ID Token liên quan nhiều audience. | Không hoán đổi với **aud** hay tự suy ra quyền API. |
| **auth_time** | Thời điểm người dùng xác thực với OpenID Provider. | Khác **iat** là thời điểm phát hành token. |
| **nonce** | Giá trị liên kết kết quả OIDC Login với yêu cầu xác thực của client. | Không phải access scope, cũng không tự thực hiện kiểm tra replay trên API. |
| **email** / **email_verified** | Thông tin danh tính người dùng theo OIDC. | Không suy ra role/quyền; hạn chế dữ liệu cá nhân trong Access Token. |
| **roles** / **permissions** | Role hoặc permission theo hệ thống. | Có thể là private claims; cần quy ước và ánh xạ tường minh. |
| **tenant_id** | Tenant ứng dụng mà token gắn với. | Phải xác minh tương quan giữa token và tài nguyên, không chỉ đọc ra để hiển thị. |

## 7. Kiểm tra claim ở Spring Security Resource Server

Trong Spring Security Servlet, **oauth2ResourceServer().jwt()** dùng cơ chế Bearer authentication và **JwtDecoder**. Resource Server cần một chuỗi kiểm tra:

~~~text
HTTP Authorization: Bearer ...
               |
               v
      BearerTokenAuthenticationFilter
               |
               v
         JWT verification
   - Chữ ký / khóa / thuật toán hợp lệ
   - Thời hạn hợp lệ
   - Issuer hợp lệ
   - Audience dành cho API
   - Quy tắc claim của profile
               |
               v
       JwtAuthenticationToken
               |
               v
       Authorization rules
   - Scope/authority đúng thao tác
   - Tenant và quyền tài nguyên
   - Chính sách nghiệp vụ khác
               |
        +------+------+
        |             |
      Cho phép      Từ chối
~~~

### 7.1. Cấu hình issuer và audience

Ví dụ Spring Boot với JWT Access Token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/training
          audiences:
            - orders-api
~~~

Trên các phiên bản Spring Boot hỗ trợ **audiences**, cấu hình này yêu cầu **aud** của JWT chứa **orders-api**. Nếu dự án dùng phiên bản không hỗ trợ thuộc tính hoặc cần quy tắc cụ thể, có thể khai báo **JwtDecoder** với validator riêng.

Ví dụ Java dùng một decoder và thêm validator kiểm tra audience:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtClaimValidationConfig {

    private static final String ISSUER =
        "https://idp.example.test/realms/training";
    private static final String API_AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(API_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "JWT is not intended for this resource server",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

**JwtValidators.createDefaultWithIssuer** giữ các điều kiện chuẩn về issuer và thời hạn. Validator tùy chỉnh bổ sung yêu cầu audience. Ví dụ này dùng constant minh họa; ứng dụng thật nên đọc issuer và audience từ cấu hình quản lý theo môi trường, đồng thời xác minh chính sách thuật toán/chữ ký của JWT.

Nếu cùng một dự án có cả cấu hình thuộc tính **audiences** và bean decoder tự định nghĩa, cần hiểu **bean tùy chỉnh có thể thay cơ chế auto-configuration**. Đảm bảo quy tắc kiểm tra audience thực sự nằm trong decoder đang được sử dụng; đừng tin rằng chỉ khai báo YAML là mọi decoder tự động áp dụng.

### 7.2. Kiểm tra kiểu dữ liệu và ngữ nghĩa của private claim

Trong API nhiều tenant, ví dụ:

~~~json
{
  "tenant_id": "tenant-42",
  "roles": ["ORDER_READER"]
}
~~~

Resource Server cần xác định:

- **tenant_id** có phải string không? Có trống hoặc null không?
- **tenant_id** có thuộc phạm vi quyền của chủ thể đã xác thực không?
- URL **/api/tenants/{tenantId}/orders** đang yêu cầu tenant nào? Token có cho phép truy cập tenant đó không?
- **roles** là mảng string hay định dạng khác? Role có được issuer này phát hành cho ứng dụng này hay không?

Ví dụ controller lấy claims từ JWT **đã được Spring Security xác thực**:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@RestController
@RequestMapping("/api/tenants")
public class TenantOrderController {

    @GetMapping("/{tenantId}/orders")
    Map<String, Object> orders(
            @PathVariable String tenantId,
            @AuthenticationPrincipal Jwt jwt) {

        String tokenTenant = jwt.getClaimAsString("tenant_id");
        if (tokenTenant == null || !tokenTenant.equals(tenantId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        // Phải kiểm tra scope/permission trong SecurityFilterChain
        // và quyền trên dữ liệu ở lớp nghiệp vụ khi cần.
        return Map.of("tenantId", tenantId, "orders", new String[0]);
    }
}
~~~

Đây là ví dụ **đối chiếu tenant cơ bản**, không phải thiết kế đa tenant hoàn chỉnh. Trong ứng dụng thật, tenant thường phải được đối chiếu với quyền sở hữu tài nguyên và chính sách cấp quyền; không cho người dùng chỉ cần đổi **tenant_id** do client gửi trong header tự do là có quyền.

### 7.3. Ánh xạ scope thành authority

Ví dụ SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/tenants/*/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Trong cấu hình mặc định phổ biến, claim **scope: "orders.read orders.write"** dẫn đến authorities **SCOPE_orders.read** và **SCOPE_orders.write**. Tên quyền phải khớp với token profile thực tế. Đoạn cấu hình tắt CSRF chỉ minh họa cho API xác thực qua Bearer header, không dùng session cookie làm credential; với web đăng nhập cookie cần chính sách CSRF tương ứng.

**Private claim roles không tự trở thành ROLE_...**. Nếu muốn dùng **roles**, lập trình viên phải cấu hình **JwtAuthenticationConverter**, hoặc kiểm tra role theo mô hình authorization khác. Không thay thế kiểm tra quyền trên dữ liệu bằng một phép so sánh role chung chung.

### 7.4. Ánh xạ roles tự định nghĩa một cách tường minh

Ví dụ một API thật sự có contract **roles** là mảng các tên role (không có tiền tố **ROLE_**):

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public class CustomJwtAuthorities {

    public static Converter<Jwt, AbstractAuthenticationToken> converter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

        return jwt -> {
            Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopeConverter.convert(jwt));

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    if ("ORDER_READER".equals(role) ||
                        "ORDER_EDITOR".equals(role)) {
                        authorities.add(
                            new SimpleGrantedAuthority("ROLE_" + role));
                    }
                }
            }
            return new JwtAuthenticationToken(
                jwt, authorities, jwt.getSubject());
        };
    }
}
~~~

Trong SecurityFilterChain của ví dụ trước, có thể thay:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .jwt(jwt -> jwt.jwtAuthenticationConverter(
        CustomJwtAuthorities.converter())))
~~~

Đoạn thay thế là một phần của **DSL cấu hình HttpSecurity**, không phải chương trình Java hoàn chỉnh đứng riêng. Cơ chế này vẫn giữ scope authorities mặc định và chỉ ánh xạ những role được ứng dụng biết rõ. Nếu sử dụng **hasRole("ORDER_READER")**, Spring Security thường so khớp authority **ROLE_ORDER_READER**. Quy ước role cần rõ ràng: tránh cấp quyền rộng từ một chuỗi **ADMIN** mà không xét phạm vi dịch vụ hoặc tenant.

## 8. Thiết kế schema claims an toàn và bền vững

### 8.1. Quy định tên, kiểu và nguồn phát hành

Trước khi đưa claim mới vào Access Token, nên trả lời:

1. **Ai là chủ sở hữu tên?** Claim dùng nội bộ hay phải chia sẻ giữa nhiều tổ chức? Có cần tên namespace chống xung đột không?
2. **Kiểu JSON là gì?** String, number, boolean, array hay object? Một tên claim phải giữ kiểu nhất quán qua các phiên bản token.
3. **Giá trị có ngữ nghĩa gì?** Ví dụ role có áp dụng cho ứng dụng, tenant, resource hoặc toàn tổ chức?
4. **Ai được gắn claim?** Claim phải được Authorization Server hoặc nguồn tin cậy gán và được bảo vệ qua cơ chế token phù hợp.
5. **Claim bắt buộc hay tùy chọn?** Khi thiếu hoặc sai kiểu, API chấp nhận hay từ chối? Quy tắc phải được định nghĩa trước.
6. **Thông tin có thể thay đổi nhanh không?** Vai trò, quyền và tenant membership có thể cũ trước lúc token hết hạn.
7. **Dữ liệu có nhạy cảm không?** Token không nên chứa thông tin cá nhân hoặc bí mật không cần thiết.
8. **Có cần đổi schema trong tương lai không?** Định nghĩa chiến lược tương thích và version cho producer lẫn consumer.

### 8.2. Không dùng claim như một cơ sở dữ liệu

JWT có thể được Resource Server xác minh cục bộ nên hấp dẫn khi nhét nhiều thông tin vào token. Nhưng claims quá lớn hoặc quá nhiều dữ liệu cá nhân gây ra:

- Tăng dung lượng HTTP header cho mọi request.
- Tăng nguy cơ lộ thông tin khi token bị sao chép, log hoặc gửi nhầm audience.
- Thông tin cấp quyền có thể không cập nhật kịp nếu vai trò/tenant membership thay đổi.
- Kết hợp dữ liệu từ các ngữ cảnh gây khó xác định nguồn sự thật.

Nên giữ JWT đủ thông tin cho xác thực và quyết định quyền đã được thiết kế. Với dữ liệu nghiệp vụ cần tính hiện thời hoặc nhạy cảm, API có thể truy vấn nguồn dữ liệu tin cậy sau khi xác thực.

### 8.3. Tránh xung đột giữa issuer và profile

Ví dụ hai issuer cùng gửi:

~~~json
{
  "roles": ["ADMIN"]
}
~~~

Một hệ thống có thể hiểu **ADMIN** là quản trị đơn hàng; hệ thống khác lại hiểu là quản trị toàn bộ tài khoản. Nếu Resource Server cho phép nhiều issuer, không thể chỉ “gộp role” mà bỏ qua **issuer, audience và quy ước mapping cho từng bên**.

Một chiến lược rõ ràng có thể là:

- Với **registered claim**, dùng đúng ý nghĩa theo RFC và profile.
- Với claim tiêu chuẩn do OIDC hoặc JWT Access Token profile định nghĩa, thực hiện đúng yêu cầu profile.
- Với claim chia sẻ liên tổ chức, ưu tiên tên đã đăng ký hoặc namespace chống xung đột.
- Với claim nội bộ, có contract và mapping riêng theo issuer, tenant, resource.

### 8.4. Không tin payload trước khi xác minh

Payload sau có thể được tạo bằng bất kỳ công cụ soạn JSON nào:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "attacker",
  "aud": "orders-api",
  "scope": "orders.admin",
  "roles": ["ADMIN"]
}
~~~

Nếu thiếu chữ ký hợp lệ và các ràng buộc thời hạn, payload đó **không phải bằng chứng được Authorization Server cấp quyền**. API phải dựa vào JwtDecoder/validator được cấu hình đúng và không tự giải mã Base64url rồi tin claims. Header **alg** của token cũng không phải lời bảo đảm; verifier phải kiểm soát thuật toán cho phép và khóa tin cậy.

Khi sử dụng nhiều loại JWT (ID Token, Access Token, token nội bộ), nên có quy tắc chống **cross-JWT confusion**: yêu cầu audience, issuer và token profile/type thích hợp với từng loại endpoint, tránh chấp nhận nhầm token phục vụ mục đích khác.

## 9. Ví dụ phân tích một JWT khi xử lý lỗi 401/403

Giả sử Resource Server **orders-api** nhận JWT đã được ký hợp lệ. Ta quan sát claims:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["inventory-api"],
  "exp": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

Token có **scope: orders.read**, nhưng **aud** chỉ chứa **inventory-api**. **orders-api phải từ chối token** vì không dành cho API này. Scope đúng không sửa được lỗi audience.

Với token thứ hai:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

Nếu chữ ký, issuer và thời hạn hợp lệ tại thời điểm yêu cầu, token có thể đi qua bước authentication. Nhưng nếu URL là **/api/tenants/tenant-99/orders**, API cần từ chối truy cập theo ràng buộc tenant và chính sách quyền trên tài nguyên; có scope đọc không cho phép đọc tenant bất kỳ.

Đối với token thứ ba:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "profile.read",
  "tenant_id": "tenant-42"
}
~~~

Token này có thể được xác thực hợp lệ nhưng **thiếu scope orders.read**, do đó request đọc đơn hàng sẽ bị chặn ở bước authorization. Trong cấu hình API thông thường, **token thiếu hoặc không hợp lệ** cho kết quả **401 Unauthorized**, còn **token hợp lệ nhưng không đủ quyền** cho kết quả **403 Forbidden**.

Các ví dụ trên là payload minh họa. Đừng dán JWT thật vào ticket, log hoặc công cụ online công khai để debug: **Bearer Token là credential nhạy cảm** ngay cả khi có thể xem payload.

## 10. Những hiểu nhầm cần tránh

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Registered claim luôn bắt buộc.” | Các tên có ngữ nghĩa chuẩn; tính bắt buộc phụ thuộc token profile và ứng dụng. |
| “Public claim có dữ liệu công khai.” | Public/private nói về cơ chế đặt **tên**, không biểu thị bí mật của **giá trị**. |
| “Private claim được mã hóa.” | Không; private claim chỉ là tên do các bên tự thỏa thuận. JWT dạng JWS có payload đọc được. |
| “JWT có sub và email là ID Token.” | Những claims này không xác định đầy đủ mục đích. Cần kiểm tra token profile và audience. |
| “JWT có aud đúng là được phép thực hiện mọi việc.” | Audience là điều kiện dành cho bên nhận; vẫn cần scope/role và kiểm tra quyền tài nguyên. |
| “Có jti nên không thể replay.” | Phải có cơ chế lưu trạng thái/kiểm tra jti và chính sách dùng một lần nếu muốn chống replay. |
| “iat là lúc token hết hạn.” | **iat** là lúc phát hành; **exp** là lúc hết hạn. |
| “scope và roles luôn giống nhau.” | Scope OAuth và role nghiệp vụ có thể khác nhau về nguồn phát hành, tên, phạm vi và cách kiểm tra. |
| “Spring Security tự hiểu mọi claim custom.” | Chỉ có mapping mặc định cho một số claim như scope; private claims cần contract, validator và authorization riêng. |
| “Chỉ decode JWT là đọc được quyền tin cậy.” | Phải xác minh chữ ký, issuer, audience, thời hạn, profile và quyền API. |

## 11. Bài thực hành nhận diện claim

Đọc JWT Claims Set sau:

~~~json
{
  "iss": "https://idp.example.test/realms/training",
  "sub": "worker-7",
  "aud": ["billing-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "jti": "billing-2026-001",
  "scope": "invoices.read",
  "https://claims.example.test/region": "apac",
  "cost_center": "FIN-01",
  "roles": ["BILLING_READER"]
}
~~~

**Câu hỏi:**

1. Những trường nào thuộc bảy registered claims của RFC 7519?
2. Trường nào minh họa **public claim name** chống xung đột bằng namespace?
3. Những trường nào minh họa **private claims** do hệ thống tự quy ước?
4. Nếu API **orders-api** nhận token này, chỉ nhìn audience thì nên xử lý ra sao?
5. **jti** có đảm bảo một Bearer Access Token chỉ dùng được một lần không?

**Gợi ý đáp án:** (1) **iss**, **sub**, **aud**, **exp**, **iat**, **jti**; (2) **https://claims.example.test/region**; (3) **cost_center** và **roles**; **scope** là tên claim được định nghĩa trong các ngữ cảnh OAuth/JWT Access Token profile, không phải một trong bảy registered claims gốc; (4) **orders-api** phải từ chối token không có audience của mình; (5) **không**, muốn chống replay cần cơ chế và chính sách kiểm soát bổ sung.

## 12. Ghi nhớ

Ba nhóm claim của JWT giúp phân biệt **nguồn gốc và quy tắc đặt tên**:

1. **Registered claims** có ngữ nghĩa chuẩn trong RFC 7519: **iss**, **sub**, **aud**, **exp**, **nbf**, **iat**, **jti**.
2. **Public claims** nên được đăng ký hoặc đặt bằng namespace chống xung đột để nhiều hệ thống hiểu cùng một nghĩa.
3. **Private claims** do các bên tự quy ước; rất hữu ích cho nghiệp vụ nhưng phải có contract và mapping rõ.

Với **Spring Security Resource Server**, cần thực hiện cả **token validation** (chữ ký, issuer, audience, thời hạn, token profile) và **authorization** (scope, role, tenant, quyền trên tài nguyên). Không thể bỏ một trong hai chỉ vì JWT chứa nhiều claims.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 4: JWT Claims](https://www.rfc-editor.org/rfc/rfc7519#section-4).
- [IANA — JSON Web Token (JWT) Claims Registry](https://www.iana.org/assignments/jwt/jwt.xhtml).
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).

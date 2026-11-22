# Discovery, issuer metadata và địa chỉ JWKS đáng tin cậy

## 1. Vì sao Resource Server cần Discovery?

Trong hệ thống OAuth 2.0 và OpenID Connect (OIDC), một API cần xác minh token thường phải biết trước:

- Issuer nào được tin cậy?
- Issuer công bố metadata ở đâu?
- API lấy khóa công khai để xác minh chữ ký JWT từ địa chỉ nào?
- Những endpoint và khả năng giao thức nào thuộc về Authorization Server hoặc OpenID Provider?
- Khi khóa ký thay đổi, API cập nhật khóa mới bằng cách nào?

Nếu mỗi dịch vụ tự cấu hình thủ công issuer, địa chỉ khóa và endpoint, cấu hình có thể lệch nhau hoặc trở nên lỗi thời. **Discovery** cung cấp một cách công bố metadata có cấu trúc để client và resource server tìm thông tin cần thiết từ một issuer đã được tin cậy.

Ví dụ một JWT access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "exp": 1900003600
}
~~~

Khi nhận token, Billing API cần xác minh chữ ký. API có thể lấy khóa công khai từ một JSON Web Key Set (JWKS) được issuer công bố. Nhưng API không được tìm một URL khóa tùy ý chỉ vì token hoặc request nói rằng URL đó đáng tin. API cần có một **trust anchor** ban đầu, xác định issuer nào được phép và cách lấy metadata của issuer đó.

Quy tắc cốt lõi:

> **Discovery chỉ an toàn khi bắt đầu từ issuer đã được tin cậy. Metadata và JWKS nhận được phải được kiểm tra theo trust policy trước khi dùng để xác minh token.**

Bài này thuộc phạm vi Security chung của OAuth 2.0, OpenID Connect và JWT. Nội dung áp dụng cho client, API Gateway, resource server và dịch vụ phân tán, không phụ thuộc ngôn ngữ lập trình hoặc framework cụ thể.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Issuer** | Bên phát hành token và chịu trách nhiệm cho các claims trong token. | https://identity.example.test |
| **Issuer identifier** | Định danh URI của issuer; cần so khớp theo hợp đồng và chuẩn tương ứng. | Giá trị iss đã cấu hình. |
| **Discovery endpoint** | Địa chỉ trả về metadata của OpenID Provider hoặc Authorization Server. | /.well-known/openid-configuration |
| **Issuer metadata** | Tài liệu mô tả issuer và các endpoint/capability mà issuer công bố. | issuer, authorization_endpoint, token_endpoint, jwks_uri. |
| **JWKS URI** | Endpoint cung cấp tập JSON Web Keys. | https://identity.example.test/keys |
| **JWKS** | JSON Web Key Set chứa các JWK, thường là khóa công khai dùng xác minh chữ ký. | Tập RSA hoặc EC public keys. |
| **JWK** | Một JSON Web Key biểu diễn một khóa mật mã cùng thuộc tính của nó. | kty, kid, use, alg, n, e. |

Các khái niệm này liên quan theo luồng:

~~~text
Issuer đã được tin cậy
       |
       v
Discovery endpoint
       |
       v
Issuer metadata
       |
       +---- issuer
       |
       +---- jwks_uri
                  |
                  v
              JWKS document
                  |
                  v
             Public signing keys
                  |
                  v
             JWT signature validation
~~~

Discovery không tự xác thực người dùng, không cấp quyền cho client và không chứng minh một request được phép truy cập tài nguyên. Nó cung cấp metadata để các bên cấu hình và xác minh giao thức đúng cách.

## 3. Trust bootstrap: phải biết tin issuer nào trước khi Discovery

Một câu hỏi quan trọng là: nếu Discovery dùng để tìm metadata, làm thế nào biết URL Discovery nào là đáng tin?

Hệ thống cần một **trust bootstrap**: nguồn đáng tin ban đầu để xác định issuer hợp lệ. Nguồn này có thể là:

- Cấu hình do tổ chức quản trị và triển khai.
- Danh mục issuer được phê duyệt.
- Cấu hình tenant được quản lý bởi hệ thống có thẩm quyền.
- Quy trình đăng ký đối tác có xác minh danh tính và quyền kiểm soát domain.
- Một trust framework hoặc federation đã được thiết lập từ trước.

Ví dụ cấu hình:

~~~yaml
trusted_issuers:
  - issuer: https://identity.example.test
    discovery_mode: oidc
    expected_audience:
      - https://api.example.test/billing
    allowed_jwks_hosts:
      - identity.example.test
~~~

Đây là cấu hình ứng dụng minh họa, không phải định dạng chuẩn OIDC. Nó thể hiện rằng issuer và phạm vi host được tin phải đến từ cấu hình quản trị có thẩm quyền.

### 3.1. Không lấy issuer từ JWT chưa xác minh rồi fetch metadata ngay

JWT có thể chứa header và payload đọc được trước khi xác minh chữ ký. Kẻ tấn công có thể tự tạo một JWT giả với:

~~~json
{
  "iss": "http://127.0.0.1:8080/internal",
  "sub": "admin"
}
~~~

Nếu resource server lấy iss chưa xác minh làm URL rồi tự động gọi địa chỉ nội bộ, request xác minh token có thể trở thành một đường **Server-Side Request Forgery (SSRF)**. Kẻ tấn công có thể cố khiến server truy cập loopback, địa chỉ private, metadata service của cloud hoặc endpoint nội bộ.

Quy trình an toàn:

1. Xác định issuer dự kiến từ cấu hình hoặc registry tin cậy.
2. Chỉ tìm metadata cho issuer đã được chấp thuận.
3. Tải metadata qua HTTPS theo chính sách mạng.
4. Kiểm tra trường issuer trong metadata khớp chính xác issuer dự kiến.
5. Lưu metadata và jwks_uri gắn với issuer đó.
6. Khi nhận JWT, xác minh chữ ký bằng khóa của issuer đã chọn, rồi kiểm tra claim iss đúng với issuer dự kiến.

Nếu hệ thống multi-tenant phải chọn issuer dựa trên token, giá trị chưa xác minh chỉ được dùng như **gợi ý tra cứu trong một registry allowlist**. Không biến nó thành URL tự do để server fetch.

### 3.2. Phân biệt trust-on-first-use với issuer được phê duyệt

Tự động tin issuer đầu tiên xuất hiện trong request hoặc token là một dạng trust-on-first-use không có bước xác minh phù hợp. Kẻ tấn công có thể trở thành nguồn tin cậy đầu tiên.

Với hệ thống doanh nghiệp, issuer mới cần quy trình đăng ký, xác minh quyền kiểm soát và phê duyệt trước khi được dùng để xác minh token. Nếu có quy trình dynamic registration hoặc federation, phải áp dụng đúng trust framework của nó.

## 4. Hai cơ chế metadata thường gặp: OIDC Discovery và OAuth AS Metadata

OIDC Discovery và OAuth 2.0 Authorization Server Metadata có mục tiêu gần nhau nhưng tên endpoint và cách tạo URL khác nhau. Không nên tự ghép đường dẫn theo cảm tính.

### 4.1. OpenID Connect Discovery

OpenID Connect Discovery 1.0 sử dụng endpoint well-known:

~~~text
/.well-known/openid-configuration
~~~

Đường dẫn này được nối vào issuer identifier sau khi bỏ dấu slash ở cuối nếu có.

Ví dụ:

~~~text
Issuer:
https://identity.example.test

Discovery URL:
https://identity.example.test/.well-known/openid-configuration
~~~

Với issuer có path:

~~~text
Issuer:
https://identity.example.test/tenant-a

Discovery URL:
https://identity.example.test/tenant-a/.well-known/openid-configuration
~~~

OIDC Discovery metadata mô tả OpenID Provider, có thể gồm issuer, authorization_endpoint, token_endpoint, userinfo_endpoint, jwks_uri, các loại response, subject type, signing algorithm và claims được hỗ trợ.

### 4.2. OAuth 2.0 Authorization Server Metadata

RFC 8414 định nghĩa endpoint:

~~~text
/.well-known/oauth-authorization-server
~~~

Với issuer có path, phần well-known được đặt **giữa authority và path của issuer**.

Ví dụ:

~~~text
Issuer:
https://auth.example.test/issuer1

Metadata URL:
https://auth.example.test/.well-known/oauth-authorization-server/issuer1
~~~

Với issuer không có path:

~~~text
Issuer:
https://auth.example.test

Metadata URL:
https://auth.example.test/.well-known/oauth-authorization-server
~~~

OAuth AS Metadata mô tả Authorization Server và có thể công bố issuer, authorization_endpoint, token_endpoint, jwks_uri, grant types, response types, token endpoint authentication methods và các capability OAuth khác.

### 4.3. Không nhầm hai cách tạo URL

Với issuer https://auth.example.test/issuer1:

| Cơ chế | URL |
| --- | --- |
| OIDC Discovery | https://auth.example.test/issuer1/.well-known/openid-configuration |
| OAuth AS Metadata (RFC 8414) | https://auth.example.test/.well-known/oauth-authorization-server/issuer1 |

Hai URL khác nhau theo đặc tả tương ứng. Client/resource server phải biết mình đang dùng discovery protocol nào và xây dựng endpoint đúng quy tắc.

### 4.4. Chọn đúng metadata cho use case

- Ứng dụng OIDC cần thông tin OpenID Provider có thể dùng OIDC Discovery.
- Client OAuth cần metadata Authorization Server có thể dùng RFC 8414.
- Resource server chỉ cần xác minh access token có thể chỉ cần issuer, audience, JWKS URI và token profile theo hợp đồng.
- Không lấy một trường chỉ có trong OIDC metadata rồi giả định mọi OAuth Authorization Server đều công bố trường đó.

## 5. Đọc và xác minh issuer metadata

Một tài liệu OIDC Discovery minh họa:

~~~json
{
  "issuer": "https://identity.example.test",
  "authorization_endpoint": "https://identity.example.test/authorize",
  "token_endpoint": "https://identity.example.test/token",
  "userinfo_endpoint": "https://identity.example.test/userinfo",
  "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Các trường trong ví dụ là metadata minh họa. Metadata thực tế phải tuân theo đặc tả và profile của issuer.

### 5.1. Kiểm tra issuer trong metadata

Trường issuer trong metadata phải khớp với issuer identifier đã dùng để tìm metadata theo quy tắc của đặc tả. Khi xác minh token, claim iss cũng phải khớp với issuer mà resource server đang xác minh.

Không nên tự ý:

- Bỏ path trong issuer.
- Bỏ hoặc thêm dấu slash ở cuối khi so khớp.
- Đổi hostname sang alias khác.
- Chấp nhận issuer chỉ vì cùng domain gốc.
- So khớp bằng chuỗi con hoặc prefix.

Ví dụ:

~~~text
https://identity.example.test
https://identity.example.test/tenant-a
https://identity.example.test.evil.example
~~~

Đây là ba định danh khác nhau. Không dùng phép so khớp lỏng lẻo khiến issuer ngoài dự kiến được chấp nhận.

### 5.2. Metadata không tự trở thành bằng chứng danh tính chỉ vì là JSON

Metadata thường được lấy qua HTTPS từ endpoint well-known. TLS bảo vệ kênh kết nối tới host được xác minh; metadata JSON thông thường không tự có chữ ký JWT độc lập.

Vì vậy, trust phụ thuộc vào:

- Issuer đã được phê duyệt trước.
- TLS certificate và hostname được xác minh đúng.
- DNS và đường mạng không bị điều hướng sang endpoint ngoài dự kiến.
- Metadata issuer khớp với issuer dự kiến.
- Metadata được kiểm tra schema và giới hạn nội dung.
- jwks_uri được kiểm tra theo policy của resource server.

Nếu một federation hoặc profile có cơ chế signed metadata riêng, chỉ dùng nó khi trust bootstrap và quy tắc xác minh chữ ký đã được định nghĩa rõ. Không giả định mọi tài liệu Discovery đều có chữ ký.

### 5.3. Kiểm tra cấu trúc và giá trị metadata

Resource server hoặc client nên:

- Yêu cầu HTTP status thành công.
- Chỉ chấp nhận content type và định dạng JSON được hỗ trợ.
- Giới hạn kích thước response và thời gian tải.
- Từ chối JSON sai cú pháp hoặc cấu trúc không hợp lệ.
- Kiểm tra các trường bắt buộc theo profile.
- Xác minh issuer chính xác.
- Kiểm tra các endpoint URI theo scheme và host policy.
- Không coi danh sách capability công bố là quyền đã cấp cho client.

Metadata có scopes_supported chỉ cho biết Authorization Server hỗ trợ những scope đó; nó không chứng minh client hoặc user hiện tại đã được cấp tất cả scope.

## 6. JWKS URI: địa chỉ khóa công khai phải được tin theo metadata đã xác minh

Trong metadata, trường jwks_uri chỉ đến endpoint trả về JSON Web Key Set.

Ví dụ:

~~~json
{
  "issuer": "https://identity.example.test",
  "jwks_uri": "https://identity.example.test/.well-known/jwks.json"
}
~~~

Resource server tải JWKS từ URI này để lấy khóa công khai tương ứng với token do issuer phát hành.

### 6.1. JWKS là gì?

Một JWKS là một JSON object có thuộc tính keys, chứa một mảng JWK:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "signing-key-2026-01",
      "alg": "RS256",
      "n": "base64url-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

Đây là dữ liệu minh họa, không phải khóa có thể sử dụng. Với RSA, n và e biểu diễn modulus và public exponent. Các thuật toán elliptic curve có các tham số công khai tương ứng như crv, x, y.

### 6.2. Các thuộc tính JWK thường gặp

| Thuộc tính | Ý nghĩa |
| --- | --- |
| kty | Loại khóa, ví dụ RSA hoặc EC. |
| kid | Key ID để chọn khóa phù hợp. |
| use | Mục đích sử dụng, ví dụ sig cho chữ ký hoặc enc cho mã hóa. |
| key_ops | Các thao tác khóa được phép, ví dụ verify. |
| alg | Thuật toán gắn với khóa nếu được công bố. |
| n, e | Tham số khóa công khai RSA. |
| crv, x, y | Đường cong và tọa độ khóa công khai EC. |

Với JWT ký số, resource server chỉ chọn khóa phù hợp cho xác minh chữ ký. Không sử dụng khóa mã hóa hoặc khóa không tương thích với thuật toán đã cấu hình.

### 6.3. JWKS công khai không nên chứa private key material

JWKS phục vụ resource server thường công bố public keys. Những tham số riêng như RSA d, p, q, dp, dq, qi hoặc private key material tương ứng của các loại khóa khác không nên xuất hiện trong JWKS công khai.

Nếu endpoint công khai trả về private key material, cần coi đó là sự cố nghiêm trọng: bảo vệ endpoint, thu hồi/rotate khóa bị lộ và đánh giá token đã được ký bằng khóa đó.

## 7. Vì sao không lấy khóa từ URL do JWT tự khai báo?

JOSE header của JWT có thể chứa các trường như:

- kid: định danh khóa.
- jku: URI của JWK Set.
- jwk: một JWK được nhúng trong header.
- x5u: URI của chứng thư hoặc chuỗi chứng thư.
- x5c: chứng thư được nhúng.

Các trường này không có cùng mức tin cậy. Header JWT chưa được xác minh chữ ký cho tới khi quá trình xác minh hoàn tất.

### 7.1. Không fetch jku hoặc x5u tùy ý từ token

Ví dụ token giả có header:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jku": "http://169.254.169.254/latest/meta-data/"
}
~~~

Nếu resource server tải khóa theo jku mà không có trust policy độc lập, nó có thể bị SSRF tới địa chỉ nội bộ, bị lừa dùng khóa do attacker kiểm soát để xác minh token giả, bỏ qua issuer/key binding đã cấu hình hoặc truy cập URL ngoài allowlist.

Thông thường, kid chỉ được dùng để tìm khóa trong JWKS đã lấy từ jwks_uri đáng tin cậy gắn với issuer đã chọn. Không dùng jku hoặc x5u do token cung cấp làm nguồn khóa tự động, trừ khi một profile đặc biệt định nghĩa cơ chế tin cậy và kiểm tra đầy đủ.

### 7.2. JWK nhúng trong header không tự đáng tin

Một token có thể nhúng public key của chính attacker rồi được ký bằng private key tương ứng. Nếu verifier tin khóa nhúng chỉ vì nó nằm trong header, attacker có thể tự tạo token và tự cung cấp khóa để xác minh.

Chỉ chấp nhận khóa được liên kết với issuer theo trust configuration. Không để token tự chọn trust anchor của chính nó.

## 8. Bảo vệ việc tải metadata và JWKS khỏi SSRF

Discovery và JWKS retrieval là các request outbound do server thực hiện. Vì vậy, chúng cần được xem như một bề mặt mạng có thể bị khai thác.

### 8.1. Những địa chỉ cần chặn hoặc kiểm soát

Một URL độc hại có thể trỏ tới:

- localhost hoặc loopback IPv4/IPv6.
- Địa chỉ private trong mạng nội bộ.
- Link-local address.
- Cloud instance metadata service.
- Endpoint quản trị, database hoặc service discovery nội bộ.
- Domain ngoài tổ chức được dùng để thu thập request.

Không chỉ kiểm tra hostname dạng chuỗi. DNS có thể trả về địa chỉ khác nhau theo thời gian; một domain nhìn hợp lệ có thể phân giải sang IP private hoặc thay đổi sau khi kiểm tra.

### 8.2. Quy tắc network egress

Một policy an toàn nên:

1. Chỉ cho phép issuer đã đăng ký.
2. Chỉ tải metadata qua HTTPS trong môi trường production.
3. Xác minh TLS certificate và hostname.
4. Giới hạn host của jwks_uri theo allowlist hoặc policy được phê duyệt.
5. Kiểm soát DNS resolution và chặn IP loopback, private, link-local hoặc dải nội bộ không được phép.
6. Giới hạn cổng và scheme.
7. Giới hạn timeout, response size và số lần retry.
8. Kiểm soát redirect; mặc định không theo redirect tùy ý hoặc phải xác minh lại từng đích redirect theo cùng policy.
9. Thực thi egress firewall để ngăn ứng dụng truy cập dịch vụ nội bộ ngoài nhu cầu.

### 8.3. jwks_uri khác host issuer có thể hợp lệ nhưng cần policy

Không phải mọi issuer đều đặt JWKS cùng hostname với issuer. Metadata có thể trỏ đến một host CDN hoặc key service riêng. Điều đó không tự động là sai, nhưng resource server phải quyết định host nào được phép dựa trên trust agreement.

Không dùng quy tắc quá rộng như “mọi subdomain của domain issuer đều đáng tin” nếu domain đó có nhiều chủ thể quản lý hoặc dịch vụ không cùng mức bảo vệ.

### 8.4. Redirect không được vượt trust boundary

Giả sử metadata trỏ đến:

~~~text
https://identity.example.test/keys
~~~

nhưng server trả redirect đến:

~~~text
http://internal-admin.local/secret
~~~

Client không nên tự động theo redirect sang đích đó. Nếu policy cho phép redirect, phải kiểm tra scheme, hostname, DNS/IP và cổng của từng hop, đồng thời giới hạn số lần redirect.

## 9. Liên kết JWKS với đúng issuer

Một resource server có thể tin nhiều issuer. Khi đó mỗi issuer phải có metadata và JWKS riêng trong trust store.

Ví dụ:

~~~text
Issuer A -> Metadata A -> JWKS A
Issuer B -> Metadata B -> JWKS B
~~~

Không gộp khóa của các issuer thành một tập không có namespace rồi chỉ tìm theo kid.

### 9.1. kid không nhất thiết duy nhất toàn hệ thống

Hai issuer có thể cùng dùng:

~~~text
kid = key-2026
~~~

Nhưng khóa thuộc issuer khác nhau. Khóa cần được chọn theo ít nhất:

~~~text
trusted issuer
    + associated JWKS
    + kid
    + algorithm/key type constraints
~~~

Không tra cứu kid toàn cục rồi dùng khóa đầu tiên có giá trị trùng.

### 9.2. Kiểm tra claim iss sau khi xác minh

Resource server cần xác minh token bằng tập khóa đã liên kết với issuer dự kiến, rồi kiểm tra claim iss đúng với issuer đó. Không chấp nhận token chỉ vì chữ ký có thể được xác minh bằng một public key bất kỳ mà server đang lưu.

Với multi-issuer, quy trình chọn issuer phải bắt đầu từ registry/configuration tin cậy. Nếu dùng iss chưa xác minh làm gợi ý chọn registry entry, chỉ chấp nhận khi giá trị đó khớp chính xác một issuer đã được đăng ký.

## 10. Chọn JWK phù hợp để xác minh chữ ký

Sau khi tải JWKS từ URI đáng tin cậy, resource server cần chọn đúng khóa cho token.

### 10.1. kid là gợi ý chọn khóa, không phải bằng chứng tin cậy

JOSE header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

Verifier có thể dùng kid để tìm JWK tương ứng trong JWKS của issuer. Nhưng kid do token gửi vẫn là dữ liệu chưa xác minh; nó chỉ dùng để chọn ứng viên trong tập khóa đã tin.

Nếu không có kid:

- Nếu JWKS chỉ có đúng một khóa phù hợp theo hợp đồng, verifier có thể có quy tắc chọn rõ ràng.
- Nếu có nhiều khóa phù hợp và không thể chọn duy nhất, từ chối token.
- Không đoán khóa theo thứ tự mảng hoặc dùng khóa đầu tiên.

Nếu có nhiều JWK cùng kid và tạo ra kết quả nhập nhằng, nên từ chối hoặc xử lý theo quy tắc xác định rõ; không chọn tùy tiện.

### 10.2. Thuật toán phải được cấu hình độc lập

Không để token tự quyết định thuật toán được chấp nhận. Resource server cần allowlist thuật toán theo profile và issuer, ví dụ chỉ chấp nhận RS256 hoặc một thuật toán EC cụ thể đã được phê duyệt.

Các kiểm tra cần thiết:

- alg trong header thuộc allowlist.
- JWK có kty tương thích với thuật toán.
- Nếu JWK có alg, giá trị phải phù hợp với policy.
- use phải phù hợp với chữ ký, thường là sig nếu có.
- key_ops nếu có phải cho phép verify.
- Kích thước khóa và curve phải đạt yêu cầu bảo mật.
- Không chấp nhận thuật toán none cho token cần chữ ký.
- Không mắc lỗi algorithm confusion giữa RSA, HMAC hoặc các loại khóa khác.

### 10.3. Không dùng khóa mã hóa để xác minh chữ ký

JWK có thể có use = enc hoặc key operation dành cho mã hóa. Không sử dụng nó để xác minh chữ ký. Nếu issuer dùng cùng một key set cho nhiều mục đích, verifier vẫn phải lọc theo use, key_ops, alg và policy.

### 10.4. Kiểm tra JOSE header và token profile

Ngoài alg và kid, cần kiểm tra typ, crit hoặc các trường bắt buộc theo profile. Ví dụ JWT access token theo RFC 9068 dùng type at+jwt. Không phải mọi JWT đều là access token.

Không xử lý extension trong crit nếu verifier không hiểu hoặc không hỗ trợ extension đó. Không dùng một bộ quy tắc lỏng để chấp nhận ID token, access token và JWT nội bộ như cùng một loại.

## 11. Cache metadata và JWKS

Tải metadata và JWKS ở mọi request sẽ gây độ trễ, tăng tải và tạo phụ thuộc mạng không cần thiết. Thông thường, client/resource server cache metadata và JWKS theo HTTP cache headers cùng policy nội bộ.

### 11.1. Cache metadata

Metadata có thể thay đổi khi endpoint token hoặc authorization thay đổi, jwks_uri được di chuyển, capability hoặc signing algorithm thay đổi, hoặc issuer triển khai phiên bản metadata mới.

Cache metadata cần:

- Tôn trọng Cache-Control, Expires, ETag hoặc Last-Modified nếu được cung cấp.
- Đặt TTL tối đa theo policy, kể cả khi server yêu cầu cache quá lâu.
- Không cache vô hạn.
- Gắn cache với issuer chính xác.
- Chỉ cập nhật sau khi metadata mới vượt qua kiểm tra trust và schema.

### 11.2. Cache JWKS

JWKS thường thay đổi khi khóa ký được xoay vòng. Cache cần:

- Gắn với issuer và jwks_uri đã xác minh.
- Tôn trọng HTTP caching trong giới hạn policy.
- Có TTL và giới hạn stale rõ ràng.
- Hỗ trợ refresh có kiểm soát khi gặp kid mới.
- Tránh nhiều request đồng thời cùng tải lại JWKS.
- Không để lỗi mạng làm xóa ngay tập khóa hợp lệ đang cache nếu policy cho phép dùng trong thời gian stale có giới hạn.

### 11.3. Unknown kid: refresh một cách có kiểm soát

Khi JWT có kid chưa thấy trong JWKS cache:

1. Kiểm tra token đã chọn đúng issuer và JWKS context chưa.
2. Thực hiện tối đa một lần refresh phù hợp, có rate limit và single-flight.
3. Tải JWKS mới từ jwks_uri đã tin cậy.
4. Xác minh metadata/response và chọn lại key.
5. Nếu không tìm thấy khóa phù hợp, từ chối token.

Không fetch JWKS không giới hạn cho mỗi kid lạ. Kẻ tấn công có thể gửi hàng nghìn token với kid ngẫu nhiên để tạo request outbound và gây cạn tài nguyên.

### 11.4. Stale cache khi issuer tạm thời không khả dụng

Một số hệ thống có thể tiếp tục dùng khóa đã cache khi JWKS endpoint tạm thời lỗi. Điều này cần giới hạn:

- Chỉ dùng khóa đã được xác minh và cache trước đó.
- Không chấp nhận kid chưa biết.
- Giới hạn thời gian stale.
- Có metric và cảnh báo khi refresh thất bại.
- Có cơ chế emergency deny khi khóa bị compromise.

Không dùng stale cache vô thời hạn. Nếu khóa cũ đã bị xâm phạm, tiếp tục tin cache cũ có thể duy trì khả năng giả mạo token.

## 12. Key rotation: thay đổi khóa mà không làm gián đoạn dịch vụ

Issuer có thể thay khóa ký định kỳ hoặc vì lý do vận hành. JWKS thường công bố nhiều public keys trong giai đoạn chuyển tiếp.

### 12.1. Quy trình rotation bình thường

~~~mermaid
flowchart TD
    A["Issuer tạo key mới"] --> B["Publish public key mới vào JWKS"]
    B --> C["Resource server refresh và cache key mới"]
    C --> D["Issuer bắt đầu ký token bằng key mới"]
    D --> E["Token cũ vẫn được xác minh bằng key cũ trong thời gian chuyển tiếp"]
    E --> F["Token cũ hết hạn và cache cập nhật"]
    F --> G["Issuer loại bỏ key cũ khỏi JWKS"]
~~~

Trình tự này giúp resource server có cơ hội nhận khóa mới trước khi token mới được ký bằng khóa đó.

### 12.2. Overlap giữa khóa cũ và mới

Issuer thường giữ public key cũ trong JWKS đủ lâu để xác minh token còn hạn đã ký bằng private key cũ.

Thời gian overlap cần xét:

- Maximum access token lifetime.
- Thời gian cache JWKS.
- Độ trễ phân phối metadata/JWKS.
- Clock skew được chấp nhận.
- Các loại token khác có thể có thời hạn dài hơn.

Không loại khóa cũ ngay sau khi bắt đầu ký bằng khóa mới nếu còn token hợp lệ dùng khóa cũ.

### 12.3. kid phải được thay đổi khi khóa thay đổi

Mỗi khóa nên có kid ổn định trong vòng đời của chính khóa đó. Khi tạo key pair mới, nên cấp kid mới để verifier phân biệt. Không tái sử dụng cùng kid cho một public key khác trong khi cache cũ có thể còn tồn tại.

## 13. Khóa ký bị compromise: rotation thông thường chưa đủ

Nếu private signing key bị lộ, kẻ tấn công có thể tạo JWT giả có chữ ký hợp lệ theo public key tương ứng. Đây là sự cố trust nghiêm trọng.

Phản ứng cần có thể gồm:

1. Xác định kid, thuật toán, issuer và thời điểm nghi ngờ bị lộ.
2. Ngừng dùng private key bị compromise để ký token mới.
3. Loại public key tương ứng khỏi JWKS hoặc đánh dấu bị thu hồi theo cơ chế khẩn cấp.
4. Buộc resource server refresh key set hoặc áp dụng deny policy cho kid đó.
5. Xem xét token đã phát hành bằng khóa bị lộ; thu hồi session/grant hoặc tăng authorization version nếu phù hợp.
6. Phát hành khóa mới và cập nhật trust configuration.
7. Điều tra log, phạm vi truy cập và khả năng dữ liệu đã bị lộ.

### 13.1. Cache có thể cản trở việc thu hồi khóa

Nếu resource server tiếp tục dùng public key cũ từ cache, token giả ký bằng private key bị lộ vẫn có thể được chấp nhận. Với sự cố compromise, cần cơ chế emergency invalidation vượt qua TTL bình thường:

- Push invalidation hoặc denylist kid.
- Giảm thời gian refresh theo sự kiện khẩn cấp.
- Xóa cache theo issuer và key ID.
- Có khả năng từ chối một khóa cụ thể ngay cả khi JWKS cache còn chứa nó.

Không nên dựa hoàn toàn vào việc chờ cache hết hạn khi khóa đã bị lộ.

### 13.2. Loại bỏ khóa khỏi JWKS có thể chưa đủ

Các resource server có thể cache JWKS quá lâu, không refresh khi key set thay đổi, có bản sao JWKS trong nhiều region hoặc chấp nhận stale key khi endpoint lỗi.

Incident response cần xác nhận tất cả resource server đã ngừng tin khóa bị compromise, không chỉ xác nhận issuer đã xóa key khỏi endpoint.

## 14. Multi-issuer và multi-tenant Discovery

Một API có thể chấp nhận token từ nhiều tổ chức hoặc nhiều Identity Provider. Khi đó, mỗi issuer cần một trust record riêng.

Ví dụ:

~~~yaml
issuer_registry:
  - issuer: https://idp.company-a.example
    discovery_url: https://idp.company-a.example/.well-known/openid-configuration
    audience: https://api.example.test/billing
    jwks_uri: https://idp.company-a.example/keys

  - issuer: https://login.company-b.example
    discovery_url: https://login.company-b.example/.well-known/openid-configuration
    audience: https://api.example.test/billing
    jwks_uri: https://login.company-b.example/.well-known/jwks.json
~~~

Đây là registry minh họa, không phải schema chuẩn.

### 14.1. Không trộn JWKS giữa issuer

Ngay cả khi hai issuer có cùng kid, public key và metadata vẫn phải gắn với issuer tương ứng. Cache key cần có issuer hoặc trust record ID:

~~~text
cache key = (issuer, jwks_uri, kid)
~~~

Không dùng kid đơn độc làm khóa cache toàn cục.

### 14.2. Tenant không tự quyết định issuer

Một request có tenant_id = company-a không đủ để chọn issuer chỉ vì tenant ID xuất hiện trong URL. Hệ thống cần mapping tenant-to-issuer từ registry được quản lý. Sau khi xác minh token, API còn phải kiểm tra principal có membership trong tenant.

### 14.3. Dynamic issuer discovery cần kiểm soát

Nếu hệ thống cho phép khách hàng đăng ký issuer mới:

- Xác minh domain/issuer ownership theo quy trình.
- Kiểm tra issuer identifier và metadata endpoint.
- Áp dụng HTTPS, SSRF protection và host allowlist.
- Giới hạn số issuer, tần suất discovery và kích thước metadata.
- Có quy trình approve, disable và revoke issuer.
- Gắn issuer với tenant/partner đã được phê duyệt.
- Không tự đăng ký issuer chỉ từ claim iss của token nhận được.

## 15. Discovery không thay thế các bước xác minh JWT

Sau khi lấy được JWKS, resource server vẫn phải xác minh token theo đầy đủ profile và policy.

Một luồng xác minh access token điển hình:

1. Xác định issuer dự kiến từ trust registry.
2. Lấy metadata đã được xác minh và JWKS gắn với issuer.
3. Đọc JOSE header để lấy kid và alg như dữ liệu chưa tin cậy.
4. Chọn public key phù hợp từ JWKS của đúng issuer.
5. Kiểm tra thuật toán và loại khóa theo allowlist.
6. Xác minh chữ ký.
7. Kiểm tra iss, aud, exp, nbf, iat và các claim bắt buộc.
8. Kiểm tra token type/profile, chẳng hạn access token theo hợp đồng.
9. Thực hiện authorization theo scope, tenant, principal, action và resource.

Discovery/JWKS chỉ hỗ trợ bước tìm khóa và metadata. Nó không tự chứng minh token chưa bị thu hồi, permission còn hiệu lực hoặc user được truy cập tài nguyên.

## 16. Pseudocode: Discovery và xác minh JWKS an toàn

Ví dụ dưới đây là pseudocode độc lập ngôn ngữ. Các hàm mạng, JSON và mật mã là khái niệm; triển khai phải dùng thư viện giao thức đã được kiểm chứng.

~~~text
function loadTrustedIssuer(issuerId):
    trustRecord = trustedIssuerRegistry.findExact(issuerId)
    if trustRecord is null or not trustRecord.enabled:
        return TRUST_FAILURE

    metadataUrl = buildDiscoveryUrl(
        trustRecord.issuer,
        trustRecord.discoveryMode
    )

    metadataResponse = secureFetch(
        url = metadataUrl,
        requireHttps = true,
        allowedHosts = trustRecord.discoveryHosts,
        blockPrivateAndLinkLocalAddresses = true,
        validateEveryRedirect = true,
        maxResponseBytes = METADATA_LIMIT,
        timeout = METADATA_TIMEOUT
    )
    if metadataResponse.failed:
        return TRUST_FAILURE

    metadata = parseAndValidateMetadata(metadataResponse.body)
    if metadata.issuer != trustRecord.issuer:
        return TRUST_FAILURE

    validateJwksUri(
        metadata.jwks_uri,
        allowedHosts = trustRecord.allowedJwksHosts,
        requireHttps = true
    )

    return cacheTrustedMetadata(trustRecord.issuer, metadata)


function verifyAccessToken(token, expectedIssuer, expectedAudience):
    trust = loadTrustedIssuer(expectedIssuer)
    if trust.failed:
        return REJECT

    header = parseUntrustedJoseHeader(token)
    if header.alg not in configuredAlgorithmAllowlist:
        return REJECT

    if header.jku exists or header.x5u exists:
        rejectUnlessExplicitlySupportedByTrustedProfile()

    jwks = loadCachedOrRefreshJwks(
        issuer = expectedIssuer,
        uri = trust.metadata.jwks_uri
    )
    key = selectUniqueCompatibleKey(
        jwks,
        kid = header.kid,
        alg = header.alg,
        requiredUse = "sig",
        requiredOperation = "verify"
    )
    if key is null:
        return REJECT

    if not verifySignature(token, key, header.alg):
        return REJECT

    claims = parseVerifiedClaims(token)
    if claims.iss != expectedIssuer:
        return REJECT
    if not audienceMatchesExactly(claims.aud, expectedAudience):
        return REJECT
    if tokenExpiredOrNotYetValid(claims):
        return REJECT
    if not accessTokenProfileIsValid(header, claims):
        return REJECT

    return VERIFIED_PRINCIPAL(claims)
~~~

Các điểm cần lưu ý:

- expectedIssuer phải đến từ trust registry hoặc cấu hình đã phê duyệt.
- buildDiscoveryUrl phải áp dụng đúng quy tắc OIDC Discovery hoặc RFC 8414.
- secureFetch phải kiểm soát TLS, DNS/IP, redirect, timeout và response size.
- jwks_uri chỉ được dùng sau khi metadata vượt qua kiểm tra.
- JOSE header chưa xác minh không được tự quyết định URL lấy khóa.
- Nếu không tìm thấy key phù hợp hoặc chữ ký sai, token phải bị từ chối.
- Sau khi chữ ký hợp lệ, API vẫn kiểm tra claims và authorization policy.

## 17. Những lỗi thường gặp

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Fetch Discovery từ iss chưa xác minh | SSRF tới endpoint nội bộ hoặc attacker-controlled issuer. | Chỉ dùng issuer trong trust registry; token claim chỉ là gợi ý tra cứu. |
| Tự động tin issuer đầu tiên | Attacker có thể trở thành trust anchor. | Có quy trình đăng ký và phê duyệt issuer. |
| Dùng sai URL construction | Không tìm được metadata hoặc lấy nhầm endpoint. | Phân biệt OIDC Discovery và RFC 8414. |
| Không so khớp metadata issuer | Metadata của issuer khác bị gắn nhầm. | So khớp chính xác với issuer dự kiến. |
| So khớp iss bằng prefix/domain suffix | Chấp nhận issuer giả gần giống. | So khớp định danh chính xác theo hợp đồng. |
| Tin jwks_uri bất kỳ | SSRF hoặc dùng khóa từ host ngoài trust boundary. | HTTPS, host policy, DNS/IP egress controls và redirect validation. |
| Fetch jku/x5u từ token | Attacker tự chọn nguồn khóa. | Chọn khóa từ JWKS đã gắn với issuer tin cậy. |
| Dùng kid toàn cục | Khóa của issuer khác có thể bị chọn nhầm. | Namespace cache và key lookup theo issuer. |
| Không giới hạn alg | Algorithm confusion hoặc thuật toán yếu. | Allowlist thuật toán độc lập với token. |
| Dùng JWK enc để verify | Sai mục đích sử dụng khóa. | Kiểm tra use, key_ops, kty và alg. |
| Refresh JWKS vô hạn khi kid lạ | DoS qua outbound request. | Rate limit, single-flight và giới hạn retry. |
| Cache JWKS vô thời hạn | Khóa cũ hoặc bị compromise vẫn được tin. | TTL, stale limit và emergency invalidation. |
| Xóa key cũ quá sớm | Token hợp lệ còn hạn bị từ chối. | Rotation overlap theo token lifetime và cache propagation. |
| Giữ key bị lộ trong cache | Token giả vẫn có thể được xác minh. | Incident response có emergency key revocation. |
| Coi Discovery là authorization | Token hợp lệ bị hiểu nhầm là được truy cập mọi resource. | Tiếp tục kiểm tra scope, tenant và object policy. |

## 18. Kịch bản kiểm thử

### 18.1. Kiểm thử trust bootstrap và Discovery

~~~text
Issuer đã đăng ký, metadata issuer khớp chính xác
    -> chấp nhận metadata nếu các kiểm tra khác đạt

Issuer không nằm trong registry
    -> từ chối; không fetch URL tùy ý

JWT có iss trỏ tới localhost/private IP
    -> không tạo outbound request tới địa chỉ đó

Metadata trả issuer khác issuer dự kiến
    -> từ chối metadata

OIDC issuer có path
    -> xây dựng URL theo OIDC Discovery

OAuth AS issuer có path
    -> xây dựng URL theo RFC 8414
~~~

### 18.2. Kiểm thử JWKS URI và SSRF

- jwks_uri dùng HTTP trong môi trường yêu cầu HTTPS.
- jwks_uri trỏ tới loopback, private hoặc link-local address.
- DNS trả về IP private hoặc thay đổi sau khi kiểm tra.
- Endpoint redirect sang host ngoài allowlist.
- Response quá lớn hoặc timeout.
- TLS certificate không khớp hostname.
- Metadata thay đổi jwks_uri sang host không được phê duyệt.

Mọi trường hợp ngoài trust policy phải bị từ chối và không được truy cập mạng nội bộ.

### 18.3. Kiểm thử key selection

- kid khớp đúng một public key.
- kid không tồn tại.
- kid trùng trên hai issuer khác nhau.
- Nhiều JWK cùng kid trong một JWKS.
- JWK có use = enc.
- JWK có key_ops không cho phép verify.
- alg trong token không thuộc allowlist.
- Key type/curve không tương thích với algorithm.
- Token có jku trỏ đến server của attacker.
- Token có chữ ký sai dù kid hợp lệ.

### 18.4. Kiểm thử cache và rotation

- Key mới được publish trước khi issuer bắt đầu ký token mới.
- Resource server refresh JWKS và xác minh được token mới.
- Token cũ vẫn được xác minh trong overlap hợp lệ.
- Key cũ bị loại sau khi token hết hạn và cache đã cập nhật.
- kid lạ gây tối đa số lần refresh được cấu hình.
- JWKS endpoint lỗi nhưng cache vẫn còn trong stale grace.
- Emergency revoke làm mọi API ngừng tin key bị compromise.

### 18.5. Kiểm thử multi-issuer

- Hai issuer dùng cùng kid nhưng khóa khác nhau.
- Token của issuer A không được xác minh bằng JWKS của issuer B.
- Tenant không thể tự chọn issuer ngoài registry.
- Issuer bị disable không được tiếp tục nhận token mới.
- Metadata/JWKS cache không bị dùng chéo giữa issuer.

## 19. Checklist triển khai Discovery và JWKS

Trước khi đưa một issuer vào trust store, hãy trả lời:

1. **Issuer bootstrap:** issuer được lấy từ cấu hình/registry nào và ai phê duyệt?
2. **Discovery mode:** dùng OIDC Discovery hay OAuth AS Metadata (RFC 8414)?
3. **URL construction:** issuer có path không; well-known URL được tạo đúng đặc tả chưa?
4. **Issuer matching:** metadata issuer và JWT iss có được so khớp chính xác không?
5. **TLS:** HTTPS, certificate chain và hostname có được xác minh không?
6. **SSRF:** DNS/IP, private/link-local, redirect, port, timeout và response size được kiểm soát thế nào?
7. **JWKS URI:** host nào được phép; thay đổi URI cần phê duyệt hay policy nào?
8. **Key selection:** kid, kty, use, key_ops, alg và curve được kiểm tra ra sao?
9. **Algorithm policy:** allowlist được cấu hình độc lập với JOSE header chưa?
10. **Cache:** metadata/JWKS TTL, ETag, stale grace và refresh rate limit là bao nhiêu?
11. **Rotation:** overlap key cũ/mới có tính token lifetime và propagation delay không?
12. **Compromise:** có thể emergency revoke một kid trên mọi API/region không?
13. **Multi-issuer:** cache và key lookup có namespace theo issuer không?
14. **Token profile:** API có phân biệt access token với ID token hoặc JWT loại khác không?
15. **Authorization:** sau khi xác minh token, API còn kiểm tra scope, tenant và resource policy không?
16. **Observability:** có metric cho discovery failure, JWKS refresh, unknown kid, key rotation và signature failure không?

## 20. Ghi nhớ trọng tâm

- Discovery giúp tìm metadata, nhưng phải bắt đầu từ issuer đã được tin cậy.
- Không fetch metadata từ URL iss chưa xác minh; chỉ dùng nó để tra cứu chính xác trong registry allowlist.
- OIDC Discovery và OAuth AS Metadata (RFC 8414) có quy tắc tạo well-known URL khác nhau, nhất là khi issuer có path.
- Metadata issuer phải khớp issuer dự kiến; jwks_uri phải vượt qua HTTPS, host, DNS/IP, redirect và egress policy.
- JWKS phải được gắn với issuer; kid không duy nhất toàn hệ thống và không tự tạo trust.
- Không lấy khóa từ jku, x5u hoặc JWK nhúng do token tự cung cấp nếu không có trust profile được phê duyệt.
- Kiểm tra alg, kty, use, key_ops, key size và token profile theo allowlist độc lập.
- Cache, unknown-kid refresh, key rotation và emergency revocation cần giới hạn, đo lường và kiểm thử.
- Xác minh chữ ký JWT không thay thế kiểm tra scope, tenant, membership hoặc quyền trên tài nguyên.

**Tài liệu tham khảo kỹ thuật:** OpenID Connect Discovery 1.0; RFC 8414 (OAuth 2.0 Authorization Server Metadata); RFC 7517 (JSON Web Key); RFC 7519 (JSON Web Token); RFC 7515 (JSON Web Signature); RFC 8725 (JSON Web Token Best Current Practices); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens); RFC 9700 (Best Current Practice for OAuth 2.0 Security). Các chuẩn này định nghĩa Discovery, metadata, JWK/JWKS và yêu cầu xử lý JWT; trust bootstrap, host allowlist, cache và quy trình vận hành vẫn cần được hệ thống triển khai thành policy cụ thể.

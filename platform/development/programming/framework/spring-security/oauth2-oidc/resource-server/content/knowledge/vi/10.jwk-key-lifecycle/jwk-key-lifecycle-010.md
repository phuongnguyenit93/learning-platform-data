# jku, x5u hoặc khóa đính kèm không phải nguồn được tự động tin cậy

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, JWT access token thường được ký bởi Authorization Server và được API kiểm chữ ký bằng **public key của issuer tin cậy**. JSON Web Signature (JWS) cho phép JOSE header chứa nhiều thông tin về khóa, chẳng hạn **kid**, **jku**, **jwk**, **x5u**, **x5c** và **x5t#S256**. Các trường này hỗ trợ nhận diện hoặc phân phối khóa, nhưng việc một token **tự khai báo** địa chỉ hay nội dung khóa **không đủ để biến khóa đó thành nguồn xác minh được tin cậy**.

Nếu Resource Server tin khóa do chính token chưa xác thực chỉ định, kẻ tấn công có thể tự tạo cặp khóa, tự ký JWT có claim **scope = admin** rồi hướng server đến public key của họ. Chữ ký toán học vẫn xác minh được, nhưng chỉ chứng minh token được ký bằng **khóa của kẻ tấn công**, không chứng minh token do Authorization Server được hệ thống ủy thác phát hành.

Bài học giải thích vai trò chính xác của các JOSE header liên quan đến khóa, chuỗi tin cậy khi dùng issuer/JWKS, những rủi ro key substitution và SSRF, cách cấu hình Spring Security an toàn, cũng như một trường hợp đặc biệt hợp lệ khi chứng minh sở hữu khóa được thiết kế tường minh.

## 1. Chữ ký hợp lệ theo khóa nào, và ai xác nhận khóa đó?

Có hai câu hỏi **khác nhau**:

1. **Cryptographic verification:** chữ ký của JWT có khớp với public key đang sử dụng không?
2. **Trust establishment:** public key đó có thực sự thuộc về **issuer mà API đã cấu hình tin cậy** và được phép dùng để xác minh loại token này không?

Nếu chỉ giải quyết câu đầu, hệ thống có thể xác minh chữ ký được tạo bởi **bất kỳ người nào tự tạo khóa**.

Ví dụ yêu cầu:

~~~http
GET /api/admin/reports HTTP/1.1
Host: orders.example.com
Authorization: Bearer <compact-jws>
~~~

JWT có protected header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "my-key",
  "jku": "https://attacker.example/keys.json",
  "typ": "at+jwt"
}
~~~

Và payload minh họa:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "administrator",
  "aud": ["orders-api"],
  "scope": "reports.export",
  "exp": 1893456000
}
~~~

Kẻ tấn công có thể tự viết các claims trên, tự tạo cặp RSA key và ký JWT bằng private key của họ. Nếu Resource Server **tải JWKS từ jku do JWT khai báo** rồi xác minh bằng khóa tải được, chữ ký có thể đúng, mặc dù **issuer trong payload chỉ là lời tự khai**.

Nguyên tắc nền tảng:

> **Một khóa chỉ đáng tin khi hệ thống xác lập được quan hệ tin cậy của khóa với issuer hoặc chính sách xác thực trước khi tin token. Khóa nằm trong JWT hay một URL do JWT nêu ra không tự chứng minh quan hệ đó.**

Điều này đúng ngay cả khi **jku** là URL HTTPS, JWT có định dạng hợp lệ, **kid** khớp, và thuật toán xác minh thực hiện chuẩn xác.

## 2. Các JOSE header liên quan đến khóa

JWS sử dụng các tham số JOSE Header để cung cấp metadata phục vụ xử lý chữ ký. Một số tham số là tùy chọn và có thể xuất hiện ở protected hoặc unprotected header theo cấu trúc JWS; với **JWS Compact Serialization** thông dụng của access token, JOSE header là protected header.

| Tham số | Dữ liệu mang theo | Dùng để làm gì? | Có tạo sự tin cậy độc lập không? |
|---|---|---|---|
| **alg** | Tên thuật toán, ví dụ **RS256**, **ES256** | Chỉ ra thuật toán JWS được dùng | **Không**; API phải giới hạn thuật toán cho phép |
| **kid** | Chuỗi định danh khóa | Gợi ý chọn khóa trong tập khóa đáng tin cậy | **Không** |
| **jku** | **JWK Set URL** | Chỉ tới tài nguyên JSON chứa tập JWK | **Không** |
| **jwk** | Một **JWK JSON object** | Gửi thông tin khóa trực tiếp trong header | **Không** |
| **x5u** | **X.509 URL** | Chỉ tới tài nguyên chứng chỉ hoặc chuỗi chứng chỉ X.509 | **Không** |
| **x5c** | Mảng chứng chỉ X.509 | Đính kèm chuỗi chứng chỉ ngay trong header | **Không** |
| **x5t** | Thumbprint SHA-1 của chứng chỉ | Hỗ trợ nhận diện chứng chỉ | **Không** |
| **x5t#S256** | Thumbprint SHA-256 của chứng chỉ | Hỗ trợ nhận diện chứng chỉ bằng SHA-256 | **Không** |
| **typ** | Loại đối tượng/token | Gợi ý loại token/profile, ví dụ **at+jwt** | **Không** |

Một ví dụ JOSE protected header kết hợp nhiều tham số:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11",
  "jku": "https://login.example.com/keys/jwks.json",
  "x5t#S256": "<certificate-thumbprint-base64url>"
}
~~~

Các giá trị là **minh họa**, không phải token dùng để gọi API thật. Ngay cả nếu hostname trông giống nhà cung cấp xác thực, Resource Server cũng không được dùng **jku** như một lệnh tải khóa không qua chính sách tin cậy.

### 2.1. **kid** chỉ chọn khóa, không xác định ai được tin

Một JWKS của issuer có thể có nhiều key với các **kid** khác nhau để luân chuyển khóa ký:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-2026-10",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-rsa-modulus-old>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-rsa-modulus-new>",
      "e": "AQAB"
    }
  ]
}
~~~

Hai giá trị **n** là placeholder; JWKS thật chứa các số modulus hợp lệ theo JWK. Nếu JWT có **kid = signing-2026-11**, decoder có thể tìm khóa tương ứng **trong JWKS đã được issuer tin cậy công bố**.

Không nên dùng **kid** để tự tạo URL, đường dẫn file hoặc truy vấn database không kiểm soát. Một chuỗi kid có thể bị kẻ tấn công tự khai; chính chữ ký đã được kiểm bằng khóa tin cậy mới có ý nghĩa mật mã.

### 2.2. **jku** là URL của JWKS

Theo JWS, **jku** là một URI trỏ tới một tài nguyên chứa **JWK Set**, tức JSON có mảng **keys**. Ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "key-a",
  "jku": "https://issuer.example.org/public/jwks.json"
}
~~~

Nếu bên xác minh **đã có chính sách tin URL này**, jku có thể giúp tham chiếu nguồn khóa. Nhưng JWT bất kỳ không được quyền mở rộng tập nguồn khóa mà API tin cậy.

**Một URL có HTTPS chỉ bảo vệ kết nối và xác minh danh tính TLS của hostname; nó không chứng minh hostname đó được phép cấp JWT cho API.** Tên miền của kẻ tấn công cũng có thể dùng HTTPS hợp lệ.

### 2.3. **jwk** là khóa đính kèm trong header

Ví dụ một JWK công khai RSA được nhúng:

~~~json
{
  "alg": "RS256",
  "jwk": {
    "kty": "RSA",
    "n": "<base64url-rsa-modulus>",
    "e": "AQAB"
  }
}
~~~

**jwk không phải jwks_uri**. Nó chứa một đối tượng khóa ngay trong JOSE header. Nếu token do người ngoài tự tạo mang public key của họ, việc kiểm chữ ký bằng chính key đó không chứng minh issuer đã cấp token.

Với các hệ thống OAuth2 Resource Server thông thường, không sử dụng **jwk** trong access token để tự động thay thế khóa xác minh lấy từ issuer/JWKS đáng tin cậy.

### 2.4. **x5u** chỉ tới chuỗi chứng chỉ X.509

Ví dụ:

~~~json
{
  "alg": "RS256",
  "x5u": "https://certs.example.org/signing-chain.pem"
}
~~~

Theo JWS, x5u trỏ tới tài nguyên chứa chứng chỉ hoặc chuỗi chứng chỉ X.509, với biểu diễn PEM phù hợp. Đó là dữ liệu giúp lấy public key và thông tin chứng chỉ.

**Một chứng chỉ tải được không tự động đáng tin.** Nếu kẻ tấn công tự cấp chứng chỉ cho public key của mình rồi đặt URL đó vào x5u, Resource Server không được xem chứng chỉ như bằng chứng rằng Authorization Server thật đã ký token.

### 2.5. **x5c** là chuỗi chứng chỉ đính kèm

Thay vì URL, JWS có thể mang chứng chỉ trực tiếp:

~~~json
{
  "alg": "RS256",
  "x5c": [
    "<base64-der-leaf-certificate>",
    "<base64-der-intermediate-certificate>"
  ]
}
~~~

Các phần tử **x5c** là chuỗi Base64 biểu diễn chứng chỉ DER, khác với Base64URL dùng cho một số thành phần JWK. Chuỗi này **có thể cung cấp dữ liệu để kiểm certificate path**, nhưng không thay thế thao tác kiểm trust anchor, chứng chỉ, ràng buộc mục đích và sự liên kết tới issuer.

Các thumbprint **x5t** hoặc **x5t#S256** cũng chỉ nhận diện chứng chỉ; một thumbprint do token tự khai không đủ để cấp quyền, trừ khi nó được so với một giá trị đã được xác nhận và pin từ nguồn tin cậy.

## 3. Trường hợp an toàn: issuer được cấu hình, metadata công bố jwks_uri

Trong hệ thống OIDC/OAuth2, Resource Server thường bắt đầu bằng issuer URI được quản trị cấu hình:

~~~text
https://login.example.com/realms/shop
~~~

Issuer cung cấp metadata qua discovery endpoint chuẩn. Metadata có thể chứa:

~~~json
{
  "issuer": "https://login.example.com/realms/shop",
  "jwks_uri": "https://login.example.com/realms/shop/protocol/openid-connect/certs"
}
~~~

Spring Security sử dụng nguồn thông tin này để thiết lập khóa xác minh access token. Chuỗi tin cậy chuẩn:

~~~mermaid
flowchart TD
    C[Resource Server cấu hình issuer tin cậy] --> M[Khám phá metadata của issuer qua HTTPS]
    M --> J[Đọc jwks_uri từ metadata phù hợp issuer]
    J --> K[Tải JWKS qua HTTPS]
    K --> P[Chọn public key phù hợp kid / alg]
    P --> V{Xác minh JWS signature thành công?}
    V -->|Không| R[401]
    V -->|Có| Q{iss / aud / exp / nbf và profile hợp lệ?}
    Q -->|Không| R
    Q -->|Có| A{Scope + quyền tài nguyên đạt?}
    A -->|Không| D[403 hoặc 404 theo chính sách]
    A -->|Có| OK[Cho phép xử lý API]
~~~

Điểm khác biệt lớn giữa **jwks_uri** và **jku**:

- **jwks_uri** trong metadata xuất phát từ quy trình discovery bắt đầu bằng **issuer mà API đã cấu hình tin cậy**.
- **jku** là một JOSE Header Parameter xuất phát từ **token do request gửi lên**. Nếu ứng dụng không có hợp đồng tin cậy riêng ràng buộc nó, đây chỉ là một thông tin do người gửi tự khai.

Không phải cứ trùng tên miền là an toàn tuyệt đối. Quyết định trust còn phụ thuộc việc kiểm issuer trong metadata, HTTPS certificate, chính sách xác thực nguồn, các redirect/network boundary và cấu hình API. Nhưng một JWKS URI được cấp từ issuer đã tin cậy tạo ra **chuỗi tin cậy có gốc rõ ràng**, trong khi jku tùy ý trong JWT thì không.

### 3.1. Protected header vẫn không tự tạo trust

Có thể lập luận: “Nếu jku nằm trong protected header được ký, tại sao không tin nó?”

Vấn đề là **chữ ký chưa được công nhận** cho đến khi xác định được key đáng tin cậy. Nếu quy trình chọn key dựa hoàn toàn vào **jku do chính protected header đó cung cấp**, ta có vòng lặp:

~~~text
Tin jku vì JWT được ký
  -> muốn kiểm JWT phải lấy key từ jku
  -> lấy key của người gửi
  -> kiểm chữ ký bằng key đó
  -> suy ra jku đáng tin
~~~

Đây là một vòng chứng minh sai: token tự chọn khóa dùng để xác nhận chính nó. **Protected header ngăn sửa sau khi ký**, nhưng không chứng minh ai là người có quyền ký.

### 3.2. JWT header chưa xác thực có thể hỗ trợ tra cứu có giới hạn

Không phải mọi thao tác đọc JOSE header trước khi xác minh đều bị cấm. Một decoder cần đọc **alg** hoặc **kid** để lựa chọn khóa và thuật toán. Điều cốt lõi là các giá trị đó chỉ được sử dụng **bên trong tập key/algorithm mà Resource Server đã cho phép**.

Ví dụ:

~~~text
Allowed issuer: https://login.example.com/realms/shop
Trusted JWKS:  https://login.example.com/realms/shop/protocol/openid-connect/certs
Allowed alg:   RS256

JWT kid:       signing-2026-11
JWT jku:       https://random.example/jwks.json
~~~

Decoder có thể tìm **kid** trong trusted JWKS. Nó không được theo **jku** sang nguồn khác chỉ vì JWT bảo như vậy. Nếu không có key phù hợp trong tập đã tin cậy, kết quả là xác minh thất bại hoặc refresh tập khóa theo chính sách đã cấu hình, không phải chuyển sang một hostname tùy ý.

## 4. Tấn công khi tự động tin **jku**

Xét một triển khai lỗi với logic sau:

~~~text
1. Nhận Bearer JWT.
2. Parse JOSE header để lấy jku.
3. Tải JWKS từ jku.
4. Chọn key theo kid.
5. Kiểm chữ ký bằng key vừa tải.
6. Chấp nhận claims và cấp quyền.
~~~

Một kẻ tấn công có thể:

1. Tạo cặp khóa RSA cá nhân, giữ private key.
2. Công bố public key tại **https://attacker.example/jwks.json**.
3. Tạo JWT tự khai **iss** bằng issuer thật, **aud** bằng API và scope quản trị.
4. Đưa **jku** trỏ tới JWKS của họ trong header.
5. Ký token bằng private key của chính họ.
6. Gửi token đến API có thiết kế lỗi.

~~~mermaid
sequenceDiagram
    participant X as Kẻ tấn công
    participant API as Resource Server lỗi
    participant H as JWKS của attacker
    X->>X: Tạo RSA key pair và token có quyền giả
    X->>H: Công bố public JWK
    X->>API: Bearer JWT với jku=https://attacker.example/keys
    API->>H: GET jku do token chỉ định
    H-->>API: Public key của attacker
    API->>API: Verify token bằng key của attacker
    Note over API: Chữ ký đúng nhưng issuer chưa được xác lập
    API-->>X: Truy cập trái phép nếu claims được tin
~~~

Lỗi không nằm ở thuật toán RS256 hay phép tính chữ ký. Lỗi nằm ở **bước chọn nguồn khóa**. Đổi sang ES256, EdDSA hoặc một thư viện JOSE khác không tự sửa được vấn đề nếu mô hình tin cậy vẫn chấp nhận nguồn khóa do người gửi quyết định.

Các cơ chế như issuer validation sau chữ ký cũng không cứu được một thiết kế mà attacker có thể tự điền **iss** tùy ý và ký bằng khóa vừa được API tin. Cần thiết lập **nguồn khóa issuer đáng tin từ trước**.

## 5. Tấn công với **jwk** được nhúng trực tiếp

Một lỗi tương tự, thậm chí không cần request mạng:

~~~text
JWT header:
  alg = RS256
  jwk = public key của người gửi

JWT payload:
  iss = issuer đáng tin được giả mạo
  scope = admin

JWT signature:
  được tạo bằng private key tương ứng
~~~

Nếu Resource Server mặc định xác minh JWT bằng khóa ở **header.jwk**, kẻ gửi có thể tạo token tùy ý và chứng minh rằng nó được ký bởi **chính khóa mà họ tự cung cấp**.

Điều đó có thể là một **self-signed token** về mặt mật mã, nhưng hoàn toàn không cho biết token đã được Authorization Server cấp. Nếu không có bước xác nhận JWK đó **được phép** ký access token cho issuer/API, không được dùng nó để tạo authenticated principal.

Một câu ghi nhớ:

> **Khóa có thể đúng với chữ ký nhưng sai với chủ thể phát hành.**

Điều tương tự xảy ra với **x5c** nhúng một chứng chỉ tự ký hay chứng chỉ không được ràng buộc với issuer; việc đọc public key trong certificate không tự thiết lập quyền phát hành token.

## 6. Tấn công với **x5u**, **x5c** và những giới hạn của chứng chỉ

**x5u** chỉ đến chứng chỉ hoặc chuỗi chứng chỉ được host ở một URL. **x5c** nhúng chuỗi chứng chỉ trực tiếp. Để biến một certificate thành nguồn khóa xác minh JWT, tùy profile ứng dụng có thể cần:

1. Xác minh cấu trúc, thời hạn, mục đích sử dụng, chữ ký của chain và trust anchor phù hợp.
2. Đảm bảo chứng chỉ hoặc public key thực sự được **liên kết với issuer được ủy thác** theo hợp đồng (pinning, metadata, registry hoặc chính sách chứng thư chuyên biệt).
3. Đảm bảo chứng chỉ được phép dùng cho thuật toán và loại token đó.
4. Xác minh chữ ký JWT bằng public key tương ứng.
5. Kiểm issuer, audience, timestamps, loại token và các yêu cầu phân quyền.

Một certificate có chain tới **public CA** không nhất thiết chứng minh nó được phép ký JWT của **login.example.com**. Public CA thường xác thực định danh theo mục đích cấp chứng chỉ; nó không mặc nhiên trao quyền phát hành OAuth access token cho mọi người sở hữu chứng chỉ TLS hợp lệ.

### 6.1. HTTPS khi tải x5u có đủ không?

**Không.** HTTPS giúp đảm bảo client kết nối tới đúng hostname/certificate TLS, dữ liệu được bảo vệ trên đường truyền. Nhưng **https://attacker.example/cert.pem** có thể được phục vụ an toàn bằng một chứng chỉ TLS hợp lệ thuộc attacker. Khi đó TLS đúng, nội dung vẫn không phải nguồn ký access token được API chấp nhận.

Tương tự, TLS của **JWKS endpoint** phải được xác minh để chống thay khóa trên đường truyền, nhưng đây chỉ là một thành phần của chuỗi trust. Nguồn endpoint phải được quản trị tin cậy trước.

### 6.2. x5t và x5t#S256 chỉ là dấu nhận diện

Một token có header:

~~~json
{
  "alg": "RS256",
  "x5t#S256": "<base64url-sha256-thumbprint>"
}
~~~

Thumbprint hỗ trợ định danh chứng chỉ. Nếu Resource Server **đã pin** một thumbprint từ cấu hình đáng tin cậy, có thể so sánh và áp dụng chính sách tương ứng. Nhưng thumbprint do chính token gửi lên không tự xác nhận certificate đáng tin; attacker có thể tạo cả certificate và thumbprint cho certificate của họ.

Khi cần thumbprint mới, nên sử dụng **x5t#S256** thay vì dựa vào SHA-1 thumbprint cũ, đồng thời vẫn kiểm trust chain và liên kết issuer theo mô hình hệ thống.

## 7. SSRF: rủi ro mạng khi tự tải jku hoặc x5u

Tự động truy cập URL trong JWT không chỉ gây **key substitution**, mà còn tạo nguy cơ **Server-Side Request Forgery (SSRF)**. Kẻ tấn công có thể yêu cầu Resource Server gửi HTTP request từ môi trường của server tới các đích mà client bên ngoài không truy cập được.

Ví dụ các đích không nên do một JWT bất kỳ tùy ý chỉ định:

~~~text
http://127.0.0.1:8080/internal
http://169.254.169.254/
http://localhost/admin
http://internal-service.cluster.local/keys
https://attacker.example/redirect-to-internal
~~~

Các địa chỉ này chỉ minh họa nguy cơ; không chạy thử URL nội bộ trái phép. Resource Server có thể nằm trong mạng cloud/Kubernetes với quyền mạng khác người gửi token, khiến SSRF nghiêm trọng hơn.

### 7.1. Chỉ kiểm “URL bắt đầu bằng https” không đủ

Đường dẫn có thể:

- Dẫn tới máy chủ do attacker kiểm soát nhưng sở hữu chứng chỉ HTTPS hợp lệ.
- Chuyển hướng (HTTP redirect) tới host hoặc IP khác.
- Có hostname DNS thay đổi kết quả phân giải.
- Dùng các dạng biểu diễn IP, IPv6, user-info, port hoặc encoding khó lường để vượt bộ lọc sơ sài.
- Trỏ tới một URL đã nằm trong allowlist theo tên nhưng nằm ngoài chính sách mạng thực tế sau redirect/proxy.

Vì vậy, nếu một giao thức **thực sự yêu cầu** tải **jku/x5u** động, phải có bộ kiểm soát cho **cả trust của khóa lẫn an toàn network fetch**. Không thể thay bằng một câu lệnh kiểm chuỗi đơn giản như kiểm hostname có chứa chữ **login**.

### 7.2. Những kiểm soát tối thiểu khi giao thức cần URL khóa động

Với thiết kế được phê duyệt cho phép một số nguồn cụ thể:

- Xác định **allowlist issuer và endpoint khóa** trước, không lấy whitelist từ chính token.
- Giới hạn HTTPS, kiểm certificate chain và hostname; không dùng **trust-all**.
- Giới hạn redirect nghiêm ngặt hoặc tắt redirect; nếu cho phép thì kiểm lại toàn bộ đích sau redirect.
- Thiết lập timeout kết nối/đọc, giới hạn response size, content type và số request tránh DoS.
- Kiểm DNS/IP/network destination phù hợp ở mỗi bước; không cho truy cập loopback, link-local, internal metadata hoặc private network ngoài ranh giới được phép.
- Áp dụng egress firewall, network policy/service mesh rule để giới hạn nguồn mà Resource Server có thể gọi.
- Không forward Authorization header, token, cookie hay client secret khi tải JWKS/certificate.
- Cache có kiểm soát, giới hạn số distinct URL/kid để tránh attacker buộc tải hàng loạt.
- Ghi telemetry ở mức an toàn, không log raw JWT hoặc secret.

**Network allowlist không thay thế trust vào issuer.** Một JWKS endpoint nằm trên mạng được phép vẫn không mặc nhiên có quyền cấp JWT cho API nếu nó chưa được ràng buộc theo chính sách phát hành token.

Trong Spring Security JWT Resource Server tiêu chuẩn, ưu tiên cách đơn giản hơn: **không cho token quyết định nguồn khóa**; dùng **issuer-uri/jwk-set-uri đáng tin cậy**.

## 8. Cấu hình Spring Boot Resource Server theo chuỗi tin cậy cố định

Một API Spring Boot dùng JWT nên để Spring Security lấy public key từ issuer/JWKS được quản trị cấu hình.

Ví dụ **application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Trong cấu hình được Spring Boot hỗ trợ:

- **issuer-uri** định danh Authorization Server mà API tin cậy.
- Spring Security có thể dùng metadata discovery để tìm **jwks_uri** của issuer.
- **audiences** yêu cầu access token dành cho **orders-api**.
- Decoder dùng khóa công khai tương ứng và áp dụng những kiểm tra token được cấu hình.

Nếu đã biết chính xác JWKS URI, có thể khai báo thêm:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

**jwk-set-uri ở đây xuất phát từ cấu hình đáng tin cậy**, không lấy từ **jku** mà client gửi kèm JWT. Giữ **issuer-uri** giúp xác thực **iss** theo cấu hình tiêu chuẩn; audience vẫn cần được kiểm riêng.

Điều kiện cần xem trên đúng release Spring Boot/Security:

- Spring Boot 3.x thường dùng **spring-boot-starter-oauth2-resource-server**.
- Spring Boot 4.x dùng starter mới **spring-boot-starter-security-oauth2-resource-server**.
- Dùng dependency management/BOM của Boot; không trộn major version của các module Spring Security.
- Nếu tự tạo JwtDecoder bean, có thể làm thay đổi auto-configuration; phải bảo toàn validator issuer, audience, timestamps và token profile theo chính sách.

### 8.1. SecurityFilterChain kiểm quyền sau khi xác thực

Ví dụ Spring Security Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );
        return http.build();
    }
}
~~~

Dù token được xác minh bằng trusted JWKS, API vẫn phải phân quyền. **SCOPE_orders.read** chỉ cho phép một loại thao tác; kiểm tenant, owner hoặc trạng thái đơn phải được thực hiện theo chính sách nghiệp vụ.

### 8.2. Dùng NimbusJwtDecoder với JWKS URI đã cấu hình

Khi cần cấu hình decoder thủ công, có thể dùng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    private static final String TRUSTED_JWKS_URI =
        "https://login.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(TRUSTED_JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token audience does not include orders-api",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(standard, audience)
        );
        return decoder;
    }
}
~~~

Đoạn code minh họa các quyết định:

1. **TRUSTED_JWKS_URI** là hằng số do API quản trị, không phải giá trị từ JWT header **jku**.
2. **RS256** được đưa vào danh sách thuật toán chấp nhận theo hợp đồng của issuer.
3. **JwtValidators.createDefaultWithIssuer** bao gồm các kiểm tra mặc định phù hợp cùng issuer.
4. Audience validator từ chối JWT không dành cho **orders-api**.
5. Decoder báo lỗi nếu chữ ký hoặc validators thất bại; API không tạo authenticated principal cho token giả.

Khi tùy biến decoder, xem yêu cầu profile access token, ví dụ **typ = at+jwt**, theo nhà phát hành; không chấp nhận OIDC ID Token như một Bearer access token chỉ vì hai loại JWT cùng được ký bởi OP.

Quan trọng: ví dụ không cần đọc **jku**, **x5u** hay **jwk** từ JOSE header để dựng URL hoặc public key. Cơ chế chọn key được giới hạn trong JWKS đáng tin cậy mà decoder đã được cấu hình.

## 9. Ví dụ code nguy hiểm cần nhận diện khi review

Một anti-pattern có thể được viết như pseudocode:

~~~java
// SAI - chỉ minh họa lỗi thiết kế; không phải API JOSE hoàn chỉnh.
String rawToken = readAuthorizationBearer(request);
Map<String, Object> header = parseHeaderWithoutVerification(rawToken);
String keyUrl = (String) header.get("jku");

// URL do token tự chọn.
JwkSet attackerControlledKeys = fetchJwks(keyUrl);

boolean signatureMatches = verifySignature(rawToken, attackerControlledKeys);
if (signatureMatches) {
    // Kẻ gửi token có thể tự ký bằng key họ đăng tại jku.
    acceptClaimsAsAuthenticated(rawToken);
}
~~~

Các hàm trong đoạn trên là **tên minh họa**, không phải Spring Security API. Ý tưởng nguy hiểm là **lấy keyUrl từ JWT chưa xác thực** và xem bất kỳ key nào trả về như khóa issuer được tin cậy.

Một biến thể tương tự:

~~~java
// SAI - mô hình tự xác minh bằng khóa đính kèm.
Map<String, Object> header = parseHeaderWithoutVerification(rawToken);
PublicKey key = parseJwk((Map<?, ?>) header.get("jwk"));
boolean valid = verifySignature(rawToken, key);
~~~

Ngay cả khi **valid = true**, câu hỏi “Ai cho phép key này ký access token?” chưa được trả lời. Chữ ký đúng với khóa tự cung cấp không đủ cho authentication.

Cách khắc phục trong ứng dụng dùng Spring Security:

- Sử dụng **JwtDecoder** với issuer/JWKS tin cậy.
- Không tự tạo **JwtAuthenticationToken** từ claims của token chưa qua decoder.
- Không tự động cho token khai báo **jku**, **x5u**, **jwk** hoặc **kid** để chuyển trust boundary.
- Từ chối JWT không thể xác minh theo hợp đồng đã cấu hình.

## 10. Đa issuer, tenant và trường hợp phải chọn khóa động

Một hệ thống SaaS có thể nhận token từ nhiều issuer, ví dụ:

~~~text
Tenant A: https://login.example.com/realms/a
Tenant B: https://login.example.com/realms/b
Tenant C: https://identity.partner.example/oidc
~~~

Hệ thống có thể cần chọn **JwtDecoder** dựa trên issuer/tenant. Trong mô hình này, **chọn động không đồng nghĩa tin mọi issuer**.

Quy tắc:

1. Hệ thống quản trị **danh sách issuer được phép**, mỗi issuer có cấu hình trust riêng.
2. Nếu đọc claim **iss** chưa xác minh để định tuyến, chỉ dùng nó làm **gợi ý tra cứu trong danh sách cho phép**.
3. Mỗi decoder xác minh token bằng JWKS của issuer đã đăng ký và validate **iss**, **aud**, thời hạn và các yêu cầu khác.
4. Claims chưa xác thực không được tạo thêm một issuer hoặc JWKS URL mới trên runtime.
5. Chính sách nghiệp vụ vẫn kiểm tenant/membership trên dữ liệu, kể cả token của issuer hợp lệ.

Spring Security có các cơ chế multi-tenancy như **JwtIssuerAuthenticationManagerResolver** trong ngữ cảnh phù hợp; với triển khai thật cần chọn cấu hình chỉ nhận issuer đã được cho phép. Không tạo resolver mặc định theo bất kỳ URL issuer mà client cung cấp.

### 10.1. Vì sao không chỉ dựa vào tên miền?

Một issuer có thể có nhiều realm hoặc tenant trên cùng hostname. Token ký bởi **/realms/a** không tự được chấp nhận cho **/realms/b**.

Ngược lại, một issuer đáng tin có thể công bố **jwks_uri** trên một hostname khác thông qua metadata đã được xác thực. Vì thế quy tắc “cùng domain là tin” hoặc “khác domain là luôn sai” đều không đầy đủ. Cần quan hệ **issuer → metadata/JWKS** được xác lập rõ trong chính sách của API.

## 11. Trường hợp đặc biệt: khóa đính kèm có thể được dùng trong DPoP

Một ngoại lệ dễ gây hiểu nhầm là **DPoP (Demonstrating Proof-of-Possession)**, được quy định bởi **RFC 9449**. DPoP proof là một JWT có thể chứa public **jwk** trong JOSE header và được ký bằng private key tương ứng.

Vậy tại sao DPoP có thể dùng khóa đính kèm?

Vì giao thức **không coi public key trong DPoP proof là issuer ký access token**. Thay vào đó, server kiểm những điều kiện khác:

- DPoP proof được ký bằng private key tương ứng với public JWK đính kèm.
- Proof có các claim/ràng buộc như HTTP method (**htm**), HTTP URI (**htu**), thời điểm (**iat**), định danh chống replay (**jti**), nonce khi được yêu cầu, và các điều kiện protocol khác.
- Access token được Authorization Server cấp và xác minh theo cách đáng tin cậy.
- Access token được **sender-constrained**, thường mang xác nhận **cnf.jkt** là JWK thumbprint; API so nó với khóa dùng trong DPoP proof.
- Resource Server kiểm sự gắn kết giữa access token, DPoP proof và request hiện tại.

Do đó, **jwk trong DPoP proof** giúp kiểm *người đang gọi có private key gắn với access token đã được issuer xác nhận hay không*. Nó không được dùng để tự xác minh và công nhận access token do attacker tự tạo.

~~~mermaid
flowchart LR
    AT[Access token từ issuer tin cậy] --> V[Kiểm signature / introspection]
    V --> C[Đọc cnf.jkt đã xác thực]
    P[DPoP proof có JWK đính kèm] --> S[Kiểm chữ ký proof]
    S --> T[Kiểm htm, htu, iat, jti, nonce...]
    C --> M{Thumbprint proof key khớp cnf.jkt?}
    T --> M
    M -->|Có, và mọi kiểm tra đạt| OK[Proof-of-possession hợp lệ]
    M -->|Không| NO[Từ chối]
~~~

Không thể biến một Bearer Resource Server bình thường thành DPoP Resource Server chỉ bằng cách chấp nhận **header.jwk**. DPoP đòi hỏi logic giao thức, token binding và replay protection đầy đủ. Đây là một ví dụ minh chứng: **khóa đính kèm chỉ có giá trị trong một chính sách tin cậy được định nghĩa tường minh**.

## 12. Khóa đính kèm và vòng đời khóa ký JWT

Trong chủ đề **JWK và vòng đời khóa**, cần thấy sự khác biệt giữa rotation do issuer kiểm soát và thay khóa tùy ý theo token.

### 12.1. Rotation đúng: issuer thay public keys tại JWKS tin cậy

Giả sử issuer có public key A và muốn chuyển sang B:

| Thời điểm | Khóa issuer dùng ký JWT | JWKS được công bố tại URL tin cậy | Resource Server |
|---|---|---|---|
| **T0** | A | A | Xác minh token bằng A |
| **T1** | A | A và B | Có thể cache B trước |
| **T2** | B | A và B | Chấp nhận token cũ A còn hạn và token mới B |
| **T3** | B | B | Ngừng dùng A sau giai đoạn overlap phù hợp |

Nguồn JWKS vẫn là endpoint được issuer quản trị; nội dung tập khóa thay đổi có kiểm soát. **kid** hỗ trợ chọn khóa trong tập; không trở thành quyền tự động đưa khóa mới từ token.

Các yêu cầu vận hành:

- Công bố public key mới trước khi ký token mới nếu có thể.
- Giữ key cũ đủ lâu cho token còn hiệu lực, trừ tình huống cần thu hồi khẩn.
- Có chính sách cache/refresh của JWKS decoder.
- Không tái sử dụng cùng **kid** cho vật liệu khóa khác trong lúc cache cũ còn tồn tại.
- Khi khóa ký bị lộ, xem xét rotation/thu hồi theo quy trình sự cố; không chỉ đổi kid trong header.
- Không công bố private key hoặc symmetric secret trong public JWKS.

### 12.2. Vì sao tùy ý chấp nhận jku làm hỏng vòng đời khóa?

Nếu mỗi token có thể trỏ tới JWKS riêng, issuer mất khả năng kiểm soát tập khóa mà Resource Server chấp nhận. Việc issuer xóa khóa A khỏi JWKS tin cậy không ngăn ai đó tiếp tục đưa khóa A hoặc một key khác qua **jku** của họ.

Điều đó làm suy yếu rotation và khả năng phản ứng khi khóa bị xâm phạm. Nguồn khóa phải có **vòng đời được quản trị**, không được nâng cấp trust chỉ qua việc xuất hiện trong JOSE header của request.

## 13. Những lỗi thường gặp và cách xử lý

| Sai lầm | Rủi ro | Hướng đúng |
|---|---|---|
| Lấy **jku** từ JWT và tải JWKS ở URL đó | Key substitution, token giả, SSRF | Chỉ tải JWKS từ issuer/JWKS URI đã được tin cậy |
| Lấy **jwk** đính kèm rồi kiểm JWT với key đó | Token tự ký được coi là token của issuer | Ràng buộc key vào issuer/khóa đã tin hoặc protocol PoP riêng |
| Lấy **x5u** và dùng certificate mà không kiểm trust | Chứng chỉ giả hoặc không được ủy quyền ký token | Kiểm chain, trust anchor, danh tính/key binding theo profile |
| Dùng **x5c** như chứng nhận quyền ký | Embedded certificate do token tự đưa lên | Không tự tin certificate đính kèm; xác minh chính sách tin cậy |
| Tin **x5t#S256** do JWT tự khai | Fingerprint của khóa không được ủy quyền | So với pin/nguồn xác nhận đã được cấu hình |
| Xem **kid** như nguồn key duy nhất | Có thể trùng kid giữa issuer hoặc attacker tự chọn | Chọn trong key set của issuer tin cậy |
| Chỉ kiểm **alg** có tồn tại | Algorithm confusion hoặc **none** | Allowlist thuật toán được issuer/API thống nhất |
| Chỉ kiểm chữ ký mà bỏ qua **iss/aud** | Token cho API hoặc issuer khác bị nhận nhầm | Kiểm issuer, audience, timestamps, token profile |
| Redirect tự do khi tải jku/x5u | SSRF hoặc chuyển endpoint sang host khác | Không tải URL từ token; nếu protocol cần, khóa allowlist và redirect |
| Coi HTTPS là đủ để tin jku | Host attacker cũng có chứng chỉ TLS hợp lệ | HTTPS và nguồn issuer được ủy thác là hai điều kiện độc lập |

### 13.1. Nếu JOSE header vẫn chứa jku/x5u thì phải làm gì?

Không phải cứ một token có trường **jku** hoặc **x5u** là phải cho phép truy cập URL đó. Một Resource Server có thể tiếp tục xử lý token theo chính sách issuer/JWKS độc lập nếu implementation và profile cho phép, hoặc **từ chối** những header bất ngờ trong chính sách nghiêm ngặt.

Điểm bắt buộc là **không để trường đó âm thầm thay nguồn trust**. Trong các giao thức JOSE đặc thù yêu cầu jku/x5u, phải xây dựng trust policy cho URL/certificate trước khi sử dụng.

### 13.2. Có thể tin x5c nếu chứng chỉ được public CA ký không?

**Không tự động.** Certificate chain hợp lệ với public CA có thể xác nhận danh tính hoặc các ràng buộc của certificate theo mục đích của nó, nhưng không đồng nghĩa người giữ private key được phép cấp OAuth2 access token cho issuer cụ thể. Cần mối quan hệ ủy quyền rõ ràng tới issuer, thuật toán/key usage và token profile.

### 13.3. Cần làm gì nếu JWKS của issuer không có kid tương ứng?

Có thể gặp rotation hoặc cache cũ. Decoder được phép refresh **JWKS tại URL tin cậy đã cấu hình** theo chính sách cache. Nếu vẫn không tìm thấy key phù hợp, phải từ chối token. Không fallback sang **jku** của JWT hoặc một host ngẫu nhiên để “sửa 401”.

### 13.4. Token do cùng issuer ký nhưng có aud dành cho API khác?

Phải từ chối nếu audience không phù hợp với Resource Server. Có JWKS/key tin cậy chỉ giúp xác minh chữ ký; **audience validation** vẫn là phần bắt buộc của chính sách nhận access token.

### 13.5. Chấp nhận khóa trong header có khi nào đúng?

Có, nếu một giao thức **định nghĩa rõ** khóa đó là dữ liệu đầu vào cho một phép xác minh riêng, và có một **trust anchor độc lập** để gắn nó với chủ thể được ủy quyền. DPoP là ví dụ. Nhưng **jwk trong access token tự gửi** không phải mặc định được chấp nhận làm signing key của issuer.

## 14. Quan sát và xử lý lỗi mà không làm lộ token

Khi triển khai, nên phân biệt lỗi ở tầng nào:

1. **Không tìm được issuer/JWKS:** kiểm issuer-uri, metadata, jwk-set-uri, HTTPS/certificate, DNS/egress.
2. **Không có key phù hợp:** kiểm kid, kty, algorithm allowlist, JWKS cache và rotation.
3. **Chữ ký sai:** token bị sửa, key sai, issuer sai, hoặc thuật toán chưa được hỗ trợ.
4. **Claims không hợp lệ:** issuer, audience, exp/nbf, token profile không đạt.
5. **Thiếu quyền:** token hợp lệ nhưng scope/role/tenant/owner không đạt.

Với Bearer Resource Server thông thường:

| Tình huống | HTTP thường gặp |
|---|---|
| JWT sai chữ ký hoặc không có key tin cậy | **401 Unauthorized** |
| JWT có issuer/audience không đúng hoặc hết hạn | **401 Unauthorized** |
| JWT đã xác thực nhưng thiếu authority hoặc quyền nghiệp vụ | **403 Forbidden**, đôi khi **404** nếu chính sách che dữ liệu |
| JWT hợp lệ và đủ quyền | API tiếp tục xử lý theo nghiệp vụ |

Đừng ghi nguyên JWT vào logs, exception messages, metrics labels hay ticket lỗi. Bearer token có thể bị tái sử dụng nếu lộ trong thời gian còn hiệu lực. Dùng request ID, status code và nguyên nhân tổng quát, cùng số liệu tải JWKS đã loại bỏ bí mật.

### 14.1. Kiểm JWKS hợp lệ bằng curl mà không dùng token thật

Nếu đã biết **JWKS URI tin cậy** từ cấu hình/metadata:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/protocol/openid-connect/certs \
  | jq '.keys[] | {kid, kty, use, alg}'
~~~

Đoạn này chỉ xem metadata public keys và không cần access token của người dùng. Không đổi URL sang một **jku** tùy ý do JWT chưa xác minh cung cấp.

Nếu cần quan sát metadata discovery:

~~~bash
curl --fail --show-error --silent \
  https://login.example.com/realms/shop/.well-known/openid-configuration \
  | jq '{issuer, jwks_uri}'
~~~

Đường dẫn issuer/provider là ví dụ; endpoint thực tế cần tra theo nhà phát hành đã cấu hình và giao thức OIDC/RFC 8414. Không dùng **curl -k**, tắt certificate verification hoặc hạ xuống HTTP để “xử lý tạm” lỗi TLS.

## 15. Kiểm thử các nhánh có nguy cơ tin nhầm khóa

Một số kịch bản đáng kiểm trong môi trường thử nghiệm:

| Kịch bản | Kết quả mong đợi |
|---|---|
| JWT hợp lệ, ký bằng private key của issuer, đúng **iss/aud/exp**, đủ quyền | Được xác thực và tiếp tục authorization |
| JWT do key không tin cậy ký nhưng **jku** trỏ tới JWKS của người gửi | **Bị từ chối** |
| JWT do key không tin cậy ký và có **jwk** public key tương ứng ngay trong header | **Bị từ chối** |
| JWT do key không tin cậy ký, có **x5u** tới chứng chỉ của người gửi | **Bị từ chối** |
| JWT mang **x5c** certificate self-signed của người gửi | **Bị từ chối** |
| JWT mang **kid** trùng key đáng tin nhưng chữ ký sai | **Bị từ chối** |
| JWT khai báo **alg = none** hoặc thuật toán không được cho phép | **Bị từ chối** |
| JWT chữ ký hợp lệ nhưng **aud** là resource khác | **Bị từ chối** |
| Issuer rotation theo JWKS đáng tin, hai key hợp lệ trong khoảng overlap | JWT có key phù hợp được xác minh theo chính sách |
| Key cũ bị gỡ và JWT không thể được xác minh | **Bị từ chối**, không fallback sang URL từ JWT |
| JWKS endpoint tạm không truy cập được và key chưa có trong cache | Không thể xác minh token mới; không bỏ bước verification |

Các test authorization dùng mock JWT trong Spring Security Test **không thay thế** bài kiểm tra decoder/chữ ký thật: mock Authentication có thể bỏ qua bước kiểm trust. Với integration test, dùng issuer/JWKS và private key **riêng cho môi trường test**, gửi token thử qua security chain và xác minh các yêu cầu bị từ chối đúng cách.

Để kiểm SSRF, không cần cố tình truy cập mạng nội bộ thật. Có thể kiểm thiết kế không thực hiện request tới **jku/x5u** được gửi từ JWT, hoặc sử dụng một HTTP server mock và chặn mọi outbound request không nằm trong allowlist được cấu hình.

## 16. Quy tắc thiết kế và review

Trước khi chấp nhận một thay đổi liên quan đến JWT/JWS/JWK, hãy trả lời được:

1. **Trust anchor là gì?** Issuer URI, JWKS URI hoặc key pin nào được quản trị cấu hình?
2. **Key selector lấy khóa từ đâu?** Chỉ nguồn đã tin hay nguồn tự khai trong header?
3. **jku/x5u/jwk/x5c có được xử lý không?** Nếu có, giao thức nào yêu cầu và quan hệ trust được thiết lập bằng cách nào?
4. **Có nguy cơ SSRF không?** URL nào được fetch, redirect/DNS/IP/egress bị ràng buộc ra sao?
5. **Thuật toán và key type được allowlist chưa?** Có chống algorithm confusion, alg none và mismatch key không?
6. **Có kiểm claims không?** issuer, audience, exp/nbf, token type/profile và các điều kiện domain?
7. **Multi-tenant có allowlist issuer chưa?** Có tránh chấp nhận issuer bất kỳ do token tự nêu không?
8. **Rotation được quản trị ở đâu?** JWKS của issuer, caching, overlapping keys, thu hồi khẩn cấp?
9. **Quyền nghiệp vụ được kiểm ở đâu?** Scope chỉ là điều kiện đầu, vẫn phải kiểm bản ghi và tenant?
10. **Test có bao phủ khóa attacker tự cung cấp chưa?** Gồm jku, jwk, x5u, x5c và token giả issuer?

Khi nhìn thấy code **readHeader("jku")**, **fetchJwks(urlFromToken)** hoặc **verifyWith(header.get("jwk"))**, hãy kiểm tra ngay trust policy. Đây là điểm đặc biệt nhạy cảm trong mọi lớp xác thực JWT.

## Kết luận

Các JOSE header **jku**, **x5u**, **jwk**, **x5c**, **kid** và thumbprint có thể hỗ trợ **tìm hoặc mô tả khóa**. Chúng **không cấp quyền cho token lựa chọn một nguồn phát hành được API tin cậy**. Chữ ký được xác minh bằng public key mà chính người gửi cung cấp chỉ chứng minh người gửi giữ private key đó; nó không chứng minh người gửi là Authorization Server hợp pháp.

Với **Spring Security OAuth 2.0/OIDC Resource Server**, hướng thông thường là cấu hình **issuer-uri**, nhận **jwks_uri** qua discovery của issuer đáng tin cậy hoặc cấu hình **jwk-set-uri** tường minh, giới hạn thuật toán rồi kiểm signature, issuer, audience, thời hạn và quyền nghiệp vụ. Chỉ sử dụng khóa đính kèm trong các giao thức chuyên biệt nếu đã có trust anchor độc lập và toàn bộ quy trình binding/verification phù hợp.

### Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS), JOSE Header Parameters](https://www.rfc-editor.org/rfc/rfc7515#section-4.1)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof-of-Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)

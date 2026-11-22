# Nguồn JWKS đáng tin cậy và ràng buộc với bên phát hành

Trong hệ thống **Security - JSON Web Token (JWT)**, public key dùng để xác minh chữ ký phải đến từ đúng bên phát hành mà ứng dụng đã quyết định tin cậy. Một JWK có thể hoàn toàn hợp lệ về mặt toán học nhưng vẫn là khóa của attacker. Vì vậy, bảo mật không dừng ở việc tải được một JWKS hoặc tìm thấy `kid`: verifier phải xây dựng và duy trì mối quan hệ tin cậy rõ ràng giữa **issuer**, **metadata của issuer**, **địa chỉ JWKS**, **tập khóa** và **chính sách chấp nhận token**.

Bài này thuộc chương **Khóa và JWKS** của module **SECURITY_TOKEN_SECURITY_JWT**. Nội dung áp dụng cho bảo mật JWT nói chung, độc lập với ngôn ngữ lập trình, nền tảng và framework.

## 1. Mục tiêu và mô hình tin cậy

Sau bài học, người đọc có thể:

1. Phân biệt việc nhận diện issuer với việc xác minh chữ ký và việc cấp quyền truy cập.
2. Thiết lập nguồn JWKS từ cấu hình tin cậy hoặc metadata discovery đã được xác thực.
3. Ràng buộc `iss` với đúng metadata, `jwks_uri` và key set.
4. Nhận diện các rủi ro như issuer injection, JWKS substitution, SSRF, redirect abuse, cache poisoning và nhầm lẫn giữa các tenant.
5. Thiết kế quy trình cập nhật metadata, rotation và thu hồi khóa mà không mở rộng miền tin cậy ngoài ý muốn.

Một mô hình tin cậy điển hình:

~~~mermaid
flowchart TD
    A["Cấu hình tin cậy / Trust anchor"] --> B["Issuer được phép"]
    B --> C["Metadata endpoint được xác thực"]
    C --> D["Metadata issuer khớp chính xác"]
    D --> E["jwks_uri trong metadata"]
    E --> F["JWKS lấy qua kênh bảo mật"]
    F --> G["JWK hợp lệ, đúng mục đích và thuật toán"]
    G --> H["Xác minh chữ ký JWT"]
    H --> I["Kiểm tra iss, aud, exp, nbf và token profile"]
    I --> J["Chính sách ứng dụng / quyền truy cập"]
~~~

Mỗi mũi tên là một ràng buộc cần được kiểm soát. Nếu nguồn ban đầu không đáng tin, các bước sau có thể được thực hiện hoàn hảo về mặt kỹ thuật nhưng vẫn xác minh token của attacker.

## 2. Phân biệt các khái niệm thường bị gộp chung

| Khái niệm | Câu hỏi được trả lời | Điều nó không tự chứng minh |
| --- | --- | --- |
| **Issuer (`iss`)** | Token tuyên bố do ai phát hành? | Giá trị `iss` trong token chưa xác minh không chứng minh danh tính bên phát hành. |
| **Trust anchor / cấu hình tin cậy** | Ứng dụng cho phép tin issuer nào và bắt đầu xác thực từ đâu? | Không chứng minh từng token hợp lệ. |
| **Metadata endpoint** | Issuer công bố endpoint và khả năng nào? | Metadata lấy từ một nguồn không đáng tin không tạo ra trust. |
| **`jwks_uri`** | Lấy tập khóa JWK ở đâu? | URL không tự chứng minh nội dung trả về thuộc issuer hợp lệ. |
| **JWKS** | Những JWK nào đang được công bố? | Không phải danh sách JWT đang có hiệu lực hoặc danh sách quyền người dùng. |
| **`kid`** | JWK nào là ứng viên cho token? | Không phải danh tính issuer hoặc bằng chứng xác thực. |
| **Chữ ký hợp lệ** | Nội dung JWS có được ký bằng khóa tương ứng và không bị sửa? | Không tự chứng minh audience, thời hạn, loại token hoặc quyền truy cập. |

**Issuer** là định danh của bên phát hành trong giao thức. **Trust anchor** là cơ sở mà ứng dụng dựa vào để quyết định issuer nào được phép tham gia. Trust anchor có thể là cấu hình do quản trị viên thiết lập, danh sách issuer được tổ chức phê duyệt, hoặc một cơ chế liên kết danh tính có quy tắc xác thực riêng. Không lấy một chuỗi `iss` tùy ý từ token làm trust anchor.

## 3. Ràng buộc `iss` với cấu hình tin cậy

Claim `iss` trong JWT là một chuỗi định danh issuer. Với cùng một hệ thống, cần xác định chính xác issuer nào được chấp nhận, bao gồm scheme, host, path và các quy tắc so khớp do profile áp dụng quy định.

Ví dụ registry tin cậy:

~~~yaml
trustedIssuers:
  - issuer: "https://id.example.test/tenant-a"
    metadataType: "oidc"
    discoveryUri: "https://id.example.test/tenant-a/.well-known/openid-configuration"
    expectedAudience:
      - "billing-api"
    allowedJwsAlgorithms:
      - "RS256"
    tokenProfile: "access-token"
~~~

Đây là cấu hình minh họa. Địa chỉ discovery thực tế phụ thuộc giao thức và cách triển khai issuer. Điều quan trọng là ứng dụng đã biết trước issuer được phép và điểm bắt đầu discovery.

### 3.1. So khớp issuer chính xác

Trong các profile như OpenID Connect, giá trị `issuer` trong metadata phải khớp chính xác với issuer được mong đợi và với `iss` của ID Token. Khi kiểm tra issuer:

- Không tự ý chuyển chữ hoa/thường của host hoặc path.
- Không tự ý thêm/bỏ dấu `/` ở cuối.
- Không bỏ path của tenant hoặc realm.
- Không đổi scheme `http`/`https`.
- Không thay thế issuer bằng domain của `jwks_uri`.
- Không coi hai chuỗi issuer gần giống nhau là tương đương theo suy đoán.

Ví dụ:

| Giá trị | Có được tự coi là cùng issuer? | Lý do |
| --- | --- | --- |
| `https://id.example.test/tenant-a` | Giá trị gốc | Issuer đã đăng ký. |
| `https://id.example.test/tenant-a/` | Không tự chuẩn hóa thành giá trị gốc | Khác chuỗi issuer; dấu `/` có thể có ý nghĩa theo profile. |
| `http://id.example.test/tenant-a` | Không | Khác scheme và mức bảo vệ kênh. |
| `https://id.example.test/tenant-b` | Không | Khác tenant/path. |
| `https://other.example.test/tenant-a` | Không | Khác host. |

Không tự viết hàm chuẩn hóa URL để biến các giá trị khác nhau thành một issuer duy nhất. Hãy áp dụng quy tắc so khớp của chuẩn/profile đang dùng và cấu hình issuer chính xác.

### 3.2. Đọc `iss` trước khi xác minh có được không?

Hệ thống nhiều issuer đôi khi cần đọc payload chưa xác minh để chọn cấu hình. Có thể làm việc đó **chỉ như thao tác tra cứu**:

1. Parse `iss` mà không tin nội dung.
2. Tra cứu chính xác trong registry issuer đã được cấu hình.
3. Nếu không có kết quả, từ chối token.
4. Nếu có kết quả, chỉ dùng metadata/JWKS endpoint gắn với registry đó.
5. Xác minh chữ ký, sau đó kiểm tra lại `iss` đã xác minh khớp issuer cấu hình.

Không dùng `iss` chưa xác minh để tạo tenant mới, tự đăng ký issuer, truy cập một URL bất kỳ hoặc mở rộng danh sách trust anchor.

## 4. Nguồn bắt đầu discovery: cấu hình tĩnh và metadata

Có hai cách phổ biến để xác định nguồn khóa.

### 4.1. Cấu hình tĩnh

Ứng dụng được cấu hình trực tiếp issuer và JWKS URI:

~~~yaml
issuer: "https://identity.example.test/"
jwksUri: "https://identity.example.test/keys/current"
allowedAlgorithms:
  - "RS256"
audience:
  - "orders-api"
~~~

Phù hợp khi:

- Số issuer ít và được quản trị tập trung.
- Endpoint khóa thay đổi hiếm hoặc được kiểm soát qua quy trình triển khai.
- Môi trường yêu cầu pin rõ nguồn khóa và không cần discovery động.

Rủi ro là cấu hình có thể lỗi thời khi issuer thay endpoint, đổi domain hoặc triển khai tenant mới. Cần có quy trình cập nhật, kiểm tra và phê duyệt thay đổi.

### 4.2. Discovery qua metadata

Thay vì cấu hình trực tiếp `jwks_uri`, ứng dụng bắt đầu từ issuer đã tin cậy, truy xuất metadata theo chuẩn tương ứng, kiểm tra metadata, sau đó lấy `jwks_uri` được quảng bá.

Ưu điểm:

- Endpoint và khả năng của issuer có thể được công bố theo định dạng chuẩn.
- Có thể thay đổi JWKS URI mà không cần thay cấu hình từng verifier, nếu discovery và metadata vẫn nằm trong trust boundary đã phê duyệt.
- Hỗ trợ các hệ sinh thái nhiều nhà cung cấp và nhiều issuer.

Rủi ro:

- Discovery từ issuer không được tin cậy có thể biến thành SSRF hoặc nguồn khóa giả.
- Metadata bị thay đổi có thể điều hướng verifier sang JWKS của attacker.
- Metadata hợp lệ về cú pháp vẫn có thể không phù hợp policy ứng dụng.

**Discovery là cách lấy metadata, không phải cách tự động tạo trust.** Trust anchor phải được thiết lập trước discovery.

## 5. OAuth Authorization Server Metadata và OpenID Connect Discovery

Hai cơ chế phổ biến có mục đích gần nhau nhưng quy tắc xây dựng metadata URL khác nhau. Không trộn lẫn hai cách tạo endpoint.

### 5.1. OAuth 2.0 Authorization Server Metadata — RFC 8414

RFC 8414 định nghĩa metadata cho OAuth 2.0 Authorization Server. Metadata có member `issuer` và có thể công bố `jwks_uri` cùng nhiều endpoint/khả năng khác.

Đối với issuer có path, quy tắc tạo metadata URL của RFC 8414 chèn đoạn `/.well-known/oauth-authorization-server` **giữa authority và path issuer**.

Ví dụ:

~~~text
Issuer:
https://as.example.test/tenant-a

Metadata endpoint theo RFC 8414:
https://as.example.test/.well-known/oauth-authorization-server/tenant-a
~~~

Nếu issuer không có path:

~~~text
Issuer:
https://as.example.test

Metadata endpoint:
https://as.example.test/.well-known/oauth-authorization-server
~~~

Sau khi lấy metadata, client/verifier phải kiểm tra member `issuer` khớp chính xác issuer đã dùng để xây dựng yêu cầu metadata. Không chấp nhận metadata chỉ vì server trả về HTTP 200 hoặc JSON parse thành công.

### 5.2. OpenID Connect Discovery 1.0

OpenID Connect Discovery công bố OpenID Provider Configuration. Endpoint chuẩn thường có dạng `/.well-known/openid-configuration` gắn với issuer.

Ví dụ:

~~~text
Issuer:
https://id.example.test/tenant-a

OpenID Provider Configuration:
https://id.example.test/tenant-a/.well-known/openid-configuration
~~~

Metadata của OpenID Provider chứa `issuer` và `jwks_uri`. Client phải kiểm tra `issuer` trong provider metadata khớp chính xác issuer mong đợi. Khi xử lý ID Token, claim `iss` cũng phải khớp issuer đã xác minh.

### 5.3. So sánh cách xây dựng URL

| Cơ chế | Well-known path | Ví dụ issuer có path |
| --- | --- | --- |
| OAuth AS Metadata — RFC 8414 | Chèn sau authority, trước path issuer | `https://as.example.test/.well-known/oauth-authorization-server/tenant-a` |
| OpenID Connect Discovery | Gắn `/.well-known/openid-configuration` sau issuer | `https://id.example.test/tenant-a/.well-known/openid-configuration` |

Không tự tạo endpoint bằng cách ghép chuỗi theo thói quen. Hãy dùng đúng quy tắc của giao thức, kiểm tra metadata `issuer`, và chỉ chấp nhận kết quả trong trust boundary đã cấu hình.

### 5.4. `jwks_uri` trong metadata

`jwks_uri` là URI nơi Authorization Server/OpenID Provider công bố JWK Set. Verifier cần:

- Xác thực metadata đến từ issuer đã tin cậy.
- Kiểm tra `jwks_uri` là URI hợp lệ theo profile và dùng HTTPS trong triển khai bảo mật.
- Lưu ánh xạ issuer → metadata → `jwks_uri`.
- Áp dụng policy mạng, redirect, timeout và kích thước response.
- Không lấy `jwks_uri` từ một metadata document có issuer không khớp.

Không yêu cầu `jwks_uri` luôn cùng host với issuer nếu chuẩn/nhà cung cấp cho phép endpoint riêng. Một số hệ thống sử dụng CDN hoặc domain chuyên biệt. Thay vào đó, kiểm tra URI được quảng bá trong metadata đã xác thực và áp dụng allowlist/egress policy phù hợp với môi trường.

## 6. Xác thực metadata trước khi tin `jwks_uri`

Metadata là một mắt xích trong chuỗi tin cậy. Một quy trình cơ bản:

1. Chọn issuer từ trust registry.
2. Tạo metadata URL theo đúng chuẩn discovery.
3. Gửi request qua HTTPS, xác minh chứng chỉ và hostname.
4. Kiểm soát redirect và địa chỉ mạng đích.
5. Parse JSON với parser an toàn; từ chối dữ liệu sai cấu trúc hoặc có member trùng tên nếu parser không bảo đảm cách xử lý nhất quán.
6. Kiểm tra `issuer` trong metadata khớp chính xác issuer đã chọn.
7. Kiểm tra `jwks_uri` tồn tại, hợp lệ và phù hợp policy.
8. Lưu metadata cùng thời điểm lấy, cache validators và cấu hình nguồn.
9. Chỉ sau đó mới tải JWKS từ URI đã được chấp nhận.

HTTPS bảo vệ kết nối đến endpoint và giúp xác thực hostname của máy chủ. Nhưng HTTPS **không tự chứng minh** issuer đó được ứng dụng cho phép. Bước trust anchor và issuer matching vẫn cần thiết.

### 6.1. Có cần metadata được ký số không?

Trong các luồng OAuth/OIDC thông thường, metadata và JWKS thường được phân phối qua HTTPS; không mặc định có chữ ký JOSE riêng bao quanh từng tài liệu metadata hoặc JWKS. TLS và trust anchor cung cấp cơ chế bảo vệ kênh và xác thực nguồn theo cấu hình.

Một số hệ thống federation có thể dùng entity statement hoặc metadata được ký theo profile riêng. Khi triển khai các profile đó, phải xác minh chữ ký, chuỗi trust và chính sách federation theo đúng chuẩn. Không tự giả định mọi JWKS đều có chữ ký riêng, cũng không bỏ qua cơ chế ký nếu profile đang dùng yêu cầu.

## 7. Tải JWKS an toàn

Sau khi `jwks_uri` được xác thực, verifier tải JSON Web Key Set. Request này vẫn là request mạng có rủi ro và phải được giới hạn.

### 7.1. Kiểm soát HTTP và mạng

- Dùng HTTPS; xác minh hostname và certificate chain.
- Chỉ cho phép URL scheme và port theo policy; thông thường dùng HTTPS port được phép.
- Kiểm tra redirect từng bước; không theo redirect sang địa chỉ nội bộ, loopback, link-local hoặc host ngoài allowlist.
- Áp dụng timeout kết nối/đọc, giới hạn số lần retry và response body.
- Kiểm soát DNS resolution và egress để giảm SSRF, DNS rebinding và truy cập dịch vụ nội bộ.
- Giới hạn số lượng JWK trong một response và kích thước từng member.
- Không gửi credential hoặc secret không cần thiết đến JWKS endpoint.
- Ghi log lỗi nguồn và thời điểm, không ghi private key hay nội dung nhạy cảm.

Không phải hệ thống nào cũng có thể dùng allowlist host tĩnh vì nhà cung cấp có thể dùng CDN. Có thể dùng allowlist domain/egress theo nhà cung cấp, nhưng vẫn cần kiểm tra redirect, IP đích và chính sách mạng; không dùng quy tắc `URL metadata đã hợp lệ thì mọi redirect đều hợp lệ`.

### 7.2. Kiểm tra nội dung JWKS

Sau khi tải:

1. JSON phải parse thành object có member `keys` là array theo RFC 7517.
2. Giới hạn số lượng JWK và kích thước dữ liệu.
3. Mỗi JWK cần được kiểm tra `kty`, tham số bắt buộc, kiểu dữ liệu và Base64url.
4. Không công bố hoặc chấp nhận private material ở endpoint JWKS công khai.
5. Xử lý `kid` trùng lặp theo policy; không chọn tùy tiện.
6. Kiểm tra metadata `use`, `key_ops`, `alg` nếu có.
7. Bỏ qua hoặc từ chối loại khóa không hỗ trợ theo policy, không tự bật thuật toán mới chỉ vì JWKS có thêm key.

### 7.3. Một JWKS hợp lệ về JSON vẫn có thể không đáng tin

JSON có thể hoàn toàn hợp lệ, các khóa có thể đúng toán học, nhưng nếu JWKS đến từ endpoint không được ràng buộc với issuer đã tin cậy thì không dùng để xác minh token. Kiểm tra định dạng và xác thực nguồn là hai lớp độc lập.

## 8. Ánh xạ issuer → metadata → JWKS → JWK

Verifier nên lưu mối quan hệ rõ ràng thay vì giữ một danh sách khóa toàn cục.

| Issuer | Metadata source | `jwks_uri` đã xác thực | Phạm vi `kid` |
| --- | --- | --- | --- |
| `https://id.example.test/tenant-a` | OIDC Discovery tenant-a | Endpoint lấy từ metadata tenant-a | Chỉ JWKS tenant-a |
| `https://id.example.test/tenant-b` | OIDC Discovery tenant-b | Endpoint lấy từ metadata tenant-b | Chỉ JWKS tenant-b |
| `https://as.example.test/tenant-c` | RFC 8414 metadata tenant-c | Endpoint lấy từ metadata tenant-c | Chỉ JWKS tenant-c |

Trong cache, key của bản ghi không nên chỉ là `kid`. Một định danh phù hợp có thể bao gồm:

~~~text
issuer identifier
    + metadata configuration/version
    + jwks_uri
    + kid
    + token profile / key purpose
~~~

Điều này ngăn một `kid` giống nhau ở hai issuer hoặc hai môi trường bị dùng thay thế cho nhau.

## 9. Ràng buộc JWKS với đúng issuer trong hệ thống nhiều tenant

Ví dụ hai tenant dùng cùng một nhà cung cấp:

| Thuộc tính | Tenant A | Tenant B |
| --- | --- | --- |
| Issuer | `https://id.example.test/tenant-a` | `https://id.example.test/tenant-b` |
| Discovery | Endpoint OpenID Provider tenant A | Endpoint OpenID Provider tenant B |
| JWKS | Key set A | Key set B |
| Audience | `tenant-a-api` | `tenant-b-api` |

Dù cùng host, mỗi tenant là một issuer riêng nếu identifier khác nhau. Không được:

- Bỏ path tenant khi so sánh `iss`.
- Dùng JWKS tenant A để xác minh token tenant B.
- Dùng cùng cache key chỉ dựa trên `kid`.
- Chấp nhận token tenant A tại API tenant B chỉ vì chữ ký hợp lệ.
- Để tenant tự gửi `jwks_uri` rồi buộc verifier tải endpoint đó.

Sau khi chữ ký hợp lệ, verifier phải kiểm tra `iss` và `aud` theo tenant/context đã chọn. Nếu ứng dụng xác định tenant từ session hoặc route đã xác thực, token phải nhất quán với tenant đó.

## 10. Cache metadata và JWKS

Metadata và JWKS có thể thay đổi khi issuer rotate khóa hoặc thay endpoint. Cache giúp giảm độ trễ và phụ thuộc mạng, nhưng cache sai cách có thể kéo dài niềm tin vào dữ liệu đã lỗi thời.

### 10.1. Cache metadata

Metadata cache nên gắn với issuer và metadata URL. Có thể sử dụng:

- HTTP `Cache-Control` và `max-age` theo chính sách.
- `ETag`/`If-None-Match` hoặc `Last-Modified`/`If-Modified-Since`.
- TTL tối đa nội bộ, kể cả khi server gửi TTL quá dài.
- Thời điểm lấy thành công cuối cùng và thời hạn stale tối đa.
- Cơ chế cập nhật metadata có kiểm soát khi endpoint thay đổi.

Nếu metadata mới thay đổi `jwks_uri`, không nên tự động chuyển sang endpoint mới mà không xác thực lại `issuer`, scheme, redirect và policy mạng. Một thay đổi endpoint là thay đổi trong chuỗi tin cậy và cần được ghi nhận.

### 10.2. Cache JWKS

- Cache theo issuer và `jwks_uri`, không chỉ theo `kid`.
- Tôn trọng HTTP cache directives, nhưng áp dụng TTL/staleness tối đa nội bộ.
- Dùng conditional request để giảm băng thông khi endpoint hỗ trợ.
- Giới hạn kích thước cache, số JWK, số issuer và thời gian tồn tại.
- Có cơ chế loại khóa bị thu hồi ngay cả khi JWKS cache chưa hết TTL.
- Không cho một response lỗi hoặc rỗng ghi đè cache hợp lệ nếu chính sách chưa xác nhận.

### 10.3. Khi endpoint tạm thời không truy cập được

Chính sách cần phân biệt:

| Trạng thái | Cách xử lý |
| --- | --- |
| Cache metadata/JWKS còn trong thời hạn tin cậy, chưa có tín hiệu thu hồi | Có thể tiếp tục sử dụng trong giới hạn stale-cache đã định. |
| Metadata cache hết hạn và không thể xác thực metadata mới | Không cập nhật trust mapping từ nguồn không xác thực; áp dụng giới hạn stale và mức rủi ro đã phê duyệt. |
| `kid` mới chưa có trong cache và JWKS endpoint lỗi | Không có khóa tin cậy để xác minh token mới; từ chối token. |
| Có thông báo khóa bị xâm phạm | Chặn khóa ngay cả khi cache còn hạn; kích hoạt cơ chế thu hồi khẩn cấp. |

Không dùng cache cũ vô thời hạn để duy trì availability. Thời gian stale tối đa phải được quyết định theo rủi ro, loại token và khả năng cập nhật khẩn cấp.

## 11. Cập nhật metadata và thay đổi `jwks_uri`

Thay đổi JWKS URI có thể hợp lệ, ví dụ issuer chuyển sang hạ tầng mới hoặc CDN. Tuy nhiên, đây là thay đổi nguồn cung cấp khóa và cần quy trình rõ ràng.

Một quy trình kiểm soát:

1. Lấy metadata mới từ endpoint đã gắn với issuer tin cậy.
2. Xác minh TLS, redirect và giá trị `issuer` khớp chính xác.
3. Kiểm tra `jwks_uri` mới hợp lệ và phù hợp network policy.
4. Ghi nhận endpoint cũ/mới, thời điểm và lý do thay đổi.
5. Tải thử JWKS mới, xác minh cấu trúc và public keys.
6. Đánh giá thời gian overlap, cache và consumer đang sử dụng endpoint cũ.
7. Cập nhật mapping theo chính sách, theo dõi lỗi xác minh và giữ phương án rollback có kiểm soát.

Nếu metadata mới có `issuer` khác issuer đã cấu hình, từ chối. Không coi đó là đổi domain hợp lệ chỉ vì cùng tổ chức hoặc cùng tên thương hiệu.

## 12. Rotation khóa trong chuỗi tin cậy

Rotation khóa và thay đổi JWKS URI là hai việc khác nhau:

- **Rotation khóa:** issuer giữ nguồn JWKS nhưng thay public key trong tập khóa.
- **Thay JWKS URI:** issuer thay địa chỉ phân phối tập khóa; nguồn mạng của key set thay đổi.
- **Thay issuer:** thay đổi định danh bên phát hành; đây là thay đổi trust anchor, cần quy trình phê duyệt và migration riêng.

Quy trình rotation khóa thông thường:

1. Sinh khóa mới, gán `kid` mới và bảo vệ private material.
2. Công bố public JWK mới trong JWKS cũ (hoặc URI đã xác thực).
3. Chờ verifier tải khóa mới; theo dõi cache và độ sẵn sàng.
4. Chuyển issuer sang ký bằng khóa mới.
5. Giữ public key cũ đủ thời gian xác minh token cũ còn hiệu lực.
6. Rút public key cũ và làm mới cache sau cửa sổ chuyển tiếp.
7. Thu hồi quyền ký và hủy private material cũ theo chính sách.

Không tái sử dụng `kid` của khóa cũ cho khóa mới. Không dùng việc thay JWKS URI để né quy trình rotation hoặc che giấu thay đổi khóa.

## 13. Thu hồi khẩn cấp và thay đổi trust mapping

Khi private key bị lộ, endpoint JWKS bị chiếm quyền hoặc metadata bị thay thế:

1. Xác định issuer, metadata URL, JWKS URI, `kid` và consumer bị ảnh hưởng.
2. Thu hồi quyền quản trị endpoint/metadata hoặc quyền sử dụng private key bị xâm phạm.
3. Chặn `kid` bị ảnh hưởng tại verifier; làm mới cache và phát tín hiệu khẩn đến consumer.
4. Nếu metadata/JWKS URI bị thay thế, quay lại trust mapping đã được xác minh hoặc cấu hình khẩn đã phê duyệt.
5. Sinh khóa mới trong môi trường tin cậy, công bố public key và chuyển ký.
6. Từ chối token ký bằng khóa bị lộ theo chính sách, kể cả token còn hạn.
7. Kiểm tra backup, log, quyền truy cập và nguyên nhân thay đổi trái phép.

Không chỉ xóa public key khỏi JWKS rồi giả định mọi verifier đã ngừng tin khóa đó. Cache cũ, cấu hình cục bộ và bản sao khóa có thể vẫn tồn tại. Cần danh sách consumer và cơ chế thu hồi có thể kiểm chứng.

## 14. Threat model: các cách nguồn JWKS có thể bị thay thế

| Mối đe dọa | Điều kiện khai thác | Hậu quả | Biện pháp kiểm soát |
| --- | --- | --- | --- |
| Issuer injection | Tin `iss` chưa xác minh như một URL tùy ý | Verifier tải metadata/JWKS của attacker | Registry issuer được phê duyệt; `iss` chỉ lookup chính xác. |
| JWKS substitution | Endpoint hoặc metadata bị thay đổi | Public key attacker được dùng để xác minh token giả | HTTPS, trust anchor, issuer match, kiểm soát endpoint và audit. |
| SSRF qua `jku`/`x5u` | Token điều khiển URL fetch | Truy cập dịch vụ nội bộ hoặc metadata service | Không fetch URL tùy ý; egress policy, redirect validation. |
| Redirect abuse | JWKS endpoint chuyển hướng ra host khác | Vượt ranh giới mạng hoặc tải key giả | Kiểm tra mọi redirect và giới hạn đích. |
| DNS rebinding | Host được phân giải sang địa chỉ nội bộ | Request đến tài nguyên không mong muốn | Kiểm soát DNS/IP đích và egress. |
| Metadata issuer mismatch | Metadata trả về issuer khác | Trộn lẫn hai miền tin cậy | So khớp `issuer` chính xác; từ chối mismatch. |
| Cross-tenant key confusion | Chỉ lookup bằng `kid` | Token tenant A được xác minh bằng key tenant B | Cache và lookup theo issuer/tenant/profile. |
| Cache poisoning | Response JWKS giả được ghi vào cache | Các request sau tiếp tục tin key giả | Xác thực nguồn trước cache; không ghi response lỗi; audit cache update. |
| Stale-key trust | Cache giữ khóa đã bị thu hồi | Token ký bằng khóa bị lộ tiếp tục được chấp nhận | TTL/staleness giới hạn và kênh thu hồi khẩn. |
| Key disclosure | Private JWK bị xuất bản | Attacker ký token hoặc giải mã dữ liệu | Schema kiểm tra public-only; bảo vệ private material. |

## 15. Pseudocode xây dựng trust chain

Pseudocode dưới đây mô tả cách bắt đầu từ issuer đã được tin cậy và ràng buộc metadata/JWKS:

~~~text
function resolveTrustedJwks(untrustedIssuerValue, trustRegistry):
    issuerConfig = trustRegistry.findExactIssuer(untrustedIssuerValue)
    if issuerConfig is null:
        reject("issuer is not configured")

    metadataUrl = buildDiscoveryUrl(
        issuerConfig.issuer,
        issuerConfig.discoveryProtocol
    )

    metadataResponse = secureHttpGet(
        metadataUrl,
        requireHttps = true,
        validateTls = true,
        validateRedirectTargets = true,
        enforceEgressPolicy = true,
        responseSizeLimit = configuredLimit
    )

    metadata = parseStrictJson(metadataResponse)
    if metadata.issuer != issuerConfig.issuer:
        reject("metadata issuer mismatch")

    jwksUri = validateTrustedJwksUri(
        metadata.jwks_uri,
        issuerConfig.networkPolicy
    )

    jwksResponse = secureHttpGet(
        jwksUri,
        requireHttps = true,
        validateTls = true,
        validateRedirectTargets = true,
        enforceEgressPolicy = true,
        responseSizeLimit = configuredLimit
    )

    jwks = parseAndValidateJwks(jwksResponse)
    cache.store(
        issuer = issuerConfig.issuer,
        metadataUrl = metadataUrl,
        jwksUri = jwksUri,
        jwks = jwks,
        expiration = boundedHttpCacheLifetime(jwksResponse)
    )
    return jwks
~~~

Đây là pseudocode khái niệm. `buildDiscoveryUrl` phải tuân theo đúng quy tắc của OAuth AS Metadata hoặc OpenID Connect Discovery, không dùng một cách ghép URL chung cho mọi giao thức. `secureHttpGet` và `validateTrustedJwksUri` cần thực thi policy mạng thực tế.

## 16. Ví dụ end-to-end: xác minh token của một issuer OIDC

Giả sử ứng dụng đã đăng ký issuer:

~~~text
Expected issuer:
https://login.example.test/realms/finance

Expected audience:
finance-api

Allowed algorithm:
RS256
~~~

**Bước 1 — Discovery**

Ứng dụng tạo OpenID Provider Configuration URL theo quy tắc OIDC:

~~~text
https://login.example.test/realms/finance/.well-known/openid-configuration
~~~

Metadata trả về (rút gọn):

~~~json
{
  "issuer": "https://login.example.test/realms/finance",
  "jwks_uri": "https://keys.example.test/finance/jwks.json",
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

Verifier kiểm tra `issuer` đúng chính xác giá trị mong đợi. Host của `jwks_uri` khác host issuer có thể hợp lệ nếu metadata đã được xác thực và network policy cho phép; không tự động tin mọi host hoặc redirect.

**Bước 2 — Tải JWKS**

JWKS trả về public JWK:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "finance-sign-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_RSA_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

Verifier kiểm tra cấu trúc, tham số public RSA và metadata. Không có private material.

**Bước 3 — Nhận JWT**

Header:

~~~json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "finance-sign-2026-01"
}
~~~

Verifier chọn khóa từ JWKS gắn với issuer đã đăng ký. Sau đó xác minh chữ ký bằng RSA public key và allowlist `RS256`.

**Bước 4 — Kiểm tra claims**

~~~json
{
  "iss": "https://login.example.test/realms/finance",
  "aud": "finance-api",
  "exp": 1893456000,
  "nbf": 1893452400,
  "sub": "user-123"
}
~~~

Các giá trị thời gian ở đây chỉ là dữ liệu minh họa. Verifier cần kiểm tra `exp`, `nbf` theo đồng hồ hệ thống và clock skew có giới hạn; xác minh `iss`/`aud` theo profile. Chỉ sau khi mọi điều kiện đều đạt, token mới được chấp nhận.

## 17. Checklist review nguồn JWKS

**Trust anchor và issuer**

- [ ] Issuer đã được phê duyệt hoặc đăng ký trong trust registry.
- [ ] `iss` chưa xác minh chỉ dùng để tra cứu, không kích hoạt trust động.
- [ ] So khớp issuer chính xác theo chuẩn/profile; không tự normalize.
- [ ] Có policy riêng cho từng tenant, môi trường và token profile.

**Discovery và metadata**

- [ ] Dùng đúng quy tắc URL của RFC 8414 hoặc OpenID Connect Discovery.
- [ ] Metadata lấy qua HTTPS và TLS được xác minh.
- [ ] Member `issuer` khớp chính xác issuer mong đợi.
- [ ] `jwks_uri` hợp lệ, được ràng buộc với metadata tin cậy và phù hợp network policy.
- [ ] Thay đổi metadata/endpoint được ghi nhận và kiểm soát.

**Tải và xử lý JWKS**

- [ ] Kiểm soát redirect, DNS, IP đích, timeout, response size và egress.
- [ ] Không fetch `jku`/`x5u` tùy ý từ token.
- [ ] JSON/JWKS được parse và kiểm tra member, số lượng key, tham số và private material.
- [ ] Cache key gắn với issuer/JWKS URI, không chỉ `kid`.
- [ ] Có TTL/staleness giới hạn và cơ chế thu hồi khẩn cấp.

**Xác minh JWT**

- [ ] Chọn khóa đúng issuer và đúng profile trước khi so khớp `kid`.
- [ ] Thuật toán nằm trong allowlist và tương thích JWK.
- [ ] Chữ ký hợp lệ trên signing input gốc.
- [ ] Kiểm tra `iss`, `aud`, `exp`, `nbf` và quyền ứng dụng.

## 18. Tài liệu chuẩn tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): cấu trúc JWK/JWKS và cách công bố tập khóa.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): header JWS, chữ ký và các tham số `jku`, `jwk`, `x5u`.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claim `iss` và cấu trúc JWT.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata, quy tắc well-known URL và `jwks_uri`.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OpenID Provider Configuration và kiểm tra issuer.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh issuer, audience, thuật toán và phòng token substitution.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0 hiện hành.

**Ghi nhớ:** tin issuer trước, discovery metadata từ đúng issuer, xác minh `issuer` trong metadata, rồi mới tin `jwks_uri` và JWKS. TLS bảo vệ kết nối; trust registry và issuer binding xác định ai được phép tin. Mọi lựa chọn khóa, cache và rotation đều phải duy trì ranh giới tin cậy đó.

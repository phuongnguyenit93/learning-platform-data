# Khóa JWK nhúng không tin cậy và giả mạo bên phát hành

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Tấn công JWT. Bài viết áp dụng cho mọi hệ thống xác minh JWT, không phụ thuộc ngôn ngữ lập trình, nền tảng hoặc framework.

## 1. Vấn đề cốt lõi: chữ ký hợp lệ chưa chứng minh issuer đáng tin

JWT ký bằng JWS có thể mang thông tin về khóa hoặc nguồn khóa trong JOSE header. Một số tham số cho phép đưa trực tiếp public key, URL tới JWK Set hoặc chứng thư X.509 vào header. Các tham số này hữu ích trong những giao thức có quy tắc tin cậy rõ ràng, nhưng chúng trở thành điểm tấn công nếu verifier tự động tin khóa do chính token cung cấp.

Kẻ tấn công có thể tự tạo một cặp khóa, ký JWT bằng private key của mình, nhúng public key tương ứng vào header rồi đặt claim `iss` thành issuer hợp lệ mà hệ thống đang tin. Nếu resource server lấy public key từ header và chỉ kiểm tra chữ ký, chữ ký sẽ xác minh thành công — nhưng nó chỉ chứng minh token được ký bởi private key tương ứng với public key do kẻ tấn công chọn.

Đây là lỗi **key trust / issuer binding**: verifier nhầm lẫn giữa “chữ ký khớp với khóa này” và “khóa này được issuer tin cậy dùng để ký token”.

Một chữ ký số chỉ có giá trị xác thực nguồn khi verifier đã có cơ sở tin cậy độc lập rằng public key thuộc đúng issuer. Việc public key nằm trong chính token không tạo ra cơ sở tin cậy đó.

## 2. Các tham số JOSE liên quan đến khóa nhúng

Một số tham số JOSE header thường xuất hiện trong kiểu tấn công này:

| Header parameter | Ý nghĩa | Rủi ro nếu tin trực tiếp |
| --- | --- | --- |
| `jwk` | JWK chứa khóa tương ứng với chữ ký JWS | Kẻ tấn công đưa public key của mình vào token |
| `jku` | URL trỏ tới JWK Set (JWKS) | Verifier tải khóa từ server do attacker kiểm soát hoặc URL gây SSRF |
| `x5u` | URL trỏ tới chứng thư X.509 hoặc chuỗi chứng thư | Verifier tải chứng thư từ nguồn không đáng tin, có thể gây SSRF hoặc key substitution |
| `x5c` | Mảng chứng thư X.509 được mã hóa Base64 DER | Verifier coi chứng thư do token cung cấp là trust anchor mà không xác minh chain/identity |
| `kid` | Key ID để chọn khóa trong một tập khóa | Bị dùng như đường dẫn, query hoặc selector không được kiểm soát |

Các giá trị này là dữ liệu header do bên tạo token cung cấp. Ngay cả khi header nằm trong phần được ký, verifier vẫn không thể dùng chữ ký đó để chứng minh khóa ký là đáng tin: kẻ tấn công có thể tự tạo cả header lẫn chữ ký bằng khóa của họ.

JWS Compact Serialization đặt protected header trong token, nhưng “protected” chỉ có nghĩa header được bao phủ bởi chữ ký/MAC của JWS. Nó không biến dữ liệu header thành nguồn cấu hình đáng tin.

## 3. Kịch bản giả mạo issuer bằng JWK nhúng

### 3.1. Điều kiện để tấn công thành công

Một lỗi triển khai thường có chuỗi xử lý như sau:

1. Nhận JWT từ request.
2. Đọc header và thấy tham số `jwk`.
3. Dùng public key trong `jwk` để xác minh chữ ký.
4. Chữ ký hợp lệ nên tiếp tục đọc claim `iss`, `sub`, `aud` và quyền.
5. Chấp nhận token mà không kiểm tra public key có thuộc issuer được tin cậy hay không.

Kẻ tấn công có thể tự tạo key pair và token:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jwk": {
    "kty": "RSA",
    "n": "ATTACKER_PUBLIC_MODULUS",
    "e": "AQAB"
  }
}
~~~

Payload giả mạo có thể khai báo:

~~~json
{
  "iss": "https://issuer.example.net",
  "sub": "administrator",
  "aud": "https://api.example.net",
  "scope": "admin:all",
  "iat": 1900000000,
  "exp": 1900003600
}
~~~

Attacker ký payload bằng private key tương ứng với JWK nhúng. Nếu verifier dùng chính JWK đó làm khóa tin cậy, chữ ký sẽ hợp lệ về mặt toán học. Tuy nhiên, issuer thật chưa từng phát hành token và không kiểm soát private key đó.

Các giá trị modulus và claim trong ví dụ chỉ là placeholder minh họa, không phải khóa hay token có thể sử dụng.

### 3.2. Vì sao kiểm tra iss sau khi verify vẫn chưa đủ nếu chọn sai khóa?

Giả sử verifier lấy khóa từ `jwk` trong header, xác minh chữ ký thành công, rồi kiểm tra `iss` bằng cách so sánh chuỗi với issuer dự kiến. Attacker có thể tự điền đúng chuỗi issuer dự kiến trong payload. Claim `iss` cũng do attacker ký bằng khóa của họ; nó chưa được chứng thực bởi issuer thật.

Trình tự đúng phải có **trust anchor độc lập**:

- issuer được cấu hình hoặc được chọn từ danh sách issuer đã tin cậy;
- public key được lấy từ JWKS/metadata gắn với issuer đó qua kênh tin cậy;
- chữ ký được xác minh bằng khóa thuộc nguồn đó;
- sau khi chữ ký hợp lệ, claim `iss` phải khớp chính xác issuer mong đợi;
- tiếp tục kiểm tra audience, thời gian, token type và policy.

Không được dùng một claim chưa xác minh làm bằng chứng để tin chính claim đó.

## 4. Phân biệt xác minh chữ ký và xác minh nguồn khóa

Hai câu hỏi cần được trả lời riêng:

1. **Chữ ký có khớp với public key đang dùng không?** Đây là kiểm tra mật mã.
2. **Vì sao verifier tin public key đó thuộc issuer được phép phát hành token?** Đây là kiểm tra nguồn gốc và trust policy.

| Tình huống | Chữ ký | Nguồn khóa | Kết quả |
| --- | --- | --- | --- |
| Token ký bằng khóa trong JWKS của issuer đã cấu hình | Hợp lệ | Được tin cậy và gắn với đúng issuer | Có thể tiếp tục kiểm tra claims |
| Token tự nhúng JWK do attacker tạo | Hợp lệ với khóa nhúng | Không có trust anchor | Từ chối |
| Token dùng khóa lấy từ `jku` tùy ý | Có thể hợp lệ | URL do token điều khiển | Từ chối hoặc không fetch theo policy |
| Token dùng chứng thư `x5c` tự ký | Có thể hợp lệ | Chưa có trust chain/issuer binding | Từ chối |
| Token dùng khóa hợp lệ nhưng `iss` không khớp issuer mong đợi | Hợp lệ | Khóa có nguồn gốc tin cậy nhưng sai ngữ cảnh | Từ chối |

Một JWK thumbprint có thể giúp định danh một khóa ổn định, nhưng thumbprint tự nó không chứng minh ai sở hữu khóa hoặc issuer nào được phép dùng nó. Trust phải đến từ cấu hình, metadata, certificate path hoặc một cơ chế binding độc lập đã được xác minh.

## 5. Xử lý header jwk an toàn

### 5.1. Không dùng JWK nhúng làm khóa issuer mặc định

Đối với access token hoặc ID Token được kỳ vọng do một issuer cụ thể phát hành, verifier nên lấy khóa xác minh từ nguồn tin cậy đã cấu hình cho issuer đó. Không thay nguồn khóa bằng tham số `jwk` trong token.

Chính sách thường phù hợp:

- từ chối header `jwk` nếu token profile không cho phép;
- không dùng khóa nhúng làm trust anchor chỉ vì chữ ký xác minh thành công;
- nếu profile có cho phép JWK nhúng, phải có quy tắc binding độc lập xác minh khóa đó thuộc đúng chủ thể hoặc mục đích;
- không suy ra issuer từ public key nhúng;
- không chấp nhận private key material trong JWK nhận từ bên ngoài.

JWK public key có thể chứa các trường như `kty`, `n`/`e` hoặc `crv`/`x`/`y`. Nếu JWK chứa thành phần private như `d`, `p`, `q`, `dp`, `dq`, `qi` hoặc `k` đối với khóa đối xứng, verifier không nên nhận nó như một public key bình thường. Dữ liệu đó có thể làm lộ secret hoặc gây nhầm lẫn trong thư viện xử lý.

### 5.2. Header được ký không đồng nghĩa đáng tin

Một attacker có thể ký header có chứa JWK bằng chính private key tương ứng. Vì vậy:

- kiểm tra chữ ký trước khi sử dụng claim là bắt buộc;
- nhưng dùng khóa trong header để tự xác minh chữ ký vẫn không chứng minh issuer;
- header phải được diễn giải theo profile và policy đã biết trước;
- không cho header tự quyết định trust source, thuật toán hoặc loại token.

Header là đầu vào để chọn cách xử lý trong một tập lựa chọn đã được cấu hình. Nó không phải nơi để token tự khai báo chính sách tin cậy của verifier.

## 6. Xử lý jku: URL JWKS do token cung cấp

### 6.1. Rủi ro key substitution

`jku` là URL tới tài nguyên chứa JWK Set. Nếu verifier tự động tải URL này từ JWT header, attacker có thể trỏ tới JWKS do mình kiểm soát, chứa public key tương ứng với chữ ký giả mạo.

Ví dụ header:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jku": "https://attacker.example/keys.json"
}
~~~

Nếu server tải JWKS từ URL trên và dùng khóa trong đó để xác minh token, attacker đã kiểm soát cả token lẫn nguồn khóa.

HTTPS chỉ bảo vệ kết nối tới hostname được chỉ định. Nó không chứng minh hostname đó thuộc issuer mà hệ thống đang tin.

### 6.2. SSRF và truy cập tài nguyên nội bộ

Nếu URL trong `jku` được fetch ở phía server, attacker có thể thử trỏ tới:

- loopback hoặc địa chỉ private;
- endpoint metadata của cloud;
- dịch vụ nội bộ không được public;
- cổng quản trị hoặc dịch vụ có giao thức khác;
- hostname bị điều khiển DNS hoặc thay đổi qua redirect.

Đây là bề mặt Server-Side Request Forgery (SSRF). Ngay cả khi response không phải JWKS hợp lệ, request đã có thể tạo tác động như dò mạng nội bộ, truy cập metadata hoặc làm cạn tài nguyên.

### 6.3. Chính sách an toàn

Đối với JWT issuer-signed thông thường:

1. Không fetch `jku` do token tùy ý cung cấp.
2. Cấu hình issuer và JWKS URI ngoài token.
3. Nếu dùng OIDC Discovery, bắt đầu từ issuer đã được đăng ký/tin cậy; tải metadata qua HTTPS và xác minh trường `issuer` khớp chính xác.
4. Chỉ dùng `jwks_uri` lấy từ metadata đã được tin cậy hoặc cấu hình quản trị.
5. Áp dụng egress allowlist, timeout, giới hạn response size và redirect policy.
6. Cache JWKS theo issuer đã xác minh; không cache lẫn khóa giữa các issuer.
7. Không cho phép header token thay đổi trust source đã cấu hình.

Không nên cố “làm an toàn” bằng cách chỉ chặn URL private nhưng vẫn fetch mọi URL public từ header. Kẻ tấn công vẫn có thể kiểm soát hostname public và cung cấp khóa của họ.

## 7. Xử lý x5u và x5c

### 7.1. x5u: URL chứng thư từ token

`x5u` trỏ tới tài nguyên chứa chứng thư X.509 hoặc chuỗi chứng thư. Nếu verifier tải URL này một cách tự do, các rủi ro tương tự `jku` xuất hiện:

- key substitution bằng chứng thư do attacker kiểm soát;
- SSRF;
- redirect tới địa chỉ nội bộ;
- response lớn hoặc chậm gây DoS;
- khác biệt cache và DNS giữa các node.

Không dùng `x5u` trong token như nguồn trust tự động. Nếu profile yêu cầu certificate URL, phải có allowlist nguồn, xác thực TLS, kiểm soát redirect/egress và quy tắc xác minh chứng thư độc lập.

### 7.2. x5c: chuỗi chứng thư nhúng

`x5c` chứa một mảng chứng thư X.509 được mã hóa Base64 DER. Việc chứng thư xuất hiện trong token không làm nó trở thành chứng thư đáng tin.

Verifier cần thực hiện các kiểm tra certificate path phù hợp:

- xây dựng và xác minh chain tới trust anchor đã cấu hình;
- kiểm tra thời hạn hiệu lực;
- kiểm tra key usage và extended key usage theo mục đích ký;
- kiểm tra thuật toán và độ dài khóa được phép;
- xác minh danh tính trong Subject/SAN theo quy tắc issuer binding;
- kiểm tra revocation nếu policy yêu cầu;
- giới hạn số chứng thư, kích thước và độ sâu chain;
- không tự coi leaf certificate hoặc self-signed certificate là root đáng tin.

Một certificate chain hợp lệ tới một CA công khai cũng chưa chắc chứng minh tổ chức đó là issuer được phép phát hành JWT cho hệ thống. Cần mapping danh tính certificate/issuer tới trust policy của ứng dụng.

### 7.3. Không nhầm chứng thư hợp lệ với issuer hợp lệ

PKI xác minh quan hệ giữa chứng thư và CA. Ứng dụng còn phải xác minh tổ chức/chủ thể trong certificate có được phép phát hành loại token này cho audience đó hay không.

Ví dụ, một certificate TLS hợp lệ cho hostname của công ty không tự động là signing certificate được phép ký access token. Key usage, EKU, danh tính, issuer mapping và token profile phải cùng khớp.

## 8. kid là selector, không phải nguồn tin cậy

`kid` thường được dùng để chọn một JWK trong JWKS đã có. Nó không chứng minh khóa thuộc issuer và không nên được diễn giải như một đường dẫn hoặc lệnh.

Các lỗi nguy hiểm:

- nối `kid` trực tiếp vào file path;
- dùng `kid` làm SQL fragment hoặc tên bảng;
- dùng `kid` để tạo URL tải khóa;
- tìm khóa trên toàn bộ issuer mà không namespace;
- chấp nhận nhiều khóa cùng `kid` nhưng không có quy tắc chọn duy nhất;
- fallback sang JWK nhúng hoặc `jku` khi không tìm thấy khóa.

Chính sách an toàn:

- giới hạn độ dài và ký tự `kid`;
- tra cứu trong JWKS gắn với issuer đã xác định;
- yêu cầu kết quả chọn khóa duy nhất theo policy;
- cache theo cặp issuer/key ID và thuật toán phù hợp;
- không dùng giá trị `kid` làm code, path hoặc URL;
- khi không tìm thấy khóa, refresh JWKS từ nguồn đã cấu hình với rate limit;
- nếu vẫn không tìm thấy, từ chối token.

Không được thử mọi khóa từ mọi issuer cho tới khi có một khóa nào xác minh được chữ ký. Cách làm này dễ gây issuer confusion và có thể chấp nhận token ở sai trust domain.

## 9. Ràng buộc issuer và chống issuer confusion

### 9.1. iss chưa được xác minh trước chữ ký

Claim `iss` nằm trong payload. Trước khi xác minh chữ ký, nó chỉ là dữ liệu không đáng tin do người tạo token kiểm soát.

Một hệ thống có nhiều issuer có thể cần đọc `iss` chưa xác minh để xác định cấu hình ứng viên. Nếu làm vậy, phải:

- chỉ dùng giá trị đó để tra cứu trong allowlist issuer đã cấu hình;
- không tự động tạo discovery URL từ một issuer tùy ý;
- không fetch metadata/JWKS từ host chưa được phê duyệt;
- sau khi xác minh chữ ký, kiểm tra `iss` khớp chính xác issuer được chọn;
- namespace cache, key set và policy theo issuer;
- kiểm tra audience và token type tương ứng với issuer đó.

Không dùng `iss` chưa xác minh để quyết định “tin issuer mới” hoặc đăng ký trust mới.

### 9.2. Tránh cross-issuer key confusion

Nếu hai issuer dùng cùng một `kid`, điều đó không có nghĩa khóa của issuer A có thể xác minh token issuer B. Mọi tra cứu khóa phải có namespace issuer.

Ngoài ra cần phân biệt:

- issuer phát hành ID Token;
- issuer phát hành access token;
- issuer của JWT client assertion;
- issuer của DPoP proof hoặc token nội bộ.

Các loại token có thể dùng chung định dạng JWT nhưng có trust model và validation rules khác nhau. Hãy dùng token profile tách biệt, kiểm tra `typ`/audience và không tái sử dụng một bộ xác minh quá rộng cho mọi loại JWT.

### 9.3. Audience không thay issuer binding

`aud` xác định recipient dự kiến. Một token có audience đúng nhưng chữ ký được xác minh bằng khóa attacker chọn vẫn không đáng tin. Ngược lại, chữ ký bằng khóa issuer đúng nhưng audience sai cũng phải bị từ chối.

Issuer, key source, audience, algorithm và token profile là các điều kiện độc lập cần cùng đạt.

## 10. Quy trình chọn khóa xác minh an toàn

Một quy trình điển hình cho access token issuer-signed:

1. Xác định endpoint đang chờ loại token nào và tập issuer được tin cậy.
2. Kiểm tra giới hạn kích thước và cấu trúc Compact Serialization.
3. Parse protected header như dữ liệu chưa tin cậy.
4. Kiểm tra `alg` thuộc allowlist cố định của token profile.
5. Chọn issuer ứng viên chỉ từ cấu hình/allowlist; không tự tin `iss` hoặc URL trong header.
6. Lấy JWKS từ nguồn đã cấu hình cho issuer đó.
7. Chọn khóa theo `kid` trong đúng JWKS; kiểm tra key type, use, key_ops, alg, curve và kích thước.
8. Xác minh chữ ký bằng khóa tin cậy.
9. Sau khi verify, kiểm tra `iss` chính xác, `aud`, `exp`, `nbf`, `iat`, token type và các claim bắt buộc.
10. Chỉ sau đó mới sử dụng subject, scope, role hoặc tenant để authorization.

Nếu header có `jwk`, `jku` hoặc `x5u` không được token profile cho phép, từ chối hoặc bỏ qua theo profile đã định nghĩa; tuyệt đối không dùng chúng để thay nguồn khóa tin cậy. Nếu profile có sử dụng `x5c`, phải xác minh certificate path và issuer mapping theo policy.

## 11. Kiểm tra JWK lấy từ JWKS tin cậy

Ngay cả JWKS đến từ endpoint được cấu hình cũng cần kiểm tra cấu trúc và policy. Không phải mọi khóa trong JWKS đều được phép xác minh mọi loại JWT.

| Thuộc tính | Điều cần kiểm tra |
| --- | --- |
| `kty` | Loại khóa phù hợp thuật toán được cho phép |
| `kid` | Selector hợp lệ, không mơ hồ trong phạm vi issuer/key set |
| `use` | Nếu có, mục đích là `sig` cho chữ ký |
| `key_ops` | Nếu có, operation cho phép `verify` |
| `alg` | Nếu có, khớp thuật toán được cấu hình |
| `crv` | Curve thuộc allowlist khi dùng EC/OKP |
| Key size | RSA modulus hoặc tham số khóa đạt ngưỡng policy |
| Public/private material | JWKS công khai không chứa thành phần private |
| Key status | Không bị thu hồi hoặc loại bỏ theo metadata/policy |
| Issuer namespace | Khóa thuộc đúng issuer và token profile |

Không chọn thuật toán chỉ dựa vào header `alg` do token cung cấp. Server phải định nghĩa allowlist trước; sau đó kiểm tra khóa phù hợp thuật toán đó. Tránh algorithm confusion như dùng khóa RSA public bytes làm HMAC secret hoặc chấp nhận `none` trong token profile bảo mật.

JWK thumbprint theo RFC 7638 hữu ích để so sánh/định danh khóa, nhưng thumbprint không tự xác minh quyền phát hành. Nó chỉ có giá trị khi được so với một binding hoặc registry đã được tin cậy.

## 12. Key rotation và cache JWKS

Key rotation là hoạt động bình thường. Verifier cần hỗ trợ nhiều khóa hợp lệ trong giai đoạn chuyển tiếp mà không mở rộng trust source.

Một quy trình an toàn:

- issuer công bố khóa mới trong JWKS tin cậy trước khi bắt đầu ký bằng khóa đó;
- verifier tải và cache JWKS theo issuer;
- token mới dùng `kid` của khóa mới;
- trong giai đoạn overlap, JWKS có thể chứa cả khóa cũ và mới;
- sau khi token cũ hết hạn và thời gian dự phòng kết thúc, issuer loại bỏ khóa cũ;
- verifier cập nhật cache theo TTL và cơ chế refresh có kiểm soát.

Khi gặp `kid` chưa biết:

1. Không thử `jwk` hoặc `jku` trong token làm fallback.
2. Có thể refresh JWKS từ URI đã cấu hình một lần theo cơ chế rate limit/single-flight.
3. Kiểm tra lại `kid` trong tập khóa mới.
4. Nếu vẫn không có, từ chối token.
5. Ghi metric/reason code mà không log token nguyên vẹn.

Nếu attacker gửi hàng nghìn token với `kid` ngẫu nhiên, verifier không nên fetch JWKS cho mỗi request. Cần cache negative result trong thời gian ngắn, rate limit refresh, giới hạn timeout và bảo vệ JWKS endpoint khỏi stampede.

## 13. Trường hợp JWK nhúng được phép: DPoP và các profile có binding

Không nên biến quy tắc “không bao giờ có JWK trong header” thành một luật áp dụng cho mọi JWT. Một số giao thức chủ động dùng public JWK trong proof JWT để xác định khóa mà client đang chứng minh quyền kiểm soát.

Ví dụ DPoP (RFC 9449):

- DPoP proof có header `jwk` chứa public key của client.
- Proof được ký bằng private key tương ứng.
- Resource server xác minh chữ ký proof bằng public key đó.
- Access token DPoP-bound có claim `cnf` chứa thumbprint `jkt` của public key đã được authorization server ràng buộc.
- Resource server kiểm tra thumbprint của JWK trong proof khớp binding trong access token.
- Sau đó còn kiểm tra `htm`, `htu`, `iat`, `jti`, nonce nếu được yêu cầu và `ath` theo quy tắc DPoP.

Trong trường hợp này, JWK nhúng không được dùng để chứng minh issuer của access token. Nó là khóa client dùng để chứng minh possession; trust binding đến từ access token đã được xác minh và các quy tắc DPoP.

Tương tự, một giao thức ký thông điệp có thể cho phép key material nhúng nếu có registry, certificate chain, thumbprint pinning hoặc binding độc lập. Phải tuân thủ đúng profile; không áp dụng ngoại lệ DPoP cho access token JWT thông thường.

## 14. Mã giả xác minh JWT issuer-signed

~~~text
function verifyIssuerJwt(token, endpointPolicy):
    require token.length <= endpointPolicy.maxTokenLength

    parts = splitPreservingEmptySegments(token, ".")
    require parts.count == 3

    header = parseProtectedHeader(parts[0])

    require header.alg in endpointPolicy.allowedAlgorithms
    require header.alg != "none"

    # Không dùng khóa hoặc URL do token tự cung cấp làm trust source.
    require header.jwk is absent or endpointPolicy.explicitlyAllowsEmbeddedJwk == true
    require header.jku is absent or endpointPolicy.explicitlyAllowsJku == true
    require header.x5u is absent or endpointPolicy.explicitlyAllowsX5u == true

    unverifiedClaims = parseClaimsForCandidateSelection(parts[1])
    candidateIssuer = endpointPolicy.trustedIssuers.lookupExact(
        unverifiedClaims.iss
    )
    require candidateIssuer exists

    trustedJwks = jwksProvider.loadFromConfiguredSource(candidateIssuer)
    key = selectUniqueKey(
        trustedJwks,
        kid = header.kid,
        algorithm = header.alg
    )

    require key satisfiesKeyPolicy(key, candidateIssuer, endpointPolicy)
    require verifyJwsSignature(parts, key, header.alg)

    claims = parseVerifiedClaims(parts[1])
    require claims.iss == candidateIssuer.issuer
    require expectedAudience(endpointPolicy) in claims.aud
    require claims.exp is valid and not expired
    require claims satisfyTokenProfile(endpointPolicy)

    return VERIFIED_TOKEN(claims)
~~~

Mã giả minh họa luồng issuer-signed thông thường. Trong thực tế, không cần parse và tin payload trước verify; nếu đọc `iss` chưa xác minh để chọn issuer ứng viên, chỉ được tra cứu allowlist tĩnh và vẫn phải xác minh chữ ký bằng key set của issuer đó trước khi tin claim. Với token profile có nhiều issuer, nên định tuyến endpoint hoặc transaction tới issuer đã biết thay vì tự khám phá issuer tùy ý.

## 15. Sơ đồ trust chain đúng

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Parse header/payload như dữ liệu chưa tin"]
    B --> C["Chọn issuer từ cấu hình/allowlist"]
    C --> D["Lấy metadata/JWKS từ nguồn đã tin"]
    D --> E["Chọn key trong JWKS theo kid và policy"]
    E --> F["Xác minh chữ ký"]
    F --> G{"Chữ ký hợp lệ?"}
    G -- "Không" --> X["Từ chối"]
    G -- "Có" --> H["Kiểm tra iss, aud, exp, nbf, typ"]
    H --> I{"Claims và profile hợp lệ?"}
    I -- "Không" --> X
    I -- "Có" --> J["Authorization theo scope/resource"]
    
    K["jwk/jku/x5u do token cung cấp"] -. "Không tự tin / không fetch" .-> X
~~~

Luồng trust bắt đầu từ cấu hình issuer và nguồn khóa đã được xác minh. Header chỉ hỗ trợ chọn khóa trong tập tin cậy đó; nó không được phép tạo trust source mới.

## 16. Xử lý khi phát hiện token có khóa nhúng đáng ngờ

Nếu hệ thống đã từng chấp nhận khóa trong header làm trust anchor:

1. Xác định phiên bản verifier và endpoint bị ảnh hưởng.
2. Tìm log reason code hoặc telemetry về header `jwk`, `jku`, `x5u`, `x5c` và nguồn khóa đã sử dụng.
3. Không log hoặc lưu lại token nguyên vẹn nếu chứa credential nhạy cảm; dùng fingerprint đã bảo vệ khi cần điều tra.
4. Cập nhật verifier để chỉ dùng key set từ issuer đã cấu hình.
5. Xem xét thu hồi session/grant và access token liên quan.
6. Xoay khóa issuer nếu private key thật có khả năng đã bị lộ.
7. Kiểm tra các request đã được chấp nhận từ token có nguồn khóa bất thường.
8. Thêm test hồi quy cho key substitution, issuer confusion và SSRF.
9. Giới hạn egress nếu verifier có thể fetch URL từ token header.
10. Theo dõi lỗi `unknown_kid`, `untrusted_key_source` và số lần JWKS refresh.

Không chỉ xóa token trong cache mà bỏ qua việc kiểm tra request/side effect đã xảy ra. Nếu attacker đã dùng token giả để thực hiện thao tác, cần xử lý ở tầng nghiệp vụ và audit.

## 17. Kiểm thử bảo mật

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| JWT ký bằng attacker key, nhúng `jwk`, claim `iss` là issuer tin cậy | Từ chối |
| JWT có chữ ký hợp lệ với khóa trong JWKS issuer đã cấu hình | Tiếp tục kiểm tra claims |
| `jku` trỏ tới host attacker | Không fetch; từ chối nếu profile cấm |
| `jku` trỏ tới loopback/private/cloud metadata | Không có outbound request tới đích |
| `x5u` trỏ tới URL không được phép | Không fetch |
| `x5c` chứa self-signed certificate không được tin | Từ chối |
| `x5c` chain hợp lệ nhưng danh tính không được mapping tới issuer | Từ chối |
| `kid` chứa path traversal hoặc chuỗi quá dài | Không truy cập file/path; từ chối |
| Hai issuer có cùng `kid` | Tra cứu tách namespace, không dùng chéo khóa |
| `iss` chưa biết | Không discovery/fetch tùy ý; từ chối |
| Header `alg` không nằm allowlist | Từ chối trước verify |
| JWK chứa private key material | Từ chối theo public-key policy |
| JWKS có key `use`/`key_ops` không phù hợp | Không chọn khóa |
| `kid` ngẫu nhiên liên tục | Không tạo JWKS fetch storm |
| Khóa rotation cũ/mới trong overlap | Chấp nhận đúng các khóa đã công bố theo policy |
| DPoP proof có `jwk` đúng, token `cnf.jkt` khớp | Xác minh theo DPoP profile |
| DPoP proof có JWK attacker nhưng token `cnf.jkt` không khớp | Từ chối |
| DPoP proof dùng sai `htm`/`htu`/`ath` | Từ chối |

Nên kiểm thử cả parser và outbound HTTP client bằng fuzzing, redirect, DNS rebinding mô phỏng, response quá lớn, timeout và `kid` bất thường. Kiểm tra rằng token sai không làm hệ thống fetch URL không tin cậy hoặc tiêu tốn tài nguyên không giới hạn.

## 18. Checklist triển khai

**Trust source và issuer:**

- [ ] Issuer được cấu hình hoặc nằm trong allowlist tin cậy.
- [ ] Không tự động tin `iss` chưa xác minh hoặc discovery URL tùy ý.
- [ ] JWKS URI đến từ cấu hình/metadata đã được tin cậy.
- [ ] Cache và key lookup được namespace theo issuer.
- [ ] Sau verify, `iss` phải khớp chính xác issuer dự kiến.

**JOSE header và JWK:**

- [ ] `jwk` nhúng không được dùng làm issuer trust anchor.
- [ ] `jku`/`x5u` từ token không được fetch tùy ý.
- [ ] `x5c` được kiểm tra certificate path, key usage và issuer mapping.
- [ ] `kid` chỉ là selector trong key set tin cậy, không phải path/URL/query tùy ý.
- [ ] `alg`, `kty`, `use`, `key_ops`, `crv` và key size khớp policy.
- [ ] Không chấp nhận private key material trong public JWK.

**Xác minh JWT:**

- [ ] Thuật toán được allowlist theo token profile.
- [ ] Chữ ký được xác minh bằng khóa lấy từ nguồn tin cậy.
- [ ] Kiểm tra `aud`, `exp`, `nbf`, `iat`, `typ` và claims bắt buộc.
- [ ] Tách biệt validation policy cho ID Token, access token, assertion và proof.

**Vận hành:**

- [ ] JWKS fetch có timeout, response-size limit, redirect/egress policy.
- [ ] Unknown `kid` không gây refresh storm.
- [ ] Rotation hỗ trợ overlap khóa có kiểm soát.
- [ ] Có metric cho nguồn khóa không tin cậy và lỗi xác minh.
- [ ] Có test forged issuer, key substitution, SSRF và cross-issuer confusion.
- [ ] Ngoại lệ như DPoP embedded JWK có binding riêng theo đúng RFC.

## 19. Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): các JOSE header parameter `jwk`, `jku`, `x5u`, `x5c` và `kid`.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): cấu trúc JWK/JWKS và các thuộc tính khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE và yêu cầu khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claim `iss`, `aud`, `exp`, `iat` và cấu trúc JWT.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): cách tính thumbprint để định danh JWK; thumbprint không tự tạo trust.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh issuer, audience, thuật toán và phân biệt token profile.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): trường hợp DPoP dùng JWK trong proof và ràng buộc bằng `cnf.jkt`.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): xác minh certificate path và PKI.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): metadata issuer và `jwks_uri` trong trust configuration OIDC.
- [OWASP Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): kiểm soát outbound request và SSRF.

**Ghi nhớ:** JWK trong header có thể giúp mô tả khóa, nhưng không tự chứng minh khóa thuộc issuer. Verifier phải lấy trust anchor từ cấu hình hoặc metadata đã xác minh, chọn khóa trong JWKS gắn với issuer, kiểm tra thuật toán và claims, rồi mới tin token. Không fetch `jku`/`x5u` tùy ý, không tin `x5c` nếu chưa xác minh chain, và chỉ chấp nhận embedded JWK trong profile có binding độc lập như DPoP.


# Thao túng kid để truy cập tệp, truy vấn hoặc chọn nhầm khóa

Trong JWT, header parameter `kid` (Key ID) thường được dùng để tìm khóa tương ứng trong một key set. Giá trị này nằm trong token do client gửi, vì vậy verifier phải xem nó là dữ liệu không đáng tin cậy cho đến khi chữ ký token được xác minh. Nếu ứng dụng ghép `kid` vào đường dẫn tệp, câu truy vấn cơ sở dữ liệu hoặc cache key mà không kiểm soát, attacker có thể gây path traversal, injection, đọc nhầm dữ liệu hoặc khiến verifier chọn sai khóa. Một lỗi lookup nhỏ có thể làm suy yếu toàn bộ bước xác minh chữ ký.

Bài này thuộc chương **Tấn công JWT** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng cho hệ thống xác minh JWT nói chung, độc lập ngôn ngữ lập trình, nền tảng và framework.

## 1. Mục tiêu và nguyên tắc

Sau bài học, người đọc có thể:

1. Giải thích vai trò của `kid` và vì sao giá trị này phải được coi là untrusted input.
2. Nhận diện cách thao túng `kid` để truy cập tệp hoặc gây injection trong truy vấn.
3. Phát hiện lỗi chọn nhầm khóa do trùng ID, thiếu issuer scope, cache collision hoặc fallback.
4. Thiết kế key resolver chỉ tra cứu trong key set được cấu hình tin cậy.
5. Ràng buộc lựa chọn khóa với issuer, token profile, thuật toán và metadata JWK.
6. Kiểm soát unknown `kid`, key rotation, cache refresh và log.
7. Xây dựng kiểm thử bảo mật cho path traversal, query injection và key confusion.

**Nguyên tắc cốt lõi:** `kid` chỉ là một gợi ý tra cứu do token cung cấp. Nó không phải đường dẫn, câu truy vấn, URL, danh tính issuer hoặc bằng chứng rằng khóa được chọn là đáng tin. Verifier chỉ được chọn khóa trong trust context đã cấu hình và phải xác minh chữ ký trước khi tin claims.

## 2. `kid` được dùng để làm gì?

`kid` là một JOSE header parameter được định nghĩa trong RFC 7517. Nó là một chuỗi dùng để giúp bên nhận chọn khóa phù hợp, đặc biệt khi một key set có nhiều khóa trong quá trình rotation.

Ví dụ header JWT:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-2026-04"
}
~~~

Verifier có thể dùng `kid` để tìm public JWK tương ứng trong JWKS của issuer đã được tin cậy. `kid` không có một định dạng bắt buộc phổ quát: nó có thể là chuỗi opaque do issuer quản lý. Vì vậy, verifier không được giả định rằng giá trị này luôn là tên file an toàn, số nguyên, UUID hoặc chuỗi chỉ gồm chữ và số.

RFC 7517 mô tả `kid` là giá trị phân biệt khóa trong key set để hỗ trợ lựa chọn khóa. Giá trị này thường phân biệt chữ hoa/chữ thường. Cách tạo và quản lý ID cụ thể thuộc policy của hệ thống.

## 3. Vì sao `kid` là untrusted input?

JWT compact serialization có header được gửi cùng request. Trước khi chữ ký được xác minh, attacker có thể tự tạo hoặc sửa header và đặt giá trị `kid` tùy ý.

Ví dụ:

~~~text
eyJhbGciOiJSUzI1NiIsImtpZCI6Ii4uLy4uLy4uL2V0Yy9wYXNzd2QifQ...
~~~

Chuỗi trên chỉ minh họa một header có `kid` chứa ký tự giống đường dẫn traversal. Nó không chứng minh chữ ký JWT hợp lệ. Tuy nhiên, nếu key resolver mở tệp theo giá trị này trước khi xác minh chữ ký, thao tác truy cập tệp đã xảy ra trước khi token bị từ chối.

Các điểm cần nhớ:

- Parser có thể đọc header trước bước xác minh chữ ký, nhưng không được coi nội dung header là đáng tin.
- `kid` có thể chứa dấu phân cách, dấu chấm, dấu gạch chéo, ký tự Unicode hoặc chuỗi rất dài.
- Việc Base64url-decode header không làm dữ liệu trở nên an toàn.
- Chữ ký hợp lệ chỉ có thể được xác định sau khi chọn được khóa trong trust context phù hợp và xác minh chữ ký thành công.
- Không được để `kid` điều khiển trực tiếp việc truy cập filesystem, database query, network URL hoặc quyền truy cập.

## 4. Luồng key lookup dễ bị khai thác

Một resolver thiếu an toàn thường có dạng:

~~~text
header = parseJwtHeader(token)
kid = header["kid"]
key = readFile("/keys/" + kid)
verifyJwt(token, key)
~~~

Hoặc:

~~~text
kid = parseJwtHeader(token)["kid"]
query = "SELECT public_key FROM signing_keys WHERE kid = '" + kid + "'"
key = database.execute(query).first()
verifyJwt(token, key)
~~~

Hai ví dụ có cùng lỗi thiết kế: dữ liệu từ JWT trực tiếp điều khiển thao tác truy cập tài nguyên. Việc xác minh chữ ký diễn ra sau lookup, nên attacker có thể tác động đến filesystem hoặc database ngay cả khi token cuối cùng không hợp lệ.

Luồng an toàn phải lấy issuer/key set từ trust configuration, sau đó thực hiện lookup chính xác trong tập khóa đã được phép. `kid` không được mở rộng trust boundary.

## 5. Path traversal qua `kid`

Nếu ứng dụng dùng `kid` như một phần của đường dẫn file, attacker có thể thử các chuỗi chứa:

- `../` hoặc `..\\` để đi lên thư mục cha.
- Đường dẫn tuyệt đối theo hệ điều hành.
- Dấu phân cách hỗn hợp hoặc mã hóa nhiều lớp.
- Ký tự null hoặc ký tự điều khiển nếu thư viện/stack xử lý không nhất quán.
- Tên thiết bị hoặc pseudo-file đặc biệt trên một số hệ điều hành.
- Chuỗi Unicode có thể bị chuẩn hóa khác nhau giữa các thành phần.

### 5.1. Tác động có thể xảy ra

Tùy cách triển khai và quyền của tiến trình, lỗi path traversal có thể dẫn đến:

1. Đọc tệp ngoài thư mục chứa public key.
2. Đọc cấu hình hoặc secret mà tiến trình có quyền truy cập.
3. Chọn một tệp không phải key dự kiến làm vật liệu xác minh.
4. Gây lỗi parser, exception hoặc khác biệt response có thể tiết lộ thông tin.
5. Tạo tải I/O hoặc mở nhiều tệp để gây từ chối dịch vụ.

Đọc được một tệp không đồng nghĩa attacker luôn có thể giả mạo JWT. Khả năng giả mạo còn phụ thuộc nội dung tệp được dùng làm key, thuật toán, cách resolver xử lý byte và quyền ký/xác minh. Tuy nhiên, để `kid` điều khiển đọc tệp đã là một lỗ hổng cần loại bỏ.

### 5.2. Ví dụ tình huống

Giả sử key resolver dự kiến đọc:

~~~text
/srv/app/keys/<kid>.pem
~~~

Nếu resolver nối chuỗi trực tiếp, giá trị `kid` chứa thành phần đường dẫn có thể khiến đường dẫn sau cùng trỏ ra ngoài `/srv/app/keys`. Việc thêm `.pem` ở cuối hoặc lọc một chuỗi `../` đơn lẻ không đủ an toàn vì có nhiều dạng encoding, separator và cách chuẩn hóa.

### 5.3. Biện pháp phòng vệ

- Không dùng `kid` làm tên file hoặc path fragment.
- Dùng registry ánh xạ ID opaque sang key reference/path được cấu hình trước.
- Nếu bắt buộc dùng file store, chỉ cho phép tên file do cấu hình tin cậy quyết định; không lấy path từ token.
- Giới hạn thư mục gốc, kiểm tra canonical path và bảo đảm kết quả vẫn nằm trong vùng được phép.
- Xử lý symlink và race condition; kiểm tra path trước khi mở file không đủ nếu file có thể bị thay thế giữa hai bước.
- Tiến trình chỉ có quyền đọc đúng thư mục và public key cần thiết.
- Không trả nội dung file hoặc exception filesystem cho caller.

Canonicalization là lớp kiểm tra bổ sung, không thay thế thiết kế allowlist hoặc mapping cố định.

## 6. Injection trong truy vấn database

Một số hệ thống lưu key registry trong database. Nếu resolver ghép `kid` vào câu SQL bằng nối chuỗi hoặc interpolation, dữ liệu header có thể thay đổi cấu trúc truy vấn.

Ví dụ mẫu nguy hiểm:

~~~sql
SELECT public_key
FROM signing_keys
WHERE kid = '<giá trị lấy từ JWT>';
~~~

Khi giá trị được chèn trực tiếp, ký tự quote hoặc toán tử trong `kid` có thể làm truy vấn được diễn giải khác ý định ban đầu. Hậu quả phụ thuộc quyền database và cấu trúc bảng:

- Trả về bản ghi không thuộc `kid` yêu cầu.
- Bỏ qua điều kiện lọc issuer/tenant.
- Đọc metadata hoặc key reference ngoài phạm vi.
- Gây lỗi truy vấn, lock hoặc tải bất thường.
- Trong cấu hình nguy hiểm, làm lộ dữ liệu ngoài bảng key registry.

### 6.1. Dùng parameterized query

Truyền `kid` như một giá trị tham số, không ghép nó vào cú pháp SQL:

~~~sql
SELECT public_key_reference
FROM signing_keys
WHERE issuer_id = :issuer_id
  AND key_id = :kid
  AND status = 'ACTIVE';
~~~

Ở đây `:issuer_id` và `:kid` là bind parameters do driver/database API hỗ trợ. Không tự thay placeholder bằng chuỗi đã escape thủ công.

### 6.2. Giới hạn phạm vi truy vấn

Ngay cả khi đã parameterize, chỉ tìm theo `kid` là chưa đủ. Query phải gắn với issuer/trust profile và tenant context đã xác định từ cấu hình đáng tin.

Ví dụ:

~~~text
lookupKey(
  trustedIssuerProfileId,
  trustedTenantBoundary,
  exactKid
)
~~~

Không lấy `issuer_id` hoặc tenant scope từ một giá trị header chưa xác minh rồi dùng làm quyền truy cập tùy ý. Nếu cần đọc `iss` từ JWT để định tuyến, chỉ dùng nó làm lookup hint vào allowlist issuer đã cấu hình; không tạo query hay trust context mới từ issuer tùy ý.

## 7. Injection ở các key store và query engine khác

Rủi ro không chỉ nằm ở SQL:

| Backend | Cách dùng sai | Biện pháp |
| --- | --- | --- |
| LDAP | Ghép `kid` vào filter string | Dùng API/filter escaping đúng chuẩn, parameter hóa nếu thư viện hỗ trợ và giới hạn base DN. |
| NoSQL | Chuyển `kid` thành object/operator hoặc query fragment | Chỉ truyền scalar string vào field cố định; không nhận object query từ token. |
| Redis/cache | Ghép key không namespace hoặc dùng separator gây va chạm | Dùng cấu trúc key có namespace issuer/profile và encoding rõ ràng. |
| Search engine | Nội suy `kid` vào query DSL | Dùng query builder và field cố định; không nhận DSL từ token. |
| Configuration service | Dùng `kid` để chọn arbitrary config path | Ánh xạ qua registry allowlist; không cho token chọn namespace tùy ý. |

Nguyên tắc chung là dữ liệu từ header chỉ được dùng làm giá trị tra cứu đã giới hạn, không được trở thành một phần cú pháp hoặc đường dẫn có quyền điều khiển hệ thống.

## 8. Chọn nhầm khóa do thiếu issuer scope

`kid` thường chỉ cần duy nhất trong một key set hoặc phạm vi quản lý cụ thể. Hai issuer độc lập có thể cùng sử dụng một chuỗi như `key-01`.

Ví dụ:

| Issuer | `kid` | Public key |
| --- | --- | --- |
| Issuer A | `key-01` | Public key A |
| Issuer B | `key-01` | Public key B |

Nếu hệ thống lưu một map toàn cục:

~~~text
keysByKid["key-01"] = ...
~~~

thì key của issuer A có thể ghi đè key của issuer B hoặc ngược lại. Một token từ issuer này có thể được đưa đến verifier chọn nhầm key của issuer khác. Kết quả thường là từ chối sai, nhưng nếu hệ thống có fallback hoặc cấu hình thuật toán yếu, có thể tạo ra lỗ hổng xác minh nghiêm trọng hơn.

Cache và registry nên có khóa định danh theo trust context, ví dụ:

~~~text
environment + issuer_profile + key_set + kid
~~~

Không cache hoặc tra cứu chỉ theo `kid` toàn cục.

## 9. Chọn nhầm khóa do trùng hoặc mơ hồ `kid`

Trong một JWKS có thể tồn tại nhiều JWK. Nếu nhiều khóa cùng khớp `kid` và các thuộc tính lọc khác, resolver không nên tùy tiện chọn khóa đầu tiên.

Các lỗi phổ biến:

- Dùng hàm tìm phần tử đầu tiên và chấp nhận kết quả mà không phát hiện bản ghi trùng.
- Phụ thuộc thứ tự phần tử trong JWKS.
- Dùng một key ID cho hai key material khác nhau trong cùng thời gian overlap.
- Không kiểm tra issuer/profile khi cache key.
- Chuẩn hóa chữ hoa/chữ thường hoặc Unicode làm hai ID khác nhau trở thành một.
- Cắt ngắn `kid` trước lookup khiến nhiều giá trị va chạm.

Policy an toàn:

1. So sánh `kid` chính xác theo quy tắc của profile; mặc định giữ phân biệt hoa/thường.
2. Lọc thêm theo `kty`, curve, `alg`, `use` và `key_ops` khi các member đó có mặt/được yêu cầu.
3. Chỉ chấp nhận đúng một khóa tương thích trong key set của issuer.
4. Nếu không có khóa hoặc có nhiều candidate mơ hồ, từ chối và ghi reason code nội bộ.
5. Không dùng thứ tự JWKS để quyết định khóa.

## 10. Chọn nhầm khóa do algorithm confusion

`kid` không quyết định thuật toán. Header `alg` cũng là dữ liệu do token cung cấp và phải được kiểm tra với allowlist từ cấu hình token profile.

Một resolver nguy hiểm có thể:

- Chọn key theo `kid` nhưng không ràng buộc key type.
- Dùng RSA public key bytes như HMAC secret nếu header yêu cầu HS256.
- Cho phép cùng một key reference được dùng cho signing/verification với mục đích khác nhau.
- Chấp nhận thuật toán không nằm trong policy vì key resolver trả về một key “có vẻ phù hợp”.

Biện pháp:

- Allowlist thuật toán theo issuer và token profile.
- Ràng buộc `alg` với key type/curve và cấu hình key registry.
- Không dùng RSA/EC public key làm HMAC secret.
- Chỉ dùng key có mục đích xác minh chữ ký phù hợp (`use=sig`, `key_ops` có `verify` nếu metadata được khai báo).
- Không để `kid` chuyển resolver sang một kho khóa khác hoặc đổi loại thuật toán.

Lựa chọn khóa và lựa chọn thuật toán phải được policy kiểm soát độc lập nhưng nhất quán.

## 11. Fallback nguy hiểm khi không tìm thấy `kid`

Một số hệ thống cố gắng “tăng khả năng tương thích” bằng cách:

- Dùng default key nếu `kid` không tìm thấy.
- Chọn key đầu tiên trong JWKS.
- Thử lần lượt mọi key ở mọi issuer cho đến khi chữ ký hợp lệ.
- Bỏ qua `kid` khi có lỗi lookup.
- Dùng khóa cũ hoặc key cache gần nhất mà không kiểm tra issuer/profile.

Những hành vi này làm mất ý nghĩa của key selection. Token được ký bằng một key khác vẫn có thể được chấp nhận ngoài phạm vi dự kiến.

Khi `kid` không tìm thấy:

1. Nếu rotation có thể vừa xảy ra, refresh JWKS đúng issuer từ endpoint đã cấu hình.
2. Giới hạn refresh bằng cooldown/single-flight và rate limit.
3. Tìm lại đúng `kid` trong key set mới.
4. Nếu vẫn không có đúng một key tương thích, từ chối token.

Không fallback sang bearer, default key, issuer khác hoặc thuật toán khác.

## 12. Unknown `kid` và tấn công từ chối dịch vụ

Attacker có thể gửi rất nhiều JWT với các giá trị `kid` ngẫu nhiên. Nếu mỗi giá trị kích hoạt một lần fetch JWKS hoặc query database, verifier có thể bị quá tải.

Các biện pháp:

- Giới hạn độ dài header và `kid` theo token profile.
- Giới hạn kích thước JWT và tốc độ request trước khi lookup.
- Dùng single-flight để nhiều request cùng unknown `kid` chia sẻ một lần refresh.
- Có cooldown cho JWKS refresh; không fetch liên tục theo từng giá trị.
- Dùng negative cache có TTL ngắn và giới hạn cardinality.
- Rate limit theo client, route, nguồn và issuer profile đã được xác định an toàn.
- Giới hạn timeout, response size và số lần retry khi lấy JWKS.
- Không tạo metric label hoặc alert riêng cho mỗi `kid` tùy ý.

Không đặt một giới hạn độ dài quá nhỏ đến mức phá vỡ issuer hợp lệ mà chưa xác định profile. Mục tiêu là có giới hạn thực tế, được công bố và kiểm thử.

## 13. Cache key và cache poisoning

Cache có thể biến lỗi lookup nhất thời thành lỗi kéo dài nếu định danh cache không đủ phạm vi.

### 13.1. Cache chỉ theo `kid`

Ví dụ không an toàn:

~~~text
cache["key-01"] = publicKey
~~~

Một issuer có thể ghi đè entry của issuer khác có cùng `kid`. Cache nên gắn với trust context:

~~~text
cache[
  environment,
  issuer_profile_id,
  jwks_uri_id,
  kid
] = validatedPublicKeyReference
~~~

Các thành phần trên phải đến từ cấu hình tin cậy, không phải từ URL tùy ý trong JWT.

### 13.2. Cache nhầm giữa key version

Nếu issuer tái sử dụng `kid` cho key material mới, cache cũ có thể khiến verifier tiếp tục dùng key trước đó hoặc các instance chọn kết quả khác nhau. Không nên tái sử dụng `kid` cho key material khác trong phạm vi còn token/cache có thể tồn tại.

Mỗi key mới nên có `kid` mới. Trong rotation, JWKS có thể đồng thời chứa key cũ và mới với ID khác nhau.

### 13.3. Negative cache

Negative cache giúp unknown `kid` không liên tục kích hoạt refresh. Tuy nhiên:

- TTL phải ngắn và có giới hạn.
- Không để attacker tạo vô hạn entry.
- Sau một refresh JWKS thành công hoặc thay đổi key set đã xác thực, phải có cách làm mới negative entry liên quan.
- Không để negative cache ngăn verifier nhận key mới hợp lệ quá lâu.

## 14. Quan hệ với `jku`, `x5u` và nguồn khóa từ xa

`kid` chỉ là key identifier; bản thân nó không phải URL. Tuy nhiên, một số implementation sai có thể diễn giải `kid` thành URL hoặc kết hợp nó với các header parameter khác để truy cập tài nguyên từ xa.

Các JOSE header như `jku` hoặc `x5u` có thể chỉ tới nguồn JWK/certificate. Nếu verifier tự động tải URL do token cung cấp, có thể phát sinh SSRF hoặc tin nhầm nguồn khóa.

Quy tắc:

- Không biến `kid` thành URL hoặc host/path fetch.
- Không tự động fetch `jku`/`x5u` do token tùy ý cung cấp.
- Dùng JWKS URI lấy từ issuer metadata/trust configuration đã được xác minh và allowlist.
- Kiểm soát redirect, DNS, địa chỉ private/link-local, TLS và response size theo policy chống SSRF.
- Không cho header trong JWT thay đổi issuer trust registry.

Đây là bề mặt tấn công liên quan của key resolution; không nhầm nó với bản thân semantics của `kid`.

## 15. Thiết kế key resolver an toàn

Một resolver an toàn nên thực hiện các bước theo thứ tự:

1. Giới hạn kích thước token và parse compact serialization an toàn.
2. Đọc header như dữ liệu chưa tin cậy; từ chối cấu trúc sai hoặc header parameter trùng nếu parser không xử lý nhất quán.
3. Xác định issuer profile từ endpoint/configuration tin cậy. Nếu đọc `iss` chưa xác minh để định tuyến, chỉ ánh xạ chính xác vào allowlist; không tự discovery/fetch theo giá trị đó.
4. Lấy algorithm allowlist và key set reference từ profile đã chọn.
5. Kiểm tra `alg` được phép trước khi lựa chọn key.
6. Đọc `kid` như một scalar string có giới hạn; không dùng làm path, query fragment hoặc URL.
7. Tìm chính xác trong key set của issuer/profile; chỉ chấp nhận một candidate tương thích.
8. Nếu unknown `kid`, refresh có giới hạn từ JWKS URI tin cậy rồi lookup lại một lần theo policy.
9. Kiểm tra `kty`, curve, `alg`, `use`, `key_ops` và key strength phù hợp.
10. Xác minh chữ ký JWT.
11. Sau khi chữ ký hợp lệ, kiểm tra `iss`, `aud`, `exp`, `nbf`, token type/profile và claims nghiệp vụ.
12. Chỉ trả dữ liệu hoặc thực hiện side effect sau khi mọi policy đạt.

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Parse header có giới hạn"]
    B --> C["Chọn issuer profile từ trust config"]
    C --> D["Lấy alg allowlist và trusted key set"]
    D --> E["Exact lookup kid trong issuer key set"]
    E --> F{"Đúng một key tương thích?"}
    F -- "Không tìm thấy" --> G["Refresh JWKS có giới hạn"]
    G --> E
    F -- "Mơ hồ hoặc sai metadata" --> X["Reject"]
    F -- "Có đúng một key" --> H["Verify chữ ký"]
    H --> I{"Chữ ký hợp lệ?"}
    I -- "Không" --> X
    I -- "Có" --> J["Validate issuer, audience, time và profile"]
    J --> K{"Claims hợp lệ?"}
    K -- "Không" --> X
    K -- "Có" --> L["Chấp nhận theo authorization policy"]
~~~

Sơ đồ mô tả logic tổng quát. Tùy kiến trúc, issuer profile có thể được chọn từ route/client configuration trước khi parse token. Điểm bắt buộc là key set và thuật toán phải đến từ trust policy, còn `kid` chỉ thực hiện exact lookup bên trong phạm vi đó.

## 16. Pseudocode lookup an toàn

Ví dụ khái niệm:

~~~text
function resolveVerificationKey(untrustedToken, trustedEndpointProfile):
    header = parseProtectedHeaderWithLimits(untrustedToken)

    if not allowedAlgorithm(
        trustedEndpointProfile.allowedAlgorithms,
        header.alg
    ):
        reject("JWT_ALGORITHM_NOT_ALLOWED")

    kid = requireBoundedString(header.kid)
    keySet = loadTrustedKeySet(trustedEndpointProfile.jwksReference)

    candidates = keySet.keys.filter(key =>
        exactStringMatch(key.kid, kid) &&
        compatibleKeyType(key, header.alg) &&
        compatiblePurpose(key, "verify") &&
        compatibleAlgorithmMetadata(key, header.alg)
    )

    if candidates.length == 0:
        keySet = refreshTrustedKeySetWithCooldown(
            trustedEndpointProfile.jwksReference
        )
        candidates = findExactCompatibleCandidates(keySet, kid, header.alg)

    if candidates.length != 1:
        reject("JWT_KEY_NOT_FOUND_OR_AMBIGUOUS")

    return candidates[0].publicKey
~~~

Pseudocode này không mô tả mọi chi tiết của JOSE. Trong triển khai, phải kiểm tra kiểu dữ liệu, key strength, curve, duplicate JSON member, key usage và lỗi parser theo token profile. `trustedEndpointProfile` phải đến từ cấu hình đã được quản trị, không được tạo từ `kid`.

## 17. Lỗi thiết kế trong file store và database

| Kiểu lưu khóa | Lỗi thường gặp | Thiết kế an toàn |
| --- | --- | --- |
| File store | Nối `kid` vào path | Map ID sang path cố định trong registry tin cậy. |
| File store | Dùng path normalization nhưng vẫn cho symlink thoát thư mục | Kiểm soát canonical path, symlink, quyền file và cách mở an toàn. |
| SQL | Nối `kid` vào câu query | Prepared statement/bind parameter. |
| SQL | Query chỉ theo `kid` | Thêm issuer/profile/tenant scope từ cấu hình. |
| SQL | Dùng key ID trùng giữa issuer | Composite unique key theo trust context. |
| Redis | Cache key chỉ là `kid` | Namespace theo environment, issuer profile, key set và `kid`. |
| Secret manager/KMS | Dùng `kid` làm resource name tùy ý | Lookup qua registry allowlist đến resource reference. |
| JWKS | Chọn phần tử đầu tiên khớp `kid` | Đếm candidate; reject nếu không đúng một key tương thích. |

Nếu database chỉ lưu metadata, private key nên tiếp tục được bảo vệ trong KMS/HSM hoặc secret-management system phù hợp. Verifier thường chỉ cần public key để xác minh chữ ký bất đối xứng.

## 18. Logging, lỗi và phản hồi an toàn

Không phản hồi hoặc ghi log toàn bộ giá trị `kid` nếu nó có thể chứa ký tự điều khiển, dữ liệu rất dài hoặc chuỗi nhạy cảm.

Internal reason code tham khảo:

- `JWT_KID_MISSING`
- `JWT_KID_INVALID_FORMAT`
- `JWT_KID_TOO_LARGE`
- `JWT_KID_NOT_FOUND`
- `JWT_KID_AMBIGUOUS`
- `JWT_KEY_LOOKUP_SCOPE_MISMATCH`
- `JWT_KEY_STORE_QUERY_FAILED`
- `JWT_KEY_STORE_ACCESS_DENIED`
- `JWT_KEY_METADATA_MISMATCH`
- `JWT_ALGORITHM_KEY_TYPE_MISMATCH`
- `JWKS_REFRESH_RATE_LIMITED`

Response bên ngoài nên dùng thông báo chung như token không hợp lệ hoặc xác thực tạm thời không khả dụng, tùy lỗi thực tế. Không tiết lộ đường dẫn file, câu SQL, tên bảng, key resource, issuer nội bộ hoặc kết quả truy cập tệp.

Log nên có request ID, issuer profile ID đã chuẩn hóa, reason code, key-set reference nội bộ và dependency status. Nếu cần ghi raw `kid` để điều tra, phải giới hạn độ dài, escape ký tự điều khiển, phân quyền log và tránh dùng nó làm metric label cardinality cao. Không ghi JWT hoặc secret.

## 19. Kiểm thử bảo mật cho `kid`

Kiểm thử phải xác nhận resolver không truy cập tài nguyên ngoài phạm vi và không chọn nhầm key.

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| `kid` bình thường và có đúng một key tương thích | Chọn đúng key trong issuer key set. |
| `kid` chứa `../`, `..\\` hoặc path tuyệt đối | Không truy cập filesystem theo giá trị đó; token bị từ chối nếu không có key tương ứng. |
| `kid` chứa quote/toán tử/query syntax | Được truyền như giá trị tham số hoặc bị từ chối theo format policy; không thay đổi cấu trúc query. |
| `kid` chứa ký tự Unicode hoặc separator lạ | So sánh theo policy nhất quán; không chuẩn hóa gây collision. |
| `kid` rất dài hoặc chứa control characters | Bị giới hạn; không gây log injection hoặc memory exhaustion. |
| Cùng `kid` xuất hiện ở hai issuer | Lookup trong key set đúng issuer; không dùng cache toàn cục. |
| Nhiều JWK cùng khớp `kid` và metadata | Reject ambiguous key; không chọn phần tử đầu tiên. |
| `kid` không tồn tại | Refresh trusted JWKS có giới hạn rồi reject. |
| Hàng nghìn unknown `kid` | Không tạo fetch storm, query storm hoặc cache cardinality vô hạn. |
| Key rotation thêm key mới với `kid` mới | Verifier refresh và chọn key mới theo issuer đúng. |
| Key material đổi nhưng `kid` bị tái sử dụng | Phát hiện vi phạm lifecycle policy; không âm thầm thay binding trong cache. |
| `alg` không nằm trong allowlist | Reject trước khi thử key hoặc fallback. |
| `kty`, curve, `use` hoặc `key_ops` không phù hợp | Reject candidate. |
| JWKS chứa key của issuer khác | Không chọn key ngoài issuer trust boundary. |
| Có default key khi lookup thất bại | Test phải chứng minh không có fallback. |

### 19.1. Kiểm thử side effect

Ngoài response HTTP, cần kiểm tra bằng chứng hệ thống:

- File ngoài thư mục key không bị mở hoặc đọc.
- Database query vẫn giữ nguyên cấu trúc và chỉ trả record trong issuer scope.
- Không có request network đến URL do `kid` điều khiển.
- Cache entry của issuer A không thể được dùng cho issuer B.
- Unknown `kid` không làm tăng fetch/DB query vượt giới hạn.
- Log không chứa JWT, secret, raw exception hoặc ký tự điều khiển chưa escape.

Kiểm thử trên môi trường cô lập với fixture giả; không dùng secret hoặc file production để thử path traversal.

## 20. Ứng cứu khi phát hiện thao túng `kid`

Nếu có dấu hiệu khai thác:

1. Xác định resolver, endpoint, issuer profile và key store bị ảnh hưởng.
2. Kiểm tra log filesystem, database audit, KMS access và outbound network để xác định tài nguyên đã bị truy cập.
3. Xác định attacker có đọc được private key, secret, configuration hoặc dữ liệu khác hay không.
4. Nếu key material hoặc credential bị lộ, revoke/rotate theo phạm vi ảnh hưởng và phát hành key ID mới.
5. Kiểm tra token có thể đã được xác minh bằng key sai hoặc fallback hay không.
6. Xóa cache entry sai và đồng bộ lại trusted JWKS/key registry.
7. Chặn injection/path lookup ở resolver, triển khai parameterized query và fixed key mapping.
8. Thêm test hồi quy cho payload và đường đi đã gây lỗi.
9. Đánh giá log/backup/ticket có chứa dữ liệu đọc được hoặc secret bị lộ hay không.

Nếu chỉ phát hiện chuỗi `kid` độc hại nhưng resolver không thực hiện truy cập ngoài phạm vi và token bị từ chối đúng, có thể là một lần dò quét. Vẫn cần theo dõi tần suất, nguồn request và các lỗi liên quan để xác định có khai thác thành công hay không.

## 21. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Dùng `kid` làm tên file/path | Path traversal và đọc file ngoài key directory. | Registry ID-to-reference cố định. |
| Nối `kid` vào SQL/LDAP/NoSQL query | Injection và truy cập record ngoài phạm vi. | Parameterized query và API query builder an toàn. |
| Lookup chỉ theo `kid` toàn cục | Chọn nhầm key giữa issuer/tenant. | Composite lookup theo trust context. |
| Chọn key đầu tiên trùng `kid` | Ambiguous key và phụ thuộc thứ tự JWKS. | Chỉ chấp nhận đúng một candidate tương thích. |
| Dùng default key khi không tìm thấy | Bỏ qua ý nghĩa của key ID và có thể xác minh bằng key sai. | Reject sau một lần refresh trusted JWKS có giới hạn. |
| Chuẩn hóa/cắt ngắn `kid` không nhất quán | Collision giữa các ID khác nhau. | Exact matching theo profile, giới hạn độ dài trước lookup. |
| Cache chỉ theo `kid` | Cache poisoning hoặc cross-issuer collision. | Namespace cache theo environment/issuer/key set. |
| Tái sử dụng `kid` cho key material mới | Cache và token cũ có thể trỏ sai key. | Mỗi key material mới dùng ID mới. |
| Tin `alg` do token khai báo | Algorithm/key confusion. | Allowlist từ issuer/token profile và kiểm tra key type. |
| Fetch JWKS theo URL từ token | SSRF và trust-source substitution. | Dùng JWKS URI từ trusted configuration. |
| Log raw `kid` không giới hạn | Log injection, log flooding và cardinality cao. | Sanitize, truncate, chuẩn hóa và kiểm soát log. |

## 22. Checklist thiết kế key resolver

**Input và lookup**

- [ ] Header JWT được coi là untrusted trước khi xác minh chữ ký.
- [ ] `kid` chỉ là scalar string có giới hạn kích thước.
- [ ] Không dùng `kid` làm path, URL, query fragment hoặc resource name tùy ý.
- [ ] File store dùng mapping cố định; database dùng parameterized query.
- [ ] Lookup luôn nằm trong issuer/profile/tenant trust boundary.
- [ ] So sánh `kid` chính xác, không cắt ngắn hoặc chuẩn hóa gây collision.

**Key selection**

- [ ] Thuật toán nằm trong allowlist từ trusted profile.
- [ ] Kiểm tra `kty`, curve, `alg`, `use`, `key_ops` và key strength.
- [ ] Chỉ chấp nhận đúng một candidate tương thích.
- [ ] Duplicate/ambiguous key bị từ chối.
- [ ] Unknown `kid` chỉ kích hoạt refresh trusted JWKS có giới hạn.
- [ ] Không có default-key, first-key hoặc cross-issuer fallback.

**Cache và rotation**

- [ ] Cache key bao gồm environment, issuer profile, key set và `kid`.
- [ ] Key material mới dùng `kid` mới.
- [ ] Negative cache có TTL và cardinality giới hạn.
- [ ] JWKS refresh có cooldown, single-flight và timeout.

**Quan sát và kiểm thử**

- [ ] Log dùng reason code, không để raw input gây log injection.
- [ ] Không ghi JWT hoặc secret.
- [ ] Có test path traversal, query injection, collision và ambiguous key.
- [ ] Có test unknown-kid flood, cache isolation và key rotation.
- [ ] Có audit cho truy cập key store và thay đổi trust configuration.

## 23. Tài liệu chuẩn tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): `kid` và cách sử dụng để chọn khóa trong JWK Set.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JOSE header parameters và xác minh chữ ký.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm tra thuật toán, issuer, audience và các thực hành xác minh JWT an toàn.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): định danh public key bằng thumbprint khi profile cần.
- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal): rủi ro truy cập tệp ngoài thư mục dự kiến.
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized queries và phòng SQL injection.
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): giới hạn và xác thực dữ liệu đầu vào.

**Ghi nhớ:** `kid` giúp tìm khóa trong một key set đã được tin cậy; nó không được quyền quyết định file path, query, URL hoặc issuer. Hãy tra cứu chính xác trong trust context đã cấu hình, ràng buộc với thuật toán và metadata JWK, reject khi thiếu hoặc mơ hồ, đồng thời giới hạn refresh/cache để ngăn injection, key confusion và denial of service.

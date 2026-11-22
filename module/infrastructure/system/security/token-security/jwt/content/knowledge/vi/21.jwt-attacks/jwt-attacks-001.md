# Giả mạo `alg=none` và bỏ qua xác minh chữ ký

## 1. Tổng quan về cuộc tấn công

JSON Web Token (JWT) thường được bảo vệ bằng chữ ký số hoặc MAC để bên nhận phát hiện nội dung bị sửa đổi. Một lỗi xác minh nghiêm trọng xảy ra khi verifier chấp nhận JWT có JOSE header `"alg": "none"` trong khi ứng dụng đang yêu cầu token được ký.

Giá trị `none` được định nghĩa cho **Unsecured JWS**: nội dung không có chữ ký mật mã. Nếu hệ thống dùng token này để xác thực hoặc phân quyền như thể chữ ký đã được kiểm tra, kẻ tấn công có thể tự tạo JWT với claims tùy ý, chẳng hạn thay `sub` hoặc thêm role quản trị, rồi gửi đến API.

Đây thường được gọi là **alg=none attack**, **unsecured JWT acceptance** hoặc **signature verification bypass**.

Điểm cốt lõi:

- `alg: none` không tạo chữ ký và không cung cấp tính toàn vẹn mật mã.
- Kẻ tấn công không cần biết private key hoặc secret ký JWT để tạo một unsecured JWT.
- Cuộc tấn công chỉ thành công nếu ứng dụng hoặc thư viện chấp nhận token không chữ ký trong ngữ cảnh cần token đã được xác thực.
- Không phải mọi thư viện JWT đều dễ bị tấn công; nhiều thư viện hiện đại từ chối `none` theo mặc định hoặc yêu cầu cấu hình cho phép rõ ràng.

## 2. JWT bình thường được bảo vệ như thế nào?

Một signed JWT thường dùng JWS Compact Serialization với ba phần được phân tách bằng dấu chấm:

~~~text
BASE64URL(protected-header).
BASE64URL(payload).
BASE64URL(signature)
~~~

Trong một JWS có chữ ký, protected header khai báo thuật toán như `RS256`, `PS256` hoặc `ES256`; payload chứa claims; phần cuối chứa chữ ký/MAC được tính trên signing input.

Verifier phải:

1. Chọn issuer và khóa tin cậy theo cấu hình hoặc metadata đã xác minh.
2. Chỉ cho phép thuật toán đã được cấu hình.
3. Xác minh chữ ký/MAC bằng khóa phù hợp.
4. Chỉ sau khi xác minh thành công mới tin claims để kiểm tra issuer, audience, thời gian, loại token và quyền.

Nếu bỏ bước xác minh chữ ký, payload JSON chỉ là dữ liệu do người gửi cung cấp. Việc Base64URL decode thành công không chứng minh token là thật.

## 3. `alg=none` có nghĩa gì theo chuẩn?

Trong JOSE, `alg` là tham số header khai báo thuật toán bảo vệ JWS. Giá trị `none` được định nghĩa cho trường hợp không áp dụng chữ ký/MAC. Đây không phải thuật toán mã hóa và cũng không phải cách viết tắt của “chữ ký không cần kiểm tra”.

Unsecured JWS vẫn có cấu trúc compact ba phần, nhưng phần signature là chuỗi rỗng:

~~~text
BASE64URL(protected-header).
BASE64URL(payload).
~~~

Ví dụ protected header:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

Ví dụ payload:

~~~json
{
  "iss": "https://identity.example.test/",
  "sub": "user-42",
  "aud": "https://api.example.test/",
  "role": "admin",
  "iat": 1893452400,
  "exp": 1893456000
}
~~~

Hai phần JSON trên có thể được Base64URL encode và nối bằng dấu chấm, kết thúc bằng dấu chấm cuối cùng để biểu thị signature rỗng. Vì không có chữ ký, bất kỳ ai cũng có thể tạo header và payload khác rồi encode lại.

RFC 7519 mô tả Unsecured JWT trong mục 6 và chỉ cho phép dùng khi tính toàn vẹn không cần thiết hoặc được bảo đảm bằng cách khác ngoài JWT. Bearer access token dùng để xác thực hoặc phân quyền thông thường cần bảo vệ tính toàn vẹn; vì vậy không được chấp nhận `none` cho mục đích đó.

## 4. Kịch bản giả mạo token

Giả sử hệ thống có một API chỉ cho phép quản trị viên truy cập. API dự kiến chỉ chấp nhận token được ký bằng khóa tin cậy.

Token hợp lệ ban đầu có claims:

~~~json
{
  "sub": "user-42",
  "role": "user",
  "aud": "https://api.example.test/admin",
  "exp": 1893456000
}
~~~

Kẻ tấn công không có khóa ký nhưng muốn mạo danh quản trị viên. Nếu verifier có lỗi chấp nhận unsecured JWT, kẻ tấn công có thể tự tạo token với header:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

và payload:

~~~json
{
  "sub": "attacker-controlled",
  "role": "admin",
  "aud": "https://api.example.test/admin",
  "exp": 1893456000
}
~~~

Token được gửi với phần signature rỗng. Nếu API chỉ decode payload, hoặc validator cho phép `none` và vẫn tạo principal từ claims, API có thể coi kẻ tấn công là admin.

### Các bước khai thác ở mức khái niệm

1. Xác định ứng dụng nhận JWT trong header, cookie hoặc một kênh khác.
2. Kiểm tra cách verifier xử lý thuật toán trong JOSE header.
3. Tạo JWT mới với `alg` là `none` và claims mục tiêu.
4. Dùng JWS Compact Serialization với signature rỗng.
5. Gửi token tới endpoint được bảo vệ.
6. Nếu ứng dụng không yêu cầu chữ ký hợp lệ, quan sát xem token có được chấp nhận hay không.

Chỉ thực hiện thử nghiệm trong hệ thống được phép kiểm thử. Không gửi token giả mạo đến dịch vụ bên thứ ba hoặc hệ thống ngoài phạm vi kiểm thử.

## 5. Điều kiện để cuộc tấn công thành công

Chỉ có một JWT ghi `alg=none` không đồng nghĩa hệ thống đã bị khai thác. Cần có lỗi ở phía chấp nhận token.

Các điều kiện thường gặp:

- Ứng dụng sử dụng JWT để xác thực hoặc phân quyền.
- Verifier chấp nhận unsecured JWS trong ngữ cảnh cần chữ ký.
- Thuật toán được phép không bị giới hạn rõ ràng ở phía ứng dụng, hoặc thư viện được cấu hình cho phép `none`.
- Claims từ token chưa được xác minh được dùng để tạo danh tính, role hoặc quyết định truy cập.
- Không có lớp kiểm tra độc lập khác ngăn request.

Ngược lại, cuộc tấn công sẽ thất bại nếu verifier yêu cầu thuật toán ký được cho phép, từ chối `none`, yêu cầu chữ ký hợp lệ và chỉ sử dụng claims sau khi xác minh thành công.

| Lỗi | Hệ quả |
| --- | --- |
| Chỉ decode JWT rồi đọc payload | Người gửi có thể sửa mọi claim mà không cần khóa |
| Dựa vào `alg` do token cung cấp để tự quyết định có xác minh hay không | Attacker có thể chọn chế độ không chữ ký nếu verifier cho phép |
| Cấu hình thư viện cho phép thuật toán `none` trong luồng bearer token | Token không chữ ký có thể được chấp nhận |
| Khi xác minh chữ ký thất bại thì fallback sang decode không xác minh | Token giả mạo có thể vượt qua nhánh fallback |
| Chấp nhận token không có signature chỉ vì parser xử lý được | Không bảo đảm tính toàn vẹn |

## 6. Vì sao có thể sửa claims mà không cần khóa?

JWS Compact Serialization ký trên signing input được tạo từ protected header và payload đã Base64URL encode. Với token được ký, thay đổi một trong hai phần làm chữ ký cũ không còn khớp.

Với `alg=none`, phần chữ ký là rỗng theo định nghĩa unsecured JWS. Không có MAC hoặc chữ ký để verifier kiểm tra header và payload có đến từ issuer hay không. Attacker có thể tạo payload mới, thay `sub`, thêm role/scope, thay `aud` hoặc chọn `exp` theo đồng hồ verifier.

Những giá trị này vẫn phải qua các kiểm tra claims khác nếu có, nhưng các kiểm tra đó không thay thế tính toàn vẹn mật mã. Nếu attacker tự tạo payload phù hợp với các điều kiện còn lại, chúng không chứng minh token được issuer phát hành.

## 7. Phân biệt `alg=none` attack với algorithm confusion

Hai nhóm lỗi thường được nhắc cùng nhau nhưng không giống nhau:

| Tiêu chí | `alg=none` attack | Algorithm confusion |
| --- | --- | --- |
| Vấn đề | Verifier chấp nhận token không có chữ ký | Verifier diễn giải sai thuật toán hoặc dùng sai loại khóa |
| Cách khai thác điển hình | Gửi unsecured JWT với signature rỗng | Ví dụ, nhầm khóa công khai RSA là secret HMAC khi xử lý HS256 |
| Có cần khóa ký hợp lệ? | Không cần nếu verifier chấp nhận unsecured JWT | Tùy biến thể; thường lợi dụng cách verifier dùng khóa |
| Phòng vệ chính | Từ chối `none`, yêu cầu chữ ký hợp lệ | Ràng buộc thuật toán với loại khóa và cấu hình tin cậy |

Không nên gộp tất cả thành một lỗi “JWT đổi alg”. Cần kiểm tra riêng việc chấp nhận unsecured JWT, allowlist thuật toán, cách ràng buộc khóa và mọi nhánh fallback.

## 8. Tác động bảo mật

Nếu token không chữ ký được chấp nhận trong luồng xác thực, tác động có thể rất nghiêm trọng:

- **Authentication bypass:** tạo danh tính giả hoặc mạo danh user khác.
- **Privilege escalation:** tự thêm role hoặc scope đặc quyền.
- **Unauthorized access:** truy cập API hoặc dữ liệu không được cấp.
- **Tenant isolation failure:** sửa tenant/organization claim nếu ứng dụng tin claim đó.
- **Audit corruption:** hoạt động giả mạo được ghi nhận dưới danh tính của người khác.
- **Business impact:** thực hiện thao tác nhạy cảm như phê duyệt, thay đổi cấu hình hoặc đọc dữ liệu riêng tư.

Phạm vi thực tế phụ thuộc vào cách ứng dụng dùng claims, audience, authorization policy và các lớp bảo vệ khác. Cần xác minh đường đi từ token đến quyết định truy cập; việc parser đọc được `none` chưa đủ chứng minh có thể thực hiện mọi hành động.

## 9. Phòng chống: allowlist thuật toán ở phía verifier

Biện pháp quan trọng nhất là verifier phải có **allowlist thuật toán được cấu hình từ nguồn tin cậy**. Không để token chưa xác minh tự quyết định thuật toán mà ứng dụng sẽ chấp nhận.

Ví dụ chính sách:

~~~text
expectedIssuer = "https://identity.example.com/"
allowedAlgorithms = ["RS256"]
requireSignature = true
allowUnsecuredJwt = false
~~~

Đây là ví dụ chính sách, không phải cấu hình bắt buộc cho mọi hệ thống. Hãy chọn thuật toán phù hợp với kiến trúc khóa và profile của issuer.

Quy tắc cần tuân thủ:

1. Chọn thuật toán được phép từ cấu hình verifier, không lấy allowlist từ header JWT.
2. Từ chối `alg` không nằm trong allowlist.
3. Từ chối `alg` bằng `none` trong mọi luồng access token/JWT đã ký thông thường.
4. Ràng buộc thuật toán với loại khóa phù hợp.
5. Yêu cầu chữ ký/MAC tồn tại và xác minh thành công.
6. Không có nhánh fallback sang decode không xác minh.

RFC 8725 mục 3.1 yêu cầu ứng dụng kiểm tra thuật toán và chỉ chấp nhận thuật toán được cấu hình cho ngữ cảnh đó. Danh sách thuật toán được phép phải do ứng dụng chỉ định, không phải do attacker điều khiển thông qua token.

## 10. Phòng chống: chỉ tin claims sau khi xác minh thành công

Quy trình an toàn cần tách rõ parse token và verify token:

~~~text
header, payload, signature = parseCompactJws(rawToken)

if header.alg not in configuredAllowedAlgorithms:
    reject("unsupported signing algorithm")

if header.alg == "none":
    reject("unsecured JWT is not accepted")

key = resolveTrustedKey(configuredIssuer, header.kid, header.alg)

if signature is empty:
    reject("signature is required")

if not verifyJws(header, payload, signature, key, header.alg):
    reject("invalid signature")

claims = parseClaims(payload)
validateIssuerAudienceTimeAndTokenType(claims)
authorize(claims)
~~~

Đây là giả mã minh họa. Trong triển khai thực tế, ưu tiên API verify của thư viện JWT/JOSE đáng tin cậy và cấu hình rõ thuật toán, issuer, audience, loại token và khóa. Không tự viết lại thuật toán chữ ký.

**Parse không phải verify.** Parser có thể đọc header/payload để phục vụ lựa chọn khóa hoặc chẩn đoán, nhưng không được dùng claims chưa xác minh để cấp danh tính, role hoặc quyền.

## 11. Phòng chống: ràng buộc thuật toán với khóa và issuer

Ngoài việc từ chối `none`, verifier cần tránh các lỗi lựa chọn khóa/thuật toán:

- Mỗi issuer có cấu hình thuật toán được phép riêng.
- Chỉ tải khóa từ JWKS URI hoặc nguồn khóa được cấu hình tin cậy.
- Không dùng URL trong token chưa xác minh để tải khóa tùy ý.
- Kiểm tra `kty`, `use`, `key_ops`, `alg` và các thuộc tính khóa cần thiết.
- Không dùng khóa RSA công khai như secret HMAC.
- Không tự động fallback từ thuật toán bất đối xứng sang đối xứng hoặc ngược lại.
- Không chọn thuật toán yếu hơn chỉ vì thuật toán mạnh hơn thất bại.
- Không dùng `kid` để bỏ qua việc xác minh chữ ký; `kid` chỉ hỗ trợ tìm khóa ứng viên.

Thuật toán được khai báo trong header chỉ là dữ liệu đầu vào chưa đáng tin cậy cho đến khi JWS được xác minh. Cấu hình verifier phải xác định trước loại token và tập thuật toán hợp lệ.

## 12. Unsecured JWT có khi nào được phép dùng?

RFC 7519 có định nghĩa Unsecured JWT, nhưng điều đó không có nghĩa ứng dụng nên chấp nhận nó trong mọi ngữ cảnh.

Một trường hợp chỉ có thể cân nhắc là môi trường mà:

- Tính toàn vẹn không cần thiết hoặc được bảo đảm độc lập bởi một cơ chế đáng tin cậy khác.
- Hai bên đã thống nhất rõ profile cho phép unsecured JWT.
- Luồng unsecured được tách biệt hoàn toàn khỏi bearer authentication, authorization và các token có yêu cầu chữ ký.
- Không thể nhầm token unsecured với token đã ký hoặc dùng token này ở resource server khác.

Đây không phải khuyến nghị cho OAuth access token, OpenID Connect ID Token hoặc JWT dùng để quyết định quyền. Nếu không có yêu cầu đặc biệt đã được phân tích và phê duyệt, chính sách an toàn là từ chối `alg=none`.

## 13. Kiểm thử để phát hiện lỗ hổng

Nên có negative tests ở tầng verifier và integration tests qua endpoint thật.

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| JWT ký bằng thuật toán nằm trong allowlist, chữ ký đúng | Chấp nhận nếu claims và policy đều đạt | Luồng hợp lệ |
| JWT có `alg=none` và signature rỗng | Từ chối | Ngăn unsecured JWT |
| JWT có `alg=none` nhưng phần signature không rỗng | Từ chối | Không diễn giải sai unsecured JWS |
| JWT đổi `alg` từ thuật toán được phép sang `none` | Từ chối | Ngăn hạ cấp sang không chữ ký |
| JWT có thuật toán không nằm trong allowlist | Từ chối | Algorithm allowlist |
| JWT có chữ ký sai | Từ chối | Integrity verification |
| JWT thiếu phần signature trong luồng yêu cầu ký | Từ chối | Signature required |
| JWT có `alg` viết sai chữ hoa/thường như `None` | Từ chối nếu không phải định danh thuật toán được cấu hình | So khớp chính xác |
| JWT có claims admin nhưng không có chữ ký hợp lệ | Từ chối | Không tin payload tự khai |
| JWT có chữ ký hợp lệ nhưng issuer sai | Từ chối | Issuer validation |
| JWT có chữ ký hợp lệ nhưng audience sai | Từ chối | Audience validation |
| JWT ký bằng khóa không thuộc issuer tin cậy | Từ chối | Trusted key selection |
| JWT ký bằng thuật toán hợp lệ nhưng sai loại khóa | Từ chối | Algorithm/key binding |
| Token không hợp lệ đi qua nhánh fallback decode-only | Request phải bị từ chối | Fallback regression |
| Token unsecured gửi đến mọi endpoint xác thực/phân quyền | Từ chối nhất quán | Kiểm tra mọi đường vào |

### Kiểm thử compact serialization

Một Unsecured JWS có ba phần và phần thứ ba rỗng. Bài test cần xác nhận verifier không nhầm “đúng định dạng compact” với “đã xác minh chữ ký”.

~~~text
protectedHeader = BASE64URL({"alg":"none","typ":"JWT"})
payload = BASE64URL({"sub":"attacker","role":"admin","exp":1893456000})
unsecuredToken = protectedHeader + "." + payload + "."

assert verifyAccessToken(unsecuredToken) == REJECTED
~~~

Test này minh họa cấu trúc token để xác nhận hành vi từ chối. Không dùng token đó làm credential trong môi trường production.

## 14. Phản ứng khi phát hiện hệ thống chấp nhận `alg=none`

Nếu verifier thực sự chấp nhận unsecured JWT trong luồng xác thực, cần coi đây là lỗ hổng có khả năng cho phép giả mạo danh tính và quyền.

Các bước xử lý:

1. **Chặn ngay:** cấu hình verifier từ chối `none` và yêu cầu chữ ký hợp lệ bằng allowlist thuật toán.
2. **Triển khai đồng bộ:** xác nhận mọi resource server, gateway, worker và endpoint đều dùng chính sách mới.
3. **Kiểm tra dấu vết:** tìm request có header `alg` là `none`, signature rỗng hoặc mẫu token bất thường.
4. **Đánh giá hành động đã thực hiện:** kiểm tra tài khoản, role, tenant và thao tác nhạy cảm được ghi nhận từ các request liên quan.
5. **Thu hồi phiên/credential:** thu hồi token, refresh token hoặc phiên bị ảnh hưởng theo phạm vi điều tra.
6. **Sửa nguyên nhân:** loại bỏ decode-only, fallback không xác minh và cấu hình cho phép unsecured JWT.
7. **Thêm regression tests:** bảo đảm token `none` luôn bị từ chối ở mọi đường xác minh.
8. **Theo dõi sau khắc phục:** cảnh báo nếu có request tiếp tục gửi token không chữ ký hoặc thuật toán ngoài allowlist.

Đổi signing key đơn thuần **không khắc phục** lỗi chấp nhận `alg=none`, vì token giả mạo không cần khóa ký. Chỉ xoay vòng khóa khi có bằng chứng khóa/secret thật sự bị lộ hoặc chính sách ứng phó yêu cầu; trọng tâm vẫn là sửa verifier và thu hồi credential/phiên bị ảnh hưởng.

## 15. Lỗi triển khai thường gặp

| Lỗi | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Chỉ decode JWT để lấy claims | Không có xác minh tính toàn vẹn | Dùng verify API và chỉ tin claims sau khi verify |
| Cho phép `none` trong allowlist của access token | Token không chữ ký có thể được chấp nhận | Loại `none` khỏi allowlist |
| Tin `alg` trong header để quyết định chính sách | Attacker kiểm soát header chưa xác minh | Cấu hình allowlist ngoài token |
| Xác minh thất bại rồi thử decode-only | Tạo đường vòng qua xác minh | Từ chối hoàn toàn khi verify thất bại |
| Chỉ kiểm tra `exp` và `sub` | Claims có thể do attacker tự tạo | Xác minh chữ ký trước, rồi kiểm tra đầy đủ claims |
| Nghĩ rằng Base64URL là mã hóa | Payload dễ đọc và sửa được khi không có chữ ký | Hiểu đúng parse/encode và bảo vệ mật mã |
| Nghĩ HTTPS làm token không thể giả mạo | HTTPS không thay thế chữ ký JWT | Xác minh JWS ở resource server |
| Dùng cùng validator cho mọi loại token | Unsecured hoặc token sai profile có thể đi vào luồng khác | Tách validator theo issuer, audience và token type |
| Chỉ kiểm tra một endpoint | Endpoint khác có thể còn cấu hình yếu | Kiểm kê và kiểm thử mọi đường nhận JWT |
| Chỉ đổi signing key sau sự cố | Không ngăn verifier chấp nhận `none` | Sửa thuật toán/policy và kiểm tra trạng thái phiên |

## 16. Sơ đồ luồng xác minh an toàn

~~~mermaid
flowchart TD
    A[Nhận JWT] --> B[Parse cấu trúc, chưa tin claims]
    B --> C[Đọc alg và kid chưa xác minh]
    C --> D{alg nằm trong allowlist?}
    D -- Không --> X[Từ chối]
    D -- Có --> E{alg có phải none?}
    E -- Có --> X
    E -- Không --> F[Chọn khóa tin cậy theo issuer và chính sách]
    F --> G{Có khóa phù hợp?}
    G -- Không --> X
    G -- Có --> H[Xác minh chữ ký]
    H --> I{Chữ ký hợp lệ?}
    I -- Không --> X
    I -- Có --> J[Đọc và xác minh claims]
    J --> K[Kiểm tra iss, aud, exp, nbf, typ và policy]
    K --> L{Mọi điều kiện đạt?}
    L -- Không --> X
    L -- Có --> M[Cho phép xử lý tiếp]
~~~

Sơ đồ giả định access token là token đã ký và profile yêu cầu xác minh chữ ký. Nếu có một profile unsecured riêng biệt, nó phải được tách biệt và không được dùng để xác thực hoặc phân quyền bearer token thông thường.

## 17. Nguyên tắc cần ghi nhớ

1. `alg=none` biểu thị Unsecured JWS; không có chữ ký/MAC và không bảo đảm tính toàn vẹn.
2. Unsecured JWT có thể đúng cấu trúc compact nhưng không phải bằng chứng token được issuer xác thực.
3. Attacker có thể tự tạo payload với `sub`, role, scope hoặc audience tùy ý nếu verifier chấp nhận token không chữ ký.
4. Lỗ hổng chỉ khai thác được khi verifier hoặc ứng dụng chấp nhận `none` trong ngữ cảnh cần chữ ký.
5. Không dùng claims trước khi xác minh chữ ký thành công.
6. Allowlist thuật toán phải được cấu hình từ nguồn tin cậy, không lấy từ token.
7. Ràng buộc thuật toán với loại khóa, issuer và token profile; không fallback khi xác minh thất bại.
8. Phân biệt `alg=none` attack với algorithm confusion.
9. Kiểm thử token có signature rỗng, thuật toán ngoài allowlist và mọi nhánh fallback.
10. Khi khắc phục, sửa verifier và thu hồi credential/phiên bị ảnh hưởng; đổi khóa đơn thuần không giải quyết việc chấp nhận `none`.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token, mục 6: Unsecured JWT](https://www.rfc-editor.org/rfc/rfc7519#section-6): định nghĩa JWT không có bảo vệ mật mã.
- [RFC 7515 — JSON Web Signature, mục 6.1: Unsecured JWS](https://www.rfc-editor.org/rfc/rfc7515#section-6.1): compact serialization và chữ ký rỗng cho JWS unsecured.
- [RFC 8725 — JSON Web Token Best Current Practices, mục 3.1: Perform Algorithm Verification](https://www.rfc-editor.org/rfc/rfc8725#section-3.1): yêu cầu giới hạn và xác minh thuật toán.
- [RFC 8725 — mục 3.2: Use Appropriate Algorithms](https://www.rfc-editor.org/rfc/rfc8725#section-3.2): chọn thuật toán phù hợp với ứng dụng và ngữ cảnh.

**Kết luận:** Cuộc tấn công `alg=none` lợi dụng verifier chấp nhận một JWT không có chữ ký trong khi ứng dụng cần token được xác thực. Phòng vệ đúng là cấu hình allowlist thuật toán từ phía verifier, từ chối unsecured JWT trong luồng xác thực/phân quyền, xác minh chữ ký trước khi tin claims và kiểm thử mọi đường xử lý token.

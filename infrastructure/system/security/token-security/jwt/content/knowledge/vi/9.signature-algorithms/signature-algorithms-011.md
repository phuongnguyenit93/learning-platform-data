# `alg=none` và chính sách từ chối token không được bảo vệ trong luồng xác thực

## 1. `alg=none` là gì?

Trong JSON Web Signature (JWS), JOSE Header Parameter `alg` xác định thuật toán dùng để tạo và kiểm tra chữ ký. Giá trị **`none`** là một thuật toán JWS được tiêu chuẩn định nghĩa cho trường hợp **không có chữ ký số hoặc MAC**. JWS dùng `alg: "none"` được gọi là *Unsecured JWS*.

Ví dụ header:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

Payload vẫn được Base64URL encode trong JWS Compact thông thường, nhưng phần signature là chuỗi rỗng:

~~~text
BASE64URL(protected-header).BASE64URL(payload).
~~~

Ví dụ, một JWT không được bảo vệ có thể có dạng:

~~~text
eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiJhbGljZSIsImFkbWluIjp0cnVlfQ.
~~~

Việc header và payload được Base64URL encode **không tạo ra chữ ký, không mã hóa nội dung và không ngăn người khác sửa đổi token**. Bất kỳ ai có thể tạo request đều có thể tự tạo header, payload và một phần signature rỗng theo cấu trúc này.

RFC 7519 cho phép biểu diễn Unsecured JWT trong các trường hợp mà JWT được bảo vệ bằng một cơ chế khác. Tuy nhiên, với JWT được dùng như credential để xác thực danh tính hoặc cấp quyền qua một ranh giới không tin cậy, ứng dụng cần cơ chế bảo vệ mật mã phù hợp và phải từ chối token `alg=none`.

## 2. Vì sao `alg=none` nguy hiểm trong luồng xác thực?

JWT thường chứa các claim có ảnh hưởng trực tiếp tới danh tính và quyền:

- `sub`: chủ thể mà token đại diện.
- `iss`: issuer được khai báo.
- `aud`: đối tượng nhận dự kiến.
- `exp`, `nbf`, `iat`: các mốc thời gian.
- `scope`, `roles`, `groups` hoặc claim riêng của ứng dụng: quyền và ngữ cảnh truy cập.

Nếu ứng dụng chấp nhận một JWT không có chữ ký, người gửi có thể tự tạo hoặc thay đổi các claim này. Ví dụ, kẻ tấn công có thể tạo payload:

~~~json
{
  "iss": "https://identity.example",
  "sub": "admin-user",
  "aud": "payments-api",
  "iat": 1893450000,
  "exp": 1893453600,
  "roles": ["administrator"]
}
~~~

Khi không có chữ ký được xác minh, các giá trị trên chỉ là lời khai của người gửi. Kẻ tấn công có thể đổi `sub`, thêm quyền quản trị, kéo dài `exp` hoặc đặt `iss` và `aud` theo ý muốn. Kiểm tra cú pháp JSON hay decode được payload không chứng minh bất kỳ claim nào là thật.

### Những thuộc tính bảo mật bị mất

| Thuộc tính | Khi JWS dùng chữ ký hợp lệ | Khi JWS dùng `alg=none` |
| --- | --- | --- |
| Toàn vẹn (integrity) | Có thể phát hiện nội dung bị sửa sau khi ký | Không có bảo vệ chữ ký/MAC; nội dung có thể bị sửa |
| Xác thực nguồn (authenticity) | Có thể liên kết chữ ký với khóa/issuer tin cậy | Không chứng minh ai đã tạo token |
| Chống giả mạo claim | Dựa vào chữ ký và chính sách khóa/issuer | Người gửi có thể tự khai claim |
| Tính bí mật | JWS không cung cấp mã hóa; cần cơ chế riêng nếu cần | Cũng không có mã hóa; payload có thể đọc được |

Ngay cả khi ứng dụng kiểm tra `iss`, `aud`, `exp` hoặc `roles`, các kiểm tra đó không khôi phục được tính toàn vẹn đã mất. Kẻ tấn công có thể tự tạo lại những claim phù hợp với điều kiện kiểm tra.

## 3. Ví dụ tấn công bằng Unsecured JWT

Giả sử một API chấp nhận access token và có logic:

1. Parse JWT.
2. Đọc `alg` từ header.
3. Nếu `alg=none`, bỏ qua bước xác minh chữ ký.
4. Đọc claim `sub` và `roles` để tạo danh tính và quyền.

Kẻ tấn công không cần khóa bí mật hay khóa riêng của issuer. Họ có thể tự tạo:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

~~~json
{
  "sub": "victim",
  "aud": "admin-api",
  "roles": ["admin"],
  "exp": 1999999999
}
~~~

Sau đó ghép ba phần Compact với phần cuối rỗng. Nếu API chấp nhận token, nó có thể tạo authenticated context cho chủ thể và quyền do kẻ tấn công tự khai.

### Luồng tấn công

~~~mermaid
flowchart TD
    A["Kẻ tấn công tạo header alg=none"] --> B["Tự tạo payload với sub/roles/aud/exp"]
    B --> C["Tạo JWS có signature rỗng"]
    C --> D["Gửi token tới API"]
    D --> E["API bỏ qua xác minh chữ ký"]
    E --> F["API tin claims do người gửi tự khai"]
    F --> G["Truy cập trái phép"]
~~~

Vấn đề nằm ở chính sách chấp nhận token: một luồng xác thực đã dùng dữ liệu không được xác minh làm căn cứ xác lập danh tính và quyền.

## 4. `none` là lựa chọn được tiêu chuẩn định nghĩa, không phải chữ ký yếu

Không nên hiểu `none` là một thuật toán chữ ký có độ mạnh thấp. Nó biểu thị rằng JWS **không được ký và không có MAC**. Vì vậy, không có phép toán mật mã nào để xác minh chữ ký của token.

Một số điểm cần phân biệt:

- `alg: "none"`: Unsecured JWS, signature rỗng.
- Thiếu `alg`: header không đáp ứng yêu cầu của JWS; không được tự suy ra `none`.
- `alg: ""`, `alg: null` hoặc `alg` sai kiểu: header không hợp lệ.
- `alg` chứa giá trị không nằm trong allowlist: thuật toán không được hỗ trợ/cho phép và phải bị từ chối.
- Signature rỗng khi chính sách yêu cầu JWS có chữ ký: token không đáp ứng chính sách, kể cả khi header khai một thuật toán khác.

Tên thuật toán là giá trị phân biệt chữ hoa/chữ thường. Không tự chuyển đổi `None`, `NONE` hoặc biến thể khác thành `none`; các giá trị không được định nghĩa/cho phép phải bị từ chối như thuật toán không hỗ trợ.

### `none` chỉ áp dụng cho JWS

`none` là định danh thuật toán trong JWS. Không dùng nó như giá trị `alg` hợp lệ của JWE. JWE có hai lựa chọn riêng:

- `alg`: thuật toán quản lý hoặc thỏa thuận khóa.
- `enc`: thuật toán mã hóa nội dung.

Nếu endpoint chỉ chấp nhận JWE mà nhận một JWS `alg=none`, phải từ chối do sai định dạng/profile. Không cố gắng diễn giải token theo một loại JOSE khác để tìm cách chấp nhận.

## 5. Chính sách bắt buộc: allowlist thuật toán độc lập

Bên xác minh phải xác định trước những thuật toán mà endpoint chấp nhận. Không để header của token tự quyết định thuật toán được phép.

Ví dụ một profile access token:

~~~yaml
accessTokenVerification:
  format: JWS
  allowedAlgorithms:
    - PS256
  rejectUnsecuredJws: true
  expectedIssuer: "https://identity.example"
  expectedAudience: "payments-api"
~~~

Đây là cấu hình khái niệm, không phải schema bắt buộc của một thư viện. Trong ví dụ này:

- Chỉ `PS256` được phép.
- `none` nằm ngoài allowlist và bị từ chối.
- Thuật toán được cấu hình tại phía xác minh, độc lập với token.
- Khóa xác minh phải lấy từ nguồn tin cậy và được ràng buộc với issuer.

Một hệ thống có thể cho phép nhiều thuật toán đã được đánh giá, nhưng mỗi khóa cần được ràng buộc với đúng thuật toán và mục đích sử dụng. Không sử dụng cùng một khóa với nhiều thuật toán theo cách làm phát sinh algorithm confusion.

### Không fallback sang `none`

Không được:

- Thử xác minh bằng thuật toán được cấu hình, thất bại rồi chuyển sang `none`.
- Bỏ qua chữ ký khi không tìm thấy `kid` hoặc không tải được JWKS.
- Chấp nhận signature rỗng để tránh lỗi tương thích.
- Chọn thuật toán theo header mà không đối chiếu allowlist.
- Dùng chế độ decode-only của thư viện như thể đó là xác minh token.

Nếu không thể xác minh bằng thuật toán và khóa đã được cấu hình, token phải bị từ chối.

## 6. Quy trình từ chối Unsecured JWT trong authentication flow

Một endpoint xác thực access token nên áp dụng quy trình:

1. Chọn profile và issuer từ cấu hình tin cậy của endpoint.
2. Giới hạn kích thước token và parse đúng loại serialization.
3. Parse protected header nghiêm ngặt; từ chối JSON sai định dạng hoặc tham số trùng lặp.
4. Yêu cầu `alg` là string và thuộc allowlist.
5. Từ chối rõ ràng `alg=none` và mọi trường hợp signature rỗng khi profile yêu cầu chữ ký.
6. Chọn khóa xác minh từ JWKS/trust store đã cấu hình; kiểm tra `kid`, loại khóa, thuật toán và mục đích.
7. Xác minh chữ ký JWS bằng đúng thuật toán đã cho phép.
8. Chỉ sau khi chữ ký hợp lệ mới tin claim và kiểm tra `iss`, `aud`, `exp`, `nbf`, `typ` cùng quy tắc quyền.
9. Chỉ tạo authenticated context hoặc cấp quyền nếu tất cả điều kiện đều đạt.

~~~mermaid
flowchart TD
    A["Nhận JWT từ request"] --> B["Chọn profile tin cậy"]
    B --> C["Parse JWS header nghiêm ngặt"]
    C --> D{"alg là string hợp lệ?"}
    D -- Không --> X["Từ chối"]
    D -- Có --> E{"alg=none?"}
    E -- Có --> X
    E -- Không --> F{"alg thuộc allowlist?"}
    F -- Không --> X
    F -- Có --> G{"Signature có mặt và đúng cấu trúc?"}
    G -- Không --> X
    G -- Có --> H["Chọn khóa tin cậy theo policy"]
    H --> I["Xác minh chữ ký"]
    I --> J{"Chữ ký hợp lệ?"}
    J -- Không --> X
    J -- Có --> K["Kiểm tra issuer, audience, thời gian và claims"]
    K --> L{"Claims hợp lệ?"}
    L -- Không --> X
    L -- Có --> M["Tạo authenticated context"]
~~~

### Mã giả độc lập nền tảng

~~~text
function authenticateAccessToken(token, endpoint):
    policy = trustedPolicyFor(endpoint)
    require policy.expectedFormat == "JWS"
    require byteLength(token) <= policy.maxTokenBytes

    jws = parseJwsCompactStrictly(token)
    header = jws.protectedHeader

    require header.alg is a string
    require header.alg != "none"
    require header.alg in policy.allowedAlgorithms
    require jws.signatureSegment is not empty

    key = selectTrustedKey(
        policy.trustedIssuerKeys,
        kid = header.kid,
        algorithm = header.alg,
        purpose = "verify"
    )
    require key exists and uniquely matches policy

    claims = verifyJwsSignature(jws, key, [header.alg])
    require signatureVerificationSucceeded

    require claims.iss == policy.expectedIssuer
    require policy.expectedAudience in claims.aud
    require timeClaimsAreValid(claims)
    require tokenTypeAndAuthorizationRulesAreSatisfied(claims)

    return authenticatedContext(claims)
~~~

Đây là mã giả mô tả chính sách. Tên hàm và cấu trúc lỗi tùy thư viện; điều kiện cốt lõi là không cấp danh tính hoặc quyền trước khi xác minh chữ ký và claims thành công.

## 7. Kiểm tra chữ ký rỗng và cách parse Compact Serialization

JWS Compact luôn có ba segment được ngăn cách bởi hai dấu chấm. Với Unsecured JWS, segment signature là chuỗi rỗng, vì vậy token kết thúc bằng dấu chấm:

~~~text
protected.payload.
~~~

Parser cần phân biệt:

- Token có đúng ba segment, nhưng signature rỗng.
- Token chỉ có hai segment do bị cắt cụt hoặc parser làm mất segment cuối.
- Token có nhiều dấu chấm hoặc segment sai cấu trúc.
- Token có signature không rỗng nhưng không hợp lệ theo thuật toán.

Với profile yêu cầu JWS có chữ ký, các trường hợp trên đều không được chấp nhận nếu không thể xác minh một chữ ký hợp lệ. Không tự động bỏ qua segment rỗng cuối hoặc biến token hai segment thành một JWS hợp lệ.

Trong JWS JSON Serialization, Unsecured JWS được biểu diễn với trường `signature` là chuỗi rỗng. Profile xác thực thông thường cũng phải từ chối trường hợp này.

## 8. Khi nào Unsecured JWT có thể được dùng?

RFC 7519 định nghĩa Unsecured JWT, nhưng việc tồn tại trong tiêu chuẩn không có nghĩa mọi ứng dụng nên chấp nhận nó. Chỉ xem xét trường hợp này khi:

- Giao thức có một cơ chế bảo vệ độc lập được đặc tả rõ ràng.
- Cơ chế ngoài token cung cấp đầy đủ tính toàn vẹn và xác thực nguồn phù hợp với rủi ro.
- Token không được chấp nhận như bearer credential độc lập trong một ranh giới không tin cậy.
- Bên nhận xác minh cơ chế bảo vệ ngoài token trước khi tin payload.
- Profile, endpoint, loại token và đối tượng nhận được tách biệt rõ khỏi luồng JWT đã ký.

Ví dụ có thể là dữ liệu JWT được đóng gói trong một kênh hoặc container đã xác thực và ràng buộc mật mã bởi giao thức khác. Khi đó, chính container/giao thức ngoài phải cung cấp các thuộc tính bảo mật cần thiết; không được giả định rằng `alg=none` tự cung cấp chúng.

### Những lý do không đủ để chấp nhận `none`

- Token chỉ được gửi qua HTTPS: TLS bảo vệ một kết nối, không tự tạo chữ ký gắn với token khi token được lưu, chuyển tiếp hoặc dùng ở nhiều dịch vụ.
- Token được tạo bởi frontend đáng tin: mã chạy phía client có thể bị kiểm soát bởi người dùng hoặc môi trường của họ.
- Token có `iss` đúng: issuer là claim trong payload chưa được xác minh.
- Token có `exp` chưa hết hạn: người gửi có thể tự đặt `exp`.
- Token có `typ` là access token: `typ` cũng là header do bên gửi cung cấp.
- Token được mã hóa Base64URL: encoding không phải mã hóa hay xác thực.

Nếu hệ thống cần một token chỉ chứa dữ liệu không nhạy cảm, không dùng nó để xác thực hoặc cấp quyền. Nếu cần truyền claim có ý nghĩa bảo mật, hãy dùng cơ chế bảo vệ đã được profile xác định.

## 9. Phân tách profile để tránh nhầm lẫn token

Nếu một hệ thống thật sự cần xử lý Unsecured JWT cho một mục đích đặc biệt, phải tách profile và luồng xử lý khỏi endpoint xác thực thông thường.

Các ràng buộc nên có:

1. Endpoint riêng, không dùng chung parser/chính sách chấp nhận với access token đã ký.
2. Loại token và audience riêng; không cho token không ký được dùng tại API cần xác thực.
3. Kiểm tra cơ chế bảo vệ ngoài token trước khi diễn giải payload.
4. Không tạo authenticated principal chỉ dựa trên claim của Unsecured JWT.
5. Không cho phép token không ký đi vào luồng refresh, session, delegation hoặc authorization.
6. Không cho phép token không ký thay thế token đã ký trong quá trình fallback.
7. Có test chứng minh token từ profile đặc biệt không thể được chấp nhận bởi endpoint xác thực thông thường.

Một hệ thống không có yêu cầu và đặc tả cụ thể cho trường hợp này nên cấm `none` ở mọi luồng JWT dùng để xác thực hoặc cấp quyền.

## 10. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Cho phép `alg=none` trong access token | Người gửi tự tạo claim và quyền | Từ chối Unsecured JWS trong authentication flow |
| Tin claim sau khi chỉ decode JWT | Payload giả được dùng làm danh tính | Chỉ đọc claim như dữ liệu tin cậy sau khi xác minh chữ ký |
| Cho phép thư viện tự chọn thuật toán theo header | Token điều khiển thuật toán xác minh | Cấu hình allowlist ở phía xác minh |
| Fallback sang none khi chữ ký lỗi | Kẻ tấn công có thể bỏ qua cơ chế chữ ký | Fail closed; lỗi xác minh luôn dẫn tới từ chối |
| Bỏ qua signature rỗng hoặc segment cuối | Unsecured JWS bị xem như token hợp lệ | Kiểm tra cấu trúc và yêu cầu chữ ký không rỗng |
| Chỉ kiểm tra `iss`, `aud`, `exp` của token không ký | Attacker tự khai mọi claim | Xác minh chữ ký trước rồi mới kiểm tra claims |
| Cho rằng HTTPS thay thế chữ ký token | Token có thể bị sửa khi lưu/chuyển tiếp hoặc ngoài kênh TLS | Dùng chữ ký hoặc cơ chế bảo vệ ngoài token được đặc tả |
| Dùng cùng một endpoint cho token đã ký và không ký | Confusion giữa các profile và quyền | Tách endpoint/profile, audience và loại token |
| Coi `none` là thuật toán JWE | Nhầm ngữ nghĩa JWS và JWE | Chỉ áp dụng `none` cho Unsecured JWS; JWE có alg/enc riêng |

## 11. Bộ ca kiểm thử cho chính sách từ chối `alg=none`

Giả sử API chỉ chấp nhận access token JWS Compact, thuật toán cho phép là PS256 và khóa ký phải thuộc issuer đã cấu hình.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| JWS PS256 có chữ ký hợp lệ, issuer/audience/thời hạn đúng | **Chấp nhận** |
| JWS có `alg: "none"` và signature rỗng | **Từ chối** |
| JWS có `alg: "none"` nhưng signature không rỗng | **Từ chối** vì thuật toán ngoài allowlist/cấu trúc không phù hợp |
| Header thiếu alg | **Từ chối** |
| alg là null, number, object hoặc string rỗng | **Từ chối** |
| alg là `NONE` hoặc `None` | **Từ chối** vì không phải giá trị thuật toán được cho phép |
| alg là HS256 hoặc RS256 khi profile chỉ cho PS256 | **Từ chối** |
| alg là PS256 nhưng signature rỗng | **Từ chối** |
| Token chỉ có hai segment | **Từ chối** vì không đúng cấu trúc JWS Compact |
| Token có segment thừa hoặc dấu phân cách sai | **Từ chối** |
| Chữ ký PS256 sai hoặc được xác minh bằng khóa không tin cậy | **Từ chối** |
| Chữ ký hợp lệ nhưng sai issuer/audience hoặc hết hạn | **Từ chối** |
| Token không ký được gửi tới endpoint profile đặc biệt | **Từ chối** tại endpoint xác thực thông thường |
| Unsecured JWT được bảo vệ ngoài token theo một profile chuyên biệt | Chỉ xử lý tại endpoint riêng sau khi xác minh cơ chế bảo vệ ngoài; không cấp quyền theo claim đơn lẻ |

Nên có kiểm thử hồi quy để bảo đảm thay đổi cấu hình thư viện hoặc nâng cấp phiên bản không vô tình bật lại khả năng chấp nhận `none`.

## 12. Ghi nhớ

- `alg=none` là Unsecured JWS: không có chữ ký hoặc MAC; signature segment rỗng.
- Base64URL chỉ là encoding, không cung cấp tính toàn vẹn, xác thực nguồn hay tính bí mật.
- Không chấp nhận Unsecured JWT làm bearer credential trong luồng xác thực hoặc cấp quyền thông thường.
- Bên xác minh phải cấu hình allowlist thuật toán độc lập; không để token tự chọn thuật toán.
- Không fallback sang `none` khi chữ ký lỗi, thiếu khóa hoặc không tải được JWKS.
- Chỉ tin claim sau khi chữ ký được xác minh bằng khóa thuộc nguồn tin cậy và sau khi kiểm tra issuer, audience, thời gian, loại token.
- Trường hợp dùng Unsecured JWT chỉ có thể được cân nhắc khi một giao thức riêng cung cấp cơ chế bảo vệ ngoài token và endpoint được tách biệt rõ.

### Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS), mục 3.6 và Appendix A.5](https://www.rfc-editor.org/rfc/rfc7515): Unsecured JWS và ví dụ thuật toán none.
- [RFC 7519 — JSON Web Token (JWT), mục 6](https://www.rfc-editor.org/rfc/rfc7519): Unsecured JWT và điều kiện sử dụng.
- [RFC 8725 — JSON Web Token Best Current Practices, mục 3.2](https://www.rfc-editor.org/rfc/rfc8725): yêu cầu ứng dụng chỉ định thuật toán được phép và tránh phụ thuộc vào lựa chọn từ token.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): registry thuật toán JOSE và định danh thuật toán.

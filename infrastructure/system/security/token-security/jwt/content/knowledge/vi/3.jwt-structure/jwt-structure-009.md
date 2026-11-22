# Nhận diện token thiếu phần, thừa phần hoặc sai định dạng

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấu trúc JWT. Bài viết áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, nền tảng hay framework.

## 1. Vì sao phải nhận diện JWT sai cấu trúc?

JWT thường được truyền ở dạng Compact Serialization. Một chuỗi token có vẻ giống JWT chưa chắc là token hợp lệ: nó có thể thiếu segment, thừa dấu chấm, dùng Base64URL sai, chứa JSON không hợp lệ, khai báo thuật toán không được phép hoặc không khớp với loại token mà API chấp nhận.

Nếu parser xử lý lỏng lẻo, các thành phần trong hệ thống có thể diễn giải cùng một chuỗi theo những cách khác nhau. Điều đó tạo ra rủi ro như:

- gateway chấp nhận token nhưng resource server từ chối, hoặc ngược lại;
- parser đọc nhầm segment, bỏ qua phần dữ liệu thừa hoặc tự sửa token;
- payload bị đọc và sử dụng trước khi chữ ký được xác minh;
- token của loại JWE/JWS khác bị đưa vào luồng không hỗ trợ;
- dữ liệu đầu vào rất dài hoặc có cấu trúc bất thường làm tiêu tốn bộ nhớ và CPU;
- lỗi parser làm lộ token, claim, khóa hoặc chi tiết cấu hình qua thông báo lỗi.

Mục tiêu của việc kiểm tra cấu trúc là xác định token có đúng **serialization, số segment, encoding, cú pháp và profile** mà hệ thống hỗ trợ hay không. Đây là bước đầu của quy trình xác minh; một chuỗi đúng định dạng vẫn có thể có chữ ký sai, issuer không đáng tin, audience sai hoặc đã hết hạn.

## 2. Nhận diện số segment theo loại Compact Serialization

Dấu chấm (`.`) phân tách các thành phần trong Compact Serialization. Số segment phụ thuộc loại JOSE object:

| Loại | Cấu trúc | Số segment |
| --- | --- | ---: |
| JWS Compact Serialization | `BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)` | 3 |
| JWE Compact Serialization | `BASE64URL(protected-header).BASE64URL(encrypted-key).BASE64URL(iv).BASE64URL(ciphertext).BASE64URL(tag)` | 5 |

JWT thường được biểu diễn bằng JWS hoặc JWE Compact Serialization. Một JWT có thể được ký (JWS), mã hóa (JWE), hoặc lồng nhau (nested JWT), ví dụ một JWT đã ký được đặt bên trong JWE. Bên nhận phải biết profile mà endpoint chấp nhận để chọn đúng cách xử lý.

### 2.1. JWS compact: đúng ba segment

Ví dụ hình thức:

~~~text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0
.
eyJzdWIiOiJ1c2VyLTg0IiwiYXVkIjoib3JkZXJzLWFwaSJ9
.
c2lnbmF0dXJlLWJ5dGVz
~~~

Khi viết liền, token có dạng `header.payload.signature`. Các thành phần:

1. **Protected header:** JSON object được mã hóa Base64URL, chứa tham số JOSE như `alg`, `kid` và có thể `typ`.
2. **Payload:** với JWT, là Claims Set dạng JSON object được mã hóa Base64URL.
3. **Signature:** byte chữ ký do thuật toán JWS tạo ra, được mã hóa Base64URL.

Các lỗi về số phần:

| Chuỗi minh họa | Vấn đề |
| --- | --- |
| `header.payload` | Thiếu segment chữ ký |
| `header.payload.signature.extra` | Có bốn segment; không phải JWS compact hợp lệ |
| `.payload.signature` | Header rỗng |
| `header..signature` | Payload rỗng; không phải Claims Set JSON của JWT thông thường |
| `header.payload.` | Chữ ký rỗng; không được chấp nhận cho access token ký thông thường |

JWS cho phép một số hình thức đặc biệt như unsecured JWS với `alg` là `none` và chữ ký rỗng; JWS detached payload cũng có quy tắc riêng. Tuy nhiên, một API phát hành/nhận access token bảo mật nên **từ chối `alg=none` và không chấp nhận detached payload**, trừ khi có profile chuyên biệt đã được phê duyệt và triển khai đầy đủ. Không được coi segment rỗng là hợp lệ chỉ vì parser có thể phân tích được.

### 2.2. JWE compact: đúng năm segment

Ví dụ hình thức:

~~~text
protected-header
.
encrypted-key
.
initialization-vector
.
ciphertext
.
authentication-tag
~~~

Khi truyền thực tế, mỗi thành phần được mã hóa Base64URL và nối bằng bốn dấu chấm. Năm segment có ý nghĩa:

1. **Protected header:** tham số JWE như `alg` (thuật toán quản lý khóa) và `enc` (thuật toán mã hóa nội dung).
2. **Encrypted key:** khóa nội dung đã được bảo vệ/đóng gói theo thuật toán `alg`.
3. **Initialization vector (IV):** giá trị khởi tạo theo thuật toán `enc`.
4. **Ciphertext:** nội dung đã mã hóa.
5. **Authentication tag:** dữ liệu xác thực tính toàn vẹn theo thuật toán mã hóa được chọn.

Không áp dụng quy tắc “cả năm segment đều phải khác rỗng” một cách máy móc. Ví dụ, với một số thuật toán quản lý khóa trực tiếp như `dir` hoặc `ECDH-ES`, segment encrypted key có thể rỗng theo đặc tả. Ngược lại, header, IV, ciphertext và authentication tag phải đáp ứng yêu cầu của thuật toán/profile đang dùng.

Nếu endpoint chỉ hỗ trợ access token dạng JWS, token có năm segment phải bị từ chối như sai loại serialization; không cố phân tích nó như JWS bằng cách lấy ba segment đầu.

## 3. Kiểm tra số dấu chấm chính xác

Một cách kiểm tra ban đầu:

- JWS compact có đúng hai dấu chấm, tạo ra ba segment.
- JWE compact có đúng bốn dấu chấm, tạo ra năm segment.

Tuy nhiên, chỉ đếm dấu chấm không đủ. Phải tách segment mà **giữ nguyên cả segment rỗng**, vì việc bỏ các phần tử rỗng có thể làm sai cấu trúc. Ví dụ `header..iv.ciphertext.tag` có năm segment nhưng encrypted key rỗng; tính hợp lệ của segment đó phụ thuộc `alg`.

Không nên dùng logic như “split rồi bỏ chuỗi rỗng, sau đó kiểm tra số phần tử”. Cách này có thể biến token lỗi thành token có vẻ hợp lệ hoặc làm lệch vị trí các segment.

### 3.1. Ví dụ bảng phân loại nhanh

| Đầu vào | Số segment | Nhận định ban đầu |
| --- | ---: | --- |
| `a.b.c` | 3 | Có hình dạng JWS compact; cần kiểm tra sâu |
| `a.b.c.d.e` | 5 | Có hình dạng JWE compact; cần kiểm tra sâu |
| `a.b` | 2 | Thiếu phần |
| `a.b.c.d` | 4 | Không phải JWS/JWE compact JWT thông thường |
| `a.b.c.d.e.f` | 6 | Thừa phần |
| `a..c` | 3 | Có segment rỗng; phải kiểm tra theo vị trí và profile |
| `a.b.c.` | 4 | Có dấu chấm cuối; sai số phần với JWS |
| `.a.b` | 3 | Header rỗng |
| `a.b.c.d.` | 5 | Authentication tag rỗng; không hợp lệ với profile JWE bảo mật thông thường |

Bảng chỉ phân loại hình dạng. Các ký tự `a`, `b`, `c`... không phải Base64URL hợp lệ cho một token hoàn chỉnh; token thật còn phải qua kiểm tra encoding và mật mã.

## 4. Kiểm tra Base64URL của từng segment

JOSE sử dụng Base64URL encoding, không phải Base64 thông thường. Base64URL thay `+` bằng `-`, thay `/` bằng `_` và trong serialization JOSE bỏ dấu padding `=` ở cuối.

### 4.1. Tập ký tự hợp lệ

Với segment Base64URL không padding, các ký tự được phép là:

~~~text
A-Z
a-z
0-9
-
_
~~~

Các dấu hiệu sai định dạng thường gặp:

- có khoảng trắng, tab hoặc newline bên trong segment;
- có ký tự `+` hoặc `/` của Base64 chuẩn;
- có padding `=` trong Compact Serialization JOSE;
- có ký tự Unicode hoặc ký tự điều khiển;
- chiều dài không thể giải mã Base64URL hợp lệ;
- dữ liệu sau giải mã không thể mã hóa lại thành cùng chuỗi Base64URL canonical.

Một decoder quá dễ dãi có thể tự bỏ whitespace, chấp nhận padding hoặc thay thế ký tự sai. Để tránh khác biệt giữa các parser, nên dùng chế độ kiểm tra nghiêm ngặt theo serialization.

### 4.2. Kiểm tra canonical encoding

Một cách kiểm tra bổ sung là:

1. xác minh chuỗi chỉ chứa ký tự Base64URL được phép;
2. kiểm tra độ dài không rơi vào trường hợp không thể giải mã (ví dụ độ dài modulo 4 bằng 1);
3. giải mã bằng decoder Base64URL nghiêm ngặt;
4. mã hóa lại byte thu được theo Base64URL không padding;
5. so sánh kết quả với chuỗi đầu vào.

Nếu hai chuỗi khác nhau, đầu vào không phải biểu diễn canonical theo quy tắc mà hệ thống yêu cầu. Không được tự sửa token bằng cách thêm/bớt padding, đổi ký tự hoặc xóa whitespace rồi tiếp tục xác minh.

### 4.3. Mỗi segment có nội dung khác nhau

Không phải tất cả segment đều là JSON:

| Segment | JWS | JWE |
| --- | --- | --- |
| 1 | Protected header: JSON UTF-8 | Protected header: JSON UTF-8 |
| 2 | JWT Claims Set: JSON UTF-8 | Encrypted key: byte dữ liệu |
| 3 | Signature: byte dữ liệu | IV: byte dữ liệu |
| 4 | — | Ciphertext: byte dữ liệu |
| 5 | — | Authentication tag: byte dữ liệu |

Không cố parse signature, encrypted key, IV, ciphertext hoặc tag như JSON. Chỉ giải mã và xử lý chúng theo thuật toán JOSE tương ứng.

## 5. Kiểm tra JSON trong header và payload

Sau khi kiểm tra số segment và Base64URL:

- Với JWS, giải mã protected header và payload theo UTF-8 rồi kiểm tra JSON.
- Với JWE, chỉ có thể kiểm tra protected header trước; payload là ciphertext nên phải giải mã và xác thực thành công trước khi đọc JSON Claims Set.
- JSON header phải là object phù hợp JOSE; payload JWT phải là Claims Set JSON object.
- Từ chối JSON không hợp lệ, kiểu top-level không đúng, tên member trùng lặp theo chính sách parser và cấu trúc vượt giới hạn.

Ví dụ header hợp lệ về hình dạng:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026",
  "typ": "JWT"
}
~~~

Ví dụ payload hợp lệ về hình dạng:

~~~json
{
  "iss": "https://auth.example.net",
  "sub": "user-84",
  "aud": "https://api.example.net/orders",
  "exp": 1900000900
}
~~~

Các ví dụ này chưa chứng minh chữ ký, issuer hoặc quyền là hợp lệ. JSON parser nên từ chối member trùng lặp để tránh tình huống các thành phần đọc các giá trị khác nhau từ cùng một token.

### 5.1. Không parse payload JWE trước khi giải mã

Với JWE, payload segment là ciphertext. Không thể Base64URL decode rồi coi kết quả là Claims Set JSON. Quy trình đúng:

1. Kiểm tra cấu trúc compact và header chưa tin cậy.
2. Chọn thuật toán/khóa giải mã trong allowlist và trust configuration.
3. Xác minh authentication tag và giải mã JWE theo thư viện JOSE đã được kiểm chứng.
4. Chỉ sau khi giải mã và xác thực thành công mới parse plaintext theo quy tắc JWT.
5. Nếu plaintext là nested JWT, tiếp tục xác minh lớp JWT bên trong theo profile yêu cầu.

Không sử dụng plaintext chưa được xác thực để cấp quyền hoặc thực hiện hành động nghiệp vụ.

## 6. Phân biệt lỗi cấu trúc và lỗi xác minh

Không phải mọi lỗi token đều là “sai định dạng”. Cần phân loại để xử lý đúng:

| Lớp kiểm tra | Ví dụ lỗi | Kết luận |
| --- | --- | --- |
| Transport/extraction | Header không có Bearer token, token bị bọc dấu ngoặc kép | Không trích xuất được credential hợp lệ |
| Compact serialization | Thiếu/thừa segment, dấu chấm sai vị trí | Sai cấu trúc |
| Base64URL | Có ký tự sai, padding không được phép, chuỗi không giải mã được | Sai encoding |
| JSON | Header/payload không phải JSON object hợp lệ, member trùng lặp | Sai cú pháp/nội dung cấu trúc |
| JOSE header | Thiếu `alg`, thuật toán không hỗ trợ, `kid` không phù hợp | Không đáp ứng profile |
| Cryptographic | Chữ ký sai, tag xác thực sai, khóa không phù hợp | Không xác minh được mật mã |
| Claims/profile | `iss`, `aud`, `exp`, `typ` hoặc claim bắt buộc không đạt | Token không hợp lệ trong ngữ cảnh |
| Authorization | Scope không đủ, tenant sai, quyền bị thu hồi | Token không được phép thực hiện hành động |

Một token có thể qua bước cấu trúc nhưng thất bại ở bước chữ ký hoặc policy. Không nên trả cùng một chẩn đoán chi tiết cho client ở mọi trường hợp; thông báo bên ngoài nên đủ chung để tránh lộ thông tin giúp dò hệ thống.

## 7. Nhận diện token bị thêm tiền tố, hậu tố hoặc ký tự ngoài dự kiến

Token Compact Serialization không chứa tiền tố `Bearer `. Trong HTTP Authorization header, scheme và credential là hai thành phần riêng:

~~~http
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature
~~~

Khi nhận request, lớp HTTP phải phân tích scheme theo quy tắc giao thức và chuyển đúng credential cho JWT parser. Không đưa cả chuỗi `Bearer <token>` vào parser như thể đó là JWT.

Những trường hợp cần từ chối hoặc xử lý ở tầng transport:

- token bị bọc trong dấu ngoặc kép ngoài giao thức;
- scheme `Bearer` bị lặp;
- có hậu tố không thuộc token;
- token bị nối với dấu phẩy hoặc giá trị header khác;
- newline hoặc whitespace được chèn vào giữa các segment;
- token bị URL decode hoặc biến đổi ký tự trước khi parser nhận.

Không tự động xóa whitespace hoặc ký tự thừa bên trong credential. Nếu giao thức HTTP cho phép khoảng trắng ở ranh giới field, hãy để HTTP parser xử lý đúng quy tắc; token sau khi trích xuất phải là chuỗi compact chính xác. Không ghi lại token lỗi nguyên vẹn trong response hoặc log.

## 8. Giới hạn kích thước và chống parser abuse

Một token có thể có cấu trúc đúng nhưng quá lớn hoặc được thiết kế để tiêu tốn tài nguyên. Trước khi giải mã, nên giới hạn:

- tổng chiều dài token;
- chiều dài từng segment;
- số segment;
- kích thước sau Base64URL decode;
- độ sâu và số lượng member của JSON;
- độ dài string và số phần tử array trong Claims Set;
- thời gian xử lý và số lần refresh JWKS/metadata do header bất thường kích hoạt.

Giới hạn phải dựa trên loại token và kích thước thực tế của claim hợp lệ. Không đặt quá thấp khiến token hợp lệ bị từ chối, cũng không để payload không giới hạn làm cạn bộ nhớ.

Một số nguyên tắc:

1. Kiểm tra chiều dài trước khi cấp phát buffer giải mã.
2. Không giải mã lặp lại cùng segment nhiều lần.
3. Dùng parser streaming hoặc parser có giới hạn nếu cần xử lý payload lớn.
4. Giới hạn số lần tải lại JWKS khi gặp `kid` không biết để chống request flood.
5. Rate limit endpoint nhận token và ghi metric cho lỗi cấu trúc tăng đột biến.
6. Không đưa stack trace, raw token hoặc dữ liệu giải mã vào response lỗi.

## 9. Quy trình kiểm tra cấu trúc an toàn

~~~mermaid
flowchart TD
    A["Nhận credential từ transport"] --> B["Trích xuất đúng Bearer token"]
    B --> C["Kiểm tra chiều dài và ký tự tổng thể"]
    C --> D["Xác định profile: JWS hay JWE"]
    D --> E["Tách segment, giữ nguyên phần rỗng"]
    E --> F{"Đúng số segment?"}
    F -- "Không" --> X["Từ chối: sai compact serialization"]
    F -- "Có" --> G["Kiểm tra Base64URL từng segment"]
    G --> H{"Encoding canonical?"}
    H -- "Không" --> X
    H -- "Có" --> I["Parse protected header theo giới hạn"]
    I --> J["Kiểm tra alg, enc, typ và key policy"]
    J --> K{"JWS hay JWE?"}
    K -- "JWS" --> L["Xác minh chữ ký"]
    K -- "JWE" --> M["Giải mã và xác minh authentication tag"]
    L --> N{"Mật mã hợp lệ?"}
    M --> N
    N -- "Không" --> X
    N -- "Có" --> O["Parse Claims Set / nested JWT"]
    O --> P["Validate issuer, audience, time và profile"]
    P --> Q{"Token hợp lệ trong ngữ cảnh?"}
    Q -- "Không" --> X
    Q -- "Có" --> R["Tiếp tục authorization"]
~~~

Các bước kiểm tra header trước xác minh chỉ phục vụ chọn thuật toán/khóa ứng viên trong danh sách đã cấu hình. Không được sử dụng claim chưa xác minh để đưa ra quyết định truy cập.

## 10. Mã giả kiểm tra JWS compact

~~~text
function parseCompactJws(token, policy):
    require token is a string
    require token.length <= policy.maxTokenLength
    require token contains no whitespace or control characters

    parts = splitPreservingEmptySegments(token, ".")
    require parts.count == 3

    headerBytes = strictBase64UrlDecode(parts[0])
    payloadBytes = strictBase64UrlDecode(parts[1])
    signatureBytes = strictBase64UrlDecode(parts[2])

    require base64UrlEncodeWithoutPadding(headerBytes) == parts[0]
    require base64UrlEncodeWithoutPadding(payloadBytes) == parts[1]
    require base64UrlEncodeWithoutPadding(signatureBytes) == parts[2]

    header = parseUtf8JsonObject(headerBytes, policy.jsonLimits)
    require header.alg in policy.allowedAlgorithms
    require header.alg != "none"

    claims = parseUtf8JsonObject(payloadBytes, policy.jsonLimits)
    require noDuplicateJsonMemberNames(header, claims)

    return {
        header: header,
        claims: claims,
        signature: signatureBytes
    }
~~~

Đây mới là bước phân tích cấu trúc và chuẩn bị xác minh. Sau đó phải lấy khóa từ trust configuration, xác minh chữ ký trên đúng signing input theo JWS, rồi mới tin claims. Trong code thực tế, nên dùng thư viện JOSE đã được kiểm chứng để thực hiện toàn bộ quy trình thay vì tự ghép lại quy tắc mật mã.

## 11. Mã giả kiểm tra JWE compact

~~~text
function parseCompactJwe(token, policy):
    require token is a string
    require token.length <= policy.maxTokenLength
    require token contains no whitespace or control characters

    parts = splitPreservingEmptySegments(token, ".")
    require parts.count == 5

    protectedHeaderBytes = strictBase64UrlDecode(parts[0])
    encryptedKeyBytes = strictBase64UrlDecode(parts[1])
    ivBytes = strictBase64UrlDecode(parts[2])
    ciphertextBytes = strictBase64UrlDecode(parts[3])
    authenticationTagBytes = strictBase64UrlDecode(parts[4])

    header = parseUtf8JsonObject(
        protectedHeaderBytes,
        policy.jsonLimits
    )

    require header.alg in policy.allowedKeyManagementAlgorithms
    require header.enc in policy.allowedContentEncryptionAlgorithms
    require emptyEncryptedKeyAllowed(header.alg) or encryptedKeyBytes is not empty
    require ivBytes satisfyEncryptionProfile(header.enc)
    require authenticationTagBytes satisfyEncryptionProfile(header.enc)

    plaintext = joseDecryptAndAuthenticate(
        token,
        trustedDecryptionKeys(header.alg),
        policy
    )

    claimsOrNestedJwt = parseAccordingToJwtProfile(plaintext, header)
    return claimsOrNestedJwt
~~~

Điều kiện segment rỗng phải dựa vào thuật toán JWE cụ thể. Ví dụ `alg=dir` có encrypted key rỗng vì CEK được cung cấp trực tiếp từ khóa chia sẻ; `ECDH-ES` trực tiếp cũng có quy tắc tương ứng. Không áp dụng quy tắc đó cho mọi thuật toán.

Mã giả không thay thế việc kiểm tra kích thước, tag, IV, khóa và profile trong thư viện JOSE. Không parse plaintext hoặc thực hiện authorization nếu xác thực mã hóa thất bại.

## 12. Các ví dụ lỗi thường gặp

| Token/đầu vào minh họa | Lỗi | Xử lý |
| --- | --- | --- |
| `eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0` | JWS chỉ có hai segment | Từ chối |
| `eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0.sig.extra` | Có bốn segment | Từ chối |
| `eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0.sig=` | Padding không thuộc canonical JOSE Base64URL | Từ chối theo strict profile |
| `eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1In0+abc.sig` | Có ký tự `+` của Base64 chuẩn | Từ chối |
| `eyJhbGciOiJSUzI1NiJ9..sig` | Payload rỗng | Từ chối cho JWT Claims Set thông thường |
| `eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1In0.` | Unsecured JWS | Từ chối cho token bảo mật |
| `Bearer eyJ...` | Scheme HTTP bị đưa vào parser | Trích xuất credential ở tầng HTTP hoặc từ chối |
| `a.b.c.d.e` gửi tới endpoint chỉ nhận JWS | JWE/serialization không được endpoint hỗ trợ | Từ chối |
| `a.b.c` nhưng header không phải JSON | Protected header sai cú pháp | Từ chối |
| JWS đúng ba segment, chữ ký sai | Lỗi mật mã, không phải lỗi segment | Từ chối sau verify |

Các chuỗi rút gọn trong bảng chỉ nhằm minh họa dạng lỗi; không phải JWT có thể sử dụng thực tế.

## 13. Kiểm thử parser và xử lý lỗi

Một bộ kiểm thử nên bao gồm:

- **Số segment:** thiếu một, thừa một, nhiều dấu chấm liên tiếp, dấu chấm đầu/cuối.
- **Segment rỗng:** header/payload/signature rỗng của JWS; encrypted key rỗng trong JWE với thuật toán cho phép; tag rỗng hoặc segment bắt buộc rỗng.
- **Base64URL:** ký tự sai, padding, độ dài modulo 4 không hợp lệ, encoding không canonical.
- **JSON:** header không phải object, payload không phải Claims Set object, UTF-8 lỗi, member trùng lặp, JSON lồng quá sâu.
- **Header/profile:** thiếu `alg`/`enc`, thuật toán ngoài allowlist, `kid` lạ, token type không phù hợp.
- **Cryptographic:** chữ ký không khớp, tag xác thực sai, khóa không phù hợp, token bị sửa một byte.
- **Transport:** Bearer prefix lặp, token bị quote, whitespace ở giữa, hậu tố không hợp lệ, header quá lớn.
- **Resource exhaustion:** token quá dài, segment quá lớn, JSON có quá nhiều member, nhiều unknown `kid` gây refresh JWKS liên tục.
- **Nested JWT:** lớp ngoài hợp lệ nhưng lớp trong sai cấu trúc hoặc sai chữ ký; không chấp nhận chỉ vì lớp ngoài giải mã được.

Nên dùng fuzz testing cho parser và thư viện JOSE, đặc biệt với đầu vào có dấu chấm, byte UTF-8, Base64URL và JSON bất thường. Kiểm thử phải bảo đảm parser không crash, không treo, không đọc vượt buffer và không rò token trong lỗi.

### 13.1. Hành vi lỗi nhất quán

- Trả lỗi chung như invalid token/unauthorized theo giao thức; không phản hồi chi tiết vị trí segment sai cho client không tin cậy nếu điều đó giúp dò parser.
- Không echo token hoặc một phần payload trong response.
- Ghi reason code nội bộ (ví dụ `segment_count_invalid`, `base64url_invalid`, `signature_invalid`) nếu cần giám sát.
- Không log token nguyên vẹn, secret hoặc plaintext nhạy cảm.
- Rate limit các nguồn liên tục gửi token lỗi.
- Không tự sửa token lỗi rồi thử xác minh lại.

## 14. Checklist trước khi chấp nhận token

- [ ] Endpoint xác định rõ chỉ nhận JWS, JWE hay profile nested JWT.
- [ ] Token được trích xuất đúng từ transport; scheme không nằm trong chuỗi token.
- [ ] Tổng chiều dài và chiều dài từng segment nằm trong giới hạn.
- [ ] Số segment chính xác và được tách mà không bỏ phần rỗng.
- [ ] Base64URL đúng bảng ký tự và canonical theo profile.
- [ ] Header là JSON object hợp lệ và chỉ dùng thuật toán được phép.
- [ ] Với JWS, payload là Claims Set JSON object; chữ ký được xác minh trước khi tin claim.
- [ ] Với JWE, kiểm tra thuật toán/khóa, xác thực tag và giải mã trước khi parse plaintext.
- [ ] Segment rỗng được đánh giá theo quy tắc thuật toán, không dùng một quy tắc chung.
- [ ] Không chấp nhận `alg=none` hoặc detached payload trong access token thông thường.
- [ ] Kiểm tra issuer, audience, thời gian, token type và policy sau bước mật mã.
- [ ] Lỗi không làm lộ token, claim nhạy cảm, khóa hoặc chi tiết nội bộ.
- [ ] Có test malformed input, fuzzing, rate limit và giám sát lỗi parser.

## 15. Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Compact Serialization, signing input và Base64URL.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): năm phần của JWE Compact Serialization và xử lý encrypted key/IV/ciphertext/tag.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT Claims Set và cách biểu diễn JWT bằng JWS/JWE.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): quy tắc thuật toán JOSE, bao gồm direct key management và content encryption.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm tra thuật toán, phân biệt loại token và xử lý JWT an toàn.
- [RFC 4648 — The Base16, Base32, and Base64 Data Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL alphabet và quy tắc encoding.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): cú pháp JSON và vấn đề tên member trùng lặp.

**Ghi nhớ:** JWS compact có ba segment, JWE compact có năm segment; phải chọn đúng profile trước khi kiểm tra. Đếm segment, xác minh Base64URL và parse JSON chỉ xác nhận cấu trúc. Chỉ sau khi chữ ký hoặc authentication tag được xác minh và các claim/profile được kiểm tra, hệ thống mới được tin nội dung JWT.

# JWT không bảo vệ bí mật của payload chỉ bằng Base64url

Một JSON Web Token (JWT) thường có thể được nhìn thấy dưới dạng ba chuỗi ngăn cách bởi dấu chấm. Phần payload trông như dữ liệu đã được biến đổi, nhưng với JWT dạng JWS thông thường, nội dung chỉ được **mã hóa biểu diễn bằng Base64url**. Bất kỳ ai có token đều có thể giải mã phần này và đọc claims mà không cần khóa bí mật. Base64url giúp dữ liệu phù hợp với môi trường truyền tải dạng văn bản; nó **không phải mã hóa mật mã và không cung cấp tính bí mật**.

Bài học thuộc chương **Cấu trúc JWT** của module **Security – JSON Web Token (JWT)**. Nội dung giải thích cách Base64url xuất hiện trong cấu trúc JWT, phân biệt encoding với encryption, chỉ ra dữ liệu nào có thể đọc được trong JWS/JWE và cách thiết kế payload an toàn cho ứng dụng, API và hệ thống phân tán trên mọi nền tảng.

## 1. Vì sao payload JWT trông như đã được mã hóa?

Một JWS Compact Serialization thường có dạng:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ một token có thể trông như một chuỗi dài gồm các ký tự chữ, số, dấu gạch ngang, gạch dưới và dấu chấm. Khi nhìn bằng mắt, phần header và payload không còn giống JSON ban đầu. Điều đó dễ khiến người mới hiểu nhầm rằng dữ liệu đã được mã hóa để giữ bí mật.

Thực tế, Base64url là **mã hóa biểu diễn (encoding)**. Nó chuyển các byte thành một tập ký tự an toàn để đặt trong URL hoặc header. Người nhận chỉ cần thực hiện phép biến đổi ngược, không cần khóa:

~~~text
JSON / dữ liệu UTF-8
        |
        v
   Base64url encode
        |
        v
Chuỗi ký tự có thể truyền tải
        |
        v
   Base64url decode
        |
        v
JSON / dữ liệu UTF-8 ban đầu
~~~

Ví dụ đơn giản:

~~~text
Base64url("JWT") = "SldU"
Base64url decode("SldU") = "JWT"
~~~

Đây là phép biến đổi thuận nghịch công khai. Bất kỳ người nào có chuỗi SldU đều có thể giải mã lại thành JWT. Không có bí mật nào được bảo vệ trong ví dụ này.

## 2. Base64url thực hiện điều gì?

Base64 là cách biểu diễn dữ liệu nhị phân thành ký tự văn bản. Base64url là biến thể phù hợp với URL và một số giao thức:

- Dùng dấu gạch ngang thay cho ký tự cộng.
- Dùng dấu gạch dưới thay cho dấu gạch chéo.
- Thông thường bỏ các ký tự đệm ở cuối chuỗi trong biểu diễn Base64url của JOSE.

Các thay đổi này giúp chuỗi thuận tiện hơn khi đặt trong URL, cookie hoặc HTTP header. Chúng **không làm thay đổi bản chất bảo mật** của Base64: người nhận vẫn có thể khôi phục dữ liệu ban đầu mà không cần khóa.

### 2.1. Encoding không phải encryption

| Đặc điểm | Base64url encoding | Encryption |
| --- | --- | --- |
| Mục đích | Biểu diễn byte thành chuỗi ký tự phù hợp truyền tải | Giữ nội dung bí mật với bên không có khóa |
| Có cần khóa bí mật? | Không | Có khóa hoặc cơ chế mật mã tương ứng |
| Có thể khôi phục dữ liệu? | Có, bất kỳ ai cũng có thể decode | Chỉ bên có khóa giải mã phù hợp mới khôi phục được plaintext |
| Chống người khác đọc nội dung? | Không | Có, nếu thuật toán và quản lý khóa an toàn |
| Ví dụ | Base64url của header/payload JWS | AES-GCM trong JWE |

Một số khái niệm khác cũng không nên nhầm:

- **Encoding:** thay đổi cách biểu diễn dữ liệu; có thể đảo ngược công khai.
- **Hashing:** tạo giá trị băm; không dùng để khôi phục dữ liệu và không tự xác thực nguồn nếu không có khóa.
- **Signing/MAC:** bảo vệ toàn vẹn và xác thực nguồn trong mô hình khóa tương ứng; không tự che giấu nội dung.
- **Encryption:** biến plaintext thành ciphertext bằng cơ chế có khóa để bảo vệ bí mật.

## 3. Đọc payload của JWS không cần khóa

### 3.1. Ví dụ một JWS Compact

Giả sử issuer phát hành JWT có header và payload sau ở dạng JSON ban đầu.

Header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

Payload:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read",
  "exp": 2000000000
}
~~~

Trong JWS Compact thông thường, header được serialize thành JSON UTF-8 rồi Base64url; payload cũng được serialize và Base64url. Ba phần được ghép bằng hai dấu chấm:

~~~text
encoded_header.encoded_payload.signature
~~~

Người có token có thể:

1. Tách chuỗi theo dấu chấm.
2. Lấy phần thứ nhất và decode Base64url để đọc protected header.
3. Lấy phần thứ hai và decode Base64url để đọc payload claims.
4. Đọc được các giá trị iss, sub, aud, scope, exp mà không cần private key hoặc public key.

Phần thứ ba là chữ ký. Người nhận cần khóa công khai phù hợp để **xác minh chữ ký**, nhưng không cần khóa đó để đọc payload.

### 3.2. Chữ ký nằm ở đâu trong quá trình bảo vệ?

Với JWS Compact thông thường, chữ ký được tính trên signing input theo quy tắc JWS, về cơ bản là:

~~~text
ASCII(
    BASE64URL(protected-header)
    + "."
    + BASE64URL(payload)
)
~~~

Issuer dùng khóa ký để tạo chữ ký; resource server xác minh bằng khóa phù hợp. Nếu ai đó thay đổi payload từ invoice:read thành invoice:write nhưng không tạo được chữ ký hợp lệ mới, xác minh phải thất bại.

Điều này bảo vệ **tính toàn vẹn của dữ liệu được ký**. Nó không che giấu dữ liệu vì chính phần payload đã được biểu diễn thành chuỗi Base64url công khai.

### 3.3. Decode thành công không có nghĩa token hợp lệ

Việc decode payload chỉ giúp đọc dữ liệu. Nó không chứng minh:

- Token được phát hành bởi issuer đáng tin.
- Chữ ký hoặc MAC hợp lệ.
- Token dành cho API đang nhận request.
- Token chưa hết hạn hoặc chưa bị thu hồi.
- Chủ thể có quyền truy cập tài nguyên.
- Người đang cầm bearer token chính là chủ thể được ghi trong sub.

Không được dùng claims đọc từ payload chưa xác minh để cấp quyền, xác định danh tính hoặc thực hiện hành động nhạy cảm. Hãy xác minh token theo đúng profile trước, rồi mới sử dụng claims.

## 4. Vì sao việc để lộ payload có thể nguy hiểm?

Nếu JWS được gửi tới browser, ứng dụng di động, gateway hoặc một dịch vụ trung gian, bên có được token có thể đọc các claims. Kể cả chữ ký rất mạnh và khóa riêng được giữ trong HSM, payload JWS vẫn không được che giấu.

### 4.1. Các loại dữ liệu dễ bị đưa nhầm vào payload

| Dữ liệu | Vì sao cần thận trọng? | Hướng xử lý |
| --- | --- | --- |
| Email, số điện thoại, tên thật | Có thể tiết lộ thông tin cá nhân và hỗ trợ liên kết danh tính | Chỉ đưa khi API thực sự cần; cân nhắc định danh nội bộ hoặc tra cứu có kiểm soát |
| Địa chỉ, thông tin vị trí | Có thể tiết lộ thói quen hoặc vị trí nhạy cảm | Không đưa vào token nếu không cần cho quyết định truy cập |
| Thông tin sức khỏe hoặc tài chính | Hậu quả lộ dữ liệu cao | Giữ tại resource server; chỉ trả qua API có phân quyền |
| Dữ liệu hồ sơ/đơn hàng | Có thể bị đọc bởi mọi bên cầm token | Dùng ID tham chiếu và kiểm tra quyền trên tài nguyên |
| Quyền, role, tenant | Có thể tiết lộ cấu trúc tổ chức và chính sách | Chỉ đưa quyền cần thiết; nhớ rằng token có thể bị lộ và claims có thể cũ |
| API key, password, refresh token | Là credential hoặc bí mật có thể bị lạm dụng trực tiếp | Tuyệt đối không nhúng vào payload JWT |
| Private key, HMAC secret, encryption key | Là vật liệu mật mã có thể làm sụp đổ ranh giới tin cậy | Không đưa vào token, log, frontend hay payload |

Một claim không nhạy cảm khi đứng riêng có thể trở nên nhạy cảm khi kết hợp. Ví dụ subject ổn định, tenant, role và thời điểm phát hành có thể giúp bên thứ ba liên kết hoạt động giữa nhiều dịch vụ.

### 4.2. Token thường đi qua nhiều nơi

~~~mermaid
flowchart LR
    I["Issuer"] -->|"Phát hành JWS"| B["Browser / Mobile"]
    B -->|"Authorization header"| G["Gateway"]
    G --> A["Resource API"]
    A --> L["Log / tracing / telemetry"]
    B --> X["Extension / mã chạy phía client"]
~~~

Mỗi thành phần có thể nhìn thấy toàn bộ chuỗi token và decode payload nếu có quyền truy cập. Các điểm rò rỉ thường gặp:

- JavaScript chạy trong browser, extension hoặc công cụ debug.
- Log của reverse proxy, API gateway, backend và APM.
- Request/response capture, trace, error report hoặc ticket hỗ trợ.
- Clipboard, ảnh chụp màn hình, URL, lịch sử trình duyệt hoặc tài liệu chia sẻ.
- Repository, file cấu hình, artifact build và bản sao dữ liệu.

TLS bảo vệ đường truyền giữa các endpoint nhưng không ngăn endpoint ghi token vào log hoặc mã độc đọc token sau khi ứng dụng nhận được.

### 4.3. Không đặt token trong URL

Không truyền access token trong query string hoặc path. URL có thể xuất hiện trong:

- Browser history và bookmark.
- Log của proxy, web server và analytics.
- Header Referer trong một số luồng điều hướng tùy chính sách.
- Liên kết được sao chép hoặc chia sẻ.

Dùng header Authorization: Bearer ... theo giao thức hoặc session cookie được thiết kế đúng. Header cũng phải được che khỏi log và hệ thống quan sát.

## 5. JWE mới là cơ chế JOSE dùng để mã hóa nội dung

Nếu yêu cầu là người không có khóa giải mã không được đọc claims, JWS không đáp ứng yêu cầu đó. Trong họ JOSE, **JWE (JSON Web Encryption)** cung cấp cơ chế mã hóa nội dung.

### 5.1. Cấu trúc JWE Compact

JWE Compact Serialization thường có năm phần:

~~~text
BASE64URL(protected-header)
.
BASE64URL(encrypted-key)
.
BASE64URL(iv)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication-tag)
~~~

Các thành phần có ý nghĩa:

| Thành phần | Vai trò | Có đọc được không? |
| --- | --- | --- |
| Protected header | Chứa thuật toán quản lý khóa, thuật toán mã hóa và metadata được bảo vệ | Có thể decode và đọc |
| Encrypted key | Khóa nội dung đã được bọc/mã hóa theo thuật toán alg | Không khôi phục khóa nội dung nếu thiếu khóa/cơ chế phù hợp |
| IV / nonce | Tham số khởi tạo cho thuật toán mã hóa | Thường được công khai để giải mã |
| Ciphertext | Nội dung JWT đã mã hóa | Không đọc được plaintext nếu không có khóa |
| Authentication tag | Giá trị xác thực của chế độ mã hóa có xác thực | Được dùng để kiểm tra tính toàn vẹn |

**Protected header vẫn không phải bí mật.** Ví dụ, bên quan sát có thể biết token dùng thuật toán RSA-OAEP-256 để quản lý khóa và A256GCM để mã hóa nội dung. Không đặt thông tin bí mật vào header.

### 5.2. alg và enc có vai trò khác nhau

- **alg** chỉ định thuật toán quản lý khóa hoặc thỏa thuận khóa cho content-encryption key (CEK).
- **enc** chỉ định thuật toán mã hóa nội dung bằng CEK.

Ví dụ header:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

Đây là ví dụ minh họa một cấu hình JWE lồng nhau; thuật toán và header phải tuân theo profile mà các bên hỗ trợ. RSA-OAEP-256 liên quan tới việc bảo vệ khóa nội dung; A256GCM mã hóa payload và xác thực ciphertext/AAD.

### 5.3. JWE có che giấu toàn bộ thông tin không?

JWE bảo vệ plaintext trong ciphertext, nhưng không che mọi metadata:

- Protected header và một số tham số cần cho giải mã có thể được nhìn thấy.
- Kích thước token có thể gợi ý kích thước dữ liệu.
- Thời điểm token được gửi, địa chỉ nguồn/đích và tần suất sử dụng vẫn có thể quan sát ở các lớp khác.
- Người nhận được cấp khóa giải mã có thể đọc nội dung.
- Nếu token được giải mã rồi ghi log hoặc chuyển tiếp dưới dạng rõ, dữ liệu vẫn có thể bị lộ.

Do đó, JWE là một lớp bảo vệ dữ liệu ở tầng token, không thay thế phân quyền, TLS, bảo vệ endpoint hoặc chính sách log.

## 6. Khi cần cả bí mật và xác thực issuer

JWE với AEAD có thể bảo vệ bí mật và tính toàn vẹn của ciphertext, nhưng khả năng xác thực nguồn phát hành phụ thuộc vào cách thiết lập khóa và giao thức. Nếu bất kỳ ai cũng có thể tạo JWE hợp lệ tới người nhận, giải mã thành công không chứng minh nội dung do issuer cụ thể gửi.

Một cấu trúc có thể dùng là **Nested JWT**: ký JWT trước bằng JWS, sau đó mã hóa JWS thành JWE.

~~~mermaid
flowchart TD
    A["Claims"] --> B["Tạo JWS bằng khóa ký của issuer"]
    B --> C["Mã hóa JWS thành JWE cho người nhận"]
    C --> D["Truyền JWE"]
    D --> E["Người nhận giải mã và xác thực JWE"]
    E --> F["Lấy JWS bên trong"]
    F --> G["Xác minh chữ ký JWS bằng khóa issuer tin cậy"]
    G --> H["Kiểm tra issuer, audience, thời hạn và quyền"]
~~~

Với nested JWT ký trước rồi mã hóa:

1. Issuer tạo JWS chứa claims và ký bằng khóa riêng.
2. Issuer mã hóa toàn bộ JWS thành JWE dành cho người nhận.
3. Người nhận xác minh/giải mã JWE theo đúng thuật toán và khóa được cấu hình.
4. Người nhận xác minh chữ ký JWS bên trong bằng khóa gắn với issuer tin cậy.
5. Chỉ sau đó mới kiểm tra claims như iss, aud, exp, loại token và quyền.

Header JWE có thể dùng cty: JWT để chỉ ra nội dung là một JWT lồng nhau theo quy tắc JOSE. Không được bỏ qua xác minh JWS bên trong chỉ vì JWE bên ngoài giải mã thành công.

Nếu chỉ cần xác minh issuer và không cần giấu claims, JWS có thể đủ. Nếu cần bí mật nhưng không yêu cầu xác minh issuer độc lập, JWE có thể phù hợp theo mô hình tin cậy. Nếu cần cả hai, hãy dùng cấu trúc được chuẩn hóa và xác minh từng lớp đúng cách.

## 7. Nguyên tắc thiết kế payload JWT an toàn

### 7.1. Chỉ đưa claims phục vụ quyết định truy cập

Payload nên nhỏ và chỉ chứa dữ liệu cần thiết để resource server đưa ra quyết định trong khoảng thời gian token có hiệu lực. Ví dụ:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://billing-api.example.org",
  "scope": "invoice:read",
  "exp": 2000000000
}
~~~

Token không cần mang toàn bộ hồ sơ người dùng, địa chỉ, thông tin thanh toán hoặc nội dung hóa đơn. API có thể dùng subject/ID để tra cứu dữ liệu sau khi xác minh quyền.

### 7.2. Dùng định danh tham chiếu thay cho dữ liệu đầy đủ

Thay vì nhúng:

~~~json
{
  "customer": {
    "name": "Nguyen Van A",
    "email": "customer@example.org",
    "phone": "+84-900-000-000",
    "address": "..."
  }
}
~~~

có thể chỉ mang một định danh chủ thể hoặc tham chiếu:

~~~json
{
  "sub": "customer-42",
  "aud": "https://customer-api.example.org",
  "scope": "profile:read"
}
~~~

Resource server tra cứu hồ sơ và áp dụng quyền hiện hành. Cách này giảm dữ liệu lộ khi token bị sao chép, đồng thời tránh claims cũ sau khi hồ sơ thay đổi.

### 7.3. Không coi claim đã ký là dữ liệu luôn đúng ở hiện tại

Claims phản ánh thông tin tại thời điểm phát hành. Ví dụ:

- role=admin có thể không còn đúng sau khi quyền bị thu hồi.
- tenant_id có thể không còn được phép truy cập.
- email có thể đã thay đổi.
- scope có thể rộng hơn chính sách hiện hành.

Chữ ký bảo vệ tính toàn vẹn, không làm claims tự cập nhật. Với quyền nhạy cảm hoặc thay đổi thường xuyên, cần tra cứu trạng thái/policy hiện tại hoặc dùng token TTL ngắn và cơ chế thu hồi phù hợp.

### 7.4. Không đưa bí mật vào protected header

Header của JWS/JWE cũng có thể được decode. Các trường như alg, enc, kid, typ, cty là metadata phục vụ xử lý. Không đặt password, API key, secret, thông tin cá nhân hoặc khóa riêng trong header.

### 7.5. Giới hạn khả năng quan sát và lưu trữ token

- Che Authorization, cookie và trường token trong access log, error log, trace và telemetry.
- Không ghi token nguyên vẹn vào ticket, chat, ảnh chụp hoặc báo cáo.
- Không đưa token vào URL hoặc tham số điều hướng.
- Hạn chế quyền đọc log và đặt thời hạn lưu phù hợp.
- Không gửi token sang bên thứ ba qua analytics hoặc script không cần thiết.
- Xem xét token có bị lưu trong browser storage, clipboard, crash dump hoặc backup hay không.

## 8. Cách kiểm tra một token có để lộ dữ liệu không

Khi đánh giá thiết kế, không cần khóa riêng để xem payload JWS. Có thể thực hiện quy trình kiểm tra trên một token thử nghiệm không chứa dữ liệu production:

1. Xác định định dạng token và số phần được ngăn bằng dấu chấm.
2. Nếu là JWS Compact thông thường, decode Base64url của protected header và payload.
3. Liệt kê mọi claim và metadata có thể nhận diện người dùng, tenant, quyền hoặc dữ liệu nghiệp vụ.
4. Kiểm tra xem có credential, secret hoặc dữ liệu không cần thiết hay không.
5. Xem xét các log, trace và công cụ quan sát có lưu nguyên token hay không.
6. Nếu là JWE, xác minh người nhận và hệ thống trung gian nào có quyền giải mã; không giả định protected header được giữ bí mật.
7. Đối chiếu với yêu cầu phân quyền và chính sách lưu trữ dữ liệu.

Không sử dụng token production của người khác để thử decode hoặc chia sẻ. Việc decode không cần khóa nhưng token vẫn là credential có thể bị sử dụng để gọi API.

### 8.1. Pseudocode minh họa decode JWS

~~~text
function inspect_jws_compact(token):
    parts = split(token, ".")
    if length(parts) != 3:
        reject_as_not_standard_jws_compact

    header_bytes = base64url_decode(parts[0])
    payload_bytes = base64url_decode(parts[1])

    header = parse_json(header_bytes)
    claims = parse_json(payload_bytes)

    return {
        "header": header,
        "claims": claims,
        "signature_present": parts[2] is not empty
    }
~~~

Hàm trên chỉ **inspect nội dung** của JWS Compact theo cấu trúc thông thường. Nó không xác minh chữ ký, không kiểm tra issuer/audience/expiration và không được dùng để cấp quyền. Một token có ba phần vẫn có thể là token giả hoặc không được hệ thống chấp nhận.

## 9. Các tình huống thường gặp

### Tình huống A — Nghĩ Base64url là mã hóa

Nhóm phát triển đưa email, tenant và quyền người dùng vào payload rồi cho rằng không ai đọc được vì token trông như chuỗi ngẫu nhiên. Người dùng sao chép token và decode payload bằng một công cụ Base64url.

**Bài học:** Base64url là encoding công khai. Mọi người có token đều có thể đọc payload JWS.

### Tình huống B — Chữ ký mạnh nhưng dữ liệu vẫn bị lộ

Issuer ký JWT bằng RS256, private key được bảo vệ tốt. Token được gửi tới browser và lưu trong localStorage. XSS đọc token và giải mã payload.

**Bài học:** bảo vệ khóa ký không tạo ra confidentiality. Cần giảm claims, bảo vệ nơi lưu token và dùng JWE khi thật sự cần mã hóa.

### Tình huống C — Đưa API key vào claim

Một service nhúng API key của nhà cung cấp bên thứ ba vào payload để các service phía sau tiện sử dụng. Bất kỳ thành phần nào nhận token đều có thể decode và lấy API key.

**Bài học:** không đưa secret vào JWT. Dùng secret manager/KMS và cấp quyền truy cập bí mật trực tiếp cho workload cần dùng.

### Tình huống D — Dùng JWE nhưng lộ header

Hệ thống mã hóa payload bằng JWE và giả định toàn bộ token không tiết lộ thông tin. Người quan sát vẫn đọc protected header, thuật toán, key ID, kích thước ciphertext và metadata ngoài token.

**Bài học:** JWE che plaintext, không che toàn bộ metadata. Không đưa bí mật vào header và đánh giá khả năng suy luận từ kích thước/thời điểm.

### Tình huống E — Giải mã JWE rồi bỏ qua chữ ký bên trong

API nhận nested JWT, giải mã JWE thành công rồi sử dụng claims ngay mà không xác minh JWS bên trong. Một bên có thể tạo JWE hợp lệ tới người nhận nhưng không phải issuer được tin cậy.

**Bài học:** giải mã không thay thế xác thực nguồn phát hành. Phải xác minh JWS bên trong theo khóa issuer khi cấu trúc yêu cầu.

### Tình huống F — Token bị lộ qua log

API gateway ghi toàn bộ request header. Người có quyền đọc log sao chép bearer token, decode payload và gọi API trong thời gian token còn hiệu lực.

**Bài học:** payload có thể đọc và token còn là credential. Redact header, hạn chế quyền log, thu hồi token bị lộ và xử lý nguồn rò rỉ.

## 10. Bảng quyết định: JWS, JWE hay tra cứu dữ liệu?

| Nhu cầu | Cách tiếp cận phù hợp | Lưu ý |
| --- | --- | --- |
| API cần xác minh issuer và claims, payload không có bí mật | JWS có chữ ký phù hợp | Payload vẫn đọc được; kiểm tra issuer, audience, thời hạn và quyền |
| Nhiều API cần xác minh độc lập | JWS chữ ký bất đối xứng và JWKS tin cậy | Quản lý private key, public key, cache và rotation |
| Chỉ cần xác thực toàn vẹn giữa nhóm chia sẻ bí mật | JWS dùng MAC theo mô hình tin cậy phù hợp | Mọi bên giữ secret đều có thể tạo MAC |
| Chỉ người nhận được phép mới đọc payload | JWE với thuật toán và khóa người nhận phù hợp | Protected header và metadata khác vẫn có thể lộ |
| Cần vừa xác thực issuer vừa giữ bí mật | JWS lồng trong JWE theo profile phù hợp | Xác minh cả lớp JWE và JWS bên trong |
| Payload chứa dữ liệu hồ sơ thay đổi thường xuyên | Chỉ mang ID/tham chiếu rồi tra cứu qua API | API phải kiểm tra quyền trên dữ liệu được tra cứu |
| Không cần claims tự chứa | Opaque token hoặc session | Có thể giảm việc lộ claims và hỗ trợ thu hồi tập trung |

Đừng dùng JWE chỉ vì payload có thể decode. Trước hết hãy hỏi dữ liệu đó có cần nằm trong token không. Loại bỏ claims không cần thiết thường đơn giản hơn việc thêm lớp mã hóa và quản lý khóa giải mã cho nhiều thành phần.

## 11. Checklist trước khi phát hành JWT

### Nội dung payload

- [ ] Payload chỉ chứa claims cần thiết cho quyết định truy cập.
- [ ] Không có password, API key, private key, HMAC secret hoặc encryption key.
- [ ] Không có dữ liệu cá nhân/tài chính/sức khỏe không cần thiết.
- [ ] Đã đánh giá khả năng liên kết người dùng qua subject, tenant và metadata.
- [ ] Không giả định JWS payload được giữ bí mật.

### Cơ chế bảo vệ

- [ ] Phân biệt rõ Base64url encoding, chữ ký/MAC và encryption.
- [ ] JWS được xác minh bằng khóa tin cậy và thuật toán được cho phép.
- [ ] JWE chỉ dùng khi có yêu cầu confidentiality và người nhận được xác định rõ.
- [ ] Nếu dùng nested JWT, xác minh đầy đủ từng lớp theo đúng thứ tự.
- [ ] Không đặt bí mật trong protected header.

### Nơi lưu, truyền và quan sát

- [ ] Dùng TLS cho các kết nối.
- [ ] Không truyền token trong URL.
- [ ] Redact Authorization header, cookie và token khỏi log/trace.
- [ ] Hạn chế quyền đọc log, ticket và hệ thống telemetry.
- [ ] Đánh giá XSS, browser storage, extension, clipboard và thiết bị.
- [ ] Có quy trình xử lý khi token hoặc khóa bị lộ.

## 12. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Có thể decode payload JWS mà không có khóa không? | **Có.** Base64url là encoding công khai. |
| Base64url có bảo vệ bí mật của claims không? | **Không.** Nó chỉ thay đổi cách biểu diễn dữ liệu. |
| Chữ ký RS256 có che giấu payload không? | **Không.** Nó bảo vệ tính toàn vẹn và nguồn ký, không cung cấp confidentiality. |
| Người cầm JWS có thể đọc sub, aud và scope không? | **Có.** Nếu các claims nằm trong payload JWS thông thường. |
| Protected header của JWE có được giữ bí mật không? | **Không mặc định.** Header được bảo vệ về toàn vẹn nhưng vẫn có thể đọc. |
| JWE giải mã thành công có chứng minh issuer cụ thể đã phát hành token không? | **Không trong mọi mô hình.** Có thể cần xác minh chữ ký JWS bên trong hoặc cơ chế nguồn gốc khác. |
| TLS có ngăn browser hoặc log đọc payload JWS không? | **Không.** Các endpoint và hệ thống quan sát vẫn có thể nhìn thấy token. |
| Có nên đặt API key vào claim để service phía sau sử dụng không? | **Không.** Secret phải được quản lý riêng và chỉ cấp cho workload cần dùng. |
| Nếu payload không cần bí mật, có nhất thiết dùng JWE không? | **Không.** JWS có thể đủ nếu yêu cầu là toàn vẹn/xác thực nguồn và claims không nhạy cảm. |

## 13. Ghi nhớ

- Base64url là **encoding**, không phải encryption. Bất kỳ ai có JWS thông thường đều có thể decode header và payload.
- Chữ ký JWS bảo vệ tính toàn vẹn và xác thực nguồn theo khóa, nhưng không che giấu claims.
- Không đưa bí mật hoặc dữ liệu nhạy cảm không cần thiết vào payload hay protected header.
- JWE mã hóa payload cho người nhận phù hợp; protected header và một số metadata vẫn có thể đọc.
- Khi cần vừa giữ bí mật vừa xác thực issuer, cân nhắc nested JWS trong JWE và xác minh từng lớp đúng cách.
- TLS bảo vệ đường truyền; storage, endpoint, log, trace và thiết bị vẫn cần được bảo vệ riêng.
- Ưu tiên payload tối thiểu và tra cứu dữ liệu nhạy cảm qua API có phân quyền.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 4648 – The Base16, Base32, and Base64 Data Encodings](https://www.rfc-editor.org/rfc/rfc4648)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)

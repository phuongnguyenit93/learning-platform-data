# Payload JWT có chữ ký vẫn đọc được bởi người giữ token

## 1. Chữ ký JWT không đồng nghĩa với mã hóa

Một hiểu nhầm phổ biến khi làm việc với JSON Web Token (JWT) là cho rằng payload đã được ký thì chỉ bên phát hành hoặc bên có khóa mới đọc được. Với JWT được biểu diễn bằng **JSON Web Signature (JWS) thông thường**, điều này không đúng: header và payload được mã hóa biểu diễn bằng Base64url rồi ký để bảo vệ tính toàn vẹn và xác thực nguồn phát hành. Base64url là phép biến đổi có thể đảo ngược, không phải mã hóa bảo mật.

Vì vậy, bất kỳ ai lấy được một JWS compact JWT đều có thể tách các phần và giải mã Base64url của header, payload mà không cần khóa ký. Chữ ký giúp bên nhận phát hiện nội dung bị sửa và xác minh token theo khóa tin cậy; chữ ký không che giấu claims.

Hãy phân biệt ba thuộc tính:

- **Tính bí mật (confidentiality):** người không được phép không đọc được nội dung.
- **Tính toàn vẹn (integrity):** thay đổi nội dung có thể bị phát hiện.
- **Tính xác thực nguồn gốc (authenticity):** bên nhận có thể xác minh nội dung được tạo bởi bên giữ khóa phù hợp.

JWS cung cấp cơ chế bảo vệ tính toàn vẹn và xác thực theo khóa. Nó không tự cung cấp tính bí mật cho payload. Muốn bảo vệ nội dung JWT khỏi người không có quyền đọc, cần một cơ chế mã hóa như JSON Web Encryption (JWE), hoặc tránh đưa dữ liệu nhạy cảm vào token.

**Người giữ được signed-only JWT có thể đọc claims ngay cả khi không có khóa ký.** Vì thế, mọi dữ liệu đưa vào payload phải được xem là có thể bị lộ nếu token bị lấy khỏi nơi lưu trữ hoặc truyền tải.

Bài viết thuộc phạm vi **Security - JSON Web Token (JWT)** tổng quát, tập trung vào khả năng đọc payload, quyền riêng tư của claims và cách giảm rò rỉ dữ liệu, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Cấu trúc JWS compact và Base64url

### 2.1. Ba phần của JWS compact

Một JWT được ký theo JWS Compact Serialization thường có ba phần, ngăn cách bằng dấu chấm:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ minh họa:

~~~text
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9
.
eyJzdWIiOiJhY2NvdW50LTQyIiwiZW1haWwiOiJhbGV4QGV4YW1wbGUub3JnIn0
.
<signature-bytes-encoded-as-base64url>
~~~

Trong đó:

1. **Protected header:** metadata được bảo vệ bởi chữ ký, chẳng hạn thuật toán, loại token và key identifier.
2. **Payload:** Claims Set chứa dữ liệu của token.
3. **Signature:** giá trị chữ ký/MAC dùng để xác minh tính toàn vẹn theo khóa.

Header và payload được Base64url-encode để tạo biểu diễn an toàn cho việc truyền tải. Người nhận có thể đảo ngược phép mã hóa biểu diễn này mà không cần khóa.

### 2.2. Base64url không phải encryption

Base64url chỉ chuyển đổi byte thành các ký tự thuộc bảng chữ cái URL-safe. Nó không sử dụng khóa bí mật, không làm nội dung trở nên bí mật và không ngăn người khác khôi phục dữ liệu.

Ví dụ JSON:

~~~json
{
  "sub": "account-42",
  "email": "alex@example.org",
  "role": "admin"
}
~~~

Sau khi Base64url-encode, nội dung có thể trông khó đọc hơn nhưng vẫn có thể decode trực tiếp về JSON ban đầu. Không nên dùng Base64url, đảo chuỗi, nén hoặc đổi tên claim như một biện pháp bảo mật dữ liệu.

### 2.3. Có cần khóa để đọc payload không?

| Thao tác | Cần khóa bí mật/khóa riêng? |
| --- | --- |
| Tách ba phần JWS compact | Không |
| Base64url-decode header | Không |
| Base64url-decode payload | Không |
| Xác minh chữ ký HMAC | Cần secret HMAC |
| Xác minh chữ ký bất đối xứng | Cần public key tin cậy |
| Tạo chữ ký HMAC mới | Cần secret HMAC |
| Tạo chữ ký bất đối xứng mới | Cần private key |

Khả năng đọc payload hoàn toàn tách biệt với khả năng tạo hoặc xác minh chữ ký. Không có khóa ký vẫn có thể đọc claims; không có khóa xác minh thì không thể kết luận token có hợp lệ hay không.

## 3. Ví dụ: claims nhạy cảm bị lộ như thế nào?

Giả sử một hệ thống phát hành JWT có payload:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "account-42",
  "aud": "orders-api",
  "email": "alex@example.org",
  "name": "Alex Nguyen",
  "tenant_id": "enterprise-17",
  "roles": ["admin", "billing-manager"],
  "scope": "orders:read payments:write",
  "exp": 1893456900
}
~~~

Người có token có thể đọc được:

- Định danh subject.
- Địa chỉ email và tên hiển thị.
- Tenant mà tài khoản thuộc về.
- Vai trò và phạm vi quyền.
- API dự kiến nhận token.
- Thời điểm hết hạn.

Không cần biết secret HMAC, private key hay public key để đọc các trường trên. Nếu token bị đưa vào log, ticket hỗ trợ, URL, công cụ phân tích hoặc báo cáo lỗi, những người có quyền đọc các hệ thống đó có thể nhìn thấy claims.

### 3.1. Claims có thể tiết lộ nhiều hơn dự kiến

Thông tin nhạy cảm không chỉ là mật khẩu hoặc số thẻ thanh toán. Claims có thể tiết lộ:

| Nhóm dữ liệu | Ví dụ | Rủi ro riêng tư |
| --- | --- | --- |
| Định danh | Subject ID, employee ID, customer ID | Liên kết hoạt động giữa nhiều hệ thống |
| Thông tin liên hệ | Email, số điện thoại | Lộ dữ liệu cá nhân, spam hoặc phishing |
| Tổ chức | Tenant, phòng ban, nhóm | Tiết lộ cấu trúc nội bộ |
| Quyền | Role, permission, scope | Tiết lộ năng lực và vùng truy cập |
| Xác thực | Thời điểm đăng nhập, phương thức MFA, mức xác thực | Tiết lộ thói quen và trạng thái bảo mật |
| Nghiệp vụ | Account tier, subscription, transaction context | Tiết lộ quan hệ khách hàng hoặc hoạt động kinh doanh |
| Thiết bị/vị trí | Device identifier, IP, location claim | Theo dõi hoặc liên kết hành vi |

Ngay cả khi một claim không được xem là bí mật riêng lẻ, kết hợp nhiều claims có thể tạo ra hồ sơ nhạy cảm hơn. Hãy đánh giá toàn bộ tập claims và khả năng liên kết dữ liệu, không chỉ từng trường.

### 3.2. Subject ID opaque không đồng nghĩa ẩn danh

Một giá trị như account-42 có thể không trực tiếp cho biết tên người dùng, nhưng vẫn là định danh ổn định. Nếu nhiều dịch vụ cùng nhìn thấy giá trị này, chúng có thể liên kết các hoạt động thuộc cùng một subject.

OIDC hỗ trợ pairwise subject identifier để giảm khả năng liên kết giữa các client/sector. Tuy vậy, pairwise identifier vẫn là định danh có thể được liên kết trong phạm vi của nó; nó không tự biến dữ liệu thành ẩn danh tuyệt đối.

## 4. Chữ ký bảo vệ điều gì và không bảo vệ điều gì?

### 4.1. Chữ ký bảo vệ tính toàn vẹn

Nếu attacker sửa payload, chẳng hạn đổi:

~~~json
{
  "role": "user"
}
~~~

thành:

~~~json
{
  "role": "admin"
}
~~~

thì chữ ký JWS ban đầu không còn khớp với signing input mới. Verifier đúng cách sẽ từ chối token đã bị sửa.

Đây là lợi ích của chữ ký: nó ngăn người không có khóa phù hợp tự ý thay đổi claims mà vẫn giữ được chữ ký hợp lệ.

### 4.2. Chữ ký không che giấu nội dung

Một người có token có thể đọc payload nhưng không thể sửa payload rồi tạo chữ ký hợp lệ nếu không có khóa ký. Hai năng lực này khác nhau:

| Năng lực của người chỉ lấy được signed JWT | Có thể thực hiện? |
| --- | --- |
| Đọc header và payload | Có |
| Xem subject, scope, role hoặc email | Có, nếu các claim có trong payload |
| Thay đổi claim mà vẫn giữ chữ ký hợp lệ | Không, nếu thuật toán và khóa được xác minh đúng |
| Tạo chữ ký mới hợp lệ | Không, nếu không có khóa ký |
| Xác minh chữ ký bất đối xứng bằng public key | Có thể, nếu có public key tin cậy |

Đừng nhầm “không thể sửa token” với “không thể đọc token”. Đây là hai thuộc tính bảo mật độc lập.

### 4.3. HMAC và chữ ký bất đối xứng đều không che giấu payload

HS256, HS384, HS512 và các thuật toán chữ ký bất đối xứng như RS256, PS256 hoặc ES256 có cách tạo/xác minh chữ ký khác nhau. Nhưng với JWS compact, header và payload vẫn được Base64url-encode và có thể đọc được.

Chuyển từ HMAC sang chữ ký bất đối xứng có thể cải thiện việc phân phối quyền xác minh và giảm số nơi cần giữ bí mật có quyền ký. Nó không tạo ra tính bí mật cho claims.

## 5. Phân biệt JWS, JWE và JWT lồng nhau

JWT là định dạng biểu diễn claims. Claims có thể được bảo vệ bằng JWS, JWE hoặc cấu trúc lồng nhau theo hợp đồng của hệ thống.

| Loại | Mục đích chính | Nội dung có đọc trực tiếp được không? |
| --- | --- | --- |
| JWS signed JWT | Toàn vẹn và xác thực nguồn gốc | Có; header và payload được Base64url-encode |
| JWE encrypted JWT | Bảo mật nội dung cho bên có khóa giải mã phù hợp | Không đọc được plaintext nếu không giải mã đúng |
| Nested JWT (ký rồi mã hóa) | Kết hợp xác thực/toàn vẹn và tính bí mật | Lớp ngoài che giấu JWT đã ký; bên nhận giải mã rồi xác minh chữ ký bên trong |

### 5.1. JWS: ký nhưng không mã hóa

JWS compact có ba phần:

~~~text
protected-header.payload.signature
~~~

Payload có thể đọc trực tiếp sau khi Base64url-decode. Chữ ký giúp phát hiện thay đổi và xác minh token theo khóa.

### 5.2. JWE: mã hóa nội dung

JWE Compact Serialization có năm phần:

~~~text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
~~~

Các thành phần gồm:

1. Protected header: thông tin thuật toán quản lý khóa và thuật toán mã hóa nội dung.
2. Encrypted key: khóa mã hóa nội dung được bảo vệ theo thuật toán quản lý khóa; có thể rỗng trong một số chế độ direct.
3. Initialization vector (IV): tham số khởi tạo theo thuật toán mã hóa.
4. Ciphertext: nội dung đã mã hóa.
5. Authentication tag: giá trị xác thực tính toàn vẹn của quá trình mã hóa theo thuật toán được chọn.

Người chỉ có JWE nhưng không có khóa giải mã phù hợp không thể đọc plaintext theo thiết kế mật mã. Tuy nhiên, một số metadata vẫn hiển thị, chẳng hạn protected header có thể cho biết thuật toán, key identifier hoặc loại nội dung. Kích thước ciphertext và một số đặc điểm lưu lượng cũng có thể tiết lộ thông tin phụ.

JWE không có nghĩa mọi dữ liệu liên quan đều bí mật trước mọi bên. Các bên nhận có quyền giải mã vẫn đọc được nội dung; hệ thống vẫn cần bảo vệ khóa giải mã, endpoint và dữ liệu sau khi giải mã.

### 5.3. Nested JWT: ký rồi mã hóa

Nếu bên nhận cần cả tính toàn vẹn/xác thực nguồn gốc lẫn tính bí mật, hệ thống có thể dùng JWT lồng nhau: tạo JWS trước, sau đó mã hóa toàn bộ JWS bằng JWE.

~~~mermaid
flowchart TD
    A["Claims Set"] --> B["Tạo JWS và ký"]
    B --> C["JWS compact"]
    C --> D["Mã hóa JWS bằng JWE"]
    D --> E["Gửi JWE cho bên nhận"]
    E --> F["Bên nhận giải mã JWE"]
    F --> G["Nhận JWS bên trong"]
    G --> H["Xác minh chữ ký JWS"]
    H --> I["Kiểm tra issuer, audience, thời gian và claims"]
~~~

Trình tự xác minh phải theo đúng profile và hợp đồng. Việc giải mã lớp ngoài không thay thế xác minh chữ ký lớp trong nếu cấu trúc được thiết kế để cung cấp cả hai thuộc tính.

### 5.4. JWE không tự chứng minh danh tính issuer

JWE bảo vệ nội dung bằng mã hóa có xác thực theo khóa mã hóa. Tuy nhiên, **mã hóa cho recipient không tự động chứng minh ai đã tạo nội dung**. Chẳng hạn, khi bất kỳ bên nào cũng có thể dùng public encryption key của recipient để tạo một JWE gửi đến recipient, việc giải mã thành công không chứng minh plaintext đến từ issuer được tin cậy.

Nếu hệ thống cần cả bí mật nội dung lẫn xác thực nguồn phát hành, hãy dùng cấu trúc có chữ ký bên trong lớp mã hóa (nested signed-then-encrypted JWT) hoặc profile JOSE đã quy định rõ cách xác minh nguồn gốc. Bên nhận phải giải mã rồi xác minh chữ ký và claims theo đúng issuer, audience, thời gian và loại token.

### 5.5. Khi nào cần JWE?

Cân nhắc JWE khi:

- Claims chứa dữ liệu cần giữ bí mật trước các thành phần trung gian có thể nhìn thấy token.
- Token phải đi qua một số thành phần không được phép đọc nội dung.
- Có yêu cầu bảo mật nội dung theo hợp đồng giữa issuer và recipient.
- Các bên có thể quản lý, phân phối, luân chuyển và thu hồi khóa giải mã an toàn.

Không nên thêm JWE chỉ vì muốn token trông khó đọc. Mã hóa làm tăng yêu cầu quản lý khóa và vận hành; nó không thay thế việc giảm dữ liệu trong token hoặc bảo vệ token khỏi bị sử dụng trái phép.

## 6. Nguyên tắc data minimization cho JWT

Biện pháp tốt nhất thường là **không đưa dữ liệu không cần thiết vào payload ngay từ đầu**. Mỗi claim bổ sung làm tăng lượng thông tin có thể bị lộ và có thể khiến token dài hơn.

### 6.1. Chỉ đưa claims mà recipient thực sự cần

Trước khi thêm claim, hãy hỏi:

1. Resource server hoặc client có thực sự cần giá trị này không?
2. Có thể lấy dữ liệu từ một API có xác thực khi cần thay vì nhúng vào token không?
3. Claim có tiết lộ thông tin cá nhân, tổ chức hoặc quyền nội bộ không?
4. Giá trị có thay đổi thường xuyên khiến token nhanh lỗi thời không?
5. Có thể dùng một định danh opaque hoặc phạm vi hẹp hơn không?
6. Có thể loại bỏ claim sau khi thay đổi thiết kế mà không phá vỡ hợp đồng không?

Ví dụ, thay vì nhúng toàn bộ hồ sơ:

~~~json
{
  "sub": "account-42",
  "name": "Alex Nguyen",
  "email": "alex@example.org",
  "phone_number": "+84...",
  "address": "...",
  "date_of_birth": "...",
  "roles": ["admin", "billing-manager"]
}
~~~

có thể chỉ giữ subject và các quyền tối thiểu cần cho API:

~~~json
{
  "sub": "account-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456900
}
~~~

Đây là ví dụ khái niệm; token thực tế vẫn phải đáp ứng các claims bắt buộc theo profile đang sử dụng.

### 6.2. Dùng reference thay cho dữ liệu lớn hoặc nhạy cảm

Nếu API cần nhiều dữ liệu nghiệp vụ, token có thể mang một subject/resource reference tối thiểu. Resource server dùng định danh đó để truy vấn dữ liệu từ hệ thống có kiểm soát quyền.

Không nên nhúng:

- Hồ sơ cá nhân đầy đủ.
- Địa chỉ nhà hoặc thông tin liên hệ không cần thiết.
- Dữ liệu sức khỏe, tài chính hoặc định danh nhạy cảm.
- Mật khẩu, API key, client secret hoặc khóa mật mã.
- Danh sách quyền nội bộ quá chi tiết nếu API không cần.
- Dữ liệu lớn hoặc thay đổi thường xuyên.

Reference không tự bảo vệ dữ liệu đích. API truy vấn reference vẫn phải xác minh quyền của subject và kiểm tra quyền truy cập tài nguyên.

### 6.3. Cẩn trọng với claims quyền

Claims như role, group và permission có thể tiết lộ cấu trúc tổ chức. Ngoài vấn đề riêng tư, chúng có thể trở nên lỗi thời khi quyền bị thay đổi nhưng token vẫn còn hiệu lực.

Chỉ phát hành quyền cần thiết cho audience cụ thể, giới hạn thời hạn token và có chiến lược xử lý thu hồi/thay đổi quyền. Không đưa toàn bộ danh sách role của người dùng vào mọi token nếu API chỉ cần một scope hẹp.

## 7. Giảm rò rỉ token và payload trong hệ thống

Ngay cả khi payload không chứa dữ liệu cá nhân, bản thân access token thường là bearer credential. Người có được token có thể thử sử dụng token trong thời gian và phạm vi còn hiệu lực. Do đó cần bảo vệ cả nội dung claims lẫn giá trị token.

### 7.1. Không đưa token vào URL

Tránh truyền token trong query string hoặc fragment của URL:

~~~text
https://api.example.org/orders?access_token=<token>
~~~

URL có thể xuất hiện trong:

- Browser history và bookmark.
- Web server, reverse proxy và CDN access logs.
- Analytics và telemetry.
- Header Referer trong một số luồng điều hướng.
- Screenshot, báo cáo lỗi hoặc nội dung hỗ trợ.

Với bearer token, ưu tiên header Authorization theo cơ chế đã thỏa thuận. Nếu dùng cookie phiên, cấu hình cookie an toàn và bảo vệ CSRF phù hợp.

### 7.2. Redact Authorization và cookie trong log

Không ghi nguyên văn:

- Authorization header.
- Cookie và Set-Cookie.
- JWT access token, ID token hoặc refresh token.
- JWE ciphertext nếu việc lưu trữ nó không có mục đích rõ ràng.

Nếu cần correlation hoặc điều tra:

- Ghi request ID riêng.
- Ghi issuer, loại token và kết quả xác minh ở mức cần thiết.
- Có thể ghi một fingerprint được tạo bằng HMAC từ token bằng khóa logging riêng, nếu threat model và chính sách lưu trữ cho phép.
- Không dùng token nguyên văn làm log correlation ID.
- Giới hạn quyền truy cập log và thời gian lưu.

Không ghi toàn bộ payload chỉ để debug. Nếu cần biết một claim có tồn tại hay không, ghi trạng thái tối thiểu thay vì giá trị nhạy cảm.

### 7.3. Bảo vệ tại browser

Nếu ứng dụng đưa JWT vào môi trường trình duyệt, cần đánh giá nơi lưu và mã nào có thể đọc:

| Nơi lưu/truyền | Rủi ro chính |
| --- | --- |
| Local storage | Script cùng origin có thể đọc; XSS có thể lấy token |
| Session storage | Script cùng origin có thể đọc; phạm vi vòng đời tab không loại bỏ XSS |
| IndexedDB | Có thể bị script cùng origin truy cập |
| JavaScript memory | Giảm lưu bền vững nhưng XSS đang hoạt động vẫn có thể truy cập hoặc dùng token |
| Cookie không HttpOnly | Script có thể đọc cookie |
| Cookie HttpOnly | Script không đọc trực tiếp cookie nhưng XSS vẫn có thể gửi request thay người dùng |

Không có nơi lưu phía browser nào biến signed JWT thành dữ liệu bí mật trước script có quyền chạy trong origin. Nếu muốn giữ access/refresh token ngoài browser, có thể cân nhắc BFF và cookie phiên opaque; BFF vẫn cần bảo vệ CSRF, XSS và session.

### 7.4. Bảo vệ qua TLS và các điểm kết thúc

HTTPS/TLS bảo vệ dữ liệu trên đường truyền giữa các điểm kết thúc TLS. Nó không che giấu JWT:

- Tại browser trước khi gửi.
- Tại BFF hoặc API sau khi TLS được kết thúc.
- Trong log hoặc trace nếu ứng dụng ghi token.
- Trong bộ nhớ hoặc dump khi process đang xử lý.
- Tại reverse proxy, gateway hoặc service mesh có quyền giải mã TLS.

Giới hạn quyền đọc ở từng điểm kết thúc TLS và không giả định TLS tự bảo vệ token khỏi log hoặc truy cập nội bộ.

### 7.5. Cache, backup và công cụ quan sát

Payload và token có thể bị lưu ngoài luồng nghiệp vụ chính:

- Cache HTTP hoặc CDN.
- APM traces và distributed tracing.
- Error monitoring và crash dumps.
- Database snapshot và backup.
- Message queue hoặc dead-letter queue.
- Support ticket và file đính kèm.
- Log trình duyệt hoặc telemetry phía client.

Không đưa credential vào cache công khai. Với response chứa dữ liệu nhạy cảm, thiết lập cache-control phù hợp; kiểm tra các bản sao trong backup, log và hệ thống quan sát theo chính sách retention và xóa dữ liệu.

## 8. Audience, thời hạn và giới hạn phạm vi

Data minimization nên đi cùng các giới hạn sử dụng:

- **Audience hẹp:** token chỉ dành cho resource server cần nhận nó.
- **Scope tối thiểu:** chỉ cấp quyền cần cho công việc.
- **Thời hạn phù hợp:** giảm khoảng thời gian token bị lộ có thể được sử dụng.
- **Sender constraint:** cân nhắc DPoP hoặc mutual TLS khi cần ràng buộc token với bên giữ khóa.
- **Thu hồi:** có cơ chế xử lý token bị lộ hoặc quyền thay đổi trước hạn.
- **Không tái sử dụng token sai mục đích:** ID token, access token và refresh token có vai trò khác nhau.

Các biện pháp này chủ yếu giới hạn khả năng sử dụng token; chúng không làm payload JWS trở nên bí mật. Một token có audience hẹp vẫn có thể bị đọc bởi người lấy được token.

## 9. Nếu cần bảo mật payload: dùng JWE đúng cách

### 9.1. Chọn đúng recipient

JWE mã hóa plaintext cho bên nhận có khóa giải mã phù hợp. Trước khi triển khai, cần xác định:

- Ai được phép giải mã?
- Khóa công khai hoặc khóa quản lý nội dung được phân phối thế nào?
- Ai có quyền giữ private/decryption key?
- Làm sao luân chuyển, thu hồi và xử lý khóa bị lộ?
- Có bao nhiêu recipient cần đọc nội dung?
- Các thành phần trung gian nào chỉ được phép chuyển tiếp ciphertext?

Không mã hóa cho một khóa mà nhiều thành phần không cần thiết cùng giữ. Càng nhiều nơi có khả năng giải mã, phạm vi dữ liệu có thể bị lộ càng lớn.

### 9.2. Thuật toán và cấu hình

JWE có hai lớp thuật toán:

- **Key management algorithm (alg):** cách tạo, chia sẻ hoặc bảo vệ Content Encryption Key (CEK).
- **Content encryption algorithm (enc):** thuật toán mã hóa nội dung bằng CEK.

Verifier/decryptor phải dùng allowlist thuật toán được cấu hình theo profile và từ chối thuật toán không hỗ trợ hoặc không được phép. Không để protected header do token cung cấp tự mở rộng chính sách thuật toán.

Các thuật toán cần được chọn theo JOSE profile, thư viện đã được đánh giá và yêu cầu tương tác giữa các bên. Không tự thiết kế thuật toán mã hóa hoặc tái sử dụng nonce/IV trái quy tắc của thuật toán.

### 9.3. Mã hóa không thay thế giảm dữ liệu

JWE giảm khả năng đọc plaintext đối với bên không có khóa giải mã, nhưng:

- Recipient hợp lệ vẫn có thể đọc mọi claims bên trong.
- Khóa giải mã bị lộ làm lộ các token tương ứng.
- Token vẫn là credential có thể bị sử dụng nếu bị đánh cắp và hệ thống chấp nhận nó.
- Metadata header và kích thước ciphertext vẫn có thể quan sát.
- Dữ liệu sau khi giải mã có thể bị log hoặc lưu sai cách.

Vì vậy, vẫn cần data minimization, audience hẹp, thời hạn phù hợp, bảo vệ token và quản lý khóa.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| JWT có chữ ký thì payload bí mật | JWS signed-only chỉ bảo vệ toàn vẹn/xác thực, payload có thể decode |
| Base64url là mã hóa | Base64url là encoding có thể đảo ngược |
| Không có signing key thì không đọc được JWT | Khóa không cần thiết để decode header/payload của JWS |
| HS512 che giấu payload tốt hơn HS256 | Kích thước MAC không tạo confidentiality |
| Chuyển từ HMAC sang RSA/ECDSA làm claims bí mật | Thuật toán chữ ký không mã hóa payload |
| HTTPS bảo vệ JWT ở mọi nơi | TLS bảo vệ đường truyền, không che payload tại endpoint/log |
| Claim không có tên thật thì vô hại | Subject ID ổn định vẫn có thể liên kết hoạt động |
| exp làm token tự biến mất khỏi log | exp chỉ giới hạn thời điểm chấp nhận, không xóa các bản sao |
| JWE làm mọi metadata bí mật | Protected header và một số đặc điểm lưu lượng vẫn có thể lộ |
| Chỉ cần mã hóa, không cần giảm claims | Recipient giải mã vẫn thấy toàn bộ plaintext |
| HttpOnly ngăn mọi tác động của XSS | Script vẫn có thể gửi request cùng phiên dù không đọc cookie |
| Token chỉ ở log nội bộ thì không sao | Log, trace, backup và ticket đều là nơi cần kiểm soát truy cập |

## 11. Checklist bảo vệ dữ liệu trong JWT

### Thiết kế claims

- [ ] Chỉ phát hành claims mà recipient thực sự cần.
- [ ] Không đưa mật khẩu, secret, khóa hoặc dữ liệu xác thực bí mật vào payload.
- [ ] Đánh giá rủi ro riêng tư khi kết hợp subject, tenant, role và profile claims.
- [ ] Dùng định danh phù hợp; cân nhắc pairwise subject nếu cần giảm liên kết giữa client.
- [ ] Không nhúng hồ sơ lớn hoặc dữ liệu thay đổi thường xuyên.
- [ ] Dùng reference và truy vấn có kiểm soát quyền khi phù hợp.

### Chọn JWS/JWE

- [ ] Hiểu rõ JWS ký nhưng không mã hóa payload.
- [ ] Chỉ dùng JWE khi có yêu cầu confidentiality và recipient rõ ràng.
- [ ] Nếu cần cả chữ ký và mã hóa, dùng cấu trúc nested JWT theo profile đã thống nhất.
- [ ] Có allowlist thuật toán và quản lý khóa ký/giải mã riêng.
- [ ] Không giả định JWE che giấu mọi metadata hoặc ngăn token bị sử dụng.

### Truyền tải và lưu trữ

- [ ] Dùng HTTPS/TLS.
- [ ] Không đưa token vào URL, query string hoặc fragment.
- [ ] Redact Authorization, Cookie và Set-Cookie trong log.
- [ ] Không gửi token/payload nhạy cảm vào analytics, APM hoặc error reporting.
- [ ] Kiểm soát cache, backup, queue và crash dump.
- [ ] Bảo vệ token ở browser; cân nhắc BFF khi muốn giữ access/refresh token phía server.

### Giới hạn sử dụng và vận hành

- [ ] Audience và scope được giới hạn theo nhu cầu.
- [ ] Thời hạn token phù hợp với rủi ro.
- [ ] Có quy trình thu hồi và xử lý token bị lộ.
- [ ] Có quản lý khóa và luân chuyển khóa.
- [ ] Resource server xác minh chữ ký, issuer, audience, thời gian và quyền.
- [ ] Có quy trình xử lý yêu cầu truy cập/xóa dữ liệu trong log và backup theo chính sách.

## 12. Kết luận

Payload của JWT được ký theo JWS thông thường vẫn đọc được bởi bất kỳ ai có token. Base64url chỉ là encoding; chữ ký bảo vệ tính toàn vẹn và xác thực nguồn gốc, không cung cấp confidentiality. Vì vậy, không nên đưa dữ liệu nhạy cảm hoặc claims không cần thiết vào signed JWT với giả định người dùng không thể đọc chúng.

Nếu cần giữ bí mật payload trước các thành phần không được phép đọc, có thể dùng JWE hoặc nested JWT để kết hợp mã hóa với chữ ký theo profile phù hợp. Tuy nhiên, recipient vẫn đọc được plaintext, metadata nhất định vẫn có thể lộ và khóa giải mã phải được quản lý an toàn.

Phòng vệ hiệu quả bắt đầu từ data minimization, audience/scope hẹp, thời hạn phù hợp, bảo vệ token trên đường truyền và tại mọi điểm lưu trữ, đồng thời redaction log và telemetry. **Đừng đặt bí mật vào payload JWS chỉ vì JWT có chữ ký.**

## Tài liệu chuẩn để đọc tiếp

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT có thể được bảo vệ bằng JWS hoặc JWE.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS, signing input và chữ ký.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): mã hóa nội dung JOSE và JWE Compact Serialization.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán ký, quản lý khóa và mã hóa nội dung.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành bảo mật JWT, kiểm tra loại token và claims.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): claims ID token và pairwise subject identifier.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh ghi credential và dữ liệu nhạy cảm vào log.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): bảo vệ token và API.

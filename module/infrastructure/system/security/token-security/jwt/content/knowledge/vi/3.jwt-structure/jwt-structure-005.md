# Giải mã để xem dữ liệu và xác minh để thiết lập tin cậy

## 1. Hai thao tác có mục đích hoàn toàn khác nhau

Khi nhận được một **JSON Web Token (JWT)**, hệ thống thường cần đọc thông tin bên trong và quyết định có tin thông tin đó hay không. Đây là hai công việc riêng biệt:

- **Giải mã/parse (decode/parse):** chuyển các segment Base64url thành byte, đọc JSON hoặc nội dung tương ứng để biết token đang mang dữ liệu gì.
- **Xác minh và kiểm tra (verify/validate):** kiểm tra bằng chứng mật mã, nguồn phát hành, đối tượng nhận, thời hạn và các điều kiện của giao thức để quyết định có chấp nhận token hay không.

Một công cụ có thể hiển thị header và payload rất dễ dàng. Điều đó chỉ chứng minh rằng dữ liệu có thể được giải mã theo định dạng; nó **không chứng minh token được phát hành bởi một bên đáng tin cậy, chưa bị sửa đổi hoặc còn hiệu lực**.

Ví dụ, người nhận có thể decode payload sau mà không cần khóa:

~~~json
{
  "sub": "customer-42",
  "role": "admin",
  "exp": 1893456300
}
~~~

Nhưng kẻ tấn công cũng có thể tự tạo một JSON tương tự, encode Base64url và ghép thành một chuỗi có hình thức JWT. Nếu ứng dụng chỉ đọc trường role rồi cấp quyền, kẻ tấn công có thể tự nhận mình là admin. Chỉ sau khi xác minh cơ chế bảo vệ và kiểm tra các claim theo chính sách, ứng dụng mới được phép sử dụng những dữ liệu này làm cơ sở ra quyết định.

**Quy tắc cần nhớ:** decode giúp *nhìn thấy dữ liệu*; verify giúp *kiểm tra bằng chứng mật mã*; validate giúp *đánh giá token có được chấp nhận trong ngữ cảnh hiện tại hay không*.

## 2. Decode JWT thực hiện điều gì?

### Với JWS Compact

JWS Compact có ba segment:

~~~text
protectedHeader.payload.signature
~~~

Segment header và payload được Base64url decode để lấy byte. Với JWT thông thường, các byte đó là UTF-8 JSON:

~~~text
headerBytes  = BASE64URL_DECODE(headerPart)
payloadBytes = BASE64URL_DECODE(payloadPart)

headerJson  = UTF8_DECODE(headerBytes)
payloadJson = UTF8_DECODE(payloadBytes)
~~~

Kết quả có thể cho biết thuật toán được khai báo, loại token, subject, audience, thời hạn và các claim ứng dụng. Nhưng **signature chưa được kiểm tra**. Bất kỳ ai có token đều có thể thực hiện thao tác decode hai phần đầu.

### Với JWE Compact

JWE Compact có năm segment:

~~~text
protectedHeader.encryptedKey.iv.ciphertext.authenticationTag
~~~

Protected Header vẫn có thể Base64url decode để xem metadata. Tuy nhiên, payload là ciphertext. Base64url decode segment ciphertext chỉ thu được **byte đã mã hóa**, không khôi phục được JSON claims.

Để đọc plaintext JWE cần:

1. Chọn khóa nhận phù hợp từ nguồn khóa tin cậy.
2. Khôi phục hoặc dẫn xuất CEK theo thuật toán quản lý khóa alg.
3. Giải mã có xác thực bằng enc, IV, ciphertext, authentication tag và AAD.
4. Chỉ khi xác thực tag thành công mới sử dụng plaintext.
5. Decode plaintext theo UTF-8 và parse JSON nếu nội dung là JWT Claims Set.

Vì vậy, từ “decode JWT” đôi khi được dùng không chính xác để chỉ cả quá trình giải mã JWE. Cần nói rõ đang **Base64url decode**, **giải mã mật mã**, hay **xác minh chữ ký/tag**.

## 3. Vì sao dữ liệu sau khi decode vẫn chưa đáng tin?

JWT là dữ liệu do bên gửi cung cấp. Trước khi hoàn tất xác minh, mọi nội dung lấy từ token đều có thể bị giả mạo hoặc thay đổi.

Kẻ tấn công có thể:

- Thay sub để giả danh một chủ thể khác.
- Thay role hoặc scope để tự nâng quyền.
- Kéo dài exp hoặc thay nbf để tác động đến thời gian hiệu lực.
- Thay iss để giả nhà phát hành.
- Thay aud để khiến token có vẻ được cấp cho một dịch vụ khác.
- Thay alg, kid hoặc metadata header để thử khai thác cách chọn thuật toán và khóa không an toàn.
- Sao chép một token hợp lệ bị đánh cắp và phát lại trước khi nó hết hạn.

Với JWS, việc thay header hoặc payload làm thay đổi signing input, nên chữ ký cũ sẽ không còn xác minh được khi dùng đúng thuật toán và khóa. Nhưng điều này chỉ có ý nghĩa nếu ứng dụng **thực sự xác minh chữ ký** và từ chối khi xác minh thất bại.

Một chuỗi có đủ ba segment, header có typ là JWT, hoặc payload chứa iss của một nhà cung cấp nổi tiếng đều không phải bằng chứng về độ tin cậy. Những giá trị đó chỉ là nội dung token tự khai báo.

## 4. Bốn khái niệm cần phân biệt

| Khái niệm | Câu hỏi được trả lời | Ví dụ thao tác |
| --- | --- | --- |
| **Decode** | Dữ liệu được biểu diễn thành gì? | Base64url decode segment và đọc JSON |
| **Verify** | Bằng chứng mật mã có hợp lệ với khóa và thuật toán được chấp nhận không? | Xác minh JWS signature hoặc JWE authentication tag |
| **Validate** | Token có đáp ứng điều kiện của giao thức và ngữ cảnh sử dụng không? | Kiểm tra issuer, audience, thời hạn, loại token và claim bắt buộc |
| **Authorize** | Chủ thể đã được xác thực có được phép thực hiện hành động cụ thể không? | Kiểm tra quyền đọc đơn hàng trong chính sách truy cập |

Các bước này có liên hệ nhưng không thay thế nhau:

- Decode không xác minh được token.
- Verify thành công không tự động chứng minh token phù hợp với dịch vụ đang nhận.
- Validate thành công không có nghĩa chủ thể được phép thực hiện mọi hành động.
- Authorization phải dựa trên danh tính và quyền đã được xác lập theo chính sách đáng tin cậy.

Trong thực tế, các thư viện có thể gộp verify và validate vào một hàm gọi chung. Dù API được đặt tên là verify, validate hay authenticate, người triển khai vẫn cần hiểu những điều kiện nào thật sự được kiểm tra và điều kiện nào phải tự cấu hình.

## 5. Quy trình xác minh JWS an toàn

Với JWT dạng JWS Compact, bên nhận cần xác minh chữ ký trên **nguyên văn signing input**:

~~~text
signingInput = ASCII(
    receivedHeaderPart + "." + receivedPayloadPart
)

VERIFY(
    algorithmAllowedByPolicy,
    trustedVerificationKey,
    signingInput,
    receivedSignature
)
~~~

Một quy trình tổng quát:

~~~mermaid
flowchart TD
    A["Nhận JWT Compact"] --> B["Giới hạn kích thước và kiểm tra 3 segment"]
    B --> C["Đọc header để lấy metadata (chưa tin cậy)"]
    C --> D["Đối chiếu thuật toán và loại token với chính sách"]
    D --> E["Chọn khóa xác minh từ nguồn tin cậy"]
    E --> F["Xác minh signature trên hai segment gốc"]
    F --> G{"Signature hợp lệ?"}
    G -- "Không" --> X["Từ chối token"]
    G -- "Có" --> H["Parse payload và kiểm tra claims"]
    H --> I{"Issuer, audience, thời gian và claim hợp lệ?"}
    I -- "Không" --> X
    I -- "Có" --> J["Xác lập danh tính theo ngữ cảnh"]
    J --> K["Kiểm tra quyền cho hành động"]
~~~

### Bước 1 — Kiểm tra cấu trúc và giới hạn đầu vào

- Đảm bảo token có đúng ba segment theo loại JWS Compact được chấp nhận.
- Kiểm tra Base64url, kích thước token, kích thước header và giới hạn xử lý.
- Từ chối segment sai định dạng, dữ liệu JSON lỗi hoặc các trường hợp không được giao thức cho phép.

Không nên parse dữ liệu không giới hạn trước khi kiểm tra kích thước; token lớn hoặc cấu trúc JSON quá sâu có thể gây tiêu tốn bộ nhớ và CPU.

### Bước 2 — Đọc header như dữ liệu chưa đáng tin

Bên nhận có thể decode protected header để biết alg, kid, typ và các tham số khác. Tuy nhiên, các giá trị này chưa được xác minh.

Ứng dụng phải có chính sách thuật toán đã cấu hình trước. Không cho token tùy ý quyết định thuật toán được dùng. Chẳng hạn, nếu một endpoint chỉ chấp nhận RS256, token yêu cầu HS256 phải bị từ chối thay vì tự động chuyển sang HMAC.

### Bước 3 — Chọn khóa từ nguồn tin cậy

Khóa xác minh phải gắn với nhà phát hành và mục đích sử dụng đã được cấu hình. kid chỉ là gợi ý tìm khóa trong tập khóa hợp lệ; không được coi là khóa hoặc nguồn khóa.

Nếu sử dụng JWKS, endpoint lấy JWKS phải được cấu hình tin cậy theo issuer hoặc cấu hình của ứng dụng. Không tải khóa từ một URL tùy ý được lấy trực tiếp từ token. Cần kiểm tra loại khóa, thuật toán, use/key_ops nếu có và trạng thái khóa.

### Bước 4 — Xác minh signature

Dùng đúng thuật toán được phép, đúng khóa và nguyên văn headerPart.payloadPart. Nếu signature không hợp lệ, thiếu khóa, thuật toán không được hỗ trợ hoặc dữ liệu không đúng định dạng, phải từ chối.

Không parse JSON rồi serialize lại để tái tạo signing input. JWS xác minh trên byte của hai segment Compact gốc cùng dấu chấm phân cách.

### Bước 5 — Kiểm tra claims và chính sách

Signature hợp lệ chỉ cho biết dữ liệu đã được bảo vệ bằng khóa tương ứng. Ứng dụng vẫn phải kiểm tra issuer, audience, thời hạn, loại token và các claim bắt buộc. Những bước này được trình bày chi tiết ở phần tiếp theo.

## 6. Kiểm tra các claim quan trọng

Sau khi xác minh JWS thành công, bên nhận mới có thể sử dụng payload làm dữ liệu đã được ràng buộc với khóa ký. Tuy nhiên, mỗi claim vẫn cần được đánh giá theo ngữ cảnh.

| Claim | Cần kiểm tra điều gì? | Ví dụ |
| --- | --- | --- |
| iss | Nhà phát hành có nằm trong danh sách được tin cậy không? | Chỉ chấp nhận https://identity.example |
| aud | Token có dành cho đúng dịch vụ đang nhận không? | API đơn hàng phải nằm trong audience |
| exp | Token đã hết hạn chưa? | Từ chối khi thời gian hiện tại đã vượt exp |
| nbf | Token đã đến thời điểm bắt đầu hiệu lực chưa? | Từ chối nếu hiện tại còn trước nbf |
| iat | Thời điểm phát hành có hợp lý theo chính sách không? | Từ chối token phát hành trong tương lai bất thường |
| sub | Chủ thể có hợp lệ và được nhận diện theo quy ước issuer không? | Mã khách hàng phải tồn tại hoặc có định dạng phù hợp |
| jti | Có cần kiểm tra trùng lặp, thu hồi hoặc phát lại không? | Tra cứu trạng thái token nếu giao thức có cơ chế đó |
| scope, role | Quyền có hợp lệ và phù hợp với hành động không? | orders:read chỉ cho phép đọc đơn hàng |

### Issuer và khóa phải được liên kết

Không chỉ so sánh chuỗi iss. Hệ thống phải đảm bảo khóa dùng để xác minh thực sự thuộc về issuer đã được cấu hình tin cậy. Nếu token ghi iss là một nhà cung cấp nhưng được xác minh bằng khóa của một nhà phát hành khác, cần từ chối.

### Audience phải được kiểm tra chính xác

aud có thể là chuỗi hoặc mảng chuỗi. Dịch vụ nhận cần xác minh định danh của chính nó xuất hiện trong audience theo quy tắc JWT. Không nên chấp nhận một token chỉ vì chữ ký hợp lệ nếu token được cấp cho một API khác.

### Thời gian và clock skew

exp, nbf và iat là các giá trị NumericDate tính theo giây từ Unix epoch. Có thể cho phép dung sai đồng hồ nhỏ (clock skew) nếu chính sách quy định rõ, nhưng không nên mở rộng quá mức thời hạn token.

- exp: token không được chấp nhận sau thời điểm hết hạn.
- nbf: token không được chấp nhận trước thời điểm bắt đầu hiệu lực.
- iat: hỗ trợ kiểm tra tuổi token hoặc thời điểm phát hành bất hợp lý; bản thân claim này không thay thế exp.

Không phải mọi JWT đều bắt buộc có tất cả các claim. Ứng dụng phải xác định rõ claim nào bắt buộc cho loại token và giao thức đang xử lý.

## 7. Xác minh JWE khác gì xác minh JWS?

JWE Compact có năm segment. Bên nhận cần giải mã có xác thực để lấy plaintext:

1. Đọc protected header như dữ liệu chưa đáng tin.
2. Kiểm tra cặp alg và enc có được cho phép.
3. Chọn khóa nhận từ nguồn tin cậy.
4. Khôi phục hoặc dẫn xuất CEK.
5. Giải mã có xác thực bằng IV, ciphertext, tag và AAD.
6. Chỉ khi tag hợp lệ mới xử lý plaintext.
7. Parse JWT Claims Set và kiểm tra claim theo chính sách.

~~~mermaid
flowchart TD
    A["Nhận JWE Compact"] --> B["Kiểm tra 5 segment và giới hạn"]
    B --> C["Đọc protected header (chưa tin cậy)"]
    C --> D["Kiểm tra alg, enc và chính sách khóa"]
    D --> E["Chọn khóa nhận tin cậy, khôi phục CEK"]
    E --> F["Giải mã có xác thực với IV, ciphertext, tag và AAD"]
    F --> G{"Authentication tag hợp lệ?"}
    G -- "Không" --> X["Từ chối, không sử dụng plaintext"]
    G -- "Có" --> H["Parse plaintext theo UTF-8/định dạng nội dung"]
    H --> I["Kiểm tra claims và chính sách"]
~~~

### Giải mã JWE thành công có xác minh nhà phát hành không?

Không nhất thiết. Với JWE dùng khóa công khai của bên nhận, bất kỳ ai có khóa công khai đó đều có thể tạo một JWE mới gửi đến bên nhận. Authentication tag chứng minh nội dung không bị thay đổi mà không có khóa mã hóa tương ứng; nó không tự chứng minh ai đã tạo token.

Nếu ứng dụng cần cả **bí mật nội dung** và **xác thực nhà phát hành**, có thể dùng JWT lồng nhau: ký JWT bằng JWS rồi mã hóa JWS thành JWE. Bên nhận giải mã JWE trước, sau đó xác minh chữ ký JWS bên trong và kiểm tra claims.

## 8. Các lỗi bảo mật thường gặp

### Chỉ decode rồi tin payload

Đây là lỗi trực tiếp nhất. Kẻ tấn công có thể tự tạo payload với role là admin hoặc thay sub. Ứng dụng phải xác minh cơ chế bảo vệ trước khi sử dụng claims.

### Chấp nhận thuật toán theo ý token

Header là dữ liệu do người gửi kiểm soát trước khi xác minh. Cần cấu hình allowlist thuật toán, loại khóa và mục đích khóa. Không chấp nhận alg là none trong luồng xác thực bearer token thông thường; chỉ một giao thức chuyên biệt có quy định rõ và biện pháp thay thế mới có thể cân nhắc dạng không chữ ký.

### Chọn khóa từ nguồn không tin cậy

Không lấy URL hoặc đường dẫn từ header để tải khóa tùy ý. kid chỉ được tra cứu trong bộ khóa đã được liên kết với issuer và cấu hình tin cậy. Cần tránh lỗi cache JWKS, tra cứu không giới hạn hoặc cho phép kid điều khiển truy vấn nguy hiểm.

### Chỉ xác minh signature mà bỏ qua claims

Một token ký hợp lệ vẫn có thể hết hạn, sai audience, sai issuer, không đúng loại token hoặc không đủ quyền. Xác minh mật mã là điều kiện cần, không phải điều kiện duy nhất để chấp nhận.

### Dùng một loại token cho nhiều ngữ cảnh

Một hệ thống có thể phát hành access token, ID token, token đổi mật khẩu hoặc token xác minh email. Nếu cùng chấp nhận chúng mà không phân biệt loại, có thể xảy ra *token substitution* hoặc *cross-JWT confusion*. Cần kiểm tra typ, issuer, audience, claim bắt buộc và quy tắc riêng cho từng loại token; có thể dùng khóa hoặc audience tách biệt khi phù hợp.

### Nhầm xác minh với chống phát lại

Signature hợp lệ không ngăn người khác sao chép và phát lại bearer token. jti chỉ có tác dụng chống phát lại khi có cơ chế theo dõi trạng thái tương ứng. Có thể cần thời hạn ngắn, thu hồi, ràng buộc token với người sở hữu hoặc cơ chế phiên tùy yêu cầu.

## 9. Ví dụ: một payload giả mạo và cách xử lý đúng

Giả sử API đơn hàng nhận token có payload:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456300
}
~~~

Một người có thể decode token và sửa payload thành:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "aud": "orders-api",
  "scope": "orders:write",
  "exp": 1999999999
}
~~~

Sau khi sửa, họ Base64url encode lại payload và ghép token. Token mới vẫn có thể trông đúng định dạng ba phần; header và payload đều đọc được. Nhưng signature ban đầu được tạo trên signing input cũ, nên xác minh bằng khóa tin cậy sẽ thất bại.

Nếu API bỏ qua bước verify và chỉ đọc scope, kẻ tấn công có thể được cấp quyền ghi đơn hàng. Nếu API xác minh signature trước, token giả mạo bị từ chối trước khi quyền được đánh giá.

Một token có chữ ký hợp lệ vẫn phải bị từ chối nếu aud không phải orders-api, iss không được tin cậy hoặc exp đã qua. Chỉ khi tất cả điều kiện xác minh và kiểm tra ngữ cảnh thành công, API mới tiếp tục kiểm tra quyền orders:read cho thao tác đọc.

## 10. Quy trình quyết định chấp nhận token

Có thể mô tả quyết định chấp nhận bằng các điều kiện nối tiếp:

~~~text
ACCEPT_TOKEN =
    valid_compact_structure
    AND allowed_token_type
    AND allowed_algorithm
    AND trusted_key
    AND valid_cryptographic_protection
    AND trusted_issuer
    AND expected_audience
    AND valid_time_window
    AND required_claims_valid
    AND application_policy_satisfied
~~~

Nếu bất kỳ điều kiện bắt buộc nào thất bại, token phải bị từ chối. Sau khi token được chấp nhận, hành động cụ thể vẫn cần qua kiểm tra authorization:

~~~text
ALLOW_ACTION =
    ACCEPT_TOKEN
    AND subject_is_allowed
    AND required_permission_present
    AND resource_policy_satisfied
~~~

Đây là mô hình khái niệm; mỗi giao thức và loại JWT có thể quy định thêm điều kiện riêng. Không nên chỉ dựa trên một hàm kiểm tra chung nếu nó không thực hiện đủ các kiểm tra mà ứng dụng cần.

## 11. Checklist khi nhận JWT

- Xác định endpoint đang chấp nhận loại token nào: JWS, JWE hay JWT lồng nhau.
- Kiểm tra kích thước, số segment và định dạng Compact.
- Chỉ cho phép thuật toán và kiểu khóa đã được cấu hình.
- Lấy khóa từ nguồn tin cậy gắn với issuer; xử lý kid như gợi ý tra cứu.
- Xác minh signature JWS trên nguyên văn signing input hoặc giải mã JWE với tag hợp lệ.
- Không sử dụng plaintext JWE trước khi authentication tag được xác minh.
- Kiểm tra iss, aud, exp, nbf, iat và claim bắt buộc theo chính sách.
- Phân biệt access token với ID token và các token có mục đích khác.
- Chỉ dùng scope/role sau khi token đã được xác minh và quyền được đối chiếu với chính sách.
- Có biện pháp phù hợp cho thu hồi, phát lại, lưu trữ và truyền bearer token.
- Không ghi nguyên token hoặc bí mật khóa vào log.
- Từ chối token sai định dạng, sai thuật toán, sai khóa, chữ ký/tag không hợp lệ hoặc claim không đạt yêu cầu.

**Ghi nhớ:** Decode chỉ mở biểu diễn dữ liệu; nó không thiết lập niềm tin. Với JWS, cần xác minh chữ ký trên đúng chuỗi segment gốc. Với JWE, cần giải mã có xác thực và chỉ sử dụng plaintext sau khi tag hợp lệ. Sau đó vẫn phải kiểm tra issuer, audience, thời gian, loại token và claim theo ngữ cảnh; cuối cùng mới quyết định quyền cho hành động cụ thể.

### Tài liệu chuẩn để tra cứu

- **RFC 7515 — JSON Web Signature (JWS):** cấu trúc JWS, signing input và xác minh chữ ký.
- **RFC 7516 — JSON Web Encryption (JWE):** giải mã có xác thực, protected header và AAD.
- **RFC 7519 — JSON Web Token (JWT):** claims, issuer, audience và thời gian.
- **RFC 8725 — JSON Web Token Best Current Practices:** kiểm tra thuật toán, issuer/audience, loại token và các rủi ro triển khai.
- **RFC 7517 — JSON Web Key (JWK):** biểu diễn khóa và JWKS dùng để phân phối khóa công khai.

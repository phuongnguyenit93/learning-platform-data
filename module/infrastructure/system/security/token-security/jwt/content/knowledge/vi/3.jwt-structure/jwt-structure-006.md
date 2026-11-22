# Dữ liệu được ký và ý nghĩa của chuỗi byte gốc

## 1. Chữ ký JWS bảo vệ dữ liệu nào?

Trong JWT dạng **JWS Compact**, chữ ký được tính trên một chuỗi byte được gọi là **JWS Signing Input**. Đây là điểm quan trọng để hiểu vì sao hai JSON có cùng ý nghĩa vẫn có thể tạo ra chữ ký khác nhau.

Một JWS Compact có ba phần:

Trong các sơ đồ dưới đây, xuống dòng chỉ giúp dễ quan sát; token Compact thực tế được truyền như một chuỗi liền mạch.

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Signing Input được định nghĩa theo dạng:

~~~text
signingInput = ASCII(
    BASE64URL(UTF8(protectedHeaderJSON))
    + "."
    + BASE64URL(payloadBytes)
)
~~~

Với JWT thông thường, payload là JWT Claims Set được biểu diễn bằng JSON UTF-8. Công thức trên cho thấy JWS ký **chuỗi Base64url của protected header, dấu chấm phân cách và chuỗi Base64url của payload**.

JWS không ký một đối tượng JSON trừu tượng sau khi parser đã đọc nó. JWS cũng không lấy toàn bộ chuỗi Compact bao gồm segment signature để làm đầu vào chữ ký. Segment signature được tạo từ Signing Input và được nối vào cuối token sau khi phép ký hoàn tất.

**Ý nghĩa thực tế:** chỉ cần thay đổi một byte làm thay đổi header segment hoặc payload segment thì Signing Input thay đổi. Chữ ký cũ sẽ không còn xác minh được với Signing Input mới, trừ trường hợp giả mạo thành công đối với thuật toán mật mã đang dùng.

## 2. Từ JSON đến Signing Input: các lớp dữ liệu

Có thể hình dung quá trình phát hành JWT/JWS qua các lớp sau:

~~~mermaid
flowchart TD
    A["Header JSON và Claims JSON"] --> B["Serialize thành JSON text"]
    B --> C["Encode thành UTF-8 bytes"]
    C --> D["Base64url không padding"]
    D --> E["headerSegment . payloadSegment"]
    E --> F["ASCII bytes = JWS Signing Input"]
    F --> G["Ký/MAC bằng thuật toán và khóa"]
    G --> H["Signature bytes"]
    H --> I["Base64url(signature)"]
    I --> J["Ghép JWS Compact 3 phần"]
~~~

Mỗi lớp có một vai trò riêng:

| Lớp | Dữ liệu | Vai trò |
| --- | --- | --- |
| JSON text | Văn bản thể hiện header hoặc claims | Mô tả cấu trúc và giá trị |
| UTF-8 bytes | Byte của JSON text | Biểu diễn văn bản thành dữ liệu nhị phân |
| Base64url segment | Ký tự đại diện cho byte | Đưa dữ liệu vào chuỗi Compact |
| Signing Input | ASCII của hai segment và dấu chấm giữa chúng | Đầu vào chính xác của thuật toán ký/MAC |
| Signature | Byte kết quả của thuật toán | Bằng chứng mật mã được đưa vào segment thứ ba |

Không được nhầm **byte JSON ban đầu** với **byte Signing Input**. JSON UTF-8 được Base64url encode trước; thuật toán JWS nhận byte ASCII của chuỗi segment đã encode và dấu chấm phân cách.

## 3. Ví dụ: JSON giống nghĩa nhưng chuỗi byte khác

Xét hai cách serialize cùng một object:

~~~json
{"sub":"customer-42","role":"reader"}
~~~

~~~json
{ "sub": "customer-42", "role": "reader" }
~~~

Sau khi parse, cả hai đều có thể tạo ra cùng một object với hai thuộc tính sub và role. Nhưng JSON text thứ hai có thêm khoảng trắng, vì vậy chuỗi UTF-8 bytes khác chuỗi thứ nhất.

Tương tự, đổi thứ tự thuộc tính:

~~~json
{"sub":"customer-42","role":"reader"}
~~~

~~~json
{"role":"reader","sub":"customer-42"}
~~~

Ý nghĩa dữ liệu có thể giống nhau, nhưng byte sequence khác nhau. Do đó:

1. JSON text khác nhau.
2. UTF-8 bytes khác nhau.
3. Base64url payload segment khác nhau.
4. JWS Signing Input khác nhau.
5. Signature được tạo cho đầu vào cũ không xác minh được trên đầu vào mới.

### Một số thay đổi nhỏ vẫn làm thay đổi byte

| Thay đổi | Ví dụ | Vì sao chữ ký thay đổi? |
| --- | --- | --- |
| Khoảng trắng | {"sub":"u1"} và { "sub":"u1" } | Byte JSON khác |
| Thứ tự thuộc tính | {"a":1,"b":2} và {"b":2,"a":1} | Thứ tự byte khác |
| Escape Unicode | {"name":"ế"} và {"name":"\u1ebf"} | Ký tự trực tiếp và chuỗi escape có byte khác |
| Unicode normalization | Ký tự dựng sẵn và chuỗi ký tự gốc kết hợp dấu | Code point sequence có thể khác |
| Cách viết số | 1, 1.0, 1e0 | Văn bản số khác |
| Escape ký tự | \n và \u000a | Cách biểu diễn JSON khác |
| Thay giá trị | reader thành admin | Nội dung payload khác |

JWS không tự động bỏ khoảng trắng, sắp xếp key, chuẩn hóa Unicode hay chuẩn hóa cách viết số trước khi xác minh. Nếu ứng dụng muốn tạo JSON theo một quy tắc thống nhất, quy tắc đó cần được áp dụng **trước khi ký** và phải thống nhất giữa các bên tạo dữ liệu. Khi nhận token, bên xác minh vẫn dùng nguyên segment gốc.

## 4. Chuỗi byte gốc là gì và vì sao cần giữ nguyên?

Trong ngữ cảnh JWS Compact, **chuỗi byte gốc** là byte sequence được hình thành từ hai segment Compact đầu tiên và dấu chấm phân cách theo đúng thứ tự:

~~~text
receivedHeaderSegment
+
ASCII(".")
+
receivedPayloadSegment
~~~

Cụ thể, Signing Input là:

~~~text
ASCII(receivedHeaderSegment + "." + receivedPayloadSegment)
~~~

Ví dụ token nhận được:

~~~text
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
.
eyJzdWIiOiJjdXN0b21lci00MiJ9
.
<signature-segment>
~~~

Dù bên nhận có thể decode hai segment đầu để đọc JSON, khi xác minh phải dùng chính hai segment **đã nhận**, không tạo lại segment từ JSON object đã parse.

### Cách xử lý sai

~~~text
received token
    |
    v
Base64url decode
    |
    v
Parse JSON objects
    |
    v
Serialize lại JSON (có thể đổi whitespace/order/escape)
    |
    v
Base64url encode mới
    |
    v
Verify chữ ký cũ trên Signing Input mới  <-- sai
~~~

### Cách xử lý đúng

~~~text
received token
    |
    v
Tách đúng ba segment, giữ nguyên chuỗi gốc
    |
    v
Tạo Signing Input từ headerSegment + "." + payloadSegment
    |
    v
Verify signature bằng khóa và thuật toán được phép
    |
    v
Nếu hợp lệ, parse payload để kiểm tra claims
~~~

Đọc JSON trước khi xác minh có thể hữu ích để lấy metadata phục vụ chọn khóa hoặc kiểm tra cấu trúc, nhưng mọi giá trị đọc được vẫn phải được xem là **chưa đáng tin** cho đến khi xác minh hoàn tất. Việc parse trước không được làm thay đổi chuỗi gốc dùng để xác minh.

## 5. Dấu chấm phân cách cũng là một byte được ký

Một lỗi dễ mắc là nghĩ thuật toán chỉ ký hai segment ghép liền nhau. Thực tế, dấu chấm ASCII **.** ở giữa là một phần của Signing Input.

~~~text
Signing Input = headerSegment + "." + payloadSegment
                                      ^
                                      |
                             byte 0x2E (ASCII ".")
~~~

Nếu bỏ dấu chấm, thay bằng ký tự khác hoặc thêm dấu phân cách, byte sequence thay đổi và chữ ký không còn hợp lệ.

Cũng cần phân biệt:

- Dấu chấm giữa header và payload **có nằm trong Signing Input**.
- Dấu chấm giữa payload và signature **không nằm trong Signing Input**.
- Segment signature không được đưa ngược vào Signing Input để tự xác minh chính nó.

## 6. Signature là byte kết quả, không phải dữ liệu JSON

Sau khi tạo Signing Input, thuật toán được khai báo và cho phép sẽ tạo ra byte signature hoặc MAC. Các byte này sau đó được Base64url encode thành segment thứ ba.

~~~text
signingInput = ASCII(headerSegment + "." + payloadSegment)

signatureBytes = SIGN_OR_MAC(
    algorithm,
    signingKey,
    signingInput
)

signatureSegment = BASE64URL(signatureBytes)

jwsCompact =
    headerSegment + "." +
    payloadSegment + "." +
    signatureSegment
~~~

Một số ví dụ về cơ chế ký:

| Thuật toán | Cơ chế | Khóa tạo chữ ký/MAC | Khóa xác minh |
| --- | --- | --- | --- |
| **HS256** | HMAC với SHA-256 | Khóa bí mật dùng chung | Cùng khóa bí mật |
| **RS256** | RSA PKCS#1 v1.5 với SHA-256 | Khóa riêng tư | Khóa công khai tương ứng |
| **PS256** | RSA-PSS với SHA-256 | Khóa riêng tư | Khóa công khai tương ứng |
| **ES256** | ECDSA P-256 với SHA-256 | Khóa riêng tư | Khóa công khai tương ứng |
| **EdDSA** | Chữ ký Edwards-curve | Khóa riêng tư | Khóa công khai tương ứng |

Đừng nhầm HMAC với chữ ký số bất đối xứng. Với HS256, bên xác minh phải có cùng khóa bí mật, vì vậy bên nào có thể xác minh cũng có khả năng tạo MAC mới. Với RS256, ES256 hoặc EdDSA, bên xác minh có thể chỉ giữ khóa công khai, còn khả năng ký thuộc về bên giữ khóa riêng tư.

Xác minh thành công cho biết chữ ký/MAC phù hợp với khóa đã dùng. Việc gắn khóa đó với một issuer đáng tin cậy là bước cấu hình và kiểm tra riêng; chữ ký không tự chứng minh mọi phát biểu trong claims là sự thật.

## 7. Vì sao không nên canonicalize token nhận được trước khi verify?

**Canonicalization** là quá trình chuyển nhiều cách biểu diễn có thể tương đương về một dạng chuẩn duy nhất. Một số giao thức hoặc định dạng dữ liệu có thể yêu cầu canonicalization, nhưng JWS Compact thông thường không yêu cầu bên nhận canonicalize JSON rồi mới xác minh.

Ví dụ, một bên nhận token có thể:

- Sắp xếp các thuộc tính theo alphabet.
- Xóa khoảng trắng.
- Chuyển ký tự Unicode thành escape.
- Chuẩn hóa Unicode NFC.
- Chuyển cách viết số 1.0 thành 1.

Nếu làm những việc này trước khi xác minh, bên nhận tạo ra segment mới khác segment đã được ký. Signature hợp lệ trên token gốc sẽ không khớp với Signing Input mới.

**JSON Canonicalization Scheme (JCS, RFC 8785)** có thể được một giao thức ứng dụng sử dụng khi các bên cùng thỏa thuận ký dữ liệu canonical theo JCS. Điều đó không biến JCS thành bước mặc định của JWT/JWS. Với JWS Compact đã nhận, hãy xác minh trên chuỗi gốc theo đặc tả JWS.

Nếu ứng dụng cần chuẩn hóa định danh, ví dụ tên tài khoản Unicode, nên xác định chính sách chuẩn hóa tại thời điểm nhập hoặc tạo dữ liệu trước khi phát hành token. Khi đã tạo token, không sửa đổi các byte được ký.

## 8. JSON được xác minh về byte nhưng vẫn cần kiểm tra về ý nghĩa

Chữ ký hợp lệ chứng minh rằng byte Signing Input khớp với chữ ký tạo bởi khóa tương ứng. Nó không đảm bảo dữ liệu sau parse có ý nghĩa đúng cho mọi ứng dụng.

Sau khi verify thành công, ứng dụng vẫn cần:

- Parse JSON bằng bộ phân tích tuân thủ định dạng.
- Kiểm tra kiểu dữ liệu của từng claim.
- Từ chối hoặc xử lý thống nhất tên thuộc tính trùng lặp.
- Kiểm tra claim bắt buộc, miền giá trị và độ dài dữ liệu.
- Kiểm tra iss, aud, exp, nbf và các điều kiện của giao thức.
- Áp dụng chính sách quyền cho hành động cụ thể.

Ví dụ, một token có signature hợp lệ vẫn có thể chứa aud không dành cho API đang nhận hoặc exp đã hết hạn. Signature hợp lệ không biến những claim đó thành điều kiện được chấp nhận.

### Tên thuộc tính trùng lặp

JSON sau có hai thuộc tính cùng tên:

~~~json
{
  "sub": "customer-42",
  "sub": "administrator"
}
~~~

Các parser khác nhau có thể xử lý trường hợp trùng tên theo cách khác nhau nếu ứng dụng không có chính sách rõ. Một số parser giữ giá trị đầu tiên, một số giữ giá trị cuối cùng, hoặc có thể báo lỗi. Điều này tạo ra rủi ro khi thành phần xác minh, thành phần ghi log và thành phần phân quyền diễn giải cùng payload khác nhau.

Nên sử dụng parser có hành vi xác định và từ chối tên claim trùng lặp theo chính sách của ứng dụng. Việc signature hợp lệ không loại bỏ rủi ro diễn giải JSON không nhất quán.

## 9. JWE cũng dựa trên byte gốc, nhưng vai trò khác JWS

Bài này tập trung vào dữ liệu được ký trong JWS. Với JWE Compact, protected header cũng được Base64url encode và được dùng làm **Additional Authenticated Data (AAD)**:

~~~text
AAD = ASCII(protectedHeaderSegment)
~~~

Bên nhận phải dùng đúng header segment gốc khi xác thực authentication tag. Không parse JSON header rồi serialize lại để tạo AAD mới.

Tuy nhiên, JWE không dùng Signing Input ba phần như JWS. JWE sử dụng CEK, IV, ciphertext, tag và AAD theo thuật toán mã hóa có xác thực. Khi nhận JWE, cần xác thực tag và giải mã thành công trước khi dùng plaintext.

| Đặc điểm | JWS Compact | JWE Compact |
| --- | --- | --- |
| Dữ liệu mật mã gắn với header | Header segment nằm trong Signing Input | Header segment được dùng làm AAD |
| Dữ liệu nội dung | Payload segment được Base64url encode | Plaintext được mã hóa thành ciphertext |
| Bằng chứng | Signature hoặc MAC | Authentication Tag |
| Phần cần giữ nguyên | Header segment, dấu chấm, payload segment | Protected Header segment để tạo AAD và các byte/segment liên quan theo thuật toán |
| Mục tiêu chính | Toàn vẹn và xác thực theo khóa | Bí mật và toàn vẹn của dữ liệu mã hóa |

## 10. Ví dụ: thay đổi whitespace làm signature không còn phù hợp

Giả sử dịch vụ phát hành token từ payload JSON sau:

~~~json
{"sub":"customer-42","scope":"orders:read"}
~~~

Bên phát hành serialize JSON thành UTF-8, Base64url encode thành payload segment rồi ký Signing Input. Token được gửi đến API.

Một middleware nhận token, decode payload, parse JSON và serialize lại thành:

~~~json
{
  "sub": "customer-42",
  "scope": "orders:read"
}
~~~

Dữ liệu sau parse có cùng ý nghĩa, nhưng JSON text và payload segment mới khác dữ liệu gốc. Nếu middleware dùng segment mới để xác minh signature cũ, phép xác minh thất bại. Nếu middleware tạo lại một token mới, nó phải có quyền ký và khóa hợp lệ; việc tự ý tái tạo token chỉ bằng cách encode lại payload không thể bảo toàn chữ ký cũ.

Thiết kế đúng là giữ nguyên token gốc trong suốt bước xác minh. Sau khi chữ ký hợp lệ, hệ thống có thể parse payload thành object để kiểm tra claim và xử lý nghiệp vụ. Nếu cần phát hành một token mới với serialization khác, bên phát hành phải tạo chữ ký mới bằng khóa được phép.

## 11. Quy trình thực hành khi tạo và xác minh JWS

### Khi phát hành token

1. Xác định các claim cần thiết, kiểu dữ liệu, issuer, audience và thời hạn.
2. Tạo header và claims JSON theo một serialization xác định của bên phát hành.
3. Encode JSON text thành UTF-8 bytes.
4. Base64url encode header và payload, không padding theo JOSE Compact.
5. Ghép đúng headerSegment.payloadSegment.
6. Chuyển chuỗi đó thành ASCII bytes làm Signing Input.
7. Ký/MAC bằng thuật toán được phép và khóa phù hợp.
8. Base64url encode signature bytes và ghép thành token ba phần.

### Khi nhận token

1. Giới hạn kích thước và kiểm tra cấu trúc ba segment.
2. Giữ nguyên chuỗi headerSegment và payloadSegment.
3. Đọc header ở chế độ chưa tin cậy để đối chiếu thuật toán và chọn khóa từ nguồn tin cậy.
4. Tạo Signing Input từ hai segment gốc cùng dấu chấm ASCII.
5. Xác minh signature với thuật toán và khóa được cấu hình.
6. Nếu thất bại, từ chối token và không dùng claims.
7. Nếu thành công, parse payload JSON và kiểm tra claim, thời hạn, issuer, audience.
8. Sau cùng, áp dụng authorization cho hành động và tài nguyên cụ thể.

~~~mermaid
sequenceDiagram
    participant Issuer as Bên phát hành
    participant API as Bên nhận
    Issuer->>Issuer: Serialize JSON thành UTF-8 bytes
    Issuer->>Issuer: Base64url(header) và Base64url(payload)
    Issuer->>Issuer: Ghép Signing Input với dấu chấm
    Issuer->>Issuer: Ký/MAC Signing Input
    Issuer-->>API: Gửi JWS Compact
    API->>API: Giữ nguyên 2 segment gốc
    API->>API: Tạo lại Signing Input từ segment gốc
    API->>API: Xác minh signature với khóa tin cậy
    API->>API: Parse JSON và kiểm tra claims
    API->>API: Áp dụng chính sách quyền
~~~

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ rằng JWS ký JSON object sau khi parse | Serialize khác có thể tạo dữ liệu không đúng signing input | Ký và xác minh trên Signing Input theo JWS |
| Bỏ dấu chấm giữa header và payload | Signing Input không còn đúng | Giữ đúng dấu chấm ASCII |
| Đưa segment signature vào Signing Input | Xác minh trên dữ liệu sai | Chỉ dùng header segment, dấu chấm và payload segment |
| Parse rồi serialize lại trước khi verify | Thay đổi byte và làm signature không khớp | Giữ nguyên segment gốc |
| Canonicalize JSON theo ý bên nhận | Thay đổi serialization không được hai bên thỏa thuận | Chỉ canonicalize nếu giao thức yêu cầu rõ; vẫn tuân thủ JWS |
| Chỉ kiểm tra signature mà bỏ qua claim | Token có thể sai issuer, audience hoặc hết hạn | Verify xong phải validate claims |
| Dùng cùng parser nhưng không xử lý duplicate names | Các thành phần có thể hiểu payload khác nhau | Từ chối tên trùng lặp hoặc quy định hành vi parser rõ ràng |
| Nhầm byte JSON với Signing Input | Tính chữ ký trên byte sai | Phân biệt UTF-8 JSON bytes, Base64url segments và ASCII Signing Input |

## 13. Tự kiểm tra kiến thức

1. JWS Signing Input được tạo từ những thành phần nào và theo đúng thứ tự nào?
2. Vì sao JWS không ký trực tiếp JSON object đã parse?
3. Dấu chấm giữa protected header và payload có vai trò gì trong Signing Input?
4. Segment signature có được đưa vào Signing Input không? Vì sao?
5. Hai JSON có cùng dữ liệu nhưng khác khoảng trắng có thể tạo ra chữ ký khác không?
6. Vì sao không được serialize lại payload trước khi xác minh?
7. JCS có phải bước mặc định khi xác minh JWT/JWS không?
8. Chữ ký hợp lệ có chứng minh aud dành cho đúng API không?
9. Vì sao tên claim trùng lặp có thể tạo rủi ro dù signature hợp lệ?
10. JWE sử dụng protected header segment trong AAD như thế nào?

**Ghi nhớ:** JWS xác minh trên **chuỗi byte Signing Input** được tạo từ header segment, dấu chấm ASCII và payload segment nguyên bản. JSON có thể giống nghĩa nhưng khác byte do khoảng trắng, thứ tự thuộc tính, escape, Unicode hoặc cách viết số; vì thế chữ ký có thể khác. Bên nhận phải giữ nguyên segment gốc khi verify, rồi mới parse JSON và kiểm tra claims, issuer, audience, thời gian cùng quyền truy cập.

### Tài liệu chuẩn để tra cứu

- **RFC 7515 — JSON Web Signature (JWS):** định nghĩa Signing Input, Compact Serialization và quy trình xác minh.
- **RFC 7519 — JSON Web Token (JWT):** JWT Claims Set, registered claims và cách JWT sử dụng JWS/JWE.
- **RFC 8259 — JSON Data Interchange Format:** cú pháp JSON, Unicode, UTF-8 và cách biểu diễn văn bản.
- **RFC 8785 — JSON Canonicalization Scheme (JCS):** quy tắc canonicalization JSON khi một giao thức có yêu cầu cụ thể.
- **RFC 8725 — JSON Web Token Best Current Practices:** khuyến nghị xác minh JWT và tránh cách diễn giải không nhất quán.

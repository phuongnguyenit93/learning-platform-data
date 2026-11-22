# Phạm vi chấp nhận biểu diễn theo hợp đồng của từng ứng dụng

## 1. Vì sao phải quy định rõ biểu diễn JOSE được chấp nhận?

**JOSE (JSON Object Signing and Encryption)** là nhóm đặc tả dùng để biểu diễn và bảo vệ dữ liệu bằng chữ ký, MAC hoặc mã hóa. Trong nhóm này có JWS (JSON Web Signature), JWE (JSON Web Encryption), JWK (JSON Web Key) và JWA (JSON Web Algorithms). JWT (JSON Web Token) là định dạng mang claims, thường được bảo vệ bằng JWS hoặc JWE.

Một chuỗi có hình thức giống JWT chưa đủ để xác định ứng dụng phải chấp nhận nó. Các chuẩn JOSE định nghĩa nhiều cách biểu diễn và nhiều cơ chế bảo vệ. Mỗi ứng dụng cần có **hợp đồng token** quy định chính xác:

- Ứng dụng nhận loại token nào: JWT ký bằng JWS, JWT mã hóa bằng JWE, JWT lồng nhau hay một loại JOSE object khác.
- Dạng serialization nào được phép.
- Thuật toán, loại khóa, issuer và audience nào được tin cậy.
- Header nào được phép, header nào bắt buộc và extension nào được hỗ trợ.
- Claims nào bắt buộc, kiểu dữ liệu và miền giá trị ra sao.
- Quy trình xác minh, giải mã, kiểm tra thời hạn và phân quyền.

Nếu không xác định hợp đồng, các thành phần có thể diễn giải cùng một thông điệp theo cách khác nhau. Điều này tạo ra lỗi tương thích, xác minh sai hoặc lỗ hổng do chấp nhận một biểu diễn mà ứng dụng không được thiết kế để xử lý.

**Nguyên tắc:** chọn một profile token rõ ràng cho từng điểm nhận. Bộ xử lý chỉ chấp nhận các dạng đã được profile đó cho phép.

## 2. JOSE Serialization và JWT không phải cùng một khái niệm

JOSE định nghĩa cách tuần tự hóa JWS và JWE. Các dạng phổ biến gồm:

| Đối tượng | Dạng Compact | Dạng JSON Serialization |
| --- | --- | --- |
| **JWS** | JWS Compact Serialization: ba phần | JWS JSON Serialization: Flattened hoặc General |
| **JWE** | JWE Compact Serialization: năm phần | JWE JSON Serialization: Flattened hoặc General |

Dạng JSON Serialization của JOSE hỗ trợ những khả năng như nhiều chữ ký, nhiều người nhận hoặc metadata tách thành các trường JSON. Dạng Compact biểu diễn các thành phần thành một chuỗi phân cách bằng dấu chấm.

Tuy nhiên, **JWT theo RFC 7519 được biểu diễn bằng JWS Compact Serialization hoặc JWE Compact Serialization**. Một JWS JSON Serialization hay JWE JSON Serialization có thể là JOSE object hợp lệ, nhưng không vì thế mà trở thành cách biểu diễn JWT theo định dạng Compact được RFC 7519 chỉ định. Nếu một ứng dụng muốn nhận JSON Serialization, hợp đồng phải nói rõ ứng dụng đang xử lý JOSE object nào và có profile mở rộng nào áp dụng; không được âm thầm coi mọi JOSE JSON object là JWT.

### JWS Compact

~~~text
protectedHeader.payload.signature
~~~

Ba segment lần lượt là protected header, payload và signature/MAC. Trong JWT thông thường, payload là JWT Claims Set được biểu diễn bằng JSON UTF-8 rồi Base64url.

### JWE Compact

~~~text
protectedHeader.encryptedKey.iv.ciphertext.authenticationTag
~~~

Năm segment lần lượt là protected header, encrypted key, IV, ciphertext và authentication tag. Một số thuật toán quản lý khóa cho phép segment encrypted key rỗng; bộ phân tích phải giữ nguyên segment rỗng theo cấu trúc.

## 3. JWS JSON Serialization: Flattened và General

JWS JSON Serialization biểu diễn một JWS dưới dạng JSON object. Nó có hai dạng chính.

### Flattened JSON Serialization

Dạng Flattened biểu diễn một chữ ký:

~~~json
{
  "payload": "eyJzdWIiOiJjdXN0b21lci00MiJ9",
  "protected": "eyJhbGciOiJSUzI1NiJ9",
  "signature": "base64url-signature"
}
~~~

Các trường thường gặp:

- **payload:** payload được biểu diễn theo quy tắc JWS.
- **protected:** protected header đã Base64url encode.
- **header:** unprotected header, nếu có.
- **signature:** chữ ký Base64url.

### General JSON Serialization

Dạng General hỗ trợ một hoặc nhiều chữ ký trong mảng **signatures**:

~~~json
{
  "payload": "eyJzdWIiOiJjdXN0b21lci00MiJ9",
  "signatures": [
    {
      "protected": "eyJhbGciOiJSUzI1NiJ9",
      "signature": "signature-by-key-a"
    },
    {
      "protected": "eyJhbGciOiJFUzI1NiJ9",
      "signature": "signature-by-key-b"
    }
  ]
}
~~~

Ứng dụng generic JWS có thể cần chính sách về số lượng chữ ký, chữ ký nào bắt buộc, thuật toán cho từng chữ ký và cách kết hợp kết quả. Ví dụ, profile có thể yêu cầu tất cả chữ ký hợp lệ hoặc chỉ cần một chữ ký từ một nhóm issuer được phép. Không nên tự chọn một cách hiểu khi hợp đồng chưa quy định.

**Lưu ý:** JWS JSON Serialization là dạng JOSE hợp lệ nhưng không phải một trong hai dạng Compact mà RFC 7519 chỉ định để biểu diễn JWT. Endpoint JWT thông thường nên từ chối dạng JSON này nếu hợp đồng không quy định rõ một giao thức JOSE khác.

## 4. JWE JSON Serialization: Flattened và General

JWE JSON Serialization cũng có hai dạng.

### Flattened JSON Serialization

Dạng Flattened biểu diễn một người nhận:

~~~json
{
  "protected": "eyJhbGciOiJSU0EtT0FFUC0yNTYiLCJlbmMiOiJBMjU2R0NNIn0",
  "encrypted_key": "base64url-encrypted-key",
  "iv": "base64url-iv",
  "ciphertext": "base64url-ciphertext",
  "tag": "base64url-authentication-tag"
}
~~~

Có thể có thêm các trường như **unprotected**, **header** và **aad** tùy dạng JWE JSON Serialization.

### General JSON Serialization

Dạng General hỗ trợ nhiều người nhận thông qua mảng **recipients**:

~~~json
{
  "protected": "base64url-protected-header",
  "iv": "base64url-iv",
  "ciphertext": "base64url-ciphertext",
  "tag": "base64url-authentication-tag",
  "recipients": [
    {
      "encrypted_key": "encrypted-key-for-recipient-a",
      "header": {"kid": "recipient-a"}
    },
    {
      "encrypted_key": "encrypted-key-for-recipient-b",
      "header": {"kid": "recipient-b"}
    }
  ]
}
~~~

JWE JSON Serialization có khả năng biểu diễn header được bảo vệ, header không được bảo vệ và thông tin người nhận. Ứng dụng generic JWE cần quy định rõ người nhận nào được phép, khóa nào có thể giải mã, thuật toán nào được dùng và metadata nào được tin cậy.

Tương tự JWS, dạng JSON Serialization là một biểu diễn JOSE hợp lệ nhưng không phải dạng Compact của JWT theo RFC 7519. Không nên để một endpoint JWT tự động chuyển qua lại giữa JWE Compact và JWE JSON Serialization nếu hợp đồng chỉ cho phép một dạng.

## 5. Hợp đồng ứng dụng cần chỉ định dạng nào?

Một hợp đồng token tốt phải mô tả đủ chi tiết để hai bên phát hành và nhận token có cùng cách hiểu. Có thể tổ chức hợp đồng theo các nhóm sau:

| Thành phần hợp đồng | Câu hỏi cần trả lời | Ví dụ quy định |
| --- | --- | --- |
| **Token purpose** | Token dùng làm gì? | Access token cho API đơn hàng |
| **Token format** | JWS hay JWE? Compact hay JSON Serialization? | JWT dạng JWS Compact |
| **Header profile** | Header nào bắt buộc/được phép? | typ theo profile, alg trong allowlist, kid tra cứu khóa |
| **Algorithm policy** | Thuật toán và loại khóa nào được chấp nhận? | Chỉ RS256 với khóa RSA công khai phù hợp |
| **Key trust** | Khóa đến từ đâu và gắn với issuer nào? | JWKS URL cấu hình sẵn theo issuer |
| **Claims schema** | Claim nào bắt buộc và kiểu gì? | iss, sub, aud, exp |
| **Validation policy** | Kiểm tra thời gian, audience, issuer thế nào? | aud phải chứa định danh API |
| **Extension policy** | Có cho phép crit, b64, zip hoặc extension nào? | Từ chối extension không được khai báo |
| **Nesting policy** | Có chấp nhận JWT lồng nhau không? | Không chấp nhận nested JWT tại endpoint này |
| **Failure policy** | Xử lý token sai định dạng hoặc xác minh thất bại ra sao? | Từ chối toàn bộ request xác thực |

### Ví dụ hợp đồng cho một API

Giả sử API đơn hàng chỉ nhận access token ký bởi dịch vụ danh tính:

~~~text
Token purpose: Access token for orders API
Representation: JWT using JWS Compact Serialization
Required protection: Signed JWS
Allowed algorithm: RS256
Key source: Configured issuer JWKS
Required claims: iss, sub, aud, exp
Audience: orders-api
Optional claims: iat, jti, scope
Nested JWT: Not accepted
JWS JSON Serialization: Not accepted
JWE: Not accepted
Unsecured JWT (alg=none): Not accepted
Unknown critical extensions: Rejected
~~~

Đây là profile minh họa. Một ứng dụng khác có thể chọn JWE Compact hoặc profile khác, nhưng phải xác định rõ thay vì chấp nhận tất cả dạng có thể parse.

## 6. Không suy đoán loại token chỉ từ hình thức bên ngoài

Một parser có thể nhìn số segment để nhận biết một chuỗi có hình thức JWS Compact ba phần hoặc JWE Compact năm phần. Tuy nhiên, số segment chỉ là **bước kiểm tra cấu trúc ban đầu**, không phải căn cứ duy nhất để quyết định token được phép dùng.

Một ứng dụng nên biết trước loại token mà endpoint chờ nhận:

- Endpoint access token có thể chỉ chấp nhận JWS Compact theo profile.
- Endpoint nhận thông điệp bí mật có thể chỉ chấp nhận JWE Compact.
- Endpoint xử lý JWT lồng nhau phải quy định thứ tự bảo vệ và cách xác minh từng lớp.
- Endpoint xử lý generic JOSE object phải khai báo riêng dạng JSON Serialization và chính sách của nó.

Không nên tự động thử nhiều parser/thuật toán cho đến khi một cách nào đó thành công. Cách xử lý này có thể tạo ra algorithm confusion, token substitution hoặc khác biệt giữa các thành phần trong hệ thống.

## 7. Header và extension cũng thuộc hợp đồng

Protected Header không phải một vùng tự do để người gửi yêu cầu bên nhận thực hiện bất kỳ thuật toán nào. Hợp đồng phải xác định tham số được chấp nhận.

| Header parameter | Vai trò | Cách quy định trong hợp đồng |
| --- | --- | --- |
| **alg** | Thuật toán bảo vệ JWS hoặc quản lý khóa JWE | Allowlist cụ thể, gắn với loại khóa phù hợp |
| **enc** | Thuật toán mã hóa nội dung JWE | Chỉ chấp nhận thuật toán được cấu hình |
| **typ** | Gợi ý loại đối tượng | Dùng để phân biệt token profile khi cần |
| **cty** | Loại nội dung bên trong, thường dùng với nested JWT | Chỉ chấp nhận giá trị theo nesting profile |
| **kid** | Gợi ý chọn khóa | Chỉ tra cứu trong tập khóa tin cậy |
| **crit** | Khai báo tham số mở rộng bắt buộc phải hiểu | Từ chối nếu có phần tử không được hỗ trợ |
| **b64** | Extension điều khiển việc Base64url encode payload JWS | Không chấp nhận cho JWT theo profile thông thường; JWT không dùng unencoded payload option |
| **zip** | Nén plaintext trước khi mã hóa JWE | Chỉ cho phép nếu profile hỗ trợ và đánh giá rủi ro |

### Unknown critical parameters

Nếu protected header có **crit**, mỗi tham số được liệt kê phải được bên nhận hiểu và xử lý theo đặc tả tương ứng. Không được bỏ qua tham số critical không biết. Nếu không hỗ trợ, từ chối token.

### Unencoded JWS payload

RFC 7797 định nghĩa extension **b64** để biểu diễn JWS payload không Base64url trong một số trường hợp. Đây là extension cho JWS; **JWT không được dùng unencoded payload option**. Endpoint JWT theo RFC 7519 phải từ chối dạng này. Không nên tự bật hỗ trợ chỉ vì thư viện JOSE có khả năng xử lý extension.

## 8. JWT lồng nhau phải được quy định rõ

Một JWT có thể chứa một JWT khác, ví dụ ký trước rồi mã hóa:

~~~text
JWT Claims Set
      |
      v
JWS Compact (ký)
      |
      v
JWE Compact (mã hóa JWS)
      |
      v
Bên nhận giải mã JWE
      |
      v
Xác minh JWS bên trong
      |
      v
Kiểm tra claims
~~~

Trong profile nested JWT, header ngoài thường dùng **cty: "JWT"** để chỉ nội dung bên trong là JWT. Hợp đồng cần xác định:

- Lớp ngoài là JWS hay JWE.
- Lớp trong là JWS hay JWE.
- Thứ tự ký và mã hóa.
- Issuer và khóa được tin cậy ở từng lớp.
- Audience và claim nào được kiểm tra ở lớp nào.
- Có giới hạn độ sâu nesting hay không.

Nếu một endpoint không cần nested JWT, hãy từ chối thay vì tự động giải mã/parse nhiều lớp. Nếu cần cả bí mật nội dung và xác thực nhà phát hành, mô hình ký trước rồi mã hóa thường phù hợp; bên nhận giải mã lớp ngoài rồi xác minh chữ ký bên trong.

## 9. Chấp nhận biểu diễn không đồng nghĩa chấp nhận thuật toán

Hai token có thể dùng cùng dạng Compact nhưng khác thuật toán, khóa hoặc profile. Việc chấp nhận một serialization không có nghĩa chấp nhận mọi thuật toán mà header đề xuất.

Ví dụ, endpoint chỉ cho phép JWS Compact và RS256 vẫn phải từ chối:

- Token khai báo HS256.
- Token dùng khóa không thuộc issuer tin cậy.
- Token có kid không tìm được trong tập khóa hợp lệ.
- Token dùng alg: none.
- Token có critical extension không hỗ trợ.
- Token có claims không đúng schema hoặc audience không phù hợp.

Ngược lại, một JWS có signature hợp lệ nhưng được đóng gói thành JWS JSON Serialization vẫn có thể bị endpoint từ chối nếu hợp đồng chỉ chấp nhận JWT Compact. **Tính hợp lệ theo một đặc tả JOSE không tự động đồng nghĩa được chấp nhận bởi mọi ứng dụng.**

## 10. Quy trình kiểm tra biểu diễn theo hợp đồng

~~~mermaid
flowchart TD
    A["Nhận token hoặc JOSE object"] --> B["Xác định profile của endpoint"]
    B --> C{"Dạng serialization có được phép?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Kiểm tra cấu trúc và giới hạn kích thước"]
    D --> E["Đối chiếu header và extension với allowlist"]
    E --> F{"Thuật toán, khóa và loại token phù hợp?"}
    F -- "Không" --> X
    F -- "Có" --> G["Xác minh JWS hoặc giải mã có xác thực JWE"]
    G --> H{"Bảo vệ mật mã hợp lệ?"}
    H -- "Không" --> X
    H -- "Có" --> I["Xử lý nesting nếu profile cho phép"]
    I --> J["Kiểm tra claims, issuer, audience và thời gian"]
    J --> K{"Claims đáp ứng hợp đồng?"}
    K -- "Không" --> X
    K -- "Có" --> L["Áp dụng authorization"]
~~~

Quy trình nên theo thứ tự:

1. **Chọn profile theo endpoint:** xác định endpoint chờ loại token và dạng biểu diễn nào.
2. **Kiểm tra serialization:** đúng số segment và định dạng Compact, hoặc đúng schema JOSE JSON nếu endpoint được thiết kế để nhận JSON Serialization.
3. **Kiểm tra header:** chỉ chấp nhận tham số, extension và thuật toán được khai báo.
4. **Chọn khóa:** lấy khóa từ nguồn tin cậy gắn với issuer và đúng mục đích sử dụng.
5. **Xác minh/giải mã:** xác minh JWS hoặc giải mã có xác thực JWE; không dùng claims trước khi hoàn tất.
6. **Xử lý nesting:** chỉ thực hiện nếu hợp đồng cho phép, theo đúng thứ tự và giới hạn đã quy định.
7. **Validate claims:** kiểm tra issuer, audience, thời hạn, kiểu dữ liệu và các claim bắt buộc.
8. **Authorize:** kiểm tra quyền trên hành động và tài nguyên cụ thể.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chấp nhận mọi dạng JOSE vì parser đọc được | Mở rộng phạm vi token vượt thiết kế ứng dụng | Chỉ chấp nhận serialization được profile khai báo |
| Nhầm JWS JSON Serialization với JWT Compact | Endpoint có thể xử lý sai loại đối tượng | Phân biệt JOSE object và JWT representation |
| Tự động thử JWS rồi JWE rồi JSON Serialization | Tạo nhiều đường xử lý và rủi ro nhầm lẫn | Chọn profile từ endpoint/cấu hình tin cậy |
| Chấp nhận thuật toán theo header | Có thể dẫn đến algorithm confusion | Allowlist thuật toán và loại khóa |
| Bỏ qua crit không hỗ trợ | Bỏ qua yêu cầu xử lý extension bắt buộc | Từ chối unknown critical parameters |
| Bật b64:false cho JWT | Chấp nhận dạng payload không phù hợp profile JWT | Từ chối unencoded payload option |
| Cho phép nesting không giới hạn | Parser có thể xử lý sai lớp hoặc tiêu tốn tài nguyên | Quy định nesting và giới hạn độ sâu |
| Cho rằng signature hợp lệ là đủ | Bỏ qua issuer, audience, thời gian và quyền | Validate đầy đủ sau verify |
| Dùng cùng profile cho mọi loại token | Access token, ID token hoặc token mục đích khác bị thay thế lẫn nhau | Tách profile theo loại token và endpoint |

## 12. Checklist thiết kế hợp đồng token

Trước khi triển khai một endpoint nhận JWT/JOSE, hãy trả lời:

- Endpoint nhận JWT hay generic JOSE object?
- Token là JWS, JWE hay nested JWT?
- Chỉ nhận Compact Serialization hay có hỗ trợ JOSE JSON Serialization?
- Nếu có JSON Serialization, dùng Flattened hay General? Có hỗ trợ nhiều chữ ký/người nhận không?
- Header nào bắt buộc, header nào tùy chọn?
- Thuật toán và loại khóa nào được phép?
- Khóa lấy từ nguồn nào và gắn với issuer nào?
- Extension nào được hỗ trợ? Xử lý crit, b64, zip ra sao?
- Có cho phép alg: none không? Với bearer access token thông thường, câu trả lời nên là không.
- Claims nào bắt buộc, kiểu dữ liệu và null policy ra sao?
- Issuer, audience, thời hạn và loại token được kiểm tra thế nào?
- Có cho phép nesting không và giới hạn bao nhiêu lớp?
- Token sai cấu trúc hoặc xác minh thất bại sẽ bị từ chối như thế nào?

**Ghi nhớ:** JOSE cung cấp nhiều dạng serialization và cơ chế bảo vệ, nhưng mỗi ứng dụng chỉ nên chấp nhận phạm vi mà hợp đồng của nó định nghĩa. JWT theo RFC 7519 dùng JWS Compact hoặc JWE Compact. JWS/JWE JSON Serialization là các dạng JOSE khác và cần profile riêng nếu ứng dụng muốn xử lý. Hợp đồng phải quy định token purpose, serialization, header, thuật toán, khóa, extension, nesting, claims và quy trình xác minh trước khi ứng dụng sử dụng dữ liệu.

### Tài liệu chuẩn để tra cứu

- **RFC 7515 — JSON Web Signature (JWS):** Compact, Flattened và General JSON Serialization.
- **RFC 7516 — JSON Web Encryption (JWE):** Compact, Flattened và General JSON Serialization.
- **RFC 7519 — JSON Web Token (JWT):** cách biểu diễn JWT bằng JWS Compact hoặc JWE Compact, claims và nested JWT.
- **RFC 7797 — JSON Web Signature (JWS) Unencoded Payload Option:** extension b64 và giới hạn áp dụng cho JWT.
- **RFC 8725 — JSON Web Token Best Current Practices:** kiểm tra thuật toán, issuer, audience, loại token và nesting an toàn.

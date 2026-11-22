# Header được bảo vệ và header không được bảo vệ trong JOSE

## 1. Vì sao JOSE phân chia header?

Trong JOSE (*JSON Object Signing and Encryption*), **JOSE Header** chứa các tham số mô tả cách một thông điệp được ký, xác minh, mã hóa, giải mã hoặc diễn giải. Ví dụ, **alg** cho biết thuật toán chữ ký/MAC hoặc thuật toán quản lý khóa; **enc** cho biết thuật toán mã hóa nội dung; **kid** hỗ trợ chọn khóa; **typ** và **cty** mô tả loại đối tượng hoặc nội dung.

Trong module **SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)**, kiến thức này áp dụng cho các tiêu chuẩn JOSE/JWT nói chung: cách header được bảo vệ trong JWS và JWE, cách các serialization biểu diễn header và cách bên nhận xác minh chúng. Đây là kiến thức bảo mật ở mức giao thức, độc lập với một ngôn ngữ lập trình hay framework cụ thể.

Không phải mọi tham số header đều có cùng yêu cầu bảo mật. Một số tham số quyết định trực tiếp cách xác minh hoặc giải mã, nên cần được ràng buộc với dữ liệu đã được bảo vệ tính toàn vẹn. Một số tham số khác chỉ mang thông tin bổ trợ và có thể được đặt ở vùng không được bảo vệ.

JOSE vì vậy phân biệt:

- **Protected Header (header được bảo vệ):** tham số được đưa vào dữ liệu ký/MAC của JWS hoặc dữ liệu xác thực của JWE.
- **Unprotected Header (header không được bảo vệ):** tham số được truyền kèm nhưng không nằm trong dữ liệu ký/MAC hoặc AAD bảo vệ nội dung.

Sự phân chia này xuất hiện rõ trong các dạng JSON Serialization của JWS/JWE. Với Compact Serialization, toàn bộ JOSE Header là protected; không có vùng unprotected riêng.

Điểm cần ghi nhớ: **protected có nghĩa là được ràng buộc tính toàn vẹn bằng cơ chế mật mã, không có nghĩa là được giữ bí mật**. Header protected vẫn có thể được đọc bằng cách base64url-decode. Ngược lại, unprotected không có bảo đảm rằng giá trị được gửi đi còn nguyên vẹn.

## 2. Header được biểu diễn ở đâu?

JOSE hỗ trợ nhiều serialization. Vị trí của header phụ thuộc vào serialization và cấu trúc chữ ký/recipient.

| Serialization | Header được bảo vệ | Header không được bảo vệ |
| --- | --- | --- |
| **JWS Compact** | Một protected header duy nhất, mã hóa trong đoạn thứ nhất | Không có |
| **JWS JSON General** | Trường **protected** riêng trong từng phần tử **signatures** | Trường **header** trong từng phần tử chữ ký |
| **JWS JSON Flattened** | Trường **protected** ở cấp cao nhất | Trường **header** ở cấp cao nhất |
| **JWE Compact** | Một protected header duy nhất, mã hóa trong đoạn thứ nhất | Không có |
| **JWE JSON General** | Trường **protected** dùng chung ở cấp cao nhất | **unprotected** dùng chung và **header** riêng trong từng recipient |
| **JWE JSON Flattened** | Trường **protected** ở cấp cao nhất | **unprotected** dùng chung và **header** của recipient duy nhất |

### 2.1. JWS JSON: mỗi chữ ký có hai vùng header

Trong JWS JSON Serialization, một chữ ký có thể được biểu diễn như sau:

§§§json
{
  "payload": "<payload-base64url>",
  "signatures": [
    {
      "protected": "<protected-header-base64url>",
      "header": {
        "kid": "key-signing-A"
      },
      "signature": "<signature-base64url>"
    }
  ]
}
§§§

- **protected** là JSON Header được mã hóa UTF-8 rồi base64url.
- **header** là unprotected header được biểu diễn trực tiếp bằng JSON.
- **signature** là chữ ký/MAC tương ứng với protected header và payload.

Trong General Serialization, mỗi phần tử **signatures** có thể có protected header và unprotected header riêng. Payload dùng chung nhưng signing input được tạo riêng cho từng chữ ký.

### 2.2. JWE JSON: có header dùng chung và header theo recipient

JWE JSON Serialization có thêm vùng unprotected dùng chung:

§§§json
{
  "protected": "<protected-header-base64url>",
  "unprotected": {
    "typ": "application/example"
  },
  "recipients": [
    {
      "header": {
        "alg": "RSA-OAEP-256",
        "kid": "recipient-A"
      },
      "encrypted_key": "<encrypted-cek>"
    }
  ],
  "iv": "<iv>",
  "ciphertext": "<ciphertext>",
  "tag": "<authentication-tag>"
}
§§§

- **protected** chứa tham số được bảo vệ chung cho JWE.
- **unprotected** chứa tham số không được bảo vệ, dùng chung cho toàn JWE.
- **header** trong mỗi recipient chứa tham số không được bảo vệ riêng cho recipient đó.

Với Flattened JWE JSON Serialization, các trường recipient như **header** và **encrypted_key** nằm ở cấp cao nhất thay vì trong mảng **recipients**.

## 3. Protected Header được bảo vệ như thế nào?

Protected Header không được bảo vệ bằng cách mã hóa bí mật. Nó được **đưa vào dữ liệu đầu vào của phép ký/MAC hoặc phép xác thực mã hóa**, nhờ vậy việc sửa đổi header sẽ làm kiểm tra mật mã thất bại.

### 3.1. Với JWS

Trong JWS thông thường, signing input được tạo từ protected header và payload:

§§§text
protectedSegment = BASE64URL(UTF8(JWS Protected Header))
payloadSegment   = BASE64URL(JWS Payload)

signingInput = ASCII(protectedSegment + "." + payloadSegment)

signatureOrMAC = SIGN_OR_MAC(alg, key, signingInput)
§§§

Vì protected header nằm trong signing input, thay đổi **alg**, **typ**, **cty**, **crit** hoặc một tham số protected khác sẽ làm chữ ký/MAC không còn hợp lệ, trừ trường hợp kẻ thay đổi có thể tạo chữ ký/MAC hợp lệ bằng khóa phù hợp.

Với JWS JSON, **header** (unprotected header) không được đưa vào signing input. Thay đổi vùng đó không làm chữ ký thất bại. Do đó, không được đặt dữ liệu quyết định quyền hoặc chính sách tin cậy ở unprotected header rồi xem chữ ký JWS là bằng chứng bảo vệ dữ liệu đó.

### 3.2. Với JWE

Trong JWE, protected header là một phần của Additional Authenticated Data (AAD) mặc định:

§§§text
protectedSegment = BASE64URL(UTF8(JWE Protected Header))

JWE Compact:
  AAD = ASCII(protectedSegment)

JWE JSON, khi có trường aad:
  AAD = ASCII(protectedSegment + "." + BASE64URL(JWE AAD))
§§§

Thuật toán mã hóa có xác thực dùng AAD khi tạo Authentication Tag. Khi giải mã, bên nhận tính lại AAD và kiểm tra tag. Nếu protected header bị sửa, tag không còn khớp.

Trong JWE JSON, **unprotected** và **header** của recipient không được đưa vào AAD mặc định. Vì vậy, chúng không nhận được bảo đảm toàn vẹn từ Authentication Tag của ciphertext. Đặc biệt, cần cẩn trọng với các tham số điều khiển quản lý khóa và lựa chọn recipient nằm ở vùng này.

### 3.3. So sánh cơ chế bảo vệ

| Thuộc tính | JWS Protected Header | JWE Protected Header | Unprotected Header |
| --- | --- | --- | --- |
| Được đưa vào dữ liệu mật mã | Signing input | AAD | Không |
| Sửa đổi có bị phát hiện? | Có, khi xác minh chữ ký/MAC | Có, khi xác minh Authentication Tag | Không được cơ chế JWS/JWE này bảo đảm |
| Có được giữ bí mật? | Không | Không | Không |
| Có thể chứa tham số ảnh hưởng xác minh? | Có, đây là vị trí phù hợp | Có, đây là vị trí phù hợp | Không nên dựa vào nó cho quyết định bảo mật |

## 4. JOSE Header được hợp nhất và quy tắc tên tham số

Trong JSON Serialization, bên xử lý thường cần hợp nhất các vùng header để có JOSE Header hoàn chỉnh.

- **JWS JSON:** hợp nhất protected header với unprotected header của chữ ký đang xét.
- **JWE JSON:** hợp nhất protected header, shared unprotected header và per-recipient unprotected header của recipient đang xét.

Việc hợp nhất là kết hợp các tham số có tên khác nhau. **Không có quy tắc ưu tiên kiểu “protected thắng unprotected” hoặc “vùng sau ghi đè vùng trước”.** Nếu cùng một tên tham số xuất hiện ở nhiều vùng của cùng JOSE Header, đối tượng phải bị từ chối.

Ví dụ không hợp lệ:

§§§json
{
  "protected": "<base64url-of-{alg:PS256}>",
  "header": {
    "alg": "HS256",
    "kid": "key-A"
  },
  "signature": "<signature>"
}
§§§

Tên **alg** xuất hiện ở cả protected và unprotected header. Bên nhận không được tự chọn một trong hai giá trị, bởi các thành phần xử lý khác nhau có thể hiểu thông điệp theo cách khác nhau.

Với JWE JSON, quy tắc tương tự áp dụng giữa:

1. Protected Header.
2. Shared Unprotected Header.
3. Per-Recipient Unprotected Header của recipient đang xử lý.

Nếu tên tham số bị trùng giữa bất kỳ vùng nào trong ba vùng này, phải từ chối JWE. Quy tắc này giúp tránh tình trạng thuật toán, định danh khóa hoặc tham số khác bị diễn giải khác nhau giữa parser, thư viện mật mã và tầng nghiệp vụ.

Một parser an toàn nên:

- Từ chối tên thành viên JSON bị lặp ngay trong cùng một đối tượng JSON.
- Từ chối tên tham số JOSE bị trùng giữa các vùng header.
- Kiểm tra kiểu và giá trị tham số theo đặc tả tương ứng.
- Không âm thầm ghi đè hoặc tự chọn giá trị khi có xung đột.

## 5. Tham số nào nên được đặt trong Protected Header?

Vị trí cụ thể phải tuân thủ RFC của tham số và giao thức đang dùng. Quy tắc thực hành là: **tham số nào ảnh hưởng đến cách xác minh, giải mã, diễn giải nội dung hoặc quyết định tin cậy thì cần được bảo vệ tính toàn vẹn hoặc được ràng buộc bằng chính sách tin cậy độc lập.**

| Tham số | Ý nghĩa | Khuyến nghị về vị trí/xử lý |
| --- | --- | --- |
| **alg** trong JWS | Thuật toán ký/MAC | Đặt trong Protected Header; bên nhận vẫn phải kiểm tra allowlist và tương thích khóa |
| **alg** trong JWE | Thuật toán quản lý/thiết lập CEK | Trong JWE JSON có thể gắn với recipient; nếu ở vùng unprotected, phải ràng buộc chặt với cấu hình recipient và khóa tin cậy |
| **enc** trong JWE | Thuật toán mã hóa nội dung | Đặt trong Protected Header; cùng một JWE nhiều recipient dùng chung **enc** |
| **crit** | Các tham số mở rộng bắt buộc phải hiểu | Phải nằm trong Protected Header |
| **b64** của JWS (RFC 7797) | Chỉ payload có được base64url-encode hay không | Phải được bảo vệ và liệt kê trong **crit** khi dùng phần mở rộng |
| **zip** của JWE | Thuật toán nén plaintext trước mã hóa | Phải được bảo vệ trong Protected Header |
| **typ**, **cty** | Loại đối tượng/nội dung | Nên bảo vệ khi chúng ảnh hưởng đến định tuyến, phân loại hoặc chính sách xử lý |
| **kid** | Gợi ý định danh khóa | Có thể xuất hiện ở vùng phù hợp theo cấu trúc; luôn coi là gợi ý tra cứu, không phải nguồn tin cậy |
| **jku**, **x5u** | Tham chiếu tới nguồn khóa/chứng thư | Không tự động tin URL; phải ràng buộc nguồn tải với cấu hình tin cậy và chống SSRF |
| **x5c**, **jwk** | Chứng thư hoặc khóa được nhúng | Dữ liệu nhúng không tự trở thành đáng tin; phải xác minh chuỗi chứng thư/chính sách nguồn khóa |

Lưu ý: JWE JSON cho phép một số tham số quản lý khóa theo recipient được đặt trong per-recipient header. Đây là đặc điểm định dạng, không có nghĩa các tham số đó được Authentication Tag của nội dung bảo vệ. Hệ thống phải ràng buộc recipient, thuật toán, khóa và nguồn khóa bằng chính sách tin cậy rõ ràng.

## 6. Tham số crit: phần mở rộng bắt buộc phải hiểu

**crit** (*Critical*) là mảng tên các header parameter mở rộng mà bên nhận bắt buộc phải hiểu và xử lý đúng. Nó ngăn một bên nhận bỏ qua âm thầm một tham số có thể làm thay đổi ý nghĩa bảo mật của thông điệp.

Ví dụ minh họa:

§§§json
{
  "alg": "PS256",
  "crit": ["example-mode"],
  "example-mode": "strict"
}
§§§

Nếu **example-mode** được khai báo là critical:

1. Tham số **crit** phải nằm trong Protected Header.
2. Tham số được liệt kê phải thực sự có mặt trong cùng JOSE Header.
3. Bên nhận phải biết và thực hiện đúng ngữ nghĩa của tham số.
4. Nếu không hiểu hoặc không hỗ trợ tham số critical, bên nhận phải từ chối thông điệp.

Không được bỏ qua **crit** chỉ vì chữ ký/MAC hoặc Authentication Tag hợp lệ. Tính toàn vẹn mật mã không đồng nghĩa với khả năng hiểu đúng ngữ nghĩa của mọi phần mở rộng.

Với JWS dùng tùy chọn payload không mã hóa base64url theo RFC 7797, **b64** phải được xử lý như tham số critical và được bảo vệ. JWT không được sử dụng tùy chọn **b64: false** này.

## 7. kid và nguồn khóa: header không thay thế trust store

**kid** (*Key ID*) là một giá trị định danh giúp bên nhận chọn khóa phù hợp từ tập khóa đã biết. Ví dụ:

§§§json
{
  "alg": "ES256",
  "kid": "issuer-signing-2026-01"
}
§§§

Ngay cả khi **kid** nằm trong Protected Header và được chữ ký bảo vệ, nó chỉ chứng minh rằng bên ký đã đưa chuỗi đó vào header. Nó **không chứng minh khóa có định danh đó thuộc về issuer mà ứng dụng tin cậy**.

Quy trình chọn khóa an toàn:

1. Xác định issuer/đối tác hoặc ngữ cảnh được phép từ cấu hình tin cậy của ứng dụng.
2. Lấy tập khóa từ nguồn đã được cấu hình tin cậy cho issuer/đối tác đó.
3. Dùng **kid** như gợi ý tìm khóa trong đúng tập khóa, không tìm toàn cục.
4. Kiểm tra loại khóa, mục đích sử dụng, thuật toán được phép và thời hạn/trạng thái của khóa nếu có.
5. Xác minh chữ ký hoặc thực hiện thao tác giải mã với khóa phù hợp.
6. Chỉ sau khi xác minh thành công mới chấp nhận claims/nội dung theo chính sách.

Không tải khóa từ URL tùy ý trong **jku**/**x5u**, không chấp nhận khóa nhúng trong **jwk** hoặc **x5c** mà không có quy trình xác minh độc lập, và không dùng một **kid** chưa xác thực làm đường dẫn file, truy vấn không giới hạn hoặc URL.

## 8. Ví dụ: cùng một thông điệp nhưng hai mức header

### 8.1. JWS JSON với protected và unprotected header

§§§json
{
  "payload": "<payload-base64url>",
  "protected": "<base64url-of-{alg:ES256,typ:JWT}>",
  "header": {
    "kid": "issuer-key-01",
    "comment": "key rotation batch 3"
  },
  "signature": "<signature-base64url>"
}
§§§

Trong ví dụ:

- **alg** và **typ** nằm trong protected header, nên được ràng buộc với chữ ký.
- **kid** nằm trong unprotected header, nên không được chữ ký bảo vệ; nếu dùng để tra cứu, nó chỉ là gợi ý và khóa tìm được phải đến từ nguồn tin cậy.
- **comment** là metadata bổ trợ; không dùng nó để quyết định quyền hoặc chính sách.

Nếu thay đổi **comment** hoặc **kid** trong unprotected header, chữ ký vẫn có thể xác minh thành công vì signing input không chứa vùng đó. Nếu thay đổi protected header hoặc payload, xác minh phải thất bại.

### 8.2. JWE JSON với ba vùng header

§§§json
{
  "protected": "<base64url-of-{enc:A256GCM,cty:JWT}>",
  "unprotected": {
    "typ": "application/example"
  },
  "recipients": [
    {
      "header": {
        "alg": "RSA-OAEP-256",
        "kid": "recipient-key-01"
      },
      "encrypted_key": "<encrypted-cek>"
    }
  ],
  "iv": "<iv>",
  "ciphertext": "<ciphertext>",
  "tag": "<tag>"
}
§§§

Trong ví dụ:

- **enc** và **cty** nằm trong protected header và được ràng buộc với tag.
- **typ** ở shared unprotected header không được bảo vệ.
- **alg** và **kid** trong header của recipient không được tag của ciphertext bảo vệ; ứng dụng cần đối chiếu với cấu hình recipient/khóa tin cậy.
- **encrypted_key** gắn với recipient tương ứng; không được thay bằng giá trị dành cho recipient khác.

Nếu một bên trung gian sửa **typ** trong shared unprotected header, tag vẫn có thể hợp lệ. Vì vậy, không dùng trường này làm căn cứ duy nhất để phân loại thông điệp nhạy cảm.

## 9. Những lỗi bảo mật thường gặp

### 9.1. Nhầm protected với encrypted

Protected Header thường chỉ được mã hóa base64url để biểu diễn. Ai có token có thể đọc nội dung header. Bảo vệ tính toàn vẹn không phải là bảo mật nội dung.

**Cách xử lý:** không đặt mật khẩu, khóa bí mật hoặc dữ liệu nhạy cảm vào header. Nếu cần bí mật, dùng cơ chế mã hóa thích hợp cho dữ liệu.

### 9.2. Đưa tham số quyết định chính sách vào unprotected header

Nếu ứng dụng dựa vào **alg**, loại token, issuer hoặc vai trò lấy từ vùng không được bảo vệ, kẻ tấn công có thể sửa các giá trị đó mà không làm chữ ký/tag thất bại.

**Cách xử lý:** đặt tham số có ảnh hưởng bảo mật vào protected header khi phù hợp; đồng thời dùng allowlist thuật toán, cấu hình issuer/recipient và kiểm tra ngữ cảnh độc lập.

### 9.3. Ghi đè khi hợp nhất header

Parser có thể vô tình cho phép cùng tên tham số xuất hiện trong protected và unprotected header, rồi âm thầm chọn một giá trị. Các thành phần khác nhau có thể đưa ra quyết định khác nhau.

**Cách xử lý:** từ chối tên tham số trùng; không áp dụng quy tắc ghi đè hoặc ưu tiên vùng header.

### 9.4. Bỏ qua crit

Một ứng dụng có thể xác minh chữ ký/tag nhưng bỏ qua tham số mở rộng làm thay đổi ngữ nghĩa thông điệp. Kết quả là thông điệp được chấp nhận trong khi bên nhận hiểu sai cách xử lý.

**Cách xử lý:** chỉ chấp nhận critical parameter đã biết và hỗ trợ đầy đủ; nếu không hiểu, từ chối.

### 9.5. Tin kid, jku, x5u hoặc khóa nhúng

Header là dữ liệu đầu vào từ phía gửi. Dùng URL tùy ý để tải khóa có thể gây SSRF hoặc đưa khóa do đối phương kiểm soát vào quá trình xác minh.

**Cách xử lý:** giới hạn nguồn khóa bằng cấu hình tin cậy, xác minh chứng thư/khóa và ràng buộc khóa với issuer hoặc recipient.

### 9.6. Cho rằng JWE tag bảo vệ mọi header JSON

Authentication Tag bảo vệ protected header và ciphertext cùng AAD theo quy tắc JWE. Shared unprotected header và per-recipient unprotected header không tự được bảo vệ bởi tag.

**Cách xử lý:** không sử dụng các vùng unprotected làm căn cứ bảo mật nếu không có cơ chế ràng buộc riêng.

### 9.7. Xử lý khác nhau giữa các parser

JSON trùng tên thành viên, kiểu dữ liệu sai, tên tham số header trùng hoặc trường bất thường có thể làm các thư viện hiểu cùng thông điệp theo các cách khác nhau.

**Cách xử lý:** parse nghiêm ngặt, từ chối cấu trúc mơ hồ, giới hạn kích thước và kiểm tra mọi trường theo RFC.

## 10. Checklist thiết kế và xác minh

- [ ] Xác định serialization đang xử lý: JWS/JWE Compact hay JSON General/Flattened.
- [ ] Chỉ coi Protected Header là vùng được ràng buộc bằng chữ ký/MAC hoặc AAD.
- [ ] Không nhầm base64url với mã hóa bí mật.
- [ ] Từ chối tên thành viên JSON lặp và tên JOSE Header trùng giữa các vùng.
- [ ] Xử lý **crit** đúng chuẩn; từ chối tham số critical không được hỗ trợ.
- [ ] Kiểm tra **alg** và **enc** bằng allowlist; ràng buộc thuật toán với khóa và mục đích.
- [ ] Không dựa vào unprotected header để xác định quyền, issuer hoặc chính sách tin cậy.
- [ ] Xử lý **kid** như gợi ý tra cứu trong nguồn khóa đã tin cậy.
- [ ] Không tự động tải khóa từ **jku**/**x5u** tùy ý hoặc tin khóa nhúng chưa xác minh.
- [ ] Với JWE, tạo lại AAD đúng và chỉ sử dụng plaintext sau khi Authentication Tag hợp lệ.
- [ ] Với JWS, xác minh trên signing input được tạo từ protected header và payload gốc.
- [ ] Kiểm tra issuer, audience, thời gian, loại token và quy tắc ứng dụng sau khi xác minh mật mã.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Protected Header có được giữ bí mật không?

**Đáp án:** Không. Nó được bảo vệ tính toàn vẹn bằng chữ ký/MAC hoặc AAD, nhưng thường có thể đọc sau khi base64url-decode.

**Câu 2.** Thay đổi unprotected header có làm JWS signature hoặc JWE authentication tag thất bại không?

**Đáp án:** Không nhất thiết. Unprotected header không nằm trong signing input hoặc AAD mặc định.

**Câu 3.** Khi cùng một tên tham số xuất hiện trong protected và unprotected header, bên nhận nên ưu tiên giá trị nào?

**Đáp án:** Không ưu tiên giá trị nào; phải từ chối đối tượng có tên tham số trùng giữa các vùng header.

**Câu 4.** **crit** dùng để làm gì và phải được đặt ở đâu?

**Đáp án:** **crit** liệt kê tham số mở rộng mà bên nhận bắt buộc phải hiểu; nó phải nằm trong Protected Header. Không hiểu tham số critical thì từ chối.

**Câu 5.** **kid** được bảo vệ trong Protected Header có chứng minh khóa thuộc issuer không?

**Đáp án:** Không. Nó chỉ chứng minh bên ký đã đưa giá trị **kid** đó vào thông điệp; nguồn khóa vẫn phải đến từ cấu hình tin cậy.

**Câu 6.** Vì sao JWE JSON có thể có **alg** trong header của từng recipient?

**Đáp án:** Vì mỗi recipient có thể dùng phương thức quản lý CEK riêng. Tuy nhiên, per-recipient unprotected header không được Authentication Tag của ciphertext bảo vệ, nên ứng dụng phải ràng buộc thuật toán và khóa với cấu hình recipient tin cậy.

## 12. Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected/unprotected header, JWS JSON Serialization, signing input và **crit**.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): protected/shared/per-recipient headers, AAD, JWE JSON Serialization và quy tắc hợp nhất header.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): biểu diễn khóa, **kid** và JWK Set.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): các thuật toán ký/MAC, quản lý khóa và mã hóa nội dung.
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): tham số **b64**, payload không mã hóa base64url và yêu cầu critical.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm soát thuật toán, khóa, loại JWT và ngữ cảnh tin cậy.

**Ghi nhớ:** Protected Header được ràng buộc với chữ ký/MAC của JWS hoặc AAD của JWE; unprotected header không có bảo đảm toàn vẹn từ cơ chế đó. JSON Serialization có thể chia header theo chữ ký hoặc recipient, nhưng các vùng không được chồng tên tham số. Hãy bảo vệ các tham số ảnh hưởng đến cách xác minh/giải mã, xử lý **crit** nghiêm ngặt và luôn chọn khóa từ nguồn tin cậy.

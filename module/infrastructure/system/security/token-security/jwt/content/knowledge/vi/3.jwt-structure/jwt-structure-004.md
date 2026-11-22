# Base64url, ký tự phân cách và sự khác biệt với Base64 thông thường

## 1. Base64url xuất hiện ở đâu trong JWT?

JWT thường được truyền dưới dạng chuỗi **Compact Serialization**. Những phần dữ liệu nhị phân hoặc văn bản JSON được chuyển thành chuỗi ký tự để có thể truyền qua các giao thức văn bản. Cơ chế chuyển đổi này là **Base64url**.

Tên gọi dễ gây nhầm lẫn: Base64url là một biến thể của **Base64**, được định nghĩa trong RFC 4648, mục tiêu là dùng bảng ký tự phù hợp với URL và tên file. Base64url **không phải mã hóa bí mật**, không ký token, không xác minh token và cũng không nén dữ liệu. Nó chỉ chuyển byte thành ký tự có thể biểu diễn an toàn hơn trong nhiều ngữ cảnh truyền tải.

Với JWT theo dạng JOSE Compact:

- **JWS Compact** có ba phần: protected header, payload và signature.
- **JWE Compact** có năm phần: protected header, encrypted key, initialization vector, ciphertext và authentication tag.
- Các phần được ngăn cách bằng ký tự dấu chấm ASCII **`.`**.
- Các phần dữ liệu được biểu diễn bằng Base64url theo quy tắc Compact Serialization; ký tự đệm **`=`** được bỏ.

Mô hình tổng quát:

~~~text
JWS Compact:
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)

JWE Compact:
BASE64URL(protected-header).
BASE64URL(encrypted-key).
BASE64URL(iv).
BASE64URL(ciphertext).
BASE64URL(authentication-tag)
~~~

Dấu chấm không thuộc bảng ký tự Base64url, vì vậy có thể dùng nó làm ký tự phân cách mà không nhầm với nội dung của từng phần.

## 2. Base64 thông thường hoạt động như thế nào?

Base64 chuyển một chuỗi byte thành các ký tự có thể đọc và truyền trong môi trường văn bản. Thuật toán lấy từng nhóm **3 byte (24 bit)**, chia thành **4 nhóm 6 bit**, rồi ánh xạ mỗi nhóm 6 bit thành một ký tự trong bảng Base64.

Bảng Base64 chuẩn có 64 ký tự:

- `A` đến `Z`: 26 ký tự.
- `a` đến `z`: 26 ký tự.
- `0` đến `9`: 10 ký tự.
- `+` và `/`: 2 ký tự cuối.

Mỗi ký tự biểu diễn một giá trị từ 0 đến 63. Do 3 byte đầu vào tạo thành 4 ký tự đầu ra, Base64 làm dữ liệu dài hơn khoảng **một phần ba** (chưa tính padding).

Ví dụ, ba byte ASCII của từ `JWT` là:

~~~text
J  = 0x4A
W  = 0x57
T  = 0x54

Bytes: 4A 57 54
Base64: SldU
~~~

Ở ví dụ này, đầu ra không có ký tự `+` hoặc `/`, nên Base64 thông thường và Base64url giống nhau.

## 3. Base64url khác Base64 ở điểm nào?

Base64url giữ nguyên phần lớn thuật toán Base64 nhưng thay hai ký tự để giảm vấn đề khi đặt dữ liệu trong URL và tên file:

| Giá trị 6 bit | Base64 chuẩn | Base64url |
| --- | --- | --- |
| 62 | `+` | `-` |
| 63 | `/` | `_` |

Các ký tự còn lại (`A-Z`, `a-z`, `0-9`) không thay đổi.

Một khác biệt nữa nằm ở padding:

- Base64 thông thường thường thêm ký tự `=` để đầu ra có độ dài là bội số của 4.
- Base64url nói chung có thể được dùng có hoặc không có padding tùy quy định của giao thức.
- **JWS Compact và JWE Compact yêu cầu Base64url không padding**, nên bỏ mọi ký tự `=` ở cuối mỗi phần.

Ví dụ với hai byte `FB FF`:

~~~text
Input bytes:    FB FF

Base64:         +/8=
Base64url:      -_8
~~~

Ví dụ này minh họa cả hai thay đổi: `+` thành `-`, `/` thành `_`, và padding `=` được bỏ trong biểu diễn Base64url không padding của JOSE Compact.

### Vì sao thay `+` và `/`?

Trong một số cách truyền URL hoặc xử lý form, dấu `+` có thể bị diễn giải thành dấu cách; dấu `/` có thể có ý nghĩa phân cấp đường dẫn. Khi dữ liệu nhị phân được chuyển thành Base64url:

- `-` và `_` không có cách diễn giải đặc biệt như `+` và `/` trong những ngữ cảnh nói trên.
- Dữ liệu ít cần percent-encoding hơn khi đặt trong thành phần URL phù hợp.
- Token Compact có thể được truyền dưới dạng chuỗi văn bản liền mạch cùng các dấu chấm phân cách.

Điều này không có nghĩa mọi vị trí trong URL đều là nơi thích hợp để đặt token. Token vẫn là thông tin xác thực nhạy cảm; tránh đưa bearer token vào query string vì URL có thể xuất hiện trong lịch sử trình duyệt, log, analytics hoặc header giới thiệu (*Referer*).

## 4. Padding `=` và cách khôi phục khi giải mã

Base64 cần padding để biểu diễn đầy đủ nhóm 24 bit cuối cùng. Tùy số byte đầu vào còn lại, đầu ra Base64 có thể có:

| Số byte còn lại ở nhóm cuối | Base64 có padding | Base64url Compact |
| --- | --- | --- |
| 0 | Không cần padding | Không có `=` |
| 1 | Thêm `==` | Bỏ cả hai `=` |
| 2 | Thêm `=` | Bỏ `=` |
| 3 | Không cần padding | Không có `=` |

Vì vậy, độ dài chuỗi Base64url không padding có thể có phần dư 0, 2 hoặc 3 khi chia cho 4. Nếu độ dài có phần dư **1**, chuỗi không thể là một biểu diễn Base64 hợp lệ theo quy tắc này và cần bị từ chối.

Khi giải mã, một thư viện có thể khôi phục padding nội bộ trước khi thực hiện thao tác Base64. Đây là chi tiết triển khai của bộ giải mã; token JOSE Compact truyền trên dây vẫn phải không có padding.

Ví dụ quy tắc khôi phục:

~~~text
remainder = encodedLength mod 4

remainder = 0  -> không cần thêm padding
remainder = 2  -> thêm "=="
remainder = 3  -> thêm "="
remainder = 1  -> từ chối
~~~

**Không tự động chấp nhận mọi dạng Base64 gần giống Base64url.** Với JWT Compact, cần từ chối `+`, `/`, padding `=` xuất hiện trong segment, khoảng trắng, ký tự ngoài bảng cho phép và các chuỗi không đúng định dạng. Việc một thư viện có thể giải mã một đầu vào rộng hơn không có nghĩa đầu vào đó hợp lệ theo định dạng JOSE Compact.

## 5. Ký tự phân cách `.` trong Compact Serialization

Dấu chấm ASCII **`.`** phân chia các phần của JWS hoặc JWE Compact. Vì dấu chấm không thuộc bảng ký tự Base64url, mỗi segment có thể được nhận diện rõ ràng.

~~~text
JWS: headerPart.payloadPart.signaturePart
       ^           ^
       |           |
     separator   separator

JWE: headerPart.encryptedKey.iv.ciphertext.tag
       ^             ^       ^         ^
       |             |       |         |
     separator     separator ...     separator
~~~

| Dạng token | Số segment | Số dấu chấm | Thứ tự |
| --- | ---: | ---: | --- |
| JWS Compact | 3 | 2 | Protected Header, Payload, Signature |
| JWE Compact | 5 | 4 | Protected Header, Encrypted Key, IV, Ciphertext, Authentication Tag |

Dấu chấm là ký tự cấu trúc, không phải dấu chấm thuộc JSON và không phải ký tự được thêm vào bên trong từng segment sau khi Base64url.

### Phải giữ cả segment rỗng

Một segment có thể rỗng theo quy tắc của loại token và thuật toán. Ví dụ:

- Với JWS không bảo vệ bằng chữ ký (`alg` là `none`), segment signature ở cuối có thể rỗng. Nhiều luồng xác thực bearer token cần từ chối dạng này trừ khi một giao thức riêng cho phép rõ ràng.
- Với JWE dùng quản lý khóa trực tiếp (`alg = dir`) hoặc ECDH-ES trực tiếp, segment Encrypted Key có thể rỗng.

Ví dụ cấu trúc JWE có Encrypted Key rỗng:

~~~text
protectedHeader..iv.ciphertext.tag
                ^^
          segment thứ hai rỗng
~~~

Hai dấu chấm liên tiếp vẫn biểu thị một segment rỗng nằm giữa chúng. Token vẫn có đủ **năm vị trí segment** và bốn dấu chấm.

Vì thế, khi tách chuỗi theo dấu chấm, bộ phân tích phải **giữ lại các phần tử rỗng**, bao gồm phần tử cuối nếu chuỗi kết thúc bằng dấu chấm. Một thao tác split mặc định có thể loại bỏ phần tử rỗng cuối trong một số ngôn ngữ/thư viện; dùng cách tách có bảo toàn phần rỗng hoặc tự kiểm tra vị trí dấu phân cách.

## 6. Cách đọc cấu trúc JWS Compact

Ví dụ một JWS Compact có dạng:

~~~text
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
.
eyJzdWIiOiJjdXN0b21lci00MiIsInNjb3BlIjoib3JkZXJzOnJlYWQifQ
.
<base64url-signature>
~~~

Khi viết thành một dòng, token gồm ba segment:

1. **Segment 1:** Base64url của UTF-8 JSON protected header.
2. **Segment 2:** Base64url của payload bytes. Với JWT thông thường, payload là UTF-8 JSON Claims Set.
3. **Segment 3:** Base64url của byte chữ ký hoặc MAC.

Ví dụ giải mã hai segment đầu cho kết quả:

~~~json
{
  "alg": "HS256",
  "typ": "JWT"
}
~~~

~~~json
{
  "sub": "customer-42",
  "scope": "orders:read"
}
~~~

Signature trong ví dụ là placeholder nên đây **không phải token có thể xác minh**. Việc giải mã header và payload chỉ cho thấy nội dung biểu diễn; nó không xác minh signature.

### Dấu chấm cũng nằm trong dữ liệu được ký

Với JWS Compact, signing input được tạo từ hai segment nguyên bản và dấu chấm ở giữa:

~~~text
signingInput = ASCII(
    receivedHeaderPart + "." + receivedPayloadPart
)
~~~

Dấu chấm giữa header và payload là một phần của signing input. Không ký chuỗi JSON đã parse, không bỏ dấu chấm, không thay đổi segment rồi mới xác minh. Nếu bất kỳ byte nào của hai segment thay đổi, signing input thay đổi và signature ban đầu không còn phù hợp.

## 7. Cách đọc cấu trúc JWE Compact

JWE Compact có năm segment:

~~~text
protectedHeader.encryptedKey.iv.ciphertext.authenticationTag
~~~

| Segment | Nội dung sau khi Base64url decode | Có thể rỗng? |
| --- | --- | --- |
| 1. Protected Header | UTF-8 JSON mô tả `alg`, `enc` và metadata | Không trong JWE hợp lệ |
| 2. Encrypted Key | Byte khóa nội dung được bọc/mã hóa | Có, tùy `alg` |
| 3. IV | Byte initialization vector/nonce | Không; độ dài phụ thuộc thuật toán mã hóa nội dung |
| 4. Ciphertext | Byte plaintext sau mã hóa | Không với JWT Claims Set JSON; độ dài phụ thuộc nội dung và thuật toán |
| 5. Authentication Tag | Byte tag xác thực | Không; độ dài phụ thuộc thuật toán mã hóa nội dung |

Ví dụ minh họa hình thức:

~~~text
eyJhbGciOiJSU0EtT0FFUC0yNTYiLCJlbmMiOiJBMjU2R0NNIn0
.
<base64url-encrypted-key>
.
<base64url-iv>
.
<base64url-ciphertext>
.
<base64url-authentication-tag>
~~~

Các giá trị trong ví dụ là placeholder để chỉ vị trí segment, không phải Base64url thực tế và không tạo thành JWE có thể giải mã.

Trong JWE Compact, **AAD (Additional Authenticated Data)** là byte ASCII của segment protected header đã Base64url:

~~~text
AAD = ASCII(protectedHeaderSegment)
~~~

Bên nhận phải dùng đúng segment header gốc để xác thực tag. Không parse header JSON rồi serialize lại hoặc tạo Base64url mới trước khi giải mã có xác thực.

Các segment còn lại được Base64url decode để lấy byte theo yêu cầu của thuật toán; riêng ciphertext vẫn là byte đã mã hóa, không phải JSON có thể đọc trực tiếp. Phải khôi phục CEK và xác thực tag thành công trước khi sử dụng plaintext.

## 8. Base64url không phải mã hóa và không phải chữ ký

Ba thao tác sau có mục đích khác nhau:

| Cơ chế | Mục đích | Có giữ bí mật dữ liệu? | Có xác minh toàn vẹn? |
| --- | --- | --- | --- |
| **Base64url** | Biểu diễn byte thành ký tự | Không | Không |
| **JWS Signature/MAC** | Phát hiện sửa đổi và xác thực theo khóa | Không mã hóa payload | Có |
| **JWE Authenticated Encryption** | Mã hóa nội dung và xác thực dữ liệu mã hóa | Có | Có, theo khóa mã hóa |

Ví dụ, bất kỳ ai có JWS đều có thể Base64url decode header và payload mà không cần khóa ký. Với JWE, Base64url decode segment ciphertext chỉ trả về byte mã hóa; cần CEK và bước giải mã có xác thực mới lấy được plaintext.

**Không dùng Base64url để che giấu mật khẩu, khóa bí mật hoặc thông tin cá nhân.** Nếu claim cần được giữ kín, cần dùng JWE hoặc một cơ chế bảo vệ dữ liệu phù hợp. Nếu cần xác minh nhà phát hành, cần chữ ký số/MAC và chính sách khóa đáng tin; JWE được mã hóa bằng khóa công khai của bên nhận không tự chứng minh ai đã tạo token.

## 9. Quy trình parse và kiểm tra segment an toàn

~~~mermaid
flowchart TD
    A["Nhận chuỗi Compact"] --> B{"Độ dài đầu vào trong giới hạn?"}
    B -- "Không" --> X["Từ chối"]
    B -- "Có" --> C["Tách theo dấu chấm, giữ segment rỗng"]
    C --> D{"Đúng 3 phần JWS hoặc 5 phần JWE?"}
    D -- "Không" --> X
    D -- "Có" --> E["Kiểm tra từng segment theo Base64url Compact"]
    E --> F{"Alphabet, padding, độ dài và biểu diễn hợp lệ?"}
    F -- "Không" --> X
    F -- "Có" --> G["Decode các segment theo đúng vai trò"]
    G --> H["Xác minh JWS hoặc giải mã/xác thực JWE"]
    H --> I{"Kiểm tra mật mã thành công?"}
    I -- "Không" --> X
    I -- "Có" --> J["Parse JSON và kiểm tra claim theo chính sách"]
~~~

Một bộ xử lý nên thực hiện các bước sau:

1. **Giới hạn đầu vào:** đặt giới hạn kích thước token trước khi tách hoặc decode để tránh tiêu thụ quá nhiều bộ nhớ và CPU.
2. **Xác định loại cấu trúc dự kiến:** giao thức hoặc endpoint phải biết đang chờ JWS hay JWE; không chỉ đoán loại token dựa vào nội dung không đáng tin.
3. **Tách segment chính xác:** JWS Compact cần ba segment, JWE Compact cần năm segment; giữ cả segment rỗng.
4. **Kiểm tra Base64url:** chỉ chấp nhận alphabet `A-Z`, `a-z`, `0-9`, `-`, `_`; Compact Serialization không có padding `=`; kiểm tra độ dài và biểu diễn hợp lệ.
5. **Decode theo vai trò:** segment JSON header/payload, signature, encrypted key, IV, ciphertext và tag có ý nghĩa khác nhau; không xử lý tất cả như JSON text.
6. **Xác minh hoặc giải mã:** JWS phải xác minh trên signing input nguyên bản; JWE phải giải mã có xác thực với đúng AAD và từ chối khi tag không hợp lệ.
7. **Kiểm tra nội dung:** chỉ sau bước mật mã thành công mới parse claims và áp dụng chính sách `iss`, `aud`, thời hạn, quyền và các điều kiện khác.

Không được tự sửa token lỗi bằng cách thay `+` thành `-`, `/` thành `_`, bỏ ký tự lạ hoặc xóa padding rồi coi token đã hợp lệ. Nếu token sai định dạng, cần từ chối. Tự động sửa có thể tạo ra nhiều biểu diễn khác nhau cho cùng một dữ liệu và làm các thành phần trong hệ thống hiểu token không nhất quán.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng Base64 chuẩn thay vì Base64url | Segment có thể chứa `+` hoặc `/`, không đúng định dạng JOSE Compact | Dùng encoder Base64url |
| Giữ dấu `=` padding trong segment Compact | Chuỗi không tuân thủ Base64url không padding của JOSE Compact | Bỏ padding khi encode; decoder khôi phục nội bộ nếu cần |
| Nghĩ Base64url là mã hóa | Để lộ payload JWS vì ai cũng có thể decode | Dùng JWE nếu cần bảo mật nội dung |
| Split theo dấu chấm và bỏ phần rỗng | Làm sai số segment, đặc biệt với Encrypted Key rỗng hoặc signature rỗng | Giữ các segment rỗng khi tách |
| Đếm nhầm số phần | Xử lý nhầm JWS thành JWE hoặc ngược lại | Kiểm tra đúng 3 segment/2 dấu chấm hoặc 5 segment/4 dấu chấm |
| Chấp nhận khoảng trắng hoặc ký tự ngoài alphabet | Parser có thể xử lý token khác nhau | Kiểm tra định dạng nghiêm ngặt |
| Decode rồi serialize lại trước khi xác minh | Thay đổi signing input hoặc AAD | Dùng nguyên văn segment gốc |
| Tự thay `+`, `/` hoặc padding để “cứu” token | Che giấu lỗi tạo token và tạo cách hiểu không thống nhất | Từ chối token sai định dạng |
| Chỉ kiểm tra đủ segment mà không xác minh mật mã | Token giả mạo vẫn có thể được đưa vào logic ứng dụng | Xác minh JWS hoặc JWE trước khi tin nội dung |

## 11. Ví dụ thực tế: token đi qua nhiều thành phần hệ thống

Một dịch vụ phát hành JWT gửi token đến API qua header HTTP:

~~~http
Authorization: Bearer <jwt-compact-token>
~~~

API nhận được chuỗi Compact và thực hiện:

- Kiểm tra kích thước token và số segment theo loại token được endpoint chấp nhận.
- Kiểm tra từng segment có đúng alphabet Base64url không padding.
- Giữ nguyên segment gốc để xác minh JWS hoặc dùng làm AAD khi giải mã JWE.
- Xác minh signature hoặc authentication tag theo thuật toán và khóa được cấu hình.
- Sau khi xác minh, parse claim và kiểm tra issuer, audience, thời hạn và quyền.

Một hệ thống log hoặc gateway không được tự động decode rồi tái tạo token theo cách serialize riêng. Việc này có thể làm thay đổi signing input hoặc AAD. Nếu cần ghi log để chẩn đoán, nên ghi trạng thái xử lý, mã tương quan và metadata an toàn; không ghi nguyên bearer token.

Base64url làm cho segment có bảng ký tự thuận tiện khi truyền, nhưng **không bảo vệ token khỏi bị đánh cắp**. Cần bảo vệ kênh truyền, lưu trữ, log và vòng đời token theo chính sách phù hợp.

## 12. Tự kiểm tra kiến thức

1. Base64url thay những ký tự nào so với Base64 chuẩn?
2. Vì sao JOSE Compact bỏ ký tự padding `=`?
3. Tại sao dấu chấm có thể làm ký tự phân cách giữa các segment Base64url?
4. JWS Compact có bao nhiêu segment và JWE Compact có bao nhiêu segment?
5. Vì sao thao tác split phải giữ lại segment rỗng?
6. Segment nào trong JWE có thể rỗng khi dùng `alg = dir`?
7. Vì sao Base64url decode payload JWS không cần khóa nhưng vẫn chưa chứng minh token hợp lệ?
8. Dấu chấm giữa header và payload tham gia vào signing input JWS như thế nào?
9. Vì sao không được parse rồi serialize lại header trước khi dùng nó làm AAD của JWE?
10. Nếu một segment có ký tự `+`, `/` hoặc `=` trong JWT Compact, bộ xử lý nên làm gì?

**Ghi nhớ:** Base64url là cách biểu diễn byte dùng alphabet `-` và `_` thay cho `+` và `/`; trong JOSE Compact, padding `=` bị bỏ. Dấu chấm ASCII phân chia ba segment của JWS hoặc năm segment của JWE. Khi parse phải kiểm tra đúng số phần, giữ phần rỗng và xác minh mật mã trên dữ liệu gốc. Base64url chỉ giúp truyền dữ liệu; tính toàn vẹn, xác thực và bí mật đến từ cơ chế bảo vệ mật mã phù hợp.

### Tài liệu chuẩn để tra cứu

- **RFC 4648 — The Base16, Base32, and Base64 Data Encodings:** bảng ký tự Base64url, padding và quy tắc biểu diễn.
- **RFC 7515 — JSON Web Signature (JWS):** JWS Compact Serialization, Base64url và signing input.
- **RFC 7516 — JSON Web Encryption (JWE):** JWE Compact Serialization, năm segment và Additional Authenticated Data.
- **RFC 7519 — JSON Web Token (JWT):** JWT được biểu diễn bằng JWS/JWE và các yêu cầu liên quan.
- **RFC 8725 — JSON Web Token Best Current Practices:** xử lý JWT an toàn, xác minh đúng loại token và chính sách thuật toán.

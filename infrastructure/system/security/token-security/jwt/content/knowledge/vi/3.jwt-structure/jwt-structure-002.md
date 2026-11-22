# Năm thành phần của JWT dạng JWE Compact

## 1. JWT dạng JWE Compact là gì?

Trong phạm vi **Security - JSON Web Token (JWT)**, JWT là định dạng mang các *claim* về chủ thể và ngữ cảnh sử dụng. Khi cần bảo vệ **tính bí mật** của những claim đó, JWT có thể được biểu diễn dưới dạng **JWE (JSON Web Encryption)**. JWE quy định cách đóng gói nội dung đã mã hóa, kèm thông tin quản lý khóa và dữ liệu kiểm tra tính toàn vẹn.

**JWE Compact Serialization** biểu diễn một đối tượng JWE thành chuỗi gồm **năm phần**, cách nhau bằng **bốn dấu chấm**:

~~~text
<protected-header>.<encrypted-key>.<initialization-vector>.<ciphertext>.<authentication-tag>
        (1)               (2)              (3)              (4)               (5)
~~~

Năm phần tương ứng:

1. **JWE Protected Header** — metadata về thuật toán và cách giải mã.
2. **JWE Encrypted Key** — khóa mã hóa nội dung (CEK) đã được bọc/mã hóa, nếu phương thức quản lý khóa cần.
3. **JWE Initialization Vector (IV)** — giá trị khởi tạo/nonce của thuật toán mã hóa nội dung.
4. **JWE Ciphertext** — nội dung đã mã hóa, ví dụ tập hợp claim của JWT.
5. **JWE Authentication Tag** — dữ liệu xác thực nhằm phát hiện sửa đổi trái phép.

Mỗi phần là một chuỗi **Base64url không padding** của dữ liệu tương ứng. Một số phần có thể **rỗng hợp lệ**, nổi bật là Encrypted Key khi dùng thuật toán quản lý khóa trực tiếp; khi đó chuỗi vẫn phải có đúng bốn dấu chấm.

**Phân biệt ngay từ đầu:** JWT dạng **JWS Compact** có ba phần, phục vụ việc ký hoặc tạo MAC. JWT dạng **JWE Compact** có năm phần, phục vụ mã hóa có xác thực. Phần thứ năm của JWE là **authentication tag**, **không phải chữ ký số**. Nếu cần cả chữ ký lẫn mã hóa, có thể dùng JWT lồng nhau (*nested JWT*).

## 2. Tổng quan vai trò của năm thành phần

| Vị trí | Tên chính thức | Giá trị trước khi Base64url | Vai trò | Người chỉ có token có đọc được nội dung không? |
| --- | --- | --- | --- | --- |
| **1** | Protected Header | Byte UTF-8 của JSON header | Chỉ dẫn thuật toán quản lý khóa, mã hóa nội dung và metadata | **Có**, nhưng chưa được tin cậy trước khi xác thực |
| **2** | Encrypted Key | Byte của CEK được mã hóa/bọc; cũng có thể là byte rỗng | Giúp bên nhận lấy CEK để giải mã | **Có thể đọc byte**, nhưng không suy ra được CEK nếu khóa được bảo vệ đúng |
| **3** | Initialization Vector | Byte IV/nonce | Phối hợp cùng CEK trong quá trình mã hóa/giải mã | **Có**; IV không phải bí mật |
| **4** | Ciphertext | Byte kết quả mã hóa plaintext | Giữ bí mật nội dung/claim | **Không**, nếu không có khóa giải mã phù hợp |
| **5** | Authentication Tag | Byte tag do cơ chế mã hóa có xác thực tạo ra | Phát hiện việc thay đổi dữ liệu/header trong quá trình truyền | **Có thể đọc byte**, nhưng không tự tạo tag hợp lệ cho nội dung sửa đổi khi thiếu khóa |

Mối liên hệ giữa các thành phần:

~~~mermaid
flowchart TB
    H["Protected Header JSON"] --> HB["Base64url(header)"]
    HB --> A["AAD = ASCII(headerPart)"]
    K["Khóa tin cậy của bên nhận"] --> KM["Quản lý khóa theo alg"]
    KM --> CEK["Content Encryption Key (CEK)"]
    KM --> EK["Encrypted Key (có thể rỗng)"]
    P["JWT Claims Set / Plaintext"] --> ENC["Mã hóa nội dung theo enc"]
    CEK --> ENC
    IV["IV / nonce"] --> ENC
    A --> ENC
    ENC --> CT["Ciphertext"]
    ENC --> TAG["Authentication Tag"]
    HB --> JWE["JWE Compact: 5 phần"]
    EK --> JWE
    IV --> JWE
    CT --> JWE
    TAG --> JWE
~~~

**Base64url chỉ chuyển byte thành ký tự thuận tiện để truyền đi.** Nó không phải thuật toán mã hóa bí mật. Khả năng giữ kín claim đến từ **Content Encryption**, không đến từ việc nhìn chuỗi token “khó đọc”.

## 3. Phần 1 — JWE Protected Header

Protected Header là JSON chứa những tham số mô tả cách tạo JWE. Ví dụ:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "typ": "JWT",
  "kid": "recipient-key-01"
}
~~~

Các trường đáng chú ý:

| Trường | Ý nghĩa | Ví dụ/lưu ý |
| --- | --- | --- |
| **alg** | Thuật toán **quản lý khóa**: xác định cách bên phát hành cung cấp/thiết lập CEK cho bên nhận | **RSA-OAEP-256**, **ECDH-ES**, **dir**, **A256KW** |
| **enc** | Thuật toán **mã hóa nội dung có xác thực** bằng CEK | **A256GCM**, **A128GCM**, **A128CBC-HS256** |
| **typ** | Gợi ý loại đối tượng | Thường là **JWT**, có thể vắng mặt theo ngữ cảnh |
| **kid** | Định danh khóa nhằm chọn khóa ứng viên | Chỉ là gợi ý tra cứu trong tập khóa **đã tin cậy** |
| **cty** | Loại nội dung nằm bên trong | Thường dùng **JWT** khi JWE chứa một JWT lồng nhau |
| **zip** | Thuật toán nén plaintext trước khi mã hóa | **DEF** khi giao thức hỗ trợ; nên hạn chế nén dữ liệu nhạy cảm |

Trong **JWE Compact**, header được chuyển thành Base64url và đặt ở **phần 1**. Bên ngoài vẫn đọc được thuật toán, **kid** và metadata khác; **không đặt bí mật cần che giấu trong header**.

Header gọi là **protected** vì dạng Base64url nguyên gốc của nó được đưa vào dữ liệu xác thực bổ sung (*Additional Authenticated Data — AAD*) của quá trình mã hóa, giúp phát hiện thay đổi header khi kiểm tra authentication tag. Tên “protected” **không có nghĩa được mã hóa để giấu nội dung**.

**alg và enc có hai chức năng khác nhau:**

- **alg** quyết định cách thiết lập/trao đổi hoặc bọc **CEK**.
- **enc** quyết định cách **CEK** mã hóa plaintext và tạo ra ciphertext, IV, authentication tag.

Không nên để một token tự quyết định tùy ý thuật toán được sử dụng. Hệ thống nhận phải đối chiếu cả **alg**, **enc**, loại khóa, công dụng khóa và nhà phát hành/kênh nhận với chính sách đã cấu hình trước. Dữ liệu **kid** không được biến thành đường dẫn file, URL tải khóa hoặc câu truy vấn tùy ý do token kiểm soát.

JWE Compact chỉ chứa **protected header**; các cơ chế như *unprotected header* hay *external AAD* là khả năng của những cách biểu diễn JWE khác, chẳng hạn JWE JSON Serialization, chứ không có phân đoạn riêng trong Compact.

## 4. Phần 2 — JWE Encrypted Key

Trong mã hóa JWE, **CEK (Content Encryption Key)** là khóa thực tế dùng để mã hóa và giải mã plaintext theo thuật toán **enc**. Phần Encrypted Key biểu diễn kết quả của cơ chế quản lý khóa theo **alg**.

### Trường hợp CEK được bọc hoặc mã hóa

Chẳng hạn với **alg = RSA-OAEP-256**:

1. Bên phát hành tạo một CEK ngẫu nhiên, có độ dài phù hợp với **enc**.
2. Bên phát hành mã hóa CEK bằng **khóa công khai** của bên nhận theo RSA-OAEP-256.
3. Byte CEK đã mã hóa được Base64url và đặt ở phần **Encrypted Key**.
4. Bên nhận dùng **khóa riêng tư** tương ứng để khôi phục CEK rồi giải mã ciphertext.

Cách này thường được gọi là **envelope encryption**: nội dung được mã hóa bằng CEK, còn CEK được bảo vệ riêng để chuyển cho bên nhận.

### Trường hợp Encrypted Key rỗng

Không phải lúc nào phần thứ hai cũng có byte dữ liệu. Hai ví dụ:

- **alg = dir** (*direct*) dùng trực tiếp một khóa bí mật đã được phân phối/tin cậy làm CEK. Không có CEK được bọc riêng, vì vậy **Encrypted Key là chuỗi rỗng**.
- **alg = ECDH-ES** ở chế độ thỏa thuận khóa trực tiếp dẫn xuất CEK từ bí mật chung của phép thỏa thuận khóa; phần **Encrypted Key cũng rỗng**.

Ngược lại, các biến thể như **ECDH-ES+A256KW** có bước bọc CEK nên **Encrypted Key có nội dung**.

| Cơ chế quản lý khóa | CEK được cung cấp thế nào? | Phần 2 |
| --- | --- | --- |
| **dir** | Dùng thẳng khóa bí mật đã chia sẻ | Rỗng |
| **RSA-OAEP-256** | CEK ngẫu nhiên được mã hóa bằng khóa công khai của bên nhận | Có dữ liệu |
| **ECDH-ES** | Dẫn xuất CEK trực tiếp bằng thỏa thuận khóa | Rỗng |
| **ECDH-ES+A256KW** | Dẫn xuất khóa bọc, rồi bọc CEK | Có dữ liệu |
| **A256KW** | Bọc CEK bằng khóa bí mật quản lý khóa | Có dữ liệu |

Vì vậy, dạng chuỗi như sau có thể là một **JWE Compact hợp lệ về mặt bố cục**:

~~~text
headerPart..ivPart.ciphertextPart.tagPart
           ^^
     Encrypted Key rỗng
~~~

Đây chỉ là ký hiệu minh họa, chưa phải token xác minh được. Hai dấu chấm đứng cạnh nhau biểu thị **phần thứ hai rỗng**; tổng thể vẫn là năm phần. **Phần rỗng không có nghĩa token thiếu mã hóa.**

## 5. Phần 3 — Initialization Vector (IV)

**IV** hoặc **nonce** là giá trị đầu vào phối hợp với CEK khi thuật toán **enc** mã hóa plaintext. IV thường không cần giữ bí mật, nên JWE truyền nó công khai tại phần 3.

Với **A256GCM**, IV phổ biến có độ dài **96 bit (12 byte)** và cần đảm bảo **không tái sử dụng cùng IV với cùng khóa**. Tái sử dụng cặp **CEK + nonce** trong GCM có thể gây hậu quả nghiêm trọng cho tính bí mật và toàn vẹn. Những thuật toán mã hóa nội dung khác có thể đặt yêu cầu khác về độ dài và cách tạo IV.

Ví dụ minh họa:

~~~text
CEK = khóa dùng cho A256GCM
IV  = 12 byte nonce được tạo theo cơ chế an toàn
ciphertext, tag = AEAD_ENCRYPT(CEK, IV, plaintext, AAD)
~~~

Không nên tự ghép IV từ thời gian hệ thống, mã người dùng hoặc một bộ đếm không được quản lý đúng theo yêu cầu thuật toán. Nên dùng thư viện mật mã có uy tín và tuân theo cơ chế tạo IV mà thư viện/đặc tả hỗ trợ.

## 6. Phần 4 — Ciphertext

**Ciphertext** là byte của nội dung sau khi được mã hóa bằng CEK và IV theo thuật toán **enc**. Với JWT dạng JWE thông thường, plaintext đầu vào là JSON **JWT Claims Set** đã mã hóa UTF-8, chẳng hạn:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456300
}
~~~

Các giá trị thời gian là ví dụ về **NumericDate** (giây kể từ Unix epoch), chỉ để minh họa thời hạn 300 giây. Khi tạo JWE, JSON này được mã hóa thành **ciphertext**; bên chỉ có chuỗi token **không thể đọc các claim bằng cách giải Base64url phần 4**.

Mã hóa giúp giữ kín nội dung nhưng không làm biến mất mọi tín hiệu bên ngoài: header, độ dài các phân đoạn, kích thước ciphertext và một số metadata giao thức vẫn có thể quan sát được. Nếu có nén plaintext trước khi mã hóa (**zip**), cần đánh giá riêng nguy cơ tiết lộ thông tin qua độ dài dữ liệu và nội dung do phía không tin cậy kiểm soát.

**Trường hợp JWT lồng nhau:** plaintext có thể là **một JWT đã được ký theo JWS Compact**, tức là chuỗi dạng ba phần, thay vì JSON claim trực tiếp. Khi đó JWE bảo vệ toàn bộ chuỗi JWS bên trong và outer header thường có **cty: "JWT"** để bên nhận xử lý đúng loại nội dung sau giải mã.

## 7. Phần 5 — Authentication Tag

**Authentication Tag** được tạo trong cơ chế mã hóa có xác thực. Nó cho phép bên nhận kiểm tra rằng ciphertext và dữ liệu liên quan, bao gồm **Protected Header** trong JWE Compact, không bị sửa đổi mà vẫn vượt qua bước xác thực mật mã.

Ví dụ với **A256GCM**, phép mã hóa tạo ra **hai đầu ra logic**:

~~~text
(ciphertext, tag) = AES-256-GCM-ENCRYPT(
    key       = CEK,
    nonce     = IV,
    plaintext = UTF8(JSON(claims)),
    aad       = ASCII(headerPart)
)
~~~

Trong JWE Compact, **ciphertext** được đặt tại phần 4, **tag** được đặt riêng tại phần 5. Với A256GCM theo JWA, tag có độ dài **128 bit (16 byte)**.

Nếu ai đó thay đổi header, ciphertext, IV hoặc tag, bước giải mã có xác thực sẽ không thành công, trừ khi người đó có khả năng tạo dữ liệu hợp lệ theo khóa tương ứng. Bộ giải mã phải **từ chối** khi tag không hợp lệ và không trả về plaintext chưa được xác thực để ứng dụng sử dụng.

**Tag không phải chữ ký số.** Nó kiểm chứng tính toàn vẹn/xác thực gắn với cơ chế mã hóa và khóa liên quan, nhưng **không mặc nhiên chứng minh ai là người phát hành JWT**. Đặc biệt, nếu một người biết **khóa công khai của bên nhận**, họ có thể tạo một JWE mã hóa bằng khóa công khai đó. Bên nhận giải mã thành công **không đủ** để kết luận JWE đến từ một nhà phát hành tin cậy.

Muốn xác thực nhà phát hành một cách độc lập với việc mã hóa cho bên nhận, giao thức có thể yêu cầu **JWT được ký trước rồi mã hóa**; sau giải mã phải xác minh tiếp chữ ký JWS bên trong.

## 8. Cách năm phần được tạo ra

Quy trình tổng quát của JWT dạng JWE Compact có thể biểu diễn như sau:

~~~text
protectedHeader = {
    "alg": "RSA-OAEP-256",
    "enc": "A256GCM",
    "typ": "JWT"
}

plaintext = UTF8(JSON(jwtClaimsSet))

headerPart = BASE64URL(UTF8(JSON(protectedHeader)))
aad        = ASCII(headerPart)

(cek, encryptedKey) = PREPARE_CEK_AND_ENCRYPTED_KEY(
    alg = protectedHeader.alg,
    recipientKey = trustedRecipientKey
)

iv = GENERATE_IV_SAFELY(enc = protectedHeader.enc, cek)

(ciphertext, tag) = AUTHENTICATED_ENCRYPT(
    enc = protectedHeader.enc,
    key = cek,
    iv = iv,
    plaintext = plaintext,
    aad = aad
)

token = headerPart
      + "." + BASE64URL(encryptedKey)
      + "." + BASE64URL(iv)
      + "." + BASE64URL(ciphertext)
      + "." + BASE64URL(tag)
~~~

Đoạn trên là **giả mã độc lập ngôn ngữ**, nhằm giải thích mối quan hệ giữa năm phần. Chi tiết về cách tạo CEK, bọc khóa, chiều dài IV và tag phải tuân theo cặp thuật toán **alg + enc** cụ thể. Không nên tự triển khai lại primitive mật mã chỉ từ giả mã này.

### Chi tiết dễ bỏ sót: AAD nằm ở đâu?

Trong **JWE Compact**, dữ liệu xác thực bổ sung (**AAD**) chính là các byte ASCII của **headerPart đã Base64url**, trước dấu chấm đầu tiên:

~~~text
AAD = ASCII(BASE64URL(UTF8(JSON(JWE Protected Header))))
~~~

Không có một “phần AAD thứ sáu”. AAD được dùng khi tạo và kiểm tra authentication tag; vì vậy, dù header hiển thị công khai, sửa header cũng làm xác thực thất bại. Khi giải mã cần dùng **nguyên văn phần 1 nhận được**, không parse JSON rồi serialize lại theo thứ tự thuộc tính hoặc khoảng trắng mới.

## 9. Quy trình đọc, giải mã và xác minh

~~~mermaid
flowchart TD
    A["Nhận JWE Compact"] --> B{"Đúng 5 phần, Base64url hợp lệ, kích thước cho phép?"}
    B -- "Không" --> X["Từ chối"]
    B -- "Có" --> C["Đọc Protected Header (chưa tin cậy)"]
    C --> D{"alg, enc, loại khóa, kiểu token được cho phép?"}
    D -- "Không" --> X
    D -- "Có" --> E["Lấy khóa nhận từ nguồn đã tin cậy; khôi phục CEK"]
    E --> F["Giải mã có xác thực bằng IV, ciphertext, tag và AAD headerPart"]
    F --> G{"Kiểm tra mật mã thành công?"}
    G -- "Không" --> X
    G -- "Có" --> H{"Payload là JWT lồng nhau?"}
    H -- "Có" --> I["Xác minh JWT bên trong theo chính sách"]
    H -- "Không" --> J["Parse JWT Claims Set"]
    I --> K["Kiểm tra claim và quyền"]
    J --> K
    K --> L{"iss, aud, thời gian, scope... hợp lệ?"}
    L -- "Không" --> X
    L -- "Có" --> M["Xử lý yêu cầu theo quyền được cấp"]
~~~

Các kiểm tra thiết yếu:

1. **Kiểm tra khuôn dạng:** đúng số phần; Base64url hợp lệ; JSON header, độ dài dữ liệu và các tham số đáp ứng quy tắc JWE. Không suy ra token đáng tin chỉ vì có bốn dấu chấm.
2. **Kiểm tra chính sách thuật toán:** chỉ cho phép những cặp **alg + enc** đã được hệ thống lựa chọn trước; không tự động tin lựa chọn từ header.
3. **Chọn khóa tin cậy:** nếu có **kid**, chỉ dùng nó để tra cứu trong tập khóa hợp lệ; kiểm tra khóa gắn với bên nhận/nhà phát hành và có công dụng phù hợp.
4. **Giải mã có xác thực:** khôi phục CEK, dùng đúng IV, ciphertext, tag và **AAD = headerPart**; từ chối nếu tag/khóa/ciphertext không hợp lệ.
5. **Hiểu nội dung sau giải mã:** nếu là JWT Claims Set, parse JSON; nếu là JWT lồng nhau, xử lý và xác minh lớp bên trong trước khi dùng claim.
6. **Kiểm tra claim và phân quyền:** xác thực **iss**, **aud**, **exp**, **nbf** và các trường bắt buộc khác theo giao thức; đánh giá quyền theo ngữ cảnh sử dụng.

Vì **JWE chủ yếu bảo vệ tính bí mật và toàn vẹn của bản mã**, thành công ở bước giải mã **không miễn trừ** các kiểm tra claim, sự tin cậy đối với nhà phát hành, quyền truy cập hoặc chính sách chống phát lại/thu hồi token.

Thông báo lỗi trả về bên ngoài nên tránh tiết lộ chi tiết nhạy cảm về khóa, tag, plaintext hoặc lý do giải mã thất bại; hệ thống vẫn có thể ghi nhận thông tin chẩn đoán an toàn trong phạm vi nội bộ phù hợp.

## 10. Ví dụ thực tế: truyền claim nhạy cảm đến một API

Giả sử dịch vụ danh tính cần gửi một JWT mang thông tin nhạy cảm đến **API hồ sơ khách hàng**:

- **Protected Header:** khai báo **alg = RSA-OAEP-256**, **enc = A256GCM** và **kid** của khóa công khai API.
- **Encrypted Key:** chứa CEK được mã hóa bằng khóa công khai API.
- **IV:** nonce dùng một lần theo yêu cầu A256GCM.
- **Ciphertext:** chứa bản mã của các claim như **sub**, **aud**, **exp** và thuộc tính cần bảo vệ.
- **Authentication Tag:** cho phép API kiểm tra dữ liệu không bị sửa trái phép.

API dùng khóa riêng tư tương ứng để khôi phục CEK, giải mã và xác thực tag. Sau đó API phải kiểm tra **aud** đúng mình, **exp** còn hiệu lực và quyền truy cập phù hợp.

Có một điểm quan trọng: **ai có khóa công khai của API cũng có thể tạo một JWE mã hóa cho API**. Nếu API cần chắc chắn claim đến từ **dịch vụ danh tính được tin cậy**, thiết kế có thể yêu cầu dịch vụ danh tính **ký JWS trước, rồi mã hóa JWS thành JWE**. Khi nhận, API giải mã JWE và xác minh chữ ký JWS bên trong trước khi chấp nhận claim.

Ví dụ khái niệm:

~~~text
JWT Claims Set
    |
    v
JWS Compact: header.payload.signature     <- ký bằng khóa phát hành
    |
    v
JWE Compact: h.ek.iv.ciphertext.tag        <- mã hóa cho bên nhận
    |
    v
Bên nhận: giải mã JWE -> xác minh JWS -> kiểm tra claim và quyền
~~~

Cách lồng này phục vụ hai mục tiêu riêng: **bảo mật nội dung** và **kiểm chứng nguồn ký**. Không thể thay thế việc xác minh chữ ký bên trong bằng phép giải mã JWE bên ngoài.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “JWT luôn có ba phần.” | **JWS Compact** có ba phần; **JWE Compact** có năm phần. |
| “Phần 5 của JWE là signature.” | Phần 5 là **authentication tag**; JWE Compact không có trường signature tách riêng. |
| “Protected Header đã được mã hóa, không thể đọc.” | Header là **Base64url của JSON**, đọc được; **tag bảo vệ tính toàn vẹn** của header. |
| “alg và enc là hai tên khác nhau cho cùng thuật toán.” | **alg** quản lý/thiết lập CEK, **enc** mã hóa nội dung bằng CEK. |
| “Encrypted Key rỗng nghĩa là token không có mã hóa.” | Với **dir** hoặc **ECDH-ES** trực tiếp, phần 2 rỗng là thiết kế hợp lệ. |
| “IV phải bí mật như khóa.” | IV có thể công khai; điều thiết yếu là đáp ứng yêu cầu duy nhất/không tái sử dụng của thuật toán. |
| “Giải Base64url ciphertext sẽ hiện JSON.” | Chỉ thu được **byte mã hóa**; muốn có plaintext cần CEK và xác thực tag thành công. |
| “Giải mã được là chắc chắn token do đơn vị tin cậy phát hành.” | Đặc biệt với mã hóa bằng khóa công khai, **bất kỳ ai có khóa công khai** cũng có thể tạo JWE; có thể cần chữ ký JWS bên trong. |
| “Có đủ năm phần nên token hợp lệ.” | Còn phải kiểm tra định dạng, chính sách thuật toán, khóa, tag, claim và quyền. |
| “JWE cho phép bỏ HTTPS và bỏ kiểm soát vòng đời token.” | Vẫn cần bảo vệ kênh truyền, khóa, log, thời hạn và nguy cơ token bị đánh cắp/phát lại. |

## 12. Tự kiểm tra kiến thức

1. Hãy kể đúng thứ tự năm phần trong JWE Compact và giải thích vì sao có bốn dấu chấm.
2. **alg** khác **enc** ở nhiệm vụ nào? CEK được dùng ở giai đoạn nào?
3. Khi **alg = dir**, tại sao phần Encrypted Key vẫn có thể rỗng mà ciphertext vẫn được bảo vệ?
4. Vì sao Protected Header đọc được nhưng sửa nó lại có thể khiến kiểm tra authentication tag thất bại?
5. IV có phải dữ liệu bí mật không? Tại sao tái sử dụng IV với cùng CEK trong GCM nguy hiểm?
6. Vì sao giải mã JWE thành công chưa đủ chứng minh người phát hành đáng tin, nhất là khi bên nhận công khai khóa mã hóa?
7. Trong trường hợp JWT được ký rồi mã hóa, bên nhận phải xác minh theo thứ tự nào?

**Ghi nhớ:** Dạng **JWE Compact = Protected Header . Encrypted Key . IV . Ciphertext . Authentication Tag**. Phần 1 mô tả thuật toán và được bảo vệ tính toàn vẹn; phần 2 giúp thiết lập CEK; phần 3 cung cấp IV; phần 4 mang nội dung đã mã hóa; phần 5 xác thực dữ liệu mã hóa. Khi áp dụng vào JWT, giải mã an toàn phải đi cùng **xác thực nội dung và kiểm tra claim/quyền truy cập theo chính sách**.

### Tài liệu chuẩn để tra cứu

- **RFC 7516 — JSON Web Encryption (JWE):** năm thành phần của Compact Serialization, AAD, cấu trúc mã hóa và giải mã.
- **RFC 7518 — JSON Web Algorithms (JWA):** các thuật toán quản lý khóa và mã hóa nội dung như RSA-OAEP-256, dir và A256GCM.
- **RFC 7519 — JSON Web Token (JWT):** JWT Claims Set, cách JWT dùng JWE và quy tắc JWT lồng nhau.
- **RFC 8725 — JSON Web Token Best Current Practices:** chính sách thuật toán, xác minh đúng ngữ cảnh và những lưu ý bảo mật khi xử lý JWT.

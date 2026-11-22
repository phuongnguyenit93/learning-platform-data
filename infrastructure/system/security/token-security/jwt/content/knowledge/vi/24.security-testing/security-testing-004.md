# Token thiếu phần, Base64url sai và JSON không hợp lệ

JWT là dữ liệu có cấu trúc theo một định dạng serialization cụ thể. Một token bị thiếu segment, chứa ký tự Base64url sai, giải mã thành UTF-8 không hợp lệ hoặc có payload JSON sai cú pháp phải bị từ chối trước khi được dùng để xác thực hay phân quyền. Parser quá dễ dãi có thể khiến API gateway, thư viện JWT và resource server diễn giải cùng một chuỗi theo các cách khác nhau, tạo ra parser differential và đường bypass kiểm soát bảo mật.

Bài học thuộc chương **Kiểm thử bảo mật** của module **Security – JSON Web Token (JWT)**. Nội dung hướng dẫn nhận diện cấu trúc JWS/JWE Compact Serialization, kiểm tra segment, giải mã Base64url nghiêm ngặt, phân tích UTF-8/JSON an toàn, giới hạn tài nguyên và xây dựng bộ kiểm thử malformed token. Các nguyên tắc áp dụng cho mọi ngôn ngữ, runtime, thư viện và nền tảng.

## 1. JWT có cấu trúc serialization cụ thể

Trước khi kiểm tra token malformed, cần biết token đang dùng dạng serialization nào. JWT có thể được bảo vệ bằng JWS (ký hoặc MAC) hoặc JWE (mã hóa). Dạng compact của hai loại có số segment khác nhau.

### 1.1. JWS Compact Serialization có ba segment

JWS Compact Serialization có dạng:

~~~text
BASE64URL(Protected Header)
.
BASE64URL(Payload)
.
BASE64URL(Signature)
~~~

Viết trên một dòng:

~~~text
header.payload.signature
~~~

Ba segment được phân cách bằng đúng hai dấu chấm:

| Segment | Nội dung | Vai trò |
| --- | --- | --- |
| Segment 1 | JOSE Protected Header đã Base64url | Cho biết thuật toán và tham số bảo vệ |
| Segment 2 | Payload đã Base64url | Với JWT claims set, chứa JSON claims |
| Segment 3 | Chữ ký hoặc MAC đã Base64url | Bảo vệ tính toàn vẹn và nguồn phát hành theo thuật toán |

Ví dụ minh họa cấu trúc:

~~~text
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vLXVzZXItMDEiLCJhdWQiOiJodHRwczovL2FwaS5leGFtcGxlIn0.SYNTHETIC_SIGNATURE
~~~

Đây chỉ là chuỗi minh họa, không phải token đã ký hợp lệ.

### 1.2. JWE Compact Serialization có năm segment

JWE Compact Serialization có dạng:

~~~text
BASE64URL(Protected Header)
.
BASE64URL(Encrypted Key)
.
BASE64URL(Initialization Vector)
.
BASE64URL(Ciphertext)
.
BASE64URL(Authentication Tag)
~~~

Viết trên một dòng:

~~~text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
~~~

| Segment | Nội dung |
| --- | --- |
| Segment 1 | Protected JOSE Header |
| Segment 2 | Encrypted Key; có thể rỗng với một số key management mode |
| Segment 3 | Initialization Vector; quy tắc phụ thuộc thuật toán |
| Segment 4 | Ciphertext |
| Segment 5 | Authentication Tag |

Không được áp dụng quy tắc “mọi JWT đều có đúng ba phần”. Parser phải biết profile/token format mà endpoint hỗ trợ. Nếu endpoint chỉ nhận signed JWT theo JWS, JWE năm phần phải bị từ chối; nếu endpoint nhận JWE, phải xác minh đúng cấu trúc năm phần và giải mã theo thuật toán được cho phép.

### 1.3. Nested JWT

Một JWT có thể được lồng bên trong một JWE hoặc JWS khác. Khi đó, định dạng compact bên ngoài quyết định số segment ở lớp ngoài; payload sau khi giải mã hoặc xác minh có thể là một JWT khác.

Không đoán nested JWT bằng cách đếm dấu chấm trong một chuỗi bất kỳ. Profile cần quy định rõ loại token được chấp nhận, lớp bảo vệ bên ngoài và có cho phép nested JWT hay không.

### 1.4. Không nhầm JWT với mọi chuỗi có ba phần

Một chuỗi có hai dấu chấm không tự động là JWT hợp lệ. Tương tự, một chuỗi có năm phần cũng không tự động là JWE hợp lệ. Cần kiểm tra:

- Đúng compact serialization mà endpoint cho phép.
- Số segment và vị trí segment.
- Base64url hợp lệ ở những segment phải mã hóa.
- JOSE Header là JSON object hợp lệ.
- Payload có cấu trúc phù hợp với token profile.
- Chữ ký/MAC hoặc authentication tag được xác minh.
- Issuer, audience, thời hạn, loại token và policy được đáp ứng.

## 2. Token thiếu phần hoặc thừa phần

Lỗi segment là lớp kiểm tra cấu trúc đầu tiên. Nếu parser tự bỏ dấu chấm thừa, tự nối segment hoặc bỏ qua phần dư, nó có thể xác minh một chuỗi khác với chuỗi mà thành phần trước đó đã xử lý.

### 2.1. Ví dụ JWS malformed

| Chuỗi minh họa | Vấn đề |
| --- | --- |
| header.payload | Thiếu segment chữ ký |
| header | Không có dấu phân cách |
| .payload.signature | Protected header rỗng |
| header..signature | Payload rỗng; không phù hợp JWT claims set thông thường |
| header.payload. | Chữ ký rỗng; không được chấp nhận trong profile access token có xác minh chữ ký |
| header.payload.signature.extra | Thừa segment |
| header.payload.signature. | Có dấu phân cách và segment dư |
| header..signature..extra | Có nhiều segment rỗng và sai số lượng |

Các từ header, payload và signature trong bảng chỉ là placeholder, không phải Base64url hợp lệ.

### 2.2. Ví dụ JWE malformed

| Chuỗi minh họa | Vấn đề |
| --- | --- |
| h.ek.iv.ciphertext | Thiếu authentication tag |
| h.ek.iv.ciphertext.tag.extra | Thừa segment |
| h.ek.iv | Thiếu ciphertext và tag |
| h.ek.iv.ciphertext.tag | Đúng số phần; vẫn phải kiểm tra từng segment và thuật toán |
| h..iv.ciphertext.tag | Encrypted Key rỗng; có thể hợp lệ ở một số key management mode |

Điểm quan trọng: không phải mọi segment rỗng đều có cùng ý nghĩa. Parser phải áp dụng quy tắc theo loại serialization và thuật toán đã được cấu hình. Ví dụ encrypted-key segment của một số JWE key management mode có thể rỗng; nhưng protected header rỗng không thể cung cấp JOSE Header hợp lệ.

### 2.3. Split phải giữ nguyên segment rỗng

Một lỗi triển khai phổ biến là dùng hàm split tự loại bỏ phần tử rỗng. Khi đó:

~~~text
header..signature
~~~

có thể bị biến thành hai phần tử thay vì ba segment. Parser sau đó có thể xử lý sai vị trí segment.

Quy tắc:

- Tách theo dấu chấm nhưng giữ nguyên phần tử rỗng.
- Không trim chuỗi trước khi kiểm tra.
- Không bỏ dấu chấm đầu/cuối.
- Không tự ghép các segment dư.
- Kiểm tra chính xác số segment theo serialization đã chọn.
- Từ chối nếu token có cấu trúc không được profile hỗ trợ.

### 2.4. Detached payload và unsecured JWS

JWS có một số dạng sử dụng đặc biệt, ví dụ detached payload hoặc unsecured JWS. Những dạng đó không nên được tự động chấp nhận như access JWT thông thường.

- Detached payload cần dữ liệu ngoài và quy tắc xác minh riêng; JWT claims set thông thường không nên được xử lý như payload rỗng.
- JWS với alg là none không cung cấp chữ ký để xác minh. Profile access token an toàn phải từ chối dạng unsecured này.
- Tùy chọn unencoded payload với tham số b64=false của RFC 7797 không được phép dùng cho JWT; không chấp nhận cách diễn giải này trong JWT parser.
- Nếu hệ thống không chủ đích hỗ trợ các dạng đặc biệt, hãy từ chối thay vì cố gắng sửa token.

## 3. Base64url là encoding bắt buộc của các segment compact

JWS/JWE Compact Serialization dùng Base64url encoding cho các phần được quy định. Base64url khác Base64 thông thường ở bảng chữ cái và cách xử lý padding.

### 3.1. Bảng chữ cái Base64url

Base64url sử dụng:

~~~text
A-Z
a-z
0-9
-
_
~~~

Khác với Base64 thông thường:

| Base64 thông thường | Base64url |
| --- | --- |
| + | - |
| / | _ |
| Có thể dùng padding = | Compact JWT bỏ padding ở cuối |

Các ký tự sau không thuộc bảng chữ cái Base64url compact:

~~~text
+
/
=
space
tab
CR
LF
~~~

Một decoder dễ dãi có thể chấp nhận chúng hoặc tự sửa chuỗi. Hành vi đó tạo khác biệt giữa các parser.

### 3.2. Kiểm tra độ dài

Với Base64/Base64url, độ dài encoded có một số ràng buộc. Độ dài modulo 4 bằng 1 là không hợp lệ vì không thể biểu diễn một chuỗi byte hợp lệ theo cách mã hóa chuẩn.

Ví dụ:

| Độ dài encoded modulo 4 | Nhận xét |
| --- | --- |
| 0 | Có thể hợp lệ |
| 2 | Có thể hợp lệ; tương ứng phần byte cuối |
| 3 | Có thể hợp lệ; tương ứng phần byte cuối |
| 1 | Không hợp lệ |

Kiểm tra modulo chỉ là một bước. Chuỗi vẫn phải dùng đúng bảng chữ cái, có cấu trúc hợp lệ và giải mã thành dữ liệu đúng định dạng.

### 3.3. Không tự chấp nhận Base64 thông thường

Các chuỗi chứa +, / hoặc = có thể được decoder Base64 thông thường chấp nhận, nhưng không phải dạng Base64url compact chuẩn.

Không nên:

- Thay + thành - và / thành _ một cách âm thầm.
- Bỏ mọi ký tự không hợp lệ rồi tiếp tục decode.
- Tự xóa whitespace.
- Chấp nhận padding tùy ý.
- Dùng decoder MIME có thể bỏ qua CR/LF.
- Dùng decoder tolerant mà không kiểm tra đầu vào trước.

Nếu endpoint hỗ trợ một định dạng khác, hãy khai báo profile riêng. Không nới lỏng parser JWT compact để phục vụ dữ liệu không đúng định dạng.

### 3.4. Padding phải theo đúng serialization

Base64url encoding trong compact serialization bỏ các ký tự padding ở cuối. Một số decoder tổng quát tự thêm padding để giải mã; việc thêm padding nội bộ có thể là bước kỹ thuật cần thiết, nhưng đầu vào vẫn phải được kiểm tra là dạng compact không padding.

Phân biệt:

- **Đầu vào:** kiểm tra alphabet và quy tắc không padding theo serialization.
- **Decoder nội bộ:** có thể bổ sung padding cần thiết trong bộ nhớ để giải mã.
- **Đầu ra kiểm tra:** không ghi lại token đã “sửa” rồi coi nó là token gốc.

Không biến một chuỗi malformed thành token khác mà không có quy tắc giao thức rõ ràng.

## 4. Kiểm tra Base64url nghiêm ngặt

Một quy trình giải mã an toàn:

1. Xác định segment đang giải mã và loại dữ liệu mong đợi.
2. Kiểm tra segment không chứa ký tự ngoài alphabet Base64url cho phép.
3. Kiểm tra độ dài không rơi vào trường hợp modulo 4 bằng 1.
4. Kiểm tra quy tắc padding của compact serialization.
5. Giải mã bằng decoder strict.
6. Nếu profile yêu cầu biểu diễn canonical, mã hóa lại và so sánh với đầu vào.
7. Kiểm tra kích thước dữ liệu sau decode.
8. Chỉ chuyển bytes sang bước tiếp theo nếu mọi điều kiện đạt.

### 4.1. Canonical encoding và nhiều biểu diễn

Một số decoder có thể chấp nhận các chuỗi khác nhau nhưng tạo ra cùng bytes do không kiểm tra các bit dư cuối hoặc padding không chuẩn. Nếu gateway và resource server có quy tắc khác nhau, một token có thể có nhiều cách biểu diễn văn bản.

Để giảm parser differential:

- Dùng decoder strict theo Base64url.
- Không chấp nhận ký tự thay thế hoặc padding ngoài profile.
- Có thể yêu cầu canonical encoding bằng cách re-encode và so sánh nếu thư viện/profile hỗ trợ đúng.
- Dùng cùng quy tắc tại mọi thành phần xử lý token.

Canonical check không thay thế kiểm tra chữ ký. Nó chỉ giúp thống nhất cách biểu diễn segment.

### 4.2. Không URL-decode token một cách tùy tiện

JWT compact thường được truyền trong Authorization header. Nếu token bị percent-encode hoặc URL-decode tùy tiện, chuỗi có thể thay đổi trước khi xác minh.

- Không URL-decode Authorization header theo thói quen xử lý query string.
- Không chuyển -/_ thành +//.
- Không trim whitespace rồi coi kết quả là token gốc.
- Nếu token được nhận từ một transport khác, phải quy định encoding của transport đó và chuyển đổi đúng một lần ở ranh giới.

## 5. UTF-8 không hợp lệ sau khi giải mã

Base64url chỉ chuyển bytes sang dạng text an toàn để truyền. Sau khi decode, JOSE Header và JWT Claims Set được biểu diễn bằng JSON text mã hóa UTF-8 theo các tiêu chuẩn liên quan.

Một decoder có thể trả bytes hợp lệ về mặt Base64url nhưng bytes đó không phải UTF-8 hợp lệ.

### 5.1. Các trường hợp UTF-8 lỗi

- Byte sequence bị cắt giữa một ký tự nhiều byte.
- Continuation byte xuất hiện sai vị trí.
- Overlong encoding.
- Encoding surrogate không hợp lệ.
- Code point vượt giới hạn Unicode.
- Payload chứa bytes ngẫu nhiên do segment bị hỏng.

Nếu runtime tự thay bytes lỗi bằng ký tự replacement, hai parser có thể nhận được nội dung khác nhau. Với header và JWT claims JSON, nên dùng UTF-8 decoder strict và từ chối chuỗi không hợp lệ.

### 5.2. Không dùng charset mặc định của máy

Không chuyển bytes sang text bằng charset mặc định của hệ điều hành hoặc process. Charset mặc định có thể khác giữa máy phát triển, container và production.

Quy tắc:

- Decode JSON bytes bằng UTF-8 rõ ràng.
- Từ chối chuỗi UTF-8 lỗi.
- Không tự chuyển đổi Latin-1, Windows-1252 hoặc charset khác sang UTF-8.
- Không chuẩn hóa payload theo locale.
- Không thay ký tự lỗi bằng dấu hỏi hoặc replacement character rồi tiếp tục xác minh.

### 5.3. BOM và JSON text

JSON được trao đổi giữa các hệ thống dùng UTF-8. RFC 8259 quy định generator không được thêm BOM vào JSON text; parser có thể bỏ qua BOM để tương thích. Trong security profile, nên thống nhất chính sách BOM giữa các thành phần và ưu tiên từ chối BOM nếu profile yêu cầu JSON UTF-8 không BOM, tránh hai parser diễn giải khác nhau.

## 6. JSON Header và Claims Set phải đúng cấu trúc

Sau khi Base64url decode và UTF-8 decode, JOSE Header và JWT Claims Set phải được parse như JSON theo profile.

### 6.1. Header phải là JSON object

Ví dụ header hợp lệ về cấu trúc:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "test-key-01"
}
~~~

Các dạng sau không phải JOSE Header object hợp lệ:

~~~json
["RS256", "JWT"]
~~~

~~~json
"RS256"
~~~

~~~json
null
~~~

~~~json
{
  "alg": "RS256",
~~~

Parser không được tự chuyển array/string/null thành object hoặc bỏ qua phần JSON bị thiếu.

### 6.2. JWT Claims Set phải là JSON object

Payload của JWT Claims Set là JSON object chứa các claim names và values. Ví dụ:

~~~json
{
  "iss": "https://identity.example",
  "sub": "demo-user-01",
  "aud": "https://api.example",
  "exp": 2000000300
}
~~~

Các payload sau phải bị từ chối như JWT Claims Set:

~~~json
["user-01", "admin"]
~~~

~~~json
"demo-user-01"
~~~

~~~json
42
~~~

~~~json
null
~~~

Không tự bọc array/string thành object hoặc tự tạo claims mặc định.

### 6.3. JSON không cho phép comment hoặc dấu phẩy thừa

JSON chuẩn không cho phép comment kiểu JavaScript, trailing comma hoặc cú pháp mở rộng riêng của một parser.

Ví dụ sai:

~~~json
{
  "sub": "demo-user-01", // comment không hợp lệ
  "aud": "https://api.example",
}
~~~

Một parser permissive có thể chấp nhận trong khi parser khác từ chối. Token cần được tạo bằng JSON serializer chuẩn và được parse bằng chế độ strict.

### 6.4. Từ chối trailing data

Một JSON document hợp lệ không được theo sau bởi một JSON fragment hoặc ký tự tùy ý mà parser âm thầm bỏ qua.

Ví dụ:

~~~text
{"sub":"demo-user-01"} {"role":"admin"}
~~~

Nếu parser chỉ đọc object đầu tiên và bỏ qua phần còn lại, thành phần khác có thể đọc object thứ hai hoặc báo lỗi. Phải yêu cầu toàn bộ byte sequence là đúng một JSON document, không có trailing non-whitespace data ngoài quy tắc JSON.

## 7. Duplicate member names và JSON mơ hồ

RFC 8259 khuyến nghị tên member trong object nên duy nhất; RFC 7519 yêu cầu Claim Names trong JWT Claims Set phải duy nhất. JOSE Header cũng có yêu cầu uniqueness theo JWS/JWE.

Ví dụ:

~~~json
{
  "alg": "RS256",
  "alg": "none"
}
~~~

Hoặc claims:

~~~json
{
  "sub": "demo-user-01",
  "role": "user",
  "role": "admin"
}
~~~

Các parser có thể giữ giá trị đầu, giá trị cuối hoặc từ chối. Chính sách an toàn nên từ chối duplicate member names sau khi giải mã JSON escapes, ở mọi cấp object.

Không chỉ quét raw text để tìm tên lặp. Hai cách viết khác nhau có thể giải mã thành cùng một JSON string. Duplicate detection cần dựa trên tên member sau khi JSON string escape được giải mã.

## 8. JSON number và kiểu dữ liệu bất thường

JSON number không đồng nghĩa với mọi chuỗi có thể ép thành số. JWT claims có schema và ngữ nghĩa riêng.

Ví dụ các kiểu sai:

~~~json
{
  "exp": "2000000300",
  "nbf": true,
  "iat": null
}
~~~

Nếu profile yêu cầu NumericDate, exp/nbf/iat phải có kiểu number hợp lệ. Không tự ép string thành number hoặc boolean thành 0/1.

Các giá trị như NaN và Infinity không phải JSON number hợp lệ theo RFC 8259. Parser phải từ chối chúng thay vì chấp nhận extension của một runtime.

Ngoài ra, cần kiểm tra:

- Miền số mà runtime có thể biểu diễn chính xác.
- Overflow/underflow.
- Số rất lớn hoặc rất nhỏ.
- Precision của fractional NumericDate.
- Giá trị ngoài miền hợp lý của profile.

Không để một parser làm tròn số còn parser khác giữ chính xác số đó.

## 9. JWE cần kiểm tra theo thứ tự khác JWS

Với JWS, payload có thể được Base64url decode trước khi xác minh chữ ký để chuẩn bị xử lý, nhưng claims chưa được tin cậy cho tới khi chữ ký/MAC hợp lệ.

Với JWE, payload là ciphertext. Không thể parse JWT Claims Set trước khi giải mã và xác minh authentication tag.

### 9.1. Luồng xử lý JWS

1. Kiểm tra compact serialization có đúng ba segment theo profile.
2. Kiểm tra Base64url và decode protected header.
3. Parse header strict như JSON object; coi mọi giá trị là chưa tin cậy.
4. Chọn thuật toán/khóa theo cấu hình trust, không theo chỉ thị tùy ý từ token.
5. Xác minh chữ ký/MAC.
6. Chỉ sau khi xác minh thành công mới chấp nhận payload là claims đáng tin.
7. Decode payload bằng UTF-8 strict và parse JSON Claims Set strict.
8. Kiểm tra issuer, audience, thời hạn, token type và authorization policy.

### 9.2. Luồng xử lý JWE

1. Kiểm tra compact serialization có đúng năm segment theo profile.
2. Decode và parse protected header strict.
3. Kiểm tra thuật toán key management và content encryption trong allowlist.
4. Chọn khóa giải mã từ cấu hình tin cậy.
5. Giải mã và xác minh authentication tag thành công.
6. Chỉ sau khi authenticated decryption thành công mới sử dụng plaintext.
7. Nếu plaintext là JWT lồng nhau, xác minh lớp JWT bên trong theo profile.
8. Nếu plaintext là JWT Claims Set, decode/parse JSON strict và kiểm tra claims.

Không parse hoặc sử dụng plaintext JWE trước khi authentication tag được xác minh. Không trả lỗi chi tiết khác nhau làm lộ thông tin về key, padding hoặc quá trình giải mã cho bên ngoài.

## 10. Giới hạn tài nguyên khi parse token

Một token malformed có thể được dùng để tiêu tốn CPU, memory hoặc kết nối mạng ngay cả khi cuối cùng bị từ chối.

### 10.1. Giới hạn ở compact token

- Tổng độ dài token.
- Độ dài từng segment.
- Số lượng segment.
- Độ dài header và payload sau decode.
- Số lượng request xác minh đồng thời.
- Thời gian tối đa cho parse/verify.

### 10.2. Giới hạn JSON

- Độ sâu lồng nhau.
- Số lượng object member.
- Số lượng phần tử array.
- Độ dài string.
- Kích thước number.
- Tổng số node trong document.

### 10.3. Giới hạn JWE và compression

Nếu profile hỗ trợ compression:

- Giới hạn kích thước plaintext sau giải nén.
- Giới hạn tỷ lệ giải nén.
- Chống decompression bomb.
- Chỉ hỗ trợ compression algorithm được cho phép.
- Không giải nén trước khi authenticated decryption hoàn tất.
- Từ chối dữ liệu vượt giới hạn thay vì cấp thêm memory vô hạn.

Nếu ứng dụng không cần compression, nên từ chối extension đó theo profile.

### 10.4. Giới hạn network và key lookup

Malformed header không được kích hoạt fetch URL tùy ý. Khi cần lấy JWKS:

- Issuer phải được tra trong allowlist.
- JWKS endpoint phải đến từ trust profile.
- Unknown kid refresh có rate limit và chống request storm.
- Có timeout, response-size limit và redirect policy.
- Không để mỗi token malformed tạo một network request không giới hạn.

## 11. Quy trình parse và xác minh an toàn

~~~mermaid
flowchart TD
    A["Nhận compact token"] --> B["Giới hạn kích thước và ký tự đầu vào"]
    B --> C["Xác định profile JWS/JWE được phép"]
    C --> D["Kiểm tra số segment và vị trí segment"]
    D --> E{"Segment hợp lệ?"}
    E -- "Không" --> X["Từ chối"]
    E -- "Có" --> F["Base64url strict decode"]
    F --> G{"Decode hợp lệ?"}
    G -- "Không" --> X
    G -- "Có" --> H["UTF-8 strict và JSON strict cho header"]
    H --> I{"Header là object hợp lệ?"}
    I -- "Không" --> X
    I -- "Có" --> J["Xác minh JWS hoặc authenticated decrypt JWE"]
    J --> K{"Mật mã hợp lệ?"}
    K -- "Không" --> X
    K -- "Có" --> L["Parse claims JSON strict"]
    L --> M{"Claims Set hợp lệ?"}
    M -- "Không" --> X
    M -- "Có" --> N["Kiểm tra issuer, audience, thời gian và profile"]
    N --> O["Authorization trên tài nguyên"]
~~~

### 11.1. Pseudocode trung lập ngôn ngữ

~~~text
function parse_and_validate_compact_jwt(token, profile):
    require(token is text)
    require(byte_length(token) <= profile.max_token_bytes)
    require(no_outer_whitespace_or_control_chars(token))

    parts = split_preserving_empty_segments(token, ".")

    if profile.serialization == "JWS_COMPACT":
        require(length(parts) == 3)
    else if profile.serialization == "JWE_COMPACT":
        require(length(parts) == 5)
    else:
        reject("unsupported_serialization")

    validate_segment_positions_and_empty_rules(parts, profile)

    header_bytes = strict_base64url_decode(parts[0])
    require(byte_length(header_bytes) <= profile.max_header_bytes)
    header_text = strict_utf8_decode(header_bytes)
    header = strict_json_parse_object(header_text)
    reject_duplicate_members(header)

    validate_header_against_profile(header, profile)

    if profile.serialization == "JWS_COMPACT":
        payload_bytes = strict_base64url_decode(parts[1])
        require(verify_jws(token, trusted_key_for(profile, header)))
    else:
        plaintext = authenticated_decrypt_jwe(
            token,
            trusted_key_for(profile, header)
        )
        require(authentication_tag_verified)
        payload_bytes = plaintext

    require(byte_length(payload_bytes) <= profile.max_payload_bytes)
    payload_text = strict_utf8_decode(payload_bytes)
    claims = strict_json_parse_object(payload_text)
    reject_duplicate_members_recursively(claims)

    validate_claim_schema(claims, profile)
    validate_issuer_audience_time_and_type(claims, header, profile)
    return authorize_using_verified_claims(claims)
~~~

Pseudocode minh họa các bước chính. Thư viện thực tế có thể kết hợp parse và verify theo API riêng. Điều bắt buộc là không dùng claims chưa xác minh để cấp quyền, không nới lỏng parser và không bỏ qua kiểm tra authentication tag của JWE.

## 12. Phân biệt malformed token với token hợp lệ về cú pháp nhưng không hợp lệ về bảo mật

Không phải mọi lỗi JWT đều là lỗi cấu trúc.

| Nhóm lỗi | Ví dụ | Lớp xử lý |
| --- | --- | --- |
| Compact syntax | Thiếu/thừa segment, dấu chấm sai | Parser compact |
| Base64url | Ký tự sai, padding không hợp lệ, length modulo 4 bằng 1 | Decoder strict |
| Text encoding | UTF-8 không hợp lệ | UTF-8 decoder |
| JSON syntax | Thiếu ngoặc, trailing comma, comment, trailing data | JSON parser |
| JSON semantics | Root không phải object, duplicate member | Schema/strict parser |
| JOSE header policy | alg không được phép, crit không hỗ trợ | JOSE validation |
| Cryptographic | Chữ ký sai, tag sai, key không phù hợp | JWS/JWE verification |
| JWT claims | Sai iss/aud, hết hạn, thiếu claim bắt buộc | JWT profile validation |
| Authorization | Thiếu scope hoặc không có quyền trên tài nguyên | Authorization policy |

Phân lớp lỗi giúp nhóm phát triển tìm đúng nguyên nhân mà không làm lộ chi tiết nhạy cảm ra response.

### 12.1. Response bên ngoài nên thống nhất

Với client không đáng tin, không nên tiết lộ quá nhiều chi tiết như:

- Header JSON hỏng ở byte nào.
- Base64url sai tại ký tự nào.
- Key ID nào tồn tại hoặc không tồn tại.
- Chữ ký sai vì key nào.
- Authentication tag sai ở bước nào.
- Issuer nội bộ nào được cấu hình.

Có thể trả 401 với mã lỗi chung cho credential không hợp lệ. Log nội bộ chỉ ghi failure code đã chuẩn hóa, request ID và stage; không ghi raw token.

## 13. Bộ kiểm thử malformed token

Một bộ test tốt cần kiểm tra từng lớp và kết quả phải nhất quán ở mọi thành phần xử lý token.

### 13.1. Kiểm thử số segment

| Test case | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| JWS thiếu signature | Hai segment | Từ chối |
| JWS thiếu header | Segment đầu rỗng | Từ chối |
| JWS thiếu payload | Segment giữa rỗng | Từ chối với JWT Claims Set thông thường |
| JWS thừa segment | Bốn segment | Từ chối |
| JWE thiếu tag | Bốn segment | Từ chối |
| JWE thừa segment | Sáu segment | Từ chối |
| JWE encrypted key rỗng | Năm segment | Chỉ chấp nhận nếu key management profile cho phép |
| JWS signature rỗng | Ba segment | Từ chối với access-token profile yêu cầu chữ ký |
| Token có dấu chấm cuối | Segment dư/rỗng | Từ chối theo số segment |
| Token có nhiều dấu chấm | Sai compact structure | Từ chối |

### 13.2. Kiểm thử Base64url

| Test case | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Ký tự + | Base64 alphabet thường | Từ chối |
| Ký tự / | Base64 alphabet thường | Từ chối |
| Padding = trong compact segment | Padding không đúng serialization | Từ chối |
| Whitespace | Space/tab/CR/LF trong segment | Từ chối |
| Độ dài modulo 4 bằng 1 | Encoded string không thể hợp lệ | Từ chối |
| Ký tự Unicode ngoài ASCII | Segment sai alphabet | Từ chối |
| Encoded string bị cắt | Decode không hoàn chỉnh | Từ chối |
| Non-canonical trailing bits | Biểu diễn không canonical | Từ chối nếu profile yêu cầu canonical |
| Segment cực dài | Vượt giới hạn | Từ chối trước decode |

### 13.3. Kiểm thử UTF-8 và JSON

| Test case | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| UTF-8 sequence bị cắt | Bytes không hợp lệ | Từ chối |
| Overlong UTF-8 | Encoding không hợp lệ | Từ chối |
| JSON header là array | Root không phải object | Từ chối |
| Claims payload là string | Root không phải object | Từ chối |
| Thiếu dấu ngoặc | JSON malformed | Từ chối |
| Có comment | JSON extension | Từ chối |
| Có trailing comma | JSON malformed | Từ chối |
| Có hai JSON document | Trailing data | Từ chối |
| Duplicate alg | Header member lặp | Từ chối |
| Duplicate sub | Claim name lặp | Từ chối |
| Duplicate sau Unicode escape | Tên trùng sau decode | Từ chối |
| NaN/Infinity | JSON number không hợp lệ | Từ chối |
| JSON quá sâu | Vượt parser limit | Từ chối |

### 13.4. Kiểm thử JWE và tài nguyên

| Test case | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Authentication tag sai | Ciphertext bị sửa | Từ chối; không sử dụng plaintext |
| Key management algorithm ngoài allowlist | Header không được phép | Từ chối |
| Compression vượt giới hạn | Plaintext sau giải nén quá lớn | Từ chối |
| Decompression ratio bất thường | Dữ liệu có nguy cơ bomb | Từ chối |
| Header chứa jku tùy ý | URL do token chỉ định | Không fetch URL |
| Unknown kid liên tục | Nhiều request với kid ngẫu nhiên | Refresh JWKS có rate limit |
| Parser timeout | Token gây tốn tài nguyên | Dừng theo timeout |
| Token vượt max bytes | Input quá lớn | Từ chối trước parse |

## 14. Fuzzing và differential testing

Malformed token có nhiều biến thể kết hợp. Test case viết tay là cần thiết nhưng không đủ để tìm lỗi parser.

### 14.1. Fuzzing

Fuzzing có thể tạo đầu vào ngẫu nhiên hoặc biến đổi token hợp lệ:

- Xóa một ký tự hoặc một segment.
- Chèn dấu chấm ở vị trí bất kỳ.
- Thay alphabet Base64url bằng ký tự gần giống.
- Thêm padding hoặc whitespace.
- Cắt giữa UTF-8 multibyte sequence.
- Thay dấu ngoặc hoặc dấu phẩy trong JSON.
- Lặp tên member.
- Tăng độ sâu object/array.
- Tạo number cực lớn hoặc fractional value.
- Sửa ciphertext hoặc authentication tag.

Các invariant cần giữ:

- Parser không crash hoặc treo.
- Input vượt giới hạn bị từ chối nhanh.
- Không có malformed token nào tạo security context.
- Không dùng dữ liệu trước khi xác minh mật mã.
- Lỗi parse không làm lộ raw token.
- Bộ nhớ và CPU luôn nằm trong giới hạn được định nghĩa.

### 14.2. Differential testing giữa các thành phần

Nếu gateway, service mesh và resource server dùng parser khác nhau:

1. Chuẩn bị corpus token hợp lệ và malformed.
2. Gửi cùng corpus qua từng parser.
3. So sánh kết quả accept/reject và phân loại lỗi.
4. Token bị từ chối ở một nơi nhưng được chấp nhận ở nơi khác là sai khác cần điều tra.
5. Kiểm tra cả JWS, JWE và nested token nếu hệ thống hỗ trợ.
6. Chạy lại corpus khi nâng cấp thư viện, runtime hoặc cấu hình.

Mục tiêu là mọi thành phần có cùng ranh giới chấp nhận. Nếu không thể dùng chung parser, cần có hợp đồng serialization/profile và test corpus chung.

### 14.3. Property-based tests

Có thể định nghĩa các thuộc tính:

- Bất kỳ token nào có số segment không đúng profile đều bị từ chối.
- Thay một byte của signed content phải làm xác minh JWS thất bại.
- Thay ciphertext hoặc tag phải làm authenticated decryption thất bại.
- Decode rồi encode lại một Base64url segment canonical phải giữ nguyên biểu diễn.
- JSON có duplicate member phải bị từ chối.
- Thêm trailing non-whitespace data phải bị từ chối.
- Tăng kích thước/depth vượt giới hạn phải bị từ chối mà không vượt resource budget.

## 15. Quy tắc vận hành parser an toàn

- Dùng thư viện JOSE/JWT được duy trì và có hỗ trợ strict parsing.
- Không tự viết lại toàn bộ Base64url, JSON hoặc cryptographic parser nếu không có lý do chuyên môn.
- Cấu hình giới hạn kích thước, độ sâu, thời gian và số lượng request.
- Không tự sửa token malformed rồi tiếp tục xác minh.
- Không fallback từ JWS sang JWE hoặc ngược lại chỉ vì parse thất bại.
- Không fallback sang parser tolerant sau khi strict parser từ chối.
- Không parse cùng token theo hai đường code có quy tắc khác nhau.
- Không log token trong lỗi parse.
- Cập nhật thư viện theo quy trình kiểm thử tương thích và bảo mật.
- Lưu corpus malformed regression để ngăn lỗi tái xuất hiện.

## 16. Tình huống thực tế

### Tình huống A — Gateway bỏ segment rỗng

Gateway dùng hàm split tự loại bỏ chuỗi rỗng. Token có payload rỗng bị biến đổi số segment; service phía sau lại dùng parser giữ nguyên segment và hiểu khác.

**Bài học:** split phải giữ segment rỗng và kiểm tra đúng số lượng trước khi xử lý.

### Tình huống B — Decoder chấp nhận Base64 thông thường

Gateway chấp nhận ký tự + và /, trong khi resource server chỉ chấp nhận - và _. Hai lớp có thể nhận cùng chuỗi theo cách khác nhau.

**Bài học:** kiểm tra alphabet Base64url nghiêm ngặt và thống nhất decoder.

### Tình huống C — JSON parser bỏ qua trailing data

Một parser chỉ đọc object đầu tiên rồi bỏ qua phần còn lại. Parser khác từ chối toàn bộ payload.

**Bài học:** yêu cầu đúng một JSON document, không có trailing non-whitespace data.

### Tình huống D — Duplicate claim được giữ giá trị cuối

Payload có hai claim role. Gateway giữ giá trị đầu, service giữ giá trị cuối và đưa ra quyết định quyền khác nhau.

**Bài học:** từ chối duplicate member names sau khi decode JSON escapes.

### Tình huống E — UTF-8 lỗi được thay bằng ký tự replacement

Một runtime thay byte lỗi bằng ký tự replacement và tiếp tục parse. Runtime khác từ chối payload.

**Bài học:** dùng UTF-8 decoder strict, không tự sửa bytes lỗi.

### Tình huống F — JWE plaintext được parse trước khi xác minh tag

Một pipeline giải mã một phần và đọc plaintext trước khi authentication tag được xác minh. Dữ liệu chưa được xác thực bị sử dụng.

**Bài học:** chỉ sử dụng plaintext sau authenticated decryption thành công.

### Tình huống G — Token quá lớn làm cạn tài nguyên

Một endpoint nhận token hàng chục MB, decode và parse JSON sâu trước khi kiểm tra giới hạn.

**Bài học:** giới hạn tổng byte và segment trước decode; giới hạn JSON depth, node count và thời gian parse.

## 17. Checklist kiểm thử token malformed

### Compact serialization

- [ ] Endpoint xác định rõ chấp nhận JWS, JWE hoặc nested JWT.
- [ ] JWS Compact có đúng ba segment.
- [ ] JWE Compact có đúng năm segment.
- [ ] Split giữ nguyên segment rỗng.
- [ ] Không trim, nối hoặc bỏ segment sai.
- [ ] Empty segment được đánh giá theo đúng vị trí và profile.
- [ ] Không chấp nhận unsecured JWT nếu profile yêu cầu xác minh chữ ký.

### Base64url và text encoding

- [ ] Chỉ chấp nhận alphabet Base64url.
- [ ] Từ chối +, /, padding và whitespace không thuộc serialization.
- [ ] Từ chối encoded length modulo 4 bằng 1.
- [ ] Decoder không bỏ qua ký tự sai hoặc tự sửa input.
- [ ] Kiểm tra canonical encoding nếu profile yêu cầu.
- [ ] Decode JSON bytes bằng UTF-8 strict.
- [ ] Không dùng charset mặc định hoặc replacement character.

### JSON và JOSE

- [ ] Header là JSON object.
- [ ] JWT Claims Set là JSON object.
- [ ] Từ chối comment, trailing comma và trailing data.
- [ ] Từ chối duplicate member names sau khi giải mã escape.
- [ ] Từ chối JSON number không hợp lệ như NaN/Infinity.
- [ ] Kiểm tra kiểu và miền số theo schema.
- [ ] Với JWE, chỉ dùng plaintext sau khi authentication tag hợp lệ.

### Resource limits và vận hành

- [ ] Có max token bytes và max segment bytes.
- [ ] Có JSON depth/member/string limits.
- [ ] Có timeout và giới hạn concurrency.
- [ ] Có giới hạn giải nén nếu hỗ trợ compression.
- [ ] Không fetch URL từ header/token tùy ý.
- [ ] Lỗi bên ngoài không tiết lộ chi tiết parser/crypto.
- [ ] Không log raw token.
- [ ] Có fuzzing, differential và regression corpus.

## 18. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| JWS Compact Serialization có bao nhiêu segment? | **Ba**: protected header, payload và signature. |
| JWE Compact Serialization có bao nhiêu segment? | **Năm**: protected header, encrypted key, IV, ciphertext và authentication tag. |
| Mọi segment JWE đều bắt buộc không rỗng? | **Không.** Một số key management mode cho phép encrypted-key segment rỗng; phải theo profile/thuật toán. |
| Có nên dùng split tự bỏ phần tử rỗng không? | **Không.** Nó có thể làm thay đổi vị trí và số segment. |
| Base64url compact có dùng +, / và padding = không? | **Không.** Dùng -, _ và bỏ padding ở cuối. |
| Encoded length modulo 4 bằng 1 có hợp lệ không? | **Không.** Không thể biểu diễn chuỗi bytes hợp lệ theo Base64url chuẩn. |
| Có thể tự bỏ ký tự Base64url sai rồi decode không? | **Không.** Phải từ chối đầu vào malformed. |
| JWS payload có thể parse thành claims đáng tin trước khi verify signature không? | **Không.** Có thể parse để chuẩn bị, nhưng không được tin hoặc dùng để cấp quyền trước khi xác minh thành công. |
| Có thể parse plaintext JWE trước khi xác minh authentication tag không? | **Không.** Chỉ sử dụng plaintext sau authenticated decryption thành công. |
| JSON array có thể thay JWT Claims Set object không? | **Không.** Claims Set phải là JSON object. |
| Parser có nên bỏ qua duplicate claim hoặc trailing JSON data không? | **Không.** Từ chối để tránh parser differential. |
| Cách kiểm thử parser tốt là gì? | Kết hợp test case viết tay, fuzzing, property-based tests và differential testing giữa các thành phần. |

## 19. Ghi nhớ

- Xác định đúng serialization: JWS Compact có ba segment; JWE Compact có năm segment.
- Không suy ra token hợp lệ chỉ từ số dấu chấm; kiểm tra đúng profile và vị trí từng segment.
- Split phải giữ segment rỗng; không tự trim, nối, bỏ hoặc sửa phần token sai.
- Base64url compact dùng alphabet URL-safe và không padding; từ chối ký tự sai, whitespace và length modulo 4 bằng 1.
- Sau decode, dùng UTF-8 strict và JSON strict; header và JWT Claims Set phải là JSON object.
- Từ chối duplicate member, trailing data, comment, trailing comma, NaN/Infinity và kiểu dữ liệu sai.
- Với JWS, không tin claims trước khi chữ ký/MAC hợp lệ; với JWE, không sử dụng plaintext trước khi authentication tag được xác minh.
- Giới hạn token size, segment size, JSON depth, node count, thời gian parse và giải nén.
- Dùng test corpus, fuzzing, property-based testing và differential testing để phát hiện parser không nhất quán.
- Không log raw token và không tự sửa malformed token để tiếp tục xử lý.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7515 – JSON Web Signature (JWS), Compact Serialization](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 – JSON Web Encryption (JWE), Compact Serialization](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 4648 – Base-N Encodings, Base64url](https://www.rfc-editor.org/rfc/rfc4648)
- [RFC 8259 – The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259)
- [RFC 7797 – JSON Web Signature (JWS) Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)

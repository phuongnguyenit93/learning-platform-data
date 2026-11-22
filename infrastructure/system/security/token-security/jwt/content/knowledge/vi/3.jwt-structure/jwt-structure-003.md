# JSON và mã hóa UTF-8 của header cùng tập claims

## 1. Vì sao JWT sử dụng JSON và UTF-8?

**JWT (JSON Web Token)** là định dạng biểu diễn một tập thông tin (*claims*) về chủ thể và ngữ cảnh sử dụng token. JSON cung cấp cấu trúc dữ liệu dễ trao đổi: mỗi claim có tên và giá trị, còn UTF-8 biến văn bản JSON thành chuỗi byte thống nhất để các hệ thống có thể ký, mã hóa và truyền tải.

Trong JWT, cần phân biệt ba lớp:

1. **JSON** mô tả cấu trúc và giá trị của header hoặc tập claims.
2. **UTF-8** chuyển văn bản JSON thành byte.
3. **Base64url** biểu diễn các byte thành chuỗi ký tự an toàn khi truyền trong token Compact.

Base64url **không thay thế JSON hay UTF-8**, và cũng không phải mã hóa bí mật. Với JWS, signature được tính trên các phần đã Base64url theo quy tắc của JWS. Với JWE, nội dung JSON được chuyển thành byte UTF-8 rồi mã hóa bằng thuật toán mã hóa nội dung.

Một quy trình khái quát:

~~~text
JSON object
    |
    v
Serialize thành JSON text
    |
    v
Encode JSON text thành UTF-8 bytes
    |
    +---- JWS: Base64url(header bytes và payload bytes)
    |          rồi ký signing input
    |
    +---- JWE: Base64url(protected header bytes)
               mã hóa plaintext bytes và tạo authentication tag
~~~

Đây là nền tảng để hiểu tại sao hai JSON có cùng ý nghĩa nhưng khác cách biểu diễn vẫn có thể tạo ra JWT có chữ ký khác nhau.

## 2. Header và JWT Claims Set là hai đối tượng JSON khác nhau

JWT dạng JWS hoặc JWE thường có hai đối tượng JSON quan trọng, nhưng chúng mang nhiệm vụ khác nhau.

### Header

Header chứa metadata mô tả cách xử lý token, ví dụ:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026"
}
~~~

- **alg** chỉ thuật toán bảo vệ JWS hoặc thuật toán quản lý khóa trong JWE, tùy loại token.
- **typ** gợi ý loại nội dung, thường là `JWT`.
- **kid** giúp chọn khóa ứng viên trong tập khóa mà bên nhận đã tin cậy.

Với JWE, header thường có thêm **enc** để chỉ thuật toán mã hóa nội dung, chẳng hạn `A256GCM`. Header của JWS/JWE Compact được biểu diễn ở phần đầu tiên của chuỗi token bằng Base64url.

Header là dữ liệu do bên phát hành đưa vào token. Trước khi xác minh chữ ký hoặc authentication tag, không được xem các giá trị header là đáng tin hay để chúng tự quyết định chính sách thuật toán và nguồn khóa.

### JWT Claims Set

Payload của JWT thông thường là một **JWT Claims Set**: đối tượng JSON gồm các claim. Ví dụ:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "aud": ["orders-api", "profile-api"],
  "name": "Trần Thị Ánh",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456300
}
~~~

Một số claim có tên được đăng ký trong chuẩn JWT:

| Claim | Kiểu dữ liệu thường dùng theo đặc tả | Ý nghĩa |
| --- | --- | --- |
| **iss** | String | Nhà phát hành token |
| **sub** | String | Chủ thể được mô tả |
| **aud** | String hoặc mảng String | Đối tượng nhận token |
| **exp** | Number (NumericDate) | Thời điểm hết hạn |
| **nbf** | Number (NumericDate) | Thời điểm token bắt đầu có hiệu lực |
| **iat** | Number (NumericDate) | Thời điểm phát hành |
| **jti** | String | Định danh token |

Các claim như `name`, `scope`, `tenant_id` hoặc `permissions` có thể là claim do ứng dụng định nghĩa. Bên phát hành và bên nhận phải thống nhất ý nghĩa, kiểu dữ liệu và điều kiện kiểm tra của chúng.

`exp`, `nbf`, `iat` sử dụng **NumericDate**, tức số giây kể từ Unix epoch; không mặc định là mili giây. `aud` có thể là một chuỗi hoặc mảng chuỗi, vì vậy bộ xử lý phải hỗ trợ đúng kiểu được chuẩn cho phép. Không nên tự động biến một chuỗi số thành Number hoặc ngược lại khi kiểm tra claim.

**Header không phải nơi chứa claim nghiệp vụ**, còn payload không phải nơi khai báo chính sách mật mã. Tách biệt hai phần giúp hệ thống đọc đúng dữ liệu và áp dụng đúng quy trình bảo vệ.

## 3. JSON được biểu diễn như thế nào?

JSON là định dạng văn bản có cú pháp xác định. Một JSON object gồm các cặp **tên thuộc tính – giá trị**; tên thuộc tính luôn là chuỗi đặt trong dấu ngoặc kép.

Các kiểu giá trị JSON hợp lệ:

- **String:** `"customer-42"`
- **Number:** `1893456300`
- **Boolean:** `true` hoặc `false`
- **Null:** `null`
- **Object:** `{ "region": "apac" }`
- **Array:** `["orders-api", "profile-api"]`

Ví dụ một JWT Claims Set hợp lệ:

~~~json
{
  "sub": "customer-42",
  "active": true,
  "roles": ["reader", "auditor"],
  "profile": {
    "region": "apac"
  },
  "middle_name": null
}
~~~

JSON không cho phép comment, dấu phẩy thừa ở cuối danh sách, tên thuộc tính không có dấu ngoặc kép hoặc các giá trị như `NaN` và `Infinity`. Ví dụ sau **không phải JSON hợp lệ**:

~~~text
{
  sub: 'customer-42', // thiếu dấu ngoặc kép và có comment
  "active": true,
}
~~~

Một số điểm cần chú ý khi dữ liệu JSON được dùng làm JWT:

- Tên claim là chuỗi và cần được xử lý nhất quán; `sub`, `Sub` và `SUB` là ba tên khác nhau.
- Giá trị claim có kiểu dữ liệu. `exp: 1893456300` là Number, còn `exp: "1893456300"` là String và không tương đương.
- JSON cho phép khoảng trắng và xuống dòng ở những vị trí cú pháp cho phép. Chúng không làm thay đổi ý nghĩa JSON, nhưng có thể làm thay đổi byte được ký.
- Không nên dùng Number cho mã định danh cần giữ chính xác tuyệt đối nếu giá trị có thể vượt giới hạn số nguyên an toàn của môi trường xử lý. Dùng String cho ID lớn thường rõ ràng và tương thích hơn.

Đặc tả JWT yêu cầu JWT Claims Set là một JSON object. Một mảng JSON ở cấp cao nhất không thay thế được Claims Set object theo quy tắc này.

## 4. UTF-8 chuyển JSON text thành byte

Máy tính truyền và xử lý dữ liệu dưới dạng byte. Vì JSON là văn bản, hai bên phải thống nhất cách chuyển ký tự thành byte. JWT sử dụng **UTF-8** cho JSON header và JWT Claims Set.

UTF-8 mã hóa một điểm mã Unicode thành từ một đến bốn byte. Ký tự ASCII thông thường dùng một byte; nhiều ký tự tiếng Việt có dấu cần nhiều byte.

Ví dụ, ký tự `ế` có điểm mã Unicode **U+1EBF** và biểu diễn UTF-8 là:

~~~text
Ký tự:       ế
Code point:  U+1EBF
UTF-8 bytes: E1 BA BF
~~~

Một JSON text có thể chứa ký tự `ế` trực tiếp:

~~~json
{
  "name": "Tuấn ế"
}
~~~

Khi encode UTF-8, ký tự này được chuyển thành các byte tương ứng. Bộ xử lý JSON có thể biểu diễn cùng ký tự bằng escape Unicode:

~~~json
{
  "name": "Tuấn \u1ebf"
}
~~~

Hai biểu diễn trên có thể tạo ra cùng một giá trị chuỗi sau khi parse JSON, nhưng **byte JSON ban đầu khác nhau**: cách thứ nhất chứa byte UTF-8 của ký tự `ế`, còn cách thứ hai chứa các ký tự ASCII của chuỗi escape `\u1ebf`.

Đây là khác biệt quan trọng trong JWT: chữ ký bảo vệ byte theo đúng cách chúng được đưa vào signing input. Hai JSON tương đương về ý nghĩa không tự động có cùng chữ ký.

### Một số quy tắc về UTF-8 và Unicode

- Dùng UTF-8 để chuyển JSON text thành byte trước khi thực hiện bước Base64url hoặc mã hóa.
- Không tự ý chuyển dữ liệu JSON sang UTF-16/UTF-32 trước khi tạo token.
- Không thêm byte BOM vào JSON được tạo để trao đổi; BOM không phải thành phần cần thiết của JSON JWT.
- Từ chối chuỗi byte UTF-8 không hợp lệ thay vì tự thay thế byte lỗi bằng ký tự khác rồi tiếp tục xác minh.
- Ký tự ngoài BMP, chẳng hạn nhiều emoji, có thể xuất hiện trực tiếp dưới dạng UTF-8 bốn byte hoặc được biểu diễn bằng cặp escape surrogate trong JSON. Hai cách viết có thể cho cùng giá trị Unicode nhưng khác byte JSON.
- Unicode có thể có nhiều chuỗi code point nhìn gần như giống nhau, ví dụ ký tự dựng sẵn và ký tự gốc kết hợp dấu. JWT không tự động chuẩn hóa NFC/NFD. Nếu ứng dụng cần chuẩn hóa định danh, phải quy định rõ tại biên dữ liệu của ứng dụng và không biến đổi byte token trước khi xác minh.

**Độ dài ký tự không bằng độ dài byte.** Một chuỗi có 10 ký tự có thể chiếm hơn 10 byte UTF-8. Khi kiểm tra giới hạn kích thước token hoặc payload, cần tính trên byte thực tế và đặt giới hạn phù hợp.

## 5. Escape trong JSON và ảnh hưởng đến byte

JSON dùng dấu ngoặc kép để bao chuỗi. Những ký tự có ý nghĩa cú pháp hoặc ký tự điều khiển cần được escape.

| Ký tự/nhóm ký tự | Cách biểu diễn trong JSON |
| --- | --- |
| Dấu ngoặc kép `"` | `\"` |
| Dấu gạch chéo ngược `\` | `\\` |
| Xuống dòng | `\n` |
| Tab | `\t` |
| Ký tự điều khiển | Có thể dùng dạng `\u00XX` |
| Ký tự Unicode | Có thể viết trực tiếp bằng UTF-8 hoặc dùng `\uXXXX` phù hợp |

Ví dụ hai chuỗi JSON sau có thể được parse thành cùng một giá trị:

~~~json
{"message":"Dòng một\nDòng hai"}
~~~

~~~json
{"message":"Dòng một\u000aDòng hai"}
~~~

Trong JSON đầu, đoạn xuống dòng được biểu diễn bằng hai ký tự escape `\` và `n`; trong JSON sau, nó được biểu diễn bằng chuỗi escape Unicode. Sau khi parse, giá trị chuỗi có thể giống nhau, nhưng các byte JSON đầu vào khác nhau.

Các khác biệt khác cũng có thể làm thay đổi byte:

- Khoảng trắng sau dấu `:` hoặc `,`.
- Thứ tự thuộc tính trong object.
- Ký tự Unicode trực tiếp so với escape Unicode.
- Cách viết escape chữ số hex hoa/thường.
- Cách biểu diễn một giá trị số, ví dụ `1`, `1.0` hoặc `1e0`.

JSON object về mặt dữ liệu không phụ thuộc thứ tự thuộc tính. Tuy nhiên, quy trình ký JWS không ký một object trừu tượng; nó ký **chuỗi byte đã mã hóa** theo định dạng JWS. Vì vậy, thay đổi cách serialize có thể làm chữ ký thay đổi dù dữ liệu sau parse có cùng ý nghĩa.

## 6. Từ JSON/UTF-8 đến Base64url trong JWS

Với JWT được bảo vệ bằng **JWS Compact**, protected header và JWT Claims Set được chuyển thành UTF-8 bytes, sau đó Base64url riêng từng phần.

~~~text
headerBytes  = UTF8(JSON(header))
payloadBytes = UTF8(JSON(claims))

headerPart  = BASE64URL(headerBytes)
payloadPart = BASE64URL(payloadBytes)

signingInput = ASCII(headerPart + "." + payloadPart)
signature    = SIGN(signingInput, signingKey, algorithm)

token = headerPart + "." + payloadPart + "." + BASE64URL(signature)
~~~

Ví dụ về nội dung trước khi encode:

~~~json
Header:
{
  "alg": "HS256",
  "typ": "JWT"
}
~~~

~~~json
Payload:
{
  "sub": "customer-42",
  "name": "Trần Thị Ánh",
  "exp": 1893456300
}
~~~

Quy trình tạo token:

1. Tạo JSON header và claims hợp lệ.
2. Serialize mỗi object thành JSON text.
3. Encode từng JSON text thành UTF-8 bytes.
4. Base64url bytes của header và payload, bỏ padding `=` theo quy tắc Compact Serialization.
5. Ghép `headerPart.payloadPart` để tạo **signing input**.
6. Tạo signature trên đúng signing input bằng thuật toán và khóa được phép.
7. Base64url signature bytes rồi ghép thành chuỗi ba phần.

### Vì sao phải giữ nguyên hai phần đầu?

Khi xác minh JWS, bên nhận phải dùng nguyên văn `headerPart` và `payloadPart` nhận được để tái tạo signing input:

~~~text
signingInput = ASCII(receivedHeaderPart + "." + receivedPayloadPart)
~~~

Không được làm theo quy trình sau trước khi xác minh:

1. Decode Base64url.
2. Parse JSON.
3. Sắp xếp lại các thuộc tính hoặc đổi khoảng trắng.
4. Serialize JSON thành chuỗi mới.
5. Encode lại Base64url rồi xác minh chữ ký.

Cách làm này thay đổi byte đầu vào. Dù JSON mới có thể mang cùng giá trị, signature ban đầu được tạo trên byte cũ và phép xác minh có thể thất bại. Một bên xác minh đúng phải kiểm tra chữ ký trên **chuỗi Compact nguyên bản**.

**Base64url khác Base64 thông thường:** ký tự `+` được thay bằng `-`, `/` được thay bằng `_`, và phần đệm `=` được bỏ trong Compact Serialization. Base64url là biểu diễn byte, không phải một lớp bảo vệ bí mật.

## 7. JSON/UTF-8 trong JWT dạng JWE

Với **JWE Compact**, protected header vẫn là JSON được encode UTF-8 rồi Base64url để tạo phần đầu tiên. Nội dung JWT Claims Set được serialize thành JSON text và chuyển thành UTF-8 bytes trước khi đưa vào thuật toán mã hóa nội dung.

~~~text
headerBytes = UTF8(JSON(protectedHeader))
headerPart  = BASE64URL(headerBytes)

plaintextBytes = UTF8(JSON(jwtClaimsSet))

(ciphertext, tag) = AUTHENTICATED_ENCRYPT(
    CEK,
    IV,
    plaintextBytes,
    AAD = ASCII(headerPart)
)

token = headerPart
      + "." + BASE64URL(encryptedKey)
      + "." + BASE64URL(IV)
      + "." + BASE64URL(ciphertext)
      + "." + BASE64URL(tag)
~~~

Trong JWE, phần ciphertext là kết quả mã hóa của plaintext bytes. **Không thể lấy ciphertext, Base64url decode rồi đọc trực tiếp JSON**; cần khôi phục CEK và hoàn thành kiểm tra xác thực mật mã trước. Chỉ sau khi giải mã thành công mới decode plaintext bytes thành UTF-8 và parse JSON claims.

Quy trình đọc payload JWE:

1. Kiểm tra cấu trúc và chính sách thuật toán của token.
2. Khôi phục CEK bằng cơ chế quản lý khóa đã cấu hình.
3. Xác thực và giải mã JWE bằng đúng IV, ciphertext, tag và AAD.
4. Nếu xác thực thất bại, từ chối và không sử dụng plaintext.
5. Nếu thành công, kiểm tra byte plaintext là UTF-8 hợp lệ.
6. Parse JSON thành JWT Claims Set rồi kiểm tra claim và quyền theo chính sách.

Protected Header của JWE vẫn đọc được sau khi Base64url decode. Vì thế, không đưa thông tin bí mật vào header. Dữ liệu claim cần giữ kín thuộc về plaintext được mã hóa.

## 8. Những khác biệt JSON có thể làm thay đổi chữ ký

Bảng dưới đây cho thấy các JSON có thể biểu diễn cùng dữ liệu nhưng không nhất thiết có cùng byte:

| Trường hợp | JSON A | JSON B | Byte có thể khác? |
| --- | --- | --- | --- |
| Khoảng trắng | `{"sub":"u1"}` | `{ "sub" : "u1" }` | Có |
| Thứ tự thuộc tính | `{"sub":"u1","role":"reader"}` | `{"role":"reader","sub":"u1"}` | Có |
| Escape Unicode | `{"name":"ế"}` | `{"name":"\u1ebf"}` | Có |
| Cách viết số | `{"score":1}` | `{"score":1.0}` | Có |
| Escape ký tự điều khiển | `{"v":"\n"}` | `{"v":"\u000a"}` | Có |

Do đó, hai hệ thống không nên tự đặt giả định rằng serialize một JSON object sẽ luôn tạo cùng một chuỗi byte trên mọi thư viện hoặc nền tảng.

JWT/JWS thông thường không yêu cầu **JSON Canonicalization Scheme (JCS)** trước khi ký. Nếu một giao thức riêng yêu cầu canonicalization, cả bên phát hành và bên xác minh phải tuân thủ chính xác cùng một quy tắc đã được thỏa thuận. Không tự ý canonicalize token nhận được rồi mới xác minh JWS.

### Tên thuộc tính trùng lặp

JSON có thể được một số bộ phân tích xử lý khác nhau khi object chứa hai thuộc tính cùng tên. Ví dụ:

~~~json
{
  "sub": "customer-42",
  "sub": "administrator"
}
~~~

Điều này dễ tạo ra cách hiểu không thống nhất giữa các hệ thống. JWT quy định cách xử lý claim name trùng lặp, nhưng ứng dụng an toàn nên **từ chối JSON có tên claim trùng lặp** để tránh khác biệt giữa parser, log, bộ xác minh và logic phân quyền. Các tên tham số trong JOSE header cũng cần tuân thủ quy tắc duy nhất của đặc tả tương ứng.

## 9. Lỗi thường gặp khi xử lý JSON và UTF-8

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Encode UTF-16 thay vì UTF-8 | Byte không đúng định dạng JWT yêu cầu, token không tương thích | Encode JSON bằng UTF-8 |
| Parse rồi serialize lại trước khi xác minh JWS | Thay đổi byte signing input, chữ ký có thể không khớp | Xác minh trên hai phần Compact nguyên bản |
| Xem Base64url là mã hóa bí mật | Để lộ claim trong payload JWS | Không đặt bí mật vào JWS payload; dùng JWE khi cần tính bí mật |
| Thay thế byte UTF-8 lỗi bằng ký tự thay thế | Nội dung được parse khác dữ liệu ban đầu | Từ chối dữ liệu UTF-8 không hợp lệ |
| Dùng sai kiểu claim | Kiểm tra `exp`, `aud` hoặc quyền không chính xác | Kiểm tra kiểu và giá trị theo đặc tả |
| Tin vào claim trước khi xác minh | Kẻ tấn công có thể sửa payload để tác động đến logic | Chỉ sử dụng claim sau khi hoàn tất xác minh và kiểm tra chính sách |
| Không giới hạn kích thước hoặc độ sâu JSON | Có thể tiêu tốn CPU/bộ nhớ khi parse | Đặt giới hạn kích thước, độ sâu và số phần tử |
| Chuẩn hóa Unicode hoặc đổi nội dung token trước khi xác minh | Thay đổi byte đã được ký hoặc tạo khác biệt định danh | Giữ nguyên token khi xác minh; quy định chuẩn hóa ở tầng ứng dụng |
| Cho phép tên claim trùng lặp không nhất quán | Các thành phần có thể hiểu cùng token theo cách khác nhau | Từ chối tên trùng lặp hoặc áp dụng chính sách parser thống nhất |

## 10. Ví dụ luồng xử lý end-to-end

Một dịch vụ phát hành token cho khách hàng tên **Trần Thị Ánh**. Dịch vụ tạo claims:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "name": "Trần Thị Ánh",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456300
}
~~~

Luồng phát hành và tiếp nhận:

~~~mermaid
flowchart TD
    A["Tạo Claims Set JSON"] --> B["Serialize thành JSON text"]
    B --> C["Encode UTF-8 bytes"]
    C --> D["Base64url payload (JWS) hoặc mã hóa plaintext (JWE)"]
    H["Tạo Header JSON"] --> I["Serialize JSON"]
    I --> J["Encode UTF-8 bytes"]
    J --> K["Base64url protected header"]
    K --> L["Tạo signing input / AAD"]
    D --> M["Tạo JWS signature hoặc JWE authentication tag"]
    L --> M
    M --> N["Ghép JWT Compact"]
    N --> O["Bên nhận kiểm tra cấu trúc và xác minh mật mã"]
    O --> P["Parse JSON/UTF-8 và kiểm tra claim"]
    P --> Q["Áp dụng chính sách truy cập"]
~~~

Bên nhận cần tuân thủ thứ tự xử lý phù hợp với loại token:

- Với **JWS**, xác minh signature trên chuỗi phần đầu và payload nguyên bản trước khi tin cậy claims. Sau đó parse payload JSON và kiểm tra `iss`, `aud`, `exp`, `nbf` cùng quyền.
- Với **JWE**, xác thực và giải mã thành công trước; sau đó xác nhận plaintext là UTF-8 hợp lệ, parse claims và kiểm tra chính sách. Nếu payload là JWT lồng nhau, tiếp tục xác minh lớp JWT bên trong theo quy tắc của giao thức.

Trong cả hai trường hợp, dữ liệu JSON đã parse vẫn là dữ liệu đầu vào cần kiểm tra: sự hiện diện của claim, kiểu dữ liệu, độ dài chuỗi, miền giá trị và quyền phải phù hợp với chính sách của ứng dụng.

## 11. Checklist khi xây dựng và xử lý JWT

- Header và JWT Claims Set được biểu diễn thành JSON object hợp lệ.
- JSON text được encode thành UTF-8 bytes đúng quy tắc.
- Không thêm BOM hoặc tự thay đổi byte trước khi xác minh.
- Dùng Base64url đúng quy tắc Compact Serialization; không nhầm với Base64 thông thường.
- Giữ nguyên các phần token gốc để xác minh JWS.
- Với JWE, chỉ parse plaintext sau khi xác thực và giải mã thành công.
- Kiểm tra kiểu dữ liệu claim, đặc biệt là NumericDate, `aud` và các claim ứng dụng.
- Từ chối JSON lỗi, UTF-8 lỗi, dữ liệu vượt giới hạn và các trường hợp tên thuộc tính trùng lặp không được chấp nhận.
- Không tin claim, header hoặc metadata chỉ vì đã decode Base64url.
- Không đưa bí mật vào JWS payload hoặc JOSE header; chọn JWE nếu cần mã hóa nội dung.
- Định nghĩa cách xử lý Unicode/chuẩn hóa định danh ở tầng ứng dụng, không biến đổi token trước bước xác minh.

**Ghi nhớ:** JSON xác định cấu trúc của header và claims; UTF-8 chuyển JSON text thành byte; Base64url tạo các phân đoạn Compact dễ truyền. JWS xác minh trên byte được biểu diễn trong signing input, còn JWE mã hóa byte plaintext và xác thực dữ liệu liên quan. Vì vậy, phải giữ nguyên token trong bước xác minh và chỉ sử dụng claims sau khi hoàn tất các kiểm tra mật mã, kiểu dữ liệu và chính sách.

### Tài liệu chuẩn để tra cứu

- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT Claims Set, registered claims và yêu cầu UTF-8.
- **RFC 7515 — JSON Web Signature (JWS):** cách biểu diễn protected header, payload và signing input.
- **RFC 7516 — JSON Web Encryption (JWE):** protected header, AAD và quy trình mã hóa/giải mã.
- **RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format:** cú pháp JSON, Unicode và UTF-8.
- **RFC 8725 — JSON Web Token Best Current Practices:** xử lý JWT an toàn, xác minh đúng ngữ cảnh và tránh cách hiểu không nhất quán.

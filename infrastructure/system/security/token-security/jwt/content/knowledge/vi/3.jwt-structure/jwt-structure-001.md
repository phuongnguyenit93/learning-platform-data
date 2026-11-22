# Ba thành phần header, payload và signature của JWT dạng JWS Compact

## 1. JWT dạng JWS Compact là gì?

Trong chủ đề **Security - JSON Web Token (JWT)**, một JWT có thể được biểu diễn dưới dạng **JWS Compact Serialization**: một chuỗi gồm **ba phần**, ngăn cách bằng hai dấu chấm, thường được dùng để chuyển các thông tin định danh và quyền truy cập giữa các hệ thống.

~~~text
<protected-header>.<payload>.<signature>
        (1)          (2)        (3)
~~~

Công thức khái quát của trường hợp JWT thông thường có payload là JSON:

~~~text
headerPart    = BASE64URL(UTF8(JSON(header)))
payloadPart   = BASE64URL(UTF8(JSON(claims)))
signingInput  = ASCII(headerPart + "." + payloadPart)
signaturePart = BASE64URL(SIGN_OR_MAC(signingInput, key, algorithm))

token = headerPart + "." + payloadPart + "." + signaturePart
~~~

**JWT** (JSON Web Token) là một định dạng mang các *claim*; **JWS** (JSON Web Signature) quy định cách bảo vệ tính toàn vẹn và xác thực nguồn phát hành của nội dung bằng chữ ký số hoặc mã xác thực thông điệp (MAC). Khi JWT dùng JWS Compact, kết quả có ba phần như trên. JWT cũng có thể dùng **JWE** (JSON Web Encryption) để mã hóa và dạng JWE Compact thường có **năm phần**. Vì vậy, quy tắc “JWT có ba phần” chỉ đúng trong phạm vi **JWT dạng JWS Compact** đang học.

**Điểm cốt lõi:** phần header và payload chỉ được **mã hóa biểu diễn** bằng Base64url, không được giữ bí mật. Bất kỳ ai có chuỗi token đều có thể giải mã hai phần đó để đọc. Signature dùng để phát hiện thay đổi trái phép và xác minh bằng khóa phù hợp; nó **không mã hóa** payload và không ngăn người khác xem hoặc sao chép token.

## 2. Nhìn toàn cảnh cấu trúc ba phần

| Phần | Nội dung sau khi giải mã | Vai trò | Có thể đọc nếu chỉ có token? |
| --- | --- | --- | --- |
| **Header** (phần 1) | JSON mô tả cách bảo vệ JWS, nổi bật là thuật toán | Cho bên kiểm tra biết thông tin cần thiết để lựa chọn cách xác minh | Có |
| **Payload** (phần 2) | Với JWT thông thường: JSON chứa các claim | Chuyển tải dữ kiện và ngữ cảnh định danh/ủy quyền | Có |
| **Signature** (phần 3) | Byte chữ ký số hoặc MAC, sau khi giải Base64url | Ràng buộc header và payload với khóa đã dùng để ký | Không thể suy ra khóa hoặc nội dung bí mật chỉ bằng giải mã |

~~~mermaid
flowchart LR
    A["Header JSON"] --> B["Base64url"]
    C["Payload JSON / Claims"] --> D["Base64url"]
    B --> E["header.payload"]
    D --> E
    E --> F["Ký / MAC bằng khóa tin cậy"]
    F --> G["Base64url(signature)"]
    E --> H["header.payload.signature"]
    G --> H
~~~

Dấu chấm là **ký tự phân tách**; nó không nằm trong chuỗi Base64url của từng phần. Bộ giải mã cần kiểm tra cấu trúc, loại dữ liệu, giới hạn kích thước và định dạng trước khi dùng dữ liệu. Một chuỗi “trông giống JWT” chưa chứng tỏ nó hợp lệ.

### Base64url khác gì Base64 thông thường?

Base64url sử dụng bảng ký tự an toàn hơn khi truyền qua URL và các giao thức văn bản:

- Thay ký tự **+** bằng **-**, thay **/** bằng **_**.
- Trong JWS Compact, **bỏ ký tự đệm =** ở cuối.
- Hai phần đầu là byte văn bản JSON được chuyển sang chuỗi Base64url; phần thứ ba là **byte chữ ký/MAC** được chuyển sang Base64url.

**Giải mã Base64url chỉ là đọc biểu diễn dữ liệu, hoàn toàn không phải xác minh token.** Việc xác minh phải dùng thuật toán và khóa tin cậy.

## 3. Phần 1 — Header: mô tả cơ chế bảo vệ

Một protected header thường gặp:

~~~json
{
  "alg": "HS256",
  "typ": "JWT"
}
~~~

Các tham số có ý nghĩa quan trọng:

| Tham số | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| **alg** | Thuật toán bảo vệ JWS, chẳng hạn HS256, RS256, ES256 hoặc EdDSA | Thông tin trong token do người gửi cung cấp; hệ thống nhận phải đối chiếu với thuật toán đã được **cấu hình cho phép** |
| **typ** | Gợi ý loại đối tượng, thường là JWT | Có thể vắng mặt; có giá trị phân biệt các loại token khi giao thức quy định, nhưng không thay thế bước xác minh |
| **kid** | Định danh khóa, giúp tìm khóa tương ứng khi có nhiều khóa hoặc khi xoay khóa | Chỉ là **gợi ý chọn khóa**; không được dùng như đường dẫn, truy vấn hay nguồn khóa tùy ý do token chỉ định |
| **cty** | Cho biết kiểu nội dung lồng bên trong khi dùng cấu trúc lồng nhau | Không cần trong trường hợp JWT đơn giản |

Header của JWS còn có các tham số khác và cơ chế phần mở rộng như **crit**. Nếu gặp tham số bảo vệ bắt buộc mà hệ thống không hiểu hoặc không hỗ trợ, phải từ chối theo quy tắc của JWS.

Header không được xem là cấu hình đáng tin cậy. Ví dụ, kẻ tấn công có thể thay giá trị **alg** trong một chuỗi tự tạo; bên xác minh phải dùng chính sách thuật toán và loại khóa của **ứng dụng**, không tự động chấp nhận thuật toán mà token yêu cầu.

## 4. Phần 2 — Payload: tập hợp các claim

*Claim* là một phát biểu về chủ thể hoặc ngữ cảnh token. Payload của JWT thông thường là một **JWT Claims Set** dưới dạng JSON. Ví dụ:

~~~json
{
  "iss": "https://issuer.example",
  "sub": "user-123",
  "aud": "orders-api",
  "iat": 1700000000,
  "nbf": 1700000000,
  "exp": 1700000600,
  "scope": "orders:read"
}
~~~

Trong ví dụ, **exp** cách **iat** 600 giây, tức khoảng 10 phút. Các con số là mốc thời gian ví dụ, không phải thời gian hiệu lực hiện tại.

Các claim phổ biến:

| Claim | Ý nghĩa | Lưu ý khi xác minh |
| --- | --- | --- |
| **iss** (*issuer*) | Đơn vị phát hành token | Phải khớp nhà phát hành mà hệ thống tin cậy |
| **sub** (*subject*) | Chủ thể được mô tả, thường là mã người dùng hoặc dịch vụ | Không mặc nhiên là tên người dùng hay địa chỉ email; phải hiểu theo quy ước của nhà phát hành |
| **aud** (*audience*) | Đối tượng/ứng dụng mà token hướng tới | Có thể là chuỗi hoặc mảng chuỗi; dịch vụ nhận phải kiểm tra mình thuộc đối tượng được phép |
| **exp** (*expiration time*) | Thời điểm sau đó token không còn được chấp nhận | Theo định dạng **NumericDate**: số giây kể từ Unix epoch, không phải mili giây |
| **nbf** (*not before*) | Thời điểm sớm nhất token được chấp nhận | Cần so sánh với thời gian hiện tại, có thể xét dung sai lệch đồng hồ nhỏ |
| **iat** (*issued at*) | Thời điểm phát hành | Hỗ trợ đánh giá tuổi token; **không thay thế exp** |
| **jti** (*JWT ID*) | Định danh duy nhất của token | Có thể hỗ trợ phát hiện phát lại hoặc thu hồi khi có cơ chế lưu trạng thái tương ứng |
| **scope**, **role** | Quyền hoặc thông tin ứng dụng tự định nghĩa | Không phải bằng chứng cho quyền truy cập nếu chưa xác minh token và đối chiếu chính sách |

Các claim như **iss**, **sub**, **aud**, **exp**, **nbf**, **iat** và **jti** được đăng ký trong đặc tả JWT; claim ứng dụng như **scope** do hệ thống quy định. Đặc tả JWT **không bắt buộc mọi token chứa toàn bộ claim trên**. Từng ứng dụng cần định nghĩa những claim nào bắt buộc, kiểu dữ liệu và giá trị nào hợp lệ.

Payload cũng có thể chứa dữ liệu nhạy cảm nếu người tạo thiết kế sai. Vì JWS không mã hóa, **không đặt mật khẩu, bí mật API, thông tin cá nhân nhạy cảm hoặc dữ liệu không muốn lộ** trong payload. Đưa ra quyết định ủy quyền chỉ từ trường **role** hoặc **scope** trước khi xác minh signature và các điều kiện hiệu lực là lỗi bảo mật.

## 5. Phần 3 — Signature: bảo vệ toàn vẹn và nguồn phát hành

Signature được tạo từ **chính hai phần đã mã hóa** đứng trước nó, gồm cả dấu chấm nằm giữa:

~~~text
signingInput = ASCII(BASE64URL(header) + "." + BASE64URL(payload))
~~~

Với **HS256**, thao tác bảo vệ dùng HMAC-SHA-256 và một khóa bí mật dùng chung:

~~~text
macBytes     = HMAC-SHA-256(secretKey, signingInput)
signature    = BASE64URL(macBytes)
compactJws   = headerPart + "." + payloadPart + "." + signature
~~~

Với các thuật toán chữ ký số bất đối xứng, ví dụ **RS256**, **ES256** hoặc **EdDSA**, bên phát hành **ký bằng khóa riêng tư**, bên nhận **xác minh bằng khóa công khai** tương ứng. Cơ chế tính toán chữ ký khác HMAC, nhưng cấu trúc ba phần và nguyên tắc ký trên **signingInput** vẫn giữ nguyên.

| Thuật toán ví dụ | Kiểu bảo vệ | Khóa dùng để tạo | Khóa dùng để xác minh |
| --- | --- | --- | --- |
| **HS256** | MAC với HMAC-SHA-256 | Khóa bí mật dùng chung | Cùng khóa bí mật |
| **RS256** | Chữ ký số RSA với SHA-256 | Khóa riêng tư | Khóa công khai |
| **ES256** | Chữ ký số ECDSA với P-256 và SHA-256 | Khóa riêng tư | Khóa công khai |
| **EdDSA** | Chữ ký số Edwards-curve (tùy khóa) | Khóa riêng tư | Khóa công khai |

Không nên nói rằng mọi signature đều “giải mã bằng public key”: **xác minh chữ ký** là một phép toán mật mã, và HS256 thậm chí không dùng cặp khóa công khai/riêng tư.

Nếu thay đổi payload từ **orders:read** thành **orders:write**, chuỗi payloadPart đổi theo, khiến signingInput thay đổi. Signature cũ sẽ không còn xác minh được với khóa đúng. Tương tự, thay header cũng làm thay đổi dữ liệu đã được bảo vệ.

Tuy nhiên, **signature hợp lệ chưa đồng nghĩa được phép truy cập**: token có thể hết hạn, dành cho một ứng dụng khác, bị thu hồi hoặc mang quyền không đủ cho hành động đang yêu cầu. Chữ ký cũng không chứng minh người đang gửi token chính là chủ thể được nhắc trong token; một token bị đánh cắp có thể bị sử dụng lại nếu không có biện pháp phù hợp.

## 6. Ví dụ tách và đọc ba phần

Xét hai phần đầu của một JWT minh họa:

~~~text
Header:
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9

Payload:
eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ

Signature:
<base64url-cua-chu-ky-thuc-te>
~~~

Chuỗi trên là **minh họa cấu trúc**, do chữ ký đang là placeholder nên **không phải JWT hợp lệ để xác minh**. Giải mã phần đầu và phần giữa thu được:

~~~json
{
  "alg": "HS256",
  "typ": "JWT"
}
~~~

~~~json
{
  "sub": "1234567890",
  "name": "John Doe",
  "iat": 1516239022
}
~~~

Ví dụ này cho thấy người cầm token có thể thấy **sub**, **name**, **iat** mà không sở hữu khóa. Nếu chỉ đưa hai phần đầu vào công cụ giải mã JWT, công cụ có thể hiển thị JSON, nhưng **chưa thể xác nhận chữ ký** nếu không có khóa tin cậy và quy tắc kiểm tra tương ứng.

Khi xác minh, phải dùng **nguyên văn chuỗi headerPart và payloadPart nhận được** để tái tạo signingInput. Không parse JSON rồi tùy ý sắp xếp lại thuộc tính, thêm khoảng trắng hoặc serialize lại trước khi xác minh; cùng ý nghĩa JSON có thể tạo ra chuỗi byte khác và dẫn đến signature khác.

## 7. Quy trình tạo và xác minh JWT dạng JWS Compact

### Khi phát hành

1. Xác định người phát hành, đối tượng nhận, thời hạn sống và các claim tối thiểu theo chính sách.
2. Tạo header với thuật toán đã được hệ thống cho phép; chọn khóa đúng loại và mục đích.
3. Chuyển header và payload thành byte UTF-8, sau đó Base64url không padding.
4. Ghép hai phần bằng dấu chấm, ký hoặc tạo MAC trên đúng **signingInput**.
5. Base64url các byte chữ ký/MAC và ghép thành chuỗi ba phần.

### Khi tiếp nhận và sử dụng

~~~mermaid
flowchart TD
    A["Nhận chuỗi token"] --> B{"Đúng định dạng 3 phần và giới hạn đầu vào?"}
    B -- "Không" --> X["Từ chối"]
    B -- "Có" --> C["Đọc protected header, chọn khóa từ nguồn tin cậy"]
    C --> D{"Thuật toán, loại khóa và header được phép?"}
    D -- "Không" --> X
    D -- "Có" --> E{"Xác minh signature/MAC trên đúng 2 phần gốc?"}
    E -- "Không" --> X
    E -- "Có" --> F{"Claim hợp lệ: iss, aud, exp, nbf và yêu cầu ứng dụng?"}
    F -- "Không" --> X
    F -- "Có" --> G["Đánh giá quyền truy cập và các kiểm soát bổ sung"]
~~~

Ở bước đọc header để chọn khóa, dữ liệu **vẫn chưa đáng tin**. Bộ kiểm tra cần có danh sách thuật toán được phép, khóa gắn với nhà phát hành tin cậy và quy tắc xử lý lỗi chặt chẽ. Không được lấy tùy ý đường dẫn, URL hoặc khóa được nhúng/gợi ý từ header làm nguồn tin cậy.

Sau xác minh mật mã, hệ thống còn cần kiểm tra các claim mà ngữ cảnh yêu cầu, chẳng hạn:

- **iss** là nhà phát hành được tin cậy và khóa xác minh thực sự thuộc về nhà phát hành đó.
- **aud** chứa chính dịch vụ đang xử lý yêu cầu; không nhận token cấp cho một dịch vụ khác.
- **exp** chưa qua và **nbf** đã đến thời điểm hiệu lực; cho phép lệch đồng hồ nhỏ nếu chính sách có quy định.
- Các claim bắt buộc hiện diện và có kiểu dữ liệu hợp lệ; **scope/role** thực sự cho phép thao tác được yêu cầu.
- Với trường hợp cần kiểm soát thu hồi, phát lại hoặc phiên đăng nhập, áp dụng các kiểm soát bổ sung như trạng thái phiên, danh sách thu hồi hoặc ràng buộc token với người sở hữu nếu hệ thống hỗ trợ.

**Lưu ý về alg = none:** JWS/JWT có khái niệm token không được bảo vệ bằng chữ ký; khi đó phần signature có thể rỗng. Phần lớn quy trình xác thực dùng bearer token phải **từ chối** dạng này, trừ khi một giao thức đặc biệt cho phép rõ ràng và có bảo vệ thay thế. Đừng coi hai dấu chấm phân cách hay trường **typ: JWT** là bằng chứng về tính xác thực.

## 8. Các nhầm lẫn thường gặp

| Nhận định sai | Hiểu đúng |
| --- | --- |
| “Payload không đọc được vì đã encode.” | Base64url không mã hóa bí mật; có thể giải mã mà không cần khóa. |
| “Có đủ ba phần nghĩa là token đáng tin.” | Phải xác minh chữ ký/MAC, thuật toán, khóa, các claim và chính sách ứng dụng. |
| “Sửa role trong payload là được cấp quyền.” | Thay payload khiến chữ ký cũ không còn phù hợp; bên nhận chuẩn phải từ chối. |
| “Signature bảo vệ token khỏi bị đánh cắp.” | Signature bảo vệ tính toàn vẹn và nguồn ký; việc sao chép/phát lại token là rủi ro riêng. |
| “Token được ký là mãi mãi hợp lệ.” | Thời hạn, audience, issuer, thu hồi và quyền phải được kiểm tra theo ngữ cảnh. |
| “Trường alg trong header quyết định tuyệt đối thuật toán xác minh.” | Chỉ chấp nhận các thuật toán đã cấu hình; cần loại khóa phù hợp để ngăn nhầm lẫn thuật toán. |
| “JWT luôn có ba phần.” | JWT dạng JWS Compact có ba phần; JWT dạng JWE Compact thường có năm phần. |

## 9. Tình huống thực tế

Một dịch vụ danh tính phát hành JWT dạng JWS Compact cho khách hàng truy cập API đơn hàng. Header chứa thuật toán ký được cho phép và có thể có **kid** để chọn khóa. Payload chứa **iss** của dịch vụ danh tính, **sub** của khách hàng, **aud** là API đơn hàng, **exp** và quyền **orders:read**.

Khi nhận yêu cầu xem đơn hàng, API xác minh signature bằng khóa tin cậy; kiểm tra **iss**, **aud**, **exp** và quyền đọc trước khi trả dữ liệu phù hợp với khách hàng. Nếu người dùng tự đổi **orders:read** thành **orders:write** trong payload mà không có khóa ký, chữ ký sẽ không còn hợp lệ. Nếu một API khác nhận lại token này nhưng không thuộc **aud**, API đó phải từ chối ngay cả khi signature vẫn hợp lệ.

Trong quá trình triển khai, nên dùng kết nối bảo mật khi truyền JWT, hạn chế ghi nguyên token vào log, dùng thời hạn ngắn hợp lý và bảo vệ khóa ký. Các kiểm soát đó bổ sung cho cấu trúc ba phần, không thể thay thế việc xác minh JWS.

## 10. Tự kiểm tra kiến thức

1. Vì sao một người không có khóa ký vẫn có thể đọc **sub** hoặc **scope** từ JWT dạng JWS Compact?
2. Thay một ký tự trong payloadPart làm ảnh hưởng đến signingInput và signature như thế nào?
3. Sự khác biệt giữa MAC của **HS256** và chữ ký số của **RS256** về khóa xác minh là gì?
4. Vì sao token có signature hợp lệ vẫn có thể bị từ chối do **aud**, **exp** hoặc **scope**?
5. Khi có **kid** và **alg** trong header, vì sao bên nhận không thể tin tuyệt đối các giá trị này?

**Ghi nhớ:** JWT dạng JWS Compact được tổ chức thành **header.payload.signature**. Header diễn tả cơ chế bảo vệ; payload mang claim có thể đọc được; signature/MAC ràng buộc hai phần trước với khóa. Một hệ thống an toàn phải **xác minh mật mã rồi áp dụng đầy đủ chính sách sử dụng token** trước khi tin và dùng các claim.

### Tài liệu chuẩn để tra cứu thêm

- RFC 7515 — JSON Web Signature (JWS): định dạng Compact Serialization và quy trình ký/xác minh.
- RFC 7519 — JSON Web Token (JWT): JWT Claims Set, các registered claims và cách biểu diễn JWT.
- RFC 7518 — JSON Web Algorithms (JWA): các thuật toán ký/MAC phổ biến.
- RFC 8725 — JSON Web Token Best Current Practices: nguyên tắc xác minh an toàn, hạn chế nhầm lẫn thuật toán và ngữ cảnh token.

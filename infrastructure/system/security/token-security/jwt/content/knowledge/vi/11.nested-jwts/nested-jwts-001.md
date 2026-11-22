# Nested JWT là gì và những trường hợp cần kết hợp ký với mã hóa

> **Chương:** JWT lồng nhau  
> **Phạm vi:** Security – JSON Web Token (JWT), áp dụng độc lập với ngôn ngữ lập trình, framework và nền tảng triển khai.

## 1. Nested JWT là gì?

**Nested JWT (JWT lồng nhau)** là JWT được đặt làm nội dung (payload hoặc plaintext) của một cấu trúc JWS hoặc JWE khác. Thay vì chỉ áp dụng một thao tác mật mã, bên phát hành có thể áp dụng nhiều lớp bảo vệ liên tiếp. Định nghĩa này nằm trong [RFC 7519, mục 2](https://www.rfc-editor.org/rfc/rfc7519.html#section-2).

Hai công nghệ nền tảng cần phân biệt:

| Cấu trúc | Chức năng chính | Điều có thể và không thể kết luận |
|---|---|---|
| **JWS** (JSON Web Signature) | Bảo vệ tính toàn vẹn bằng chữ ký số hoặc MAC. | Khi xác minh thành công bằng khóa tin cậy, có thể xác định nội dung không bị sửa và được tạo bởi bên nắm khóa tương ứng. **Không che giấu claims**: payload của JWS thông thường chỉ được mã hóa base64url. |
| **JWE** (JSON Web Encryption) | Mã hóa nội dung và cung cấp bảo vệ toàn vẹn của bản mã bằng cơ chế mã hóa có xác thực. | Người không có khóa giải mã phù hợp không đọc được plaintext. Tuy nhiên, **giải mã JWE thành công không tự chứng minh JWT do đúng issuer phát hành**, đặc biệt khi bất kỳ ai có khóa công khai của người nhận đều có thể tạo JWE. |
| **Nested JWT** | Đặt một JWS/JWE bên trong lớp JWS/JWE khác. | Có thể kết hợp **xác thực nguồn phát hành, toàn vẹn nội dung và bí mật thông tin**, tùy thứ tự lớp và chính sách kiểm tra. |

Cấu hình phổ biến nhất khi cần cả chữ ký lẫn mã hóa là:

**Claims → ký thành JWS → mã hóa toàn bộ JWS thành JWE.**

Ở cấu hình này, JWT gửi đi có hình thức **JWE**, còn nội dung bên trong sau khi giải mã là **JWS**. Đây thường được gọi là **sign-then-encrypt** (ký trước, mã hóa sau).

Không phải mọi JWT có nhiều claims hoặc nhiều phần ngăn bởi dấu chấm đều là Nested JWT. Điều quyết định là **một đối tượng JWT hoàn chỉnh được nhúng trong một cấu trúc JOSE bên ngoài**.

## 2. Vì sao cần cả ký và mã hóa?

Giả sử một hệ thống phát hành token cho API đối tác. Token chứa định danh tài khoản, phạm vi được phép truy cập và thông tin nghiệp vụ nhạy cảm.

- **Chỉ ký bằng JWS:** API xác minh được chữ ký của bên phát hành, nhưng bất kỳ bên nào có chuỗi token đều có thể giải mã base64url để đọc claims.
- **Chỉ mã hóa bằng JWE:** Bên ngoài không đọc được claims, nhưng riêng việc giải mã thành công không đủ để khẳng định ai đã phát hành nội dung và liệu người phát hành đó có được API tin cậy hay không.
- **Ký rồi mã hóa:** API giải mã bằng khóa của mình, sau đó xác minh JWS bằng khóa của issuer đã được tin cậy. Hai lớp giải quyết hai yêu cầu khác nhau.

Các mục tiêu cần tách bạch:

1. **Confidentiality – tính bí mật:** Ngăn bên không có quyền giải mã đọc nội dung.
2. **Integrity – tính toàn vẹn:** Phát hiện nội dung bị thay đổi trái phép.
3. **Issuer authentication – xác thực bên phát hành:** Xác minh chữ ký/MAC và ràng buộc khóa xác minh với issuer được phép.
4. **Authorization – ủy quyền:** Kiểm tra claims, quyền truy cập và ngữ cảnh nghiệp vụ; một token có chữ ký hợp lệ vẫn có thể không được phép thực hiện hành động đang yêu cầu.

JWE cung cấp tính bí mật và tính toàn vẹn của plaintext nhờ authenticated encryption; JWS giúp xác thực nguồn phát hành khi có quan hệ tin cậy về khóa. **Không lớp mật mã nào thay thế bước kiểm tra quyền của ứng dụng.**

## 3. Cấu trúc và luồng xử lý sign-then-encrypt

~~~mermaid
flowchart TD
    A["Claims JSON"] --> B["Issuer ký claims bằng JWS"]
    B --> C["JWT bên trong: JWS"]
    C --> D["Mã hóa toàn bộ JWS bằng JWE cho recipient"]
    D --> E["Nested JWT bên ngoài: JWE"]
    E --> F["Recipient giải mã và xác thực JWE"]
    F --> G["Xác minh chữ ký JWS và issuer"]
    G --> H["Kiểm tra claims, thời hạn, audience và quyền"]
~~~

### 3.1. Lớp trong: JWT đã ký (JWS)

Ví dụ tập claims giả định:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "account-123",
  "aud": "invoice-api",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000300,
  "scope": "invoice:read",
  "invoice_id": "inv-456"
}
~~~

Các mốc thời gian trên là **Unix timestamp tính bằng giây**. Thời hạn ví dụ là 300 giây kể từ thời điểm phát hành; đây chỉ là dữ liệu minh họa, không phải token sử dụng thực tế.

Protected header của JWS có thể là:

~~~json
{
  "alg": "ES256",
  "typ": "invoice-access+jwt",
  "kid": "issuer-sign-03"
}
~~~

Trong ví dụ:

- **alg = ES256**: thuật toán chữ ký ECDSA trên đường cong P-256 với SHA-256; issuer ký bằng khóa riêng và bên nhận xác minh bằng khóa công khai đáng tin cậy.
- **typ = invoice-access+jwt**: định danh *loại JWT theo quy ước riêng của ứng dụng*, giúp tránh sử dụng nhầm token cho mục đích khác. Đây là giá trị minh họa, không phải loại token chuẩn mặc định.
- **kid = issuer-sign-03**: gợi ý lựa chọn khóa xác minh chữ ký đã được cấu hình cho issuer; bản thân kid không phải bằng chứng tin cậy.

Dạng JWS Compact Serialization có **3 thành phần**:

~~~text
BASE64URL(jws_protected_header).BASE64URL(claims_json).BASE64URL(jws_signature)
~~~

### 3.2. Lớp ngoài: JWE chứa toàn bộ JWS

Bên phát hành lấy **chuỗi JWS hoàn chỉnh**, mã hóa dưới dạng byte UTF-8 và dùng chuỗi byte đó làm plaintext cho JWE. Không chỉ mã hóa riêng phần claims.

Protected header JWE giả định:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT",
  "kid": "recipient-enc-02"
}
~~~

Ý nghĩa:

| Header | Vai trò |
|---|---|
| **alg** | Thuật toán quản lý hoặc trao đổi khóa dùng cho JWE. Trong ví dụ, RSA-OAEP-256 bảo vệ Content Encryption Key (CEK) bằng khóa công khai của recipient. |
| **enc** | Thuật toán mã hóa nội dung; A256GCM là AES-256-GCM, cung cấp mã hóa có xác thực. |
| **cty** | Cho biết nội dung là JWT lồng bên trong. Khi có nesting, [RFC 7519 §5.2](https://www.rfc-editor.org/rfc/rfc7519.html#section-5.2) **yêu cầu** header này và giá trị **JWT**. |
| **kid** | Gợi ý lựa chọn khóa giải mã của **recipient**, có vai trò khác với kid của lớp JWS. |

Dạng JWE Compact Serialization có **5 thành phần**:

~~~text
BASE64URL(jwe_protected_header).BASE64URL(encrypted_key).BASE64URL(iv).BASE64URL(ciphertext).BASE64URL(authentication_tag)
~~~

Đây là cú pháp minh họa, **không phải token có thể kiểm tra bằng mật mã**. Với một số thuật toán quản lý khóa như direct encryption (**alg = dir**), phần encrypted_key có thể rỗng nhưng dấu chấm phân cách vẫn tồn tại.

JWE ciphertext chứa toàn bộ JWS bên trong. Bên quan sát có thể đọc protected header của JWE và suy ra một số thông tin như độ dài token; họ không thể đọc JWS header, claims hoặc chữ ký được mã hóa trong ciphertext nếu không có khóa giải mã.

### 3.3. Vai trò của cty và typ

Hai trường dễ bị nhầm lẫn:

- **cty = JWT** ở **lớp bên ngoài** thông báo rằng phần nội dung được bao bọc là một JWT khác; theo RFC 7519, đây là yêu cầu bắt buộc khi nesting.
- **typ** định danh **loại JWT** để bên nhận chọn đúng chính sách xử lý. Khi sử dụng explicit typing với Nested JWT, [RFC 8725 §3.11](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.11) yêu cầu typ mang giá trị loại cụ thể nằm trong **JWT trong cùng chứa claims**. Một số hệ thống cũng đặt typ ở lớp ngoài.

Cả cty và typ đều **không tự xác thực token**. Bên nhận chỉ tin các giá trị đó sau khi hoàn tất kiểm tra mật mã liên quan và đối chiếu với chính sách loại token được chấp nhận.

## 4. Những trường hợp nên kết hợp ký với mã hóa

| Bối cảnh | Vì sao JWS đơn thuần chưa đủ? | Giá trị bổ sung của Nested JWT |
|---|---|---|
| **Trao đổi định danh giữa các tổ chức** | Bên trung gian nhận token có thể đọc dữ liệu nhạy cảm trong payload JWS. | Bên nhận đích giải mã nội dung bằng khóa tương ứng và xác minh được issuer bằng chữ ký. |
| **API nhận claims nghiệp vụ có tính riêng tư** | Claims có thể xuất hiện trong thiết bị, proxy, hệ thống giám sát hoặc lưu trữ ngoài phạm vi tin cậy dự kiến. | Mã hóa đầu cuối phần claims trong lúc vẫn bảo toàn khả năng kiểm chứng nguồn phát hành. |
| **Token đi qua nhiều thành phần truyền tiếp** | TLS chỉ bảo vệ từng kết nối; thành phần kết thúc TLS có thể đọc JWS. | JWE giữ kín nội dung đối với thành phần trung gian không có khóa giải mã. |
| **Bên nhận cần bằng chứng mật mã về issuer** | JWE được mã hóa bằng khóa công khai của recipient có thể được tạo bởi nhiều bên khác nhau. | JWS bên trong chứng minh việc bên nắm khóa ký đã tạo nội dung, khi khóa được ràng buộc với issuer tin cậy. |
| **Thông tin cần được lưu hoặc chuyển giao mà chỉ một recipient được đọc** | JWS vẫn có thể bị đọc từ nơi lưu token. | JWE bổ sung lớp bảo vệ dữ liệu ngay cả khi chuỗi token bị lộ; chữ ký còn phục vụ xác minh bên phát hành. |

Một ví dụ: **Hệ thống A** phát hành JWT có quyền đọc hóa đơn cho **dịch vụ B**. A ký claims bằng khóa riêng của A, rồi mã hóa JWS bằng khóa công khai của B. B giải mã bằng khóa riêng của B, sau đó dùng khóa công khai tin cậy của A xác minh chữ ký và kiểm tra aud phải là B, thời hạn còn hiệu lực và scope phù hợp.

Kết hợp này hữu ích khi **cả hai yêu cầu đều thật sự tồn tại**: (1) người nhận phải xác minh được issuer; (2) nội dung cần bí mật ngoài việc bảo vệ đường truyền.

## 5. Khi nào không cần Nested JWT?

Sử dụng nhiều lớp mật mã tạo thêm chi phí xử lý, phân phối khóa, xoay vòng khóa, kích thước token và nguy cơ cấu hình sai. Có thể chọn cơ chế đơn giản hơn khi mô hình đe dọa cho phép:

| Yêu cầu thực tế | Phương án có thể phù hợp |
|---|---|
| Cần xác thực issuer và tính toàn vẹn, claims không nhạy cảm đối với bên có thể nhìn thấy token. | **JWS**, kết hợp TLS và xác minh chặt chẽ claims. |
| Cần bí mật nội dung và đã có cơ chế xác thực issuer độc lập, được ràng buộc rõ ràng với thông điệp. | **JWE** trong một giao thức được thiết kế để xử lý nguồn phát hành bằng cơ chế khác. |
| Không cần truyền claims cho người nhận hoặc muốn dễ thu hồi quyền truy cập tập trung. | **Opaque/reference token** và tra cứu thông tin tại bên phát hành hoặc dịch vụ tin cậy. |
| Claims chứa dữ liệu không cần thiết cho quyết định truy cập. | **Giảm dữ liệu trong token** trước khi cân nhắc bổ sung mã hóa. |

**Không nên dùng Nested JWT chỉ vì token có nhiều claims**. Việc đưa dữ liệu quá nhạy cảm hoặc dữ liệu bí mật lâu dài vào JWT thường vẫn là quyết định thiết kế kém, kể cả khi JWT được mã hóa.

## 6. Quy trình tạo và xác minh an toàn

### 6.1. Tại bên phát hành

1. Xác định issuer, recipient, loại token, audience, tập claims tối thiểu và thời hạn sử dụng.
2. Chọn thuật toán ký từ danh sách được phép; ký JWT bằng khóa phù hợp với issuer để tạo JWS.
3. Chọn thuật toán quản lý khóa và mã hóa nội dung cho đúng recipient; tạo JWE với **plaintext là toàn bộ JWS**, trong đó protected header chứa **cty = JWT**.
4. Truyền hoặc lưu token JWE theo kênh phù hợp, tiếp tục dùng TLS khi truyền qua mạng.

Mã giả dưới đây diễn đạt các bước, **không phải API của một thư viện cụ thể**:

~~~text
claims = build_minimal_claims(issuer, audience, subject, expiry, permissions)

inner_jws = sign_jws(
    claims,
    issuer_private_signing_key,
    allowed_signature_algorithm = "ES256",
    protected_header = { "typ": "invoice-access+jwt", "kid": "issuer-sign-03" }
)

outer_jwe = encrypt_jwe(
    plaintext = utf8(inner_jws),
    recipient_public_encryption_key,
    allowed_key_management_algorithm = "RSA-OAEP-256",
    allowed_content_encryption_algorithm = "A256GCM",
    protected_header = { "cty": "JWT", "kid": "recipient-enc-02" }
)

send(outer_jwe)
~~~

### 6.2. Tại bên nhận

**Phải kiểm tra cả lớp ngoài và lớp trong**; chỉ giải mã thành công chưa đủ để chấp nhận token.

1. **Nhận đúng định dạng đã thỏa thuận.** Nếu endpoint yêu cầu Nested JWT dạng JWE Compact, chỉ nhận cấu trúc tương ứng; áp dụng giới hạn kích thước, độ sâu nesting và tài nguyên xử lý.
2. **Kiểm tra chính sách của JWE.** Chỉ cho phép các cặp alg/enc đã cấu hình; yêu cầu cty = JWT; sử dụng kid đã kiểm soát để tìm khóa nhận phù hợp. Không để token tự quyết định thuật toán hay nguồn khóa tin cậy.
3. **Giải mã và xác thực JWE.** Thực hiện kiểm tra authentication tag. Nếu sai khóa, sai tag, sai thuật toán hoặc plaintext không hợp lệ thì từ chối, không chuyển dữ liệu chưa xác thực cho logic ứng dụng.
4. **Nhận diện JWS bên trong.** Bắt buộc đúng định dạng và loại token đã thỏa thuận; kiểm tra typ cụ thể nếu profile có quy định. Không tự động chấp nhận lớp nesting bổ sung ngoài chính sách.
5. **Xác minh chữ ký/MAC JWS.** Chỉ dùng thuật toán ký được cho phép, lựa chọn khóa từ cấu hình tin cậy và kiểm tra khóa đó thực sự thuộc issuer được chấp nhận. Với hệ thống dùng chữ ký bất đối xứng, xác minh bằng khóa công khai của issuer.
6. **Xác thực claims và ngữ cảnh.** Kiểm tra iss, aud, sub, exp, nbf và iat theo quy tắc ứng dụng; cân nhắc lệch đồng hồ nhỏ nếu cần; giới hạn quyền bằng scope, đối tượng tài nguyên và ngữ cảnh người gọi. Với yêu cầu chống phát lại, thêm kiểm soát jti/nonce hoặc cơ chế ràng buộc token phù hợp.
7. **Chỉ trả kết quả tin cậy sau khi tất cả bước đều thành công.** Bất kỳ lỗi mật mã, cấu trúc, thời gian hoặc quyền nào cũng dẫn đến từ chối. Không fallback sang nhận JWS không mã hóa nếu endpoint yêu cầu JWE.

Mã giả xác minh:

~~~text
function validate_nested_jwt(token):
    require_expected_outer_jwe_format(token)
    require_allowed_outer_alg_enc_and_cty(token, cty = "JWT")
    inner_jws = decrypt_and_authenticate_jwe(token, recipient_private_key)

    require_expected_inner_jws_and_typ(inner_jws, "invoice-access+jwt")
    claims = verify_jws_signature(inner_jws, trusted_issuer_keys, allowed_alg = "ES256")

    require_trusted_issuer(claims.iss)
    require_expected_audience(claims.aud, "invoice-api")
    require_valid_subject_and_time_window(claims.sub, claims.iat, claims.nbf, claims.exp)
    require_sufficient_permission(claims.scope, requested_resource)

    return claims
~~~

Mã giả lược bỏ việc tra khóa và một số kiểm tra để dễ nhìn; triển khai thực tế phải sử dụng thư viện JOSE đáng tin cậy, xác minh ràng buộc issuer–key và quy định đầy đủ chính sách token.

## 7. Có thể mã hóa trước rồi ký không?

**Có thể về mặt cú pháp.** Nested JWT cho phép lồng các cấu trúc JWS/JWE theo nhiều thứ tự. Tuy nhiên, [RFC 7519 §11.2](https://www.rfc-editor.org/rfc/rfc7519.html#section-11.2) khuyến nghị trong trường hợp cần cả ký và mã hóa thì **thông thường ký trước rồi mã hóa sau**.

| Cách làm | Lớp ngoài | Người nhận xử lý | Điểm cần cân nhắc |
|---|---|---|---|
| **Sign-then-encrypt** | JWE chứa JWS | Giải mã, kiểm tra tag JWE → xác minh JWS → kiểm tra claims. | Che giấu cả claims, JWS header và chữ ký của issuer; là lựa chọn thường được khuyến nghị. |
| **Encrypt-then-sign** | JWS chứa JWE | Xác minh chữ ký JWS ngoài → giải mã JWE trong → kiểm tra claims. | Chữ ký ở ngoài có thể lộ thông tin về bên ký; chữ ký xác nhận đối tượng bản mã, nên cần chính sách cụ thể để ràng buộc bên ký với ngữ nghĩa claims bên trong. |

Không áp dụng một quy tắc xử lý duy nhất cho mọi cấu hình: bên nhận cần **biết trước thứ tự và các thuật toán được phép**, sau đó xác minh từng lớp theo đúng hợp đồng bảo mật. JWE sử dụng authenticated encryption, vì vậy bản thân lớp mã hóa đã có kiểm tra tính toàn vẹn của bản mã; chữ ký JWS bổ sung bảo đảm phù hợp với quan hệ tin cậy về issuer.

## 8. Những lỗi dễ gặp và cách phòng tránh

| Lỗi | Hậu quả hoặc cách xử lý đúng |
|---|---|
| Chỉ kiểm tra JWE rồi tin claims, bỏ qua chữ ký JWS. | Có thể chấp nhận nội dung do bên không được phép phát hành. Phải kiểm tra **mọi thao tác mật mã** của Nested JWT. |
| Tự chấp nhận thuật toán theo giá trị alg/enc trong token. | Tạo rủi ro algorithm confusion và cấu hình yếu. Phải có **allowlist từ phía ứng dụng**, gắn khóa với thuật toán cố định. |
| Nhầm kid là bằng chứng về issuer hoặc tải khóa từ URL do token cung cấp. | Có thể chọn khóa do kẻ tấn công kiểm soát, gây injection/SSRF khi dùng các header như jku hoặc x5u. Chỉ giải quyết khóa theo cấu hình tin cậy. |
| Thiếu cty = JWT hoặc bỏ qua profile của typ. | Xử lý sai lớp hoặc chấp nhận nhầm loại token. Phân biệt **content type** của lớp bao và **token type** của lớp trong. |
| Chấp nhận token đã ký đúng nhưng sai aud, sai issuer hoặc quá hạn. | Chữ ký hợp lệ không đồng nghĩa được ủy quyền. Xác minh **iss, aud, exp, nbf, sub** và claims nghiệp vụ. |
| Dùng chung khóa thiếu kiểm soát hoặc không có cơ chế xoay vòng. | Tăng phạm vi ảnh hưởng khi lộ khóa. Quản lý tách bạch khóa ký và giải mã, phiên bản khóa, thời hạn và chính sách thu hồi. |
| Dùng nén dữ liệu trước mã hóa theo mặc định. | Biến động độ dài bản mã có thể làm lộ thông tin; [RFC 8725 §3.6](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.6) khuyến nghị tránh nén đầu vào trước mã hóa. |
| Ghi plaintext sau giải mã, khóa hoặc toàn bộ token vào log. | Làm mất mục tiêu bảo mật dù cơ chế mã hóa đúng. Giới hạn log, kiểm soát truy cập và thời gian lưu vết. |
| Coi mã hóa là biện pháp chống phát lại hoặc chống lấy cắp bearer token. | Bất kỳ ai giữ token bearer hợp lệ vẫn có thể trình token nếu không có ràng buộc khác. Cần kiểm soát thời hạn, jti/nonce khi phù hợp, hoặc token có ràng buộc với bên gửi. |

Ngoài ra, kích thước JWE có thể tiết lộ **một phần thông tin về độ dài plaintext**, và protected header của JWE Compact Serialization vẫn đọc được. Mã hóa không che giấu mọi metadata hay thay thế cơ chế bảo vệ đầu cuối của giao thức truyền tải.

## 9. Các câu hỏi tự kiểm tra

1. Vì sao một JWS được ký hợp lệ vẫn không phù hợp nếu claims chứa thông tin nhạy cảm mà nhiều bên trung gian có thể nhìn thấy?
2. Nếu API giải mã thành công JWE được tạo bằng khóa công khai của API, đã đủ để kết luận token do issuer tin cậy phát hành chưa? Vì sao?
3. Trong sign-then-encrypt, lớp nào chứa claims, lớp nào chứa toàn bộ JWS và vì sao header lớp ngoài cần cty = JWT?
4. Vì sao phải xác minh **cả chữ ký JWS lẫn authentication tag của JWE**, sau đó vẫn phải kiểm tra aud, exp và quyền?
5. Khi chỉ cần xác thực nguồn phát hành, không có yêu cầu bảo mật thêm cho nội dung token ngoài TLS và phạm vi lưu trữ được kiểm soát, vì sao JWS có thể là lựa chọn hợp lý hơn Nested JWT?

## 10. Tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): định nghĩa Nested JWT, header cty, quy trình xử lý nesting và thứ tự ký/mã hóa (đặc biệt §2, §5.2, §7 và §11.2).
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): chữ ký/MAC, protected header và các dạng serialization của JWS.
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): mã hóa có xác thực, cấu trúc JWE và 5 thành phần của Compact Serialization.
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): định danh thuật toán, yêu cầu khóa và cơ chế mật mã của JOSE.
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): xác thực tất cả các lớp mật mã (§3.3), giới hạn thuật toán (§3.1), xác minh issuer/audience (§3.8–3.9), explicit typing (§3.11) và chống nhầm loại token (§3.12).

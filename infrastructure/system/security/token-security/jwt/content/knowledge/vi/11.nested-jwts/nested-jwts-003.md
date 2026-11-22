# Mã hóa rồi ký và ý nghĩa khác biệt đối với các bên tham gia

> **Chương:** JWT lồng nhau  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung áp dụng cho các hệ thống dùng JWT/JOSE nói chung, độc lập với ngôn ngữ lập trình và framework.

## 1. Mã hóa rồi ký là gì?

**Mã hóa rồi ký** (*encrypt-then-sign*) là cách tạo Nested JWT theo thứ tự:

**Claims → mã hóa thành JWE → ký toàn bộ JWE thành JWS.**

Kết quả có cấu trúc:

`JWS(JWE(claims))`

Lớp trong là **JWE** chứa claims đã mã hóa. Lớp ngoài là **JWS** chứa toàn bộ chuỗi JWE trong payload và chữ ký bảo vệ chuỗi đó.

Cách kết hợp này có một đặc điểm quan trọng: **chữ ký bên ngoài có thể được xác minh mà không cần giải mã nội dung**. Một bên trung gian có khóa xác minh đáng tin cậy có thể kiểm tra ai đã ký chính xác đối tượng JWE đang được chuyển tiếp, trong khi claims vẫn được giữ kín đối với bên không có khóa giải mã.

Theo [RFC 7519 §7.1](https://www.rfc-editor.org/rfc/rfc7519.html#section-7.1), khi thực hiện thao tác ký hoặc mã hóa lồng nhau, kết quả JWS/JWE của lớp trước trở thành Message cho lớp tiếp theo và JOSE Header mới phải có `cty: "JWT"`. Do đó, với encrypt-then-sign, **cty nằm trong protected header của JWS ngoài**.

> **Điểm cần nhớ:** Encrypt-then-sign ký lên **biểu diễn JWE đã mã hóa**, không ký trực tiếp lên JSON claims. Chữ ký xác thực người ký của đối tượng JWE; ý nghĩa của nó đối với nguồn phát hành claims phụ thuộc vào việc ai ký và mối quan hệ tin cậy giữa các bên.

## 2. Phân biệt vai trò của JWE và JWS

| Lớp | Đối tượng được bảo vệ | Chức năng | Ai có thể kiểm tra? |
|---|---|---|---|
| **JWE bên trong** | Claims JSON là plaintext đầu vào của JWE. | Mã hóa để giữ bí mật và xác thực tính toàn vẹn của nội dung khi giải mã. | Bên có khóa giải mã phù hợp có thể giải mã và kiểm tra xác thực JWE. |
| **JWS bên ngoài** | Toàn bộ chuỗi JWE. | Chữ ký số hoặc MAC xác thực đối tượng JWE đã được ký và phát hiện thay đổi. | Bất kỳ bên nào có khóa xác minh phù hợp (đối với chữ ký bất đối xứng) hoặc bí mật MAC (đối với MAC) đều có thể kiểm tra. |

Hai lớp trả lời hai câu hỏi khác nhau:

- **JWE:** Ai có quyền đọc nội dung? Bên sở hữu khóa giải mã phù hợp có thể phục hồi claims.
- **JWS:** Ai đã ký hoặc xác nhận đúng chuỗi JWE này? Câu trả lời phụ thuộc vào danh tính được ràng buộc với khóa ký.

**Không thể suy ra người phát hành claims chỉ từ việc giải mã JWE thành công.** Một bên bất kỳ có khóa công khai của recipient có thể tạo một JWE gửi cho recipient đó. Chữ ký JWS bên ngoài xác nhận người ký của ciphertext, nhưng nếu người ký khác issuer thì chữ ký đó không tự chứng minh issuer bên trong claims là đúng.

## 3. Các bên tham gia và ranh giới tin cậy

Xét một tình huống có bốn vai trò:

- **Issuer A:** tạo claims, ví dụ thông tin quyền truy cập hóa đơn.
- **Encryptor E:** mã hóa claims cho recipient B bằng khóa công khai của B. E có thể là A hoặc một dịch vụ được ủy quyền.
- **Signer S:** ký toàn bộ chuỗi JWE bằng khóa ký của mình. S có thể trùng với A/E hoặc là một gateway trung gian.
- **Recipient B:** nhận token, xác minh chữ ký JWS ngoài, giải mã JWE bằng khóa riêng và kiểm tra claims.

Một thành phần trung gian **M** có thể chuyển tiếp token hoặc xác minh chữ ký mà không cần giải mã JWE.

~~~mermaid
flowchart TD
    A["Issuer A tạo Claims"] --> E["Encryptor E mã hóa Claims cho B"]
    E --> J["JWE chứa Claims đã mã hóa"]
    J --> S["Signer S ký toàn bộ chuỗi JWE"]
    S --> T["Nested JWT: JWS bên ngoài"]
    T --> M["Trung gian M có thể xác minh chữ ký"]
    M --> B["Recipient B nhận token"]
    B --> V["Xác minh JWS bằng khóa tin cậy của S"]
    V --> D["Giải mã và xác thực JWE bằng khóa riêng của B"]
    D --> C["Kiểm tra Claims và quyền"]
~~~

### 3.1. Vai trò của từng bên

| Bên tham gia | Khóa hoặc dữ liệu cần có | Điều có thể làm | Điều không thể tự suy ra |
|---|---|---|---|
| **Issuer A** | Claims hợp lệ; thông tin về recipient; khóa ký nếu A cũng là signer. | Phát hành claims và yêu cầu mã hóa cho đúng recipient; có thể tự ký JWE nếu là signer. | Việc claims có `iss = A` trong plaintext không tự làm chúng đáng tin. |
| **Encryptor E** | Khóa công khai của B (hoặc cơ chế khóa chung theo cấu hình). | Tạo JWE để B có thể giải mã. | Việc tạo JWE không chứng minh E là issuer; với mã hóa khóa công khai, nhiều bên có thể tạo JWE cho B. |
| **Signer S** | Khóa riêng ký hoặc bí mật MAC theo cấu hình. | Ký chính xác chuỗi JWE; cho phép các bên có khóa xác minh kiểm tra chữ ký mà không giải mã. | Nếu S không biết hoặc không xác minh nguồn gốc claims, chữ ký của S không chứng minh nội dung do A phát hành. |
| **Recipient B** | Khóa xác minh của S và khóa riêng giải mã JWE; chính sách issuer/audience. | Xác minh lớp ngoài, giải mã lớp trong, kiểm tra claims và quyết định quyền. | Khóa giải mã không tự xác định ai đã tạo JWE hoặc ai phát hành claims. |
| **Trung gian M** | Khóa công khai xác minh chữ ký của S và chính sách xử lý token. | Kiểm tra chữ ký ngoài, phát hiện token bị thay đổi sau khi ký và chuyển tiếp token nguyên vẹn. | Không thể đọc claims hoặc quyết định quyền dựa trên nội dung đã mã hóa. |

### 3.2. Khi signer trùng với issuer

Nếu **A vừa phát hành claims, vừa mã hóa JWE, vừa ký JWE**, chữ ký bên ngoài có thể được xem là bằng chứng mật mã rằng A đã phát hành đúng đối tượng JWE đó, với điều kiện:

- Khóa ký được xác thực và ràng buộc với A.
- A thực sự tạo JWE từ claims mà A có ý định phát hành.
- Recipient kiểm tra chữ ký, xác thực JWE và kiểm tra claims theo profile đã thỏa thuận.

Trong trường hợp này, B có thể xác minh chữ ký của A **trước khi giải mã**. M có thể kiểm tra chữ ký của A mà không cần biết nội dung hóa đơn.

### 3.3. Khi signer là gateway khác issuer

Giả sử **A tạo claims và mã hóa JWE**, còn **G là gateway ký JWE** trước khi chuyển đến B.

B xác minh chữ ký G thành công chỉ chứng minh **G đã ký đúng chuỗi JWE đó**. Nếu G không đọc hoặc không xác minh nguồn gốc claims, chữ ký của G không tự chứng minh rằng claims thực sự do A phát hành.

Để B tin claims có `iss = A`, giao thức phải quy định thêm một quan hệ tin cậy, chẳng hạn:

- G chỉ ký sau khi xác thực A qua một kênh hoặc cơ chế có nguồn gốc đáng tin.
- G được A ủy quyền rõ ràng để xác nhận các thông điệp thay mặt A.
- B có cơ chế độc lập để xác minh nguồn gốc claims từ A, chẳng hạn một chữ ký/MAC nằm bên trong JWE.
- Chính sách của B xác định rõ G là bên phát hành token có quyền khẳng định các claims đó, thay vì nhầm G với A.

Nếu không có ràng buộc này, không nên xem `iss` đã giải mã là đáng tin chỉ vì JWS ngoài có chữ ký hợp lệ.

## 4. Cấu trúc Nested JWT: JWS(JWE(claims))

### 4.1. Claims được mã hóa trong JWE

Ví dụ Claims Set:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "customer-123",
  "aud": "invoice-api",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000300,
  "scope": "invoice:read",
  "invoice_id": "INV-456"
}
~~~

Đây là dữ liệu minh họa. Các mốc thời gian là NumericDate, tính bằng giây kể từ Unix epoch. Claims Set được mã hóa thành plaintext của JWE.

### 4.2. Lớp trong — JWE

Ví dụ protected header của JWE:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "recipient-B-encryption-02",
  "typ": "invoice-access+jwt"
}
~~~

- **alg:** thuật toán quản lý khóa của JWE; ví dụ dùng RSA-OAEP-256 để bảo vệ Content Encryption Key.
- **enc:** thuật toán mã hóa nội dung; ví dụ A256GCM là AES-256-GCM, cung cấp mã hóa có xác thực.
- **kid:** gợi ý lựa chọn khóa giải mã của recipient B.
- **typ:** loại JWT cụ thể theo profile ứng dụng. Ví dụ `invoice-access+jwt` là loại minh họa, không phải giá trị chuẩn bắt buộc.

JWE Compact Serialization có năm phần:

~~~text
BASE64URL(jwe_protected_header).BASE64URL(encrypted_key).BASE64URL(iv).BASE64URL(ciphertext).BASE64URL(authentication_tag)
~~~

Trong cấu trúc này, JWE plaintext là Claims Set JSON. Vì plaintext không phải một JWT khác, header JWE không cần `cty: "JWT"` để chỉ một lớp nesting tiếp theo.

### 4.3. Lớp ngoài — JWS ký toàn bộ JWE

Signer S nhận **chuỗi JWE Compact hoàn chỉnh** và dùng nó làm payload của JWS.

Ví dụ protected header của JWS:

~~~json
{
  "alg": "ES256",
  "kid": "signer-S-signing-07",
  "cty": "JWT",
  "typ": "invoice-access+jwt"
}
~~~

- **alg:** thuật toán ký; ví dụ ES256.
- **kid:** gợi ý khóa xác minh chữ ký của S, được tra trong tập khóa tin cậy đã cấu hình.
- **cty: JWT:** bắt buộc cho trường hợp Nested JWT; chỉ ra payload chứa một JWT khác, ở đây là JWE.
- **typ:** ví dụ định danh loại token của toàn bộ cấu trúc. Nếu dùng explicit typing, `typ` phải có ở JWT trong cùng chứa Claims Set (trong ví dụ là JWE); có thể đặt cùng giá trị ở lớp ngoài để định danh cả Nested JWT.

JWS Compact Serialization có ba phần:

~~~text
BASE64URL(jws_protected_header).BASE64URL(UTF8(jwe_compact_string)).BASE64URL(jws_signature)
~~~

Chữ ký được tính trên JWS Signing Input theo quy tắc JWS, bao gồm protected header đã mã hóa và payload đã base64url. Vì payload là **chuỗi JWE**, chữ ký ràng buộc toàn bộ biểu diễn JWE đó.

### 4.4. Hai trường header dễ nhầm

| Header | Nơi đặt trong ví dụ | Ý nghĩa |
|---|---|---|
| `cty: JWT` | JWS bên ngoài | Cho biết payload của JWS là một JWT khác, tức JWE lồng bên trong. |
| `typ: invoice-access+jwt` | JWE bên trong | Định danh loại JWT chứa Claims Set. Khi sử dụng explicit typing trong Nested JWT, RFC 8725 yêu cầu typ ở JWT trong cùng. |
| `typ: invoice-access+jwt` | JWS bên ngoài (tùy chọn) | Có thể lặp lại để định danh toàn bộ Nested JWT theo cùng profile. |
| `kid` | JWE bên trong | Gợi ý khóa mã hóa/giải mã của recipient. |
| `kid` | JWS bên ngoài | Gợi ý khóa ký/xác minh của signer. |

**cty mô tả cấu trúc lồng**, còn **typ mô tả loại token**. Cả hai không thay thế việc xác thực chữ ký, tag JWE, issuer hay claims.

## 5. Quy trình tạo token: mã hóa trước, ký sau

### Bước 1 — Xây dựng Claims Set

Issuer tạo các claims tối thiểu, xác định audience, thời hạn và quyền. Ví dụ B chỉ được đọc hóa đơn thuộc phạm vi được cấp.

### Bước 2 — Mã hóa claims thành JWE

Encryptor E sử dụng khóa công khai của B (hoặc cấu hình khóa tương ứng) để mã hóa Claims Set. E phải dùng thuật toán quản lý khóa và thuật toán mã hóa nội dung nằm trong allowlist của giao thức.

Kết quả là chuỗi JWE Compact gồm năm thành phần. Nội dung claims không thể đọc được nếu không có khóa giải mã phù hợp.

### Bước 3 — Ký chuỗi JWE thành JWS

Signer S lấy **toàn bộ chuỗi JWE** làm payload, tạo JWS protected header với thuật toán được cho phép và `cty: JWT`, sau đó ký bằng khóa riêng của S (nếu dùng chữ ký bất đối xứng).

Kết quả là chuỗi JWS Compact gồm ba thành phần. Payload sau khi base64url-decode phải chính là chuỗi JWE đã được ký.

### Mã giả phát hành

~~~text
function issue_encrypt_then_sign(context):
    issued_at = now_in_unix_seconds()
    claims = {
        iss: context.issuer,
        sub: context.subject,
        aud: "invoice-api",
        iat: issued_at,
        nbf: issued_at,
        exp: issued_at + 300,
        scope: "invoice:read",
        invoice_id: context.invoice_id
    }

    inner_jwe = JWE.encrypt(
        plaintext = UTF8(JSON(claims)),
        recipient_public_key = recipient_B_encryption_public_key,
        protected_header = {
            alg: "RSA-OAEP-256",
            enc: "A256GCM",
            kid: "recipient-B-encryption-02",
            typ: "invoice-access+jwt"
        }
    )

    outer_jws = JWS.sign(
        payload = UTF8(inner_jwe),
        signing_private_key = signer_S_private_key,
        protected_header = {
            alg: "ES256",
            kid: "signer-S-signing-07",
            cty: "JWT",
            typ: "invoice-access+jwt"
        }
    )

    return outer_jws
~~~

Đây là mã giả diễn đạt quy trình, không phải API của thư viện cụ thể. Nếu signer S khác issuer A, ứng dụng phải có quy tắc ủy quyền/đảm bảo nguồn gốc rõ ràng trước khi coi chữ ký S là bằng chứng cho claims do A phát hành.

## 6. Thứ tự xác minh tại recipient

Với `JWS(JWE(claims))`, recipient B xử lý **từ ngoài vào trong**:

**Kiểm tra và xác minh JWS → lấy payload JWE → giải mã và xác thực JWE → kiểm tra Claims Set → quyết định quyền.**

~~~mermaid
flowchart TD
    A["Nhận Nested JWT: JWS ngoài"] --> B["Kiểm tra cấu trúc và giới hạn đầu vào"]
    B --> C["Kiểm tra chính sách alg, typ, cty"]
    C --> D["Chọn khóa S từ tập khóa tin cậy"]
    D --> E["Xác minh chữ ký JWS"]
    E -->|Sai| X["Từ chối token"]
    E -->|Đúng| F["Lấy payload: chuỗi JWE"]
    F --> G["Kiểm tra định dạng và chính sách JWE"]
    G --> H["Giải mã và xác thực JWE"]
    H -->|Sai| X
    H -->|Đúng| I["Phân tích Claims Set JSON"]
    I --> J["Kiểm tra iss, sub, aud, exp, nbf, typ và quyền"]
    J -->|Không đạt| X
    J -->|Đạt| K["Chấp nhận theo quyền được cấp"]
~~~

### 6.1. Kiểm tra cấu trúc JWS bên ngoài

Trước khi xác minh chữ ký, cần phân tích đúng định dạng endpoint mong đợi. Với JWS Compact, có ba thành phần được phân cách bằng hai dấu chấm.

Protected header có thể đọc được trước xác minh, nhưng vẫn là dữ liệu chưa đáng tin. Có thể dùng `alg` và `kid` để đối chiếu với chính sách và chọn khóa từ tập khóa đã cấu hình. Không được để header tự mở rộng thuật toán, chọn nguồn khóa tùy ý hoặc thay đổi danh tính signer được kỳ vọng.

Các kiểm tra đầu vào nên gồm:

- Đúng định dạng JWS Compact hoặc profile serialization đã thỏa thuận.
- Đúng giới hạn kích thước token và độ sâu lồng.
- `alg` thuộc allowlist của endpoint.
- `cty` bằng `JWT` khi yêu cầu Nested JWT.
- `kid` được ánh xạ đến khóa xác minh trong kho khóa tin cậy của signer dự kiến.

### 6.2. Xác minh chữ ký JWS ngoài

Dùng khóa xác minh tương ứng để kiểm tra chữ ký trên đúng JWS Signing Input. Nếu chữ ký sai, không tiếp tục giải mã JWE và không chấp nhận token.

Khi chữ ký hợp lệ, payload JWS được xác thực là chuỗi JWE đã được signer S ký. Đây là điểm mà bên trung gian cũng có thể dừng nếu nhiệm vụ chỉ là kiểm tra chữ ký và chuyển tiếp token.

**Chữ ký chỉ chứng minh danh tính của S theo quan hệ tin cậy về khóa.** Nếu S là gateway, chữ ký chứng minh gateway đã ký ciphertext. Bên nhận chỉ được coi claims do A phát hành khi A là signer hoặc khi có một cơ chế ủy quyền/xác thực nguồn gốc khác được chính sách chấp nhận.

### 6.3. Giải mã và xác thực JWE bên trong

Sau khi JWS ngoài hợp lệ, lấy payload đã được xác thực làm chuỗi JWE. Kiểm tra đúng định dạng JWE và allowlist của `alg`, `enc`, sau đó chọn khóa giải mã của B từ kho khóa được cấu hình.

Recipient dùng khóa riêng phù hợp để giải mã JWE và **phải xác thực thành công authentication tag** trước khi sử dụng plaintext. Nếu giải mã hoặc xác thực tag thất bại, từ chối token.

Dù chữ ký ngoài đã bảo vệ nguyên vẹn chuỗi JWE, recipient vẫn phải kiểm tra JWE theo đúng chuẩn. Hai thao tác mật mã đều phải thành công.

### 6.4. Kiểm tra Claims Set sau giải mã

Sau khi JWE được xác thực, phân tích plaintext thành JSON Claims Set và kiểm tra theo profile ứng dụng:

| Điều kiện | Nội dung cần xác minh |
|---|---|
| **Issuer (`iss`)** | Issuer có nằm trong danh sách được tin cậy không? Khóa ký ngoài có thuộc issuer đó hoặc signer có được ủy quyền xác nhận cho issuer không? |
| **Subject (`sub`)** | Chủ thể có tồn tại và phù hợp với issuer/ngữ cảnh ứng dụng không? |
| **Audience (`aud`)** | Token có được phát hành cho API/recipient hiện tại không? |
| **Expiration (`exp`)** | Token còn hiệu lực không? |
| **Not Before (`nbf`)** | Token đã đến thời điểm được phép sử dụng chưa? |
| **Issued At (`iat`)** | Thời điểm phát hành có hợp lệ và phù hợp với giới hạn tuổi token không? |
| **Token type** | `typ` có đúng profile mà endpoint yêu cầu không? |
| **Scope và tài nguyên** | Quyền trong token có cho phép hành động trên đúng tài nguyên không? |
| **Replay** | Có cần kiểm tra `jti`, nonce hoặc trạng thái đã sử dụng để ngăn phát lại không? |

Chỉ chấp nhận token khi mọi thao tác mật mã bắt buộc và mọi điều kiện claims đều đạt. Chữ ký hợp lệ không thay thế kiểm tra audience, thời hạn hoặc ủy quyền.

### 6.5. Mã giả xác minh

~~~text
function validate_encrypt_then_sign(token, request):
    # Chính sách tin cậy được cấu hình sẵn ở recipient
    expected_signer = "trusted-signer-S"
    expected_issuer = "https://issuer.example.test"
    expected_audience = "invoice-api"
    allowed_jws_alg = ["ES256"]
    allowed_jwe_alg = ["RSA-OAEP-256"]
    allowed_jwe_enc = ["A256GCM"]

    # 1. Phân tích JWS ngoài; header chưa xác thực
    require_jws_compact_format_and_size_limit(token)
    outer_header = read_untrusted_jws_header(token)
    require_member(outer_header.alg, allowed_jws_alg)
    require_equal(outer_header.cty, "JWT")

    signing_key = find_configured_signing_key(
        signer = expected_signer,
        key_id = outer_header.kid,
        allowed_algorithms = allowed_jws_alg
    )

    # 2. Xác minh chữ ký trước khi dùng payload
    inner_jwe = verify_jws_signature_and_get_payload(token, signing_key)

    # 3. Phân tích JWE bên trong
    require_jwe_compact_format_and_size_limit(inner_jwe)
    inner_header = read_untrusted_jwe_header(inner_jwe)
    require_member(inner_header.alg, allowed_jwe_alg)
    require_member(inner_header.enc, allowed_jwe_enc)
    require_equal(inner_header.typ, "invoice-access+jwt")

    decryption_key = find_configured_recipient_key(inner_header.kid)

    # Thao tác phải giải mã và xác thực tag hoàn chỉnh
    claims_json = decrypt_and_authenticate_jwe(inner_jwe, decryption_key)
    claims = parse_utf8_json_claims(claims_json)

    # 4. Xác minh danh tính issuer và chính sách token
    require_trusted_issuer(claims.iss, expected_issuer)
    require_signer_authorized_for_issuer(expected_signer, claims.iss)
    require_valid_subject(claims.sub)
    require_expected_audience(claims.aud, expected_audience)
    require_valid_time_window(claims.iat, claims.nbf, claims.exp)
    require_authorized_resource(claims.scope, request.invoice_id)
    require_replay_policy_if_configured(claims.jti)

    return claims
~~~

Dòng `require_signer_authorized_for_issuer` thể hiện một **chính sách quan hệ tin cậy**. Nếu signer S chính là issuer A, phép kiểm tra xác nhận khóa S thuộc A. Nếu S là gateway, cần xác minh quyền đại diện hoặc cơ chế nguồn gốc độc lập đã được thỏa thuận. Không được tự động chấp nhận mọi signer chỉ vì chữ ký hợp lệ.

## 7. Trung gian có thể làm gì khi không giải mã?

Đây là điểm khiến encrypt-then-sign khác đáng kể với sign-then-encrypt.

Với JWS ngoài, trung gian M có thể:

- Xác minh chữ ký của S bằng khóa công khai tin cậy mà không cần khóa giải mã.
- Phát hiện token đã bị sửa sau khi ký.
- Xác định signer theo khóa đã xác minh.
- Chuyển tiếp nguyên vẹn chuỗi JWS đến recipient.
- Thực hiện một số quyết định định tuyến dựa trên metadata đã được xác thực và được phép lộ.

Trung gian M **không thể**:

- Đọc claims bên trong JWE.
- Tự xác minh nội dung `iss`, `sub`, `aud`, `scope` hoặc `exp` trong plaintext.
- Tự quyết định người dùng có quyền đọc hóa đơn nào.
- Khẳng định signer S là issuer A nếu chưa có quan hệ tin cậy/ủy quyền.

JWS Compact payload chỉ được base64url-encode, không được mã hóa. Người quan sát có thể giải mã lớp biểu diễn JWS để lấy chuỗi JWE và đọc protected header JWE. Họ không thể lấy claims từ ciphertext nếu không có khóa giải mã.

## 8. So sánh mã hóa rồi ký với ký rồi mã hóa

| Tiêu chí | **Encrypt-then-sign** — `JWS(JWE(claims))` | **Sign-then-encrypt** — `JWE(JWS(claims))` |
|---|---|---|
| Thứ tự tạo | Mã hóa claims → ký JWE. | Ký claims → mã hóa JWS. |
| Lớp ngoài | JWS. | JWE. |
| Thứ tự kiểm tra tại recipient | Xác minh chữ ký JWS → giải mã/xác thực JWE → kiểm tra claims. | Giải mã/xác thực JWE → xác minh chữ ký JWS → kiểm tra claims. |
| Xác minh không cần giải mã | Có thể xác minh chữ ký ngoài trước khi giải mã. | Không thể xác minh JWS bên trong trước khi giải mã. |
| Khả năng kiểm tra của trung gian | Có thể xác minh chữ ký và signer của ciphertext. | Không thể thấy chữ ký JWS bên trong nếu không giải mã. |
| Metadata chữ ký | Header JWS, thuật toán và chữ ký ngoài có thể quan sát. | Header/chữ ký JWS nằm trong ciphertext, được che giấu bởi JWE ngoài. |
| Nội dung claims | Được mã hóa trong cả hai cách. | Được mã hóa trong cả hai cách. |
| Ý nghĩa chữ ký | Chữ ký xác thực đúng đối tượng JWE; signer có thể là issuer hoặc gateway. | Chữ ký xác thực claims/JWS bên trong và được recipient kiểm tra sau giải mã. |
| Phù hợp khi | Gateway hoặc nhiều bên cần xác minh người ký mà không cần đọc nội dung. | Muốn che giấu cả claims và chữ ký/metadata của issuer trước bên trung gian. |

Hai cách đều là cấu trúc lồng hợp lệ. Lựa chọn dựa trên **ai cần xác minh điều gì, ai được phép nhìn thấy metadata và signer có quan hệ nào với issuer**.

### Ví dụ lựa chọn

- **Chọn encrypt-then-sign:** Một gateway kiểm tra chữ ký của tổ chức phát hành trước khi chuyển tiếp gói dữ liệu đã mã hóa cho dịch vụ đích. Gateway không cần giải mã nhưng vẫn cần xác minh gói dữ liệu do bên ký được phép gửi.
- **Chọn sign-then-encrypt:** Dịch vụ đích cần xác minh chữ ký issuer, nhưng hệ thống trung gian không nên biết chữ ký hoặc claims của issuer. JWE ngoài che giấu cả JWS trong.
- **Cần xác thực issuer gốc nhưng signer là gateway:** Phải thiết kế thêm cơ chế xác thực/ủy quyền giữa issuer và gateway, hoặc giữ một chữ ký/MAC của issuer trong lớp bên trong. Không nên dựa vào chữ ký gateway như thể đó là chữ ký của issuer.

## 9. Các rủi ro và cách phòng tránh

| Rủi ro | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Coi chữ ký gateway là bằng chứng issuer đã tạo claims. | JWS ngoài chỉ xác thực signer của chuỗi JWE. | Ràng buộc signer với issuer hoặc xác minh quan hệ ủy quyền. |
| Tin `iss` sau khi giải mã mà không kiểm tra nguồn gốc. | Bất kỳ ai có thể tạo JWE cho recipient nếu dùng khóa công khai của B. | Kiểm tra chữ ký và quan hệ signer–issuer theo profile. |
| Bỏ qua giải mã JWE vì chữ ký ngoài đã hợp lệ. | Chữ ký ngoài không cung cấp plaintext; claims vẫn chưa được kiểm tra. | Bắt buộc giải mã và xác thực JWE. |
| Bỏ qua chữ ký ngoài vì JWE tag hợp lệ. | JWE tag không xác định duy nhất người tạo ciphertext. | Bắt buộc xác minh mọi lớp mật mã. |
| Chấp nhận `alg` hoặc `enc` do token tự quyết định. | Có thể dẫn đến algorithm confusion hoặc cấu hình yếu. | Cố định allowlist thuật toán và ràng buộc từng khóa với đúng thuật toán. |
| Chọn khóa theo `kid` không kiểm soát hoặc tải `jku`/`x5u` tùy ý. | Có thể gây key substitution, injection hoặc SSRF. | Chỉ tra khóa từ kho tin cậy; kiểm tra/sanitize key ID. |
| Bỏ `cty: JWT` ở JWS ngoài. | Không mô tả rõ cấu trúc payload lồng. | Yêu cầu cty đúng quy định khi Nested JWT. |
| Không dùng `typ` cho các loại token dễ nhầm lẫn. | Token dùng cho mục đích khác có thể bị chấp nhận nhầm. | Đặt explicit typ ở JWT trong cùng và áp dụng quy tắc xác minh riêng. |
| Xem chữ ký là biện pháp chống phát lại. | Token đã ký vẫn có thể bị gửi lại nguyên vẹn. | Dùng thời hạn, `jti`, nonce hoặc cơ chế chống phát lại phù hợp. |
| Dùng MAC nhưng tuyên bố đã xác định duy nhất người ký. | Mọi bên giữ shared secret đều có khả năng tạo MAC hợp lệ. | Phân biệt xác thực nhóm chia sẻ khóa với chữ ký bất đối xứng có định danh khóa. |
| Ký rồi parse và serialize lại JWE trước khi xác minh. | Chuỗi payload thay đổi có thể làm chữ ký không còn khớp hoặc tạo sai cách diễn giải. | Xác minh đúng JWS Signing Input và giữ nguyên payload đã ký. |
| Log nguyên token hoặc plaintext. | Token có thể được sử dụng lại; claims có thể chứa dữ liệu nhạy cảm. | Hạn chế log, che dữ liệu và kiểm soát quyền truy cập. |

[RFC 8725 §2.3](https://www.rfc-editor.org/rfc/rfc8725.html#section-2.3) nêu rủi ro các triển khai giải mã JWT mã hóa nhưng không xác minh chữ ký bên trong. Nguyên tắc chung ở §3.3 là **mọi thao tác mật mã trong Nested JWT đều phải được xác minh**; chỉ cần một thao tác thất bại thì phải từ chối toàn bộ JWT.

## 10. Ma trận kiểm thử cho JWS(JWE(claims))

| Trường hợp | Kết quả mong đợi |
|---|---|
| JWS ngoài hợp lệ, signer được tin cậy; JWE hợp lệ; claims đúng profile. | Chấp nhận theo quyền được cấp. |
| Chữ ký JWS ngoài sai hoặc bị sửa. | Từ chối trước bước giải mã JWE. |
| JWS có `alg` ngoài allowlist hoặc `kid` không thuộc kho khóa tin cậy. | Từ chối. |
| JWS hợp lệ nhưng thiếu `cty: JWT` theo profile Nested JWT. | Từ chối. |
| Payload JWS sau xác minh không phải JWE đúng định dạng. | Từ chối. |
| JWE sai authentication tag hoặc giải mã thất bại. | Từ chối sau bước JWS. |
| JWE dùng `alg`/`enc` ngoài allowlist. | Từ chối. |
| JWE hợp lệ nhưng `typ` không đúng loại token được endpoint chấp nhận. | Từ chối. |
| JWS do gateway G ký hợp lệ, nhưng chính sách không cho G đại diện issuer A. | Từ chối claims yêu cầu xác thực từ A. |
| JWS do issuer A ký hợp lệ, khóa đã được ràng buộc với A, claims có `iss` khác A. | Từ chối. |
| Claims có audience không bao gồm recipient hiện tại. | Từ chối. |
| Claims quá hạn hoặc chưa đến thời điểm có hiệu lực. | Từ chối. |
| Token hợp lệ về mật mã nhưng scope không cho phép thao tác. | Từ chối theo ủy quyền. |
| Token hợp lệ được gửi lại và vi phạm chính sách chống phát lại. | Từ chối theo cơ chế replay detection. |

## 11. Câu hỏi tự kiểm tra

1. Trong `JWS(JWE(claims))`, lớp nào được xác minh trước và vì sao?
2. Vì sao trung gian có thể xác minh chữ ký JWS ngoài mà không cần khóa giải mã JWE?
3. Chữ ký của gateway G trên JWE do A tạo chứng minh điều gì? Điều gì vẫn cần kiểm tra để tin `iss = A`?
4. Tại sao JWE tag hợp lệ không thay thế chữ ký xác thực issuer?
5. Trong cấu trúc encrypt-then-sign, `cty: JWT` phải xuất hiện ở header nào? Nếu dùng explicit typing, `typ` phải xuất hiện ở đâu?
6. Những metadata nào có thể lộ ra khi JWS là lớp ngoài?
7. Khi nào encrypt-then-sign phù hợp hơn sign-then-encrypt?

## 12. Tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): Nested JWT, `cty`, cách tạo và xác minh JWT lồng nhau (§5.2, §7.1–7.2).
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JWS Compact Serialization, tính chữ ký và xác minh chữ ký (§3, §5).
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): JWE Compact Serialization, mã hóa, giải mã và xác thực thông điệp (§3, §5, §7).
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): định danh thuật toán ký, quản lý khóa và mã hóa nội dung.
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): lỗi kết hợp chữ ký/mã hóa (§2.3), xác minh tất cả thao tác mật mã (§3.3), kiểm tra issuer/audience và explicit typing (§3.8–3.12).

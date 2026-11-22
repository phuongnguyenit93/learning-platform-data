# Ký rồi mã hóa và thứ tự kiểm tra tương ứng

> **Chương:** JWT lồng nhau  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung áp dụng cho các hệ thống sử dụng JWT/JOSE nói chung, không phụ thuộc ngôn ngữ lập trình hoặc framework.

## 1. Tại sao thứ tự ký và mã hóa lại quan trọng?

Khi một JWT cần đồng thời **chứng minh nguồn phát hành** và **giữ bí mật claims**, một cách thiết kế phổ biến là:

**Ký JWT thành JWS trước, sau đó mã hóa toàn bộ JWS thành JWE** (*sign-then-encrypt*).

Thứ tự này tạo ra một **Nested JWT** với hai lớp:

- **Lớp trong — JWS:** giữ nội dung claims và chữ ký số/MAC để bên nhận xác minh bên phát hành cùng tính toàn vẹn của dữ liệu.
- **Lớp ngoài — JWE:** mã hóa toàn bộ biểu diễn JWS, giúp bên không có quyền giải mã không đọc được claims, header hoặc chữ ký JWS bên trong.

[RFC 7519, mục 11.2](https://www.rfc-editor.org/rfc/rfc7519.html#section-11.2) khuyến nghị **thông thường nên ký trước, mã hóa sau** khi cần cả hai cơ chế.

Thứ tự tạo token quyết định **thứ tự xử lý tại bên nhận**: để kiểm tra chữ ký của JWS nằm bên trong ciphertext, bên nhận phải giải mã và xác thực JWE bên ngoài trước. Sau đó mới có JWS hoàn chỉnh để kiểm tra chữ ký; bước cuối cùng là kiểm tra claims theo chính sách ứng dụng.

> **Nguyên tắc cốt lõi:** Với cấu trúc **JWE(JWS(claims))**, đường đi khi tạo token là **claims → ký → mã hóa**, còn đường đi khi xác minh là **kiểm tra và giải mã JWE → xác minh JWS → kiểm tra claims → ra quyết định**.

## 2. Ba dạng cần phân biệt trước khi thiết kế

| Cách bảo vệ | Dạng khái niệm | Người có token đọc claims được không? | Bên nhận có thể kiểm tra issuer qua chữ ký không? |
|---|---|---|---|
| **JWS đơn lẻ** | `JWS(claims)` | **Có** nếu payload là JSON thường được mã hóa base64url; JWS không cung cấp bí mật nội dung. | Có, với điều kiện khóa xác minh được ràng buộc đúng với issuer tin cậy. |
| **JWE đơn lẻ** | `JWE(claims)` | Không, nếu không sở hữu khóa giải mã phù hợp. | Không tự động; giải mã JWE thành công chưa đủ xác nhận issuer. |
| **Ký rồi mã hóa** | `JWE(JWS(claims))` | Không, nếu không giải mã được JWE. | Có, sau khi giải mã JWE và xác minh JWS bằng khóa issuer tin cậy. |

Lưu ý, JWE cung cấp **mã hóa có xác thực** và cơ chế kiểm tra toàn vẹn bản mã. Tuy nhiên, khi sử dụng mã hóa bằng **khóa công khai của recipient**, bất kỳ ai có khóa công khai đó về lý thuyết đều có thể tạo một JWE cho recipient. Vì vậy **JWE đơn lẻ không chứng minh thông điệp do issuer cụ thể phát hành**. Chữ ký JWS bên trong đảm nhận vai trò xác thực nguồn phát hành, với giả định quản lý khóa đáng tin cậy.

## 3. Minh họa đầy đủ luồng ký rồi mã hóa

Giả sử:

- **Issuer A** phát hành token cho đối tác.
- **Recipient B** là API xử lý hóa đơn.
- **Người chuyển tiếp C** chỉ chuyển token và không cần xem claims.
- A sở hữu **khóa riêng để ký**; B đã có **khóa công khai xác minh chữ ký của A** thông qua cấu hình tin cậy.
- B sở hữu **khóa riêng giải mã JWE**; A có **khóa công khai mã hóa của B** thông qua kênh tin cậy.

~~~mermaid
sequenceDiagram
    participant A as Issuer A
    participant C as Trung gian C
    participant B as API B

    Note over A: Tạo claims phù hợp audience B
    A->>A: Ký claims bằng khóa riêng của A → JWS
    A->>A: Mã hóa toàn bộ JWS bằng khóa công khai của B → JWE
    A->>C: Gửi Nested JWT là JWE
    C->>B: Chuyển tiếp JWE
    Note over C: Không cần thấy claims hoặc chữ ký JWS
    B->>B: Kiểm tra chính sách JWE và xác thực tag
    B->>B: Giải mã JWE bằng khóa riêng của B → JWS
    B->>B: Xác minh chữ ký JWS bằng khóa công khai tin cậy của A
    B->>B: Kiểm tra iss, aud, exp, nbf và quyền
    B-->>C: Kết quả theo chính sách API
~~~

### 3.1. Bước 1 — Tạo claims

Ví dụ JSON được dùng làm payload của JWT trong cùng:

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

Đây là **dữ liệu minh họa**. Các giá trị thời gian là NumericDate (số giây kể từ Unix epoch); khoảng cách giữa `iat` và `exp` là 300 giây. Với hệ thống thực tế, cần sinh mốc thời gian theo đồng hồ tin cậy và kiểm tra thời hạn khi nhận.

Các claims quan trọng:

- **iss:** định danh bên phát hành cần được tin cậy.
- **sub:** đối tượng mà token đại diện.
- **aud:** bên nhận mà token được dành cho; ở đây là `invoice-api`.
- **iat/nbf/exp:** thời điểm phát hành, thời điểm bắt đầu có hiệu lực và hết hạn.
- **scope/invoice_id:** quyền và tài nguyên cụ thể mà API còn phải xác thực.

Chỉ đưa vào claims dữ liệu thực sự cần thiết; việc mã hóa không phải lý do để đưa thông tin dư thừa hoặc bí mật dài hạn vào token.

### 3.2. Bước 2 — Ký claims thành JWS bên trong

Ví dụ JWS protected header:

~~~json
{
  "alg": "ES256",
  "typ": "invoice-access+jwt",
  "kid": "issuer-sign-2027-01"
}
~~~

Trong đó:

| Trường | Ý nghĩa |
|---|---|
| `alg: ES256` | Thuật toán ký ECDSA dùng P-256 và SHA-256, được ví dụ là **cấu hình cho phép sẵn** ở ứng dụng. |
| `typ: invoice-access+jwt` | Loại JWT cụ thể của ứng dụng, giúp tách token truy cập hóa đơn khỏi token khác. Đây là giá trị ví dụ, không phải loại được chuẩn hóa sẵn. |
| `kid: issuer-sign-2027-01` | Gợi ý lựa chọn khóa xác minh thuộc tập khóa đáng tin cậy của issuer A; không tự chứng minh nguồn phát hành. |

Issuer A ký bằng **khóa riêng ký** của mình. Với JWS Compact Serialization, kết quả có ba thành phần:

~~~text
BASE64URL(protected_header).BASE64URL(claims_payload).BASE64URL(signature)
~~~

Toàn bộ ba thành phần này hợp thành **chuỗi JWS hoàn chỉnh**. Chữ ký JWS bảo vệ các byte đã ký theo quy tắc JWS; bên nhận không được tự sửa hoặc chuẩn hóa payload rồi xem chữ ký cũ là hợp lệ.

### 3.3. Bước 3 — Mã hóa toàn bộ JWS thành JWE bên ngoài

Issuer A mã hóa **toàn bộ chuỗi JWS**, không phải chỉ phần claims. Ví dụ protected header của JWE:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT",
  "kid": "recipient-enc-2027-01"
}
~~~

| Trường | Ý nghĩa |
|---|---|
| `alg: RSA-OAEP-256` | Thuật toán quản lý khóa JWE; trong ví dụ, dùng khóa công khai mã hóa của B để bảo vệ khóa mã hóa nội dung. |
| `enc: A256GCM` | Thuật toán mã hóa nội dung có xác thực. |
| `cty: JWT` | Thông báo plaintext là một JWT được lồng bên trong. [RFC 7519 §5.2](https://www.rfc-editor.org/rfc/rfc7519.html#section-5.2) yêu cầu `cty` với giá trị `JWT` khi sử dụng Nested JWT. |
| `kid: recipient-enc-2027-01` | Gợi ý chọn **khóa giải mã của B**; khác với kid thuộc khóa ký của A ở lớp trong. |

Trong JWE Compact Serialization, token gửi qua mạng có **năm thành phần**:

~~~text
BASE64URL(jwe_protected_header).BASE64URL(encrypted_key).BASE64URL(iv).BASE64URL(ciphertext).BASE64URL(authentication_tag)
~~~

Ciphertext chứa JWS hoàn chỉnh. Trong JWE Compact, protected header của lớp ngoài **không bị che giấu**, nhưng được đưa vào dữ liệu được xác thực bằng cơ chế JWE. Các header như `alg`, `enc`, `kid` vẫn phải được xem là dữ liệu do phía gửi cung cấp cho đến khi xác thực thành công.

### 3.4. Mã giả phát hành token

~~~text
function issue_nested_jwt(context):
    claims = {
        iss: trusted_issuer_id,
        sub: context.subject,
        aud: "invoice-api",
        iat: now_in_unix_seconds(),
        nbf: now_in_unix_seconds(),
        exp: now_in_unix_seconds() + 300,
        scope: "invoice:read",
        invoice_id: context.invoice_id
    }

    inner_jws = JWS.sign(
        payload = claims,
        private_key = issuer_A_signing_private_key,
        protected_header = {
            alg: "ES256",
            typ: "invoice-access+jwt",
            kid: "issuer-sign-2027-01"
        }
    )

    outer_jwe = JWE.encrypt(
        plaintext = UTF8(inner_jws),
        recipient_public_key = recipient_B_encryption_public_key,
        protected_header = {
            alg: "RSA-OAEP-256",
            enc: "A256GCM",
            cty: "JWT",
            kid: "recipient-enc-2027-01"
        }
    )

    return outer_jwe
~~~

Mã giả nêu ý tưởng, không gắn với bất kỳ thư viện nào. Trong triển khai thực, gọi thời điểm hiện tại **một lần** rồi tính `iat`, `nbf`, `exp` nhất quán; cần cấu hình rõ loại JWT, thuật toán và nguồn khóa từ phía hệ thống.

## 4. Thứ tự kiểm tra tại bên nhận: đi từ lớp ngoài vào trong

Với **sign-then-encrypt**, bên nhận không có JWS để xác minh chữ ký ngay từ đầu. Token mà B nhìn thấy là một JWE. Do đó quy trình chuẩn là:

~~~mermaid
flowchart TD
    A["Nhận chuỗi Nested JWT"] --> B["Kiểm tra định dạng, giới hạn kích thước và chính sách JWE"]
    B --> C["Chọn khóa nhận từ tập khóa tin cậy, kiểm tra alg/enc/cty"]
    C --> D["Giải mã và xác thực JWE bằng kiểm tra tag"]
    D -->|Thất bại| R["Từ chối token"]
    D -->|Thành công| E["Lấy JWS hoàn chỉnh từ plaintext"]
    E --> F["Kiểm tra định dạng và chính sách JWS, xác minh chữ ký"]
    F -->|Thất bại| R
    F -->|Thành công| G["Kiểm tra iss, aud, thời hạn, loại token, quyền"]
    G -->|Không đạt| R
    G -->|Đạt| H["Cho phép thao tác theo phạm vi đã cấp"]
~~~

### 4.1. Trước giải mã: chỉ kiểm tra cấu trúc và lựa chọn cấu hình

Các kiểm tra có thể thực hiện trước giải mã:

1. Token có đúng dạng JWE Compact mà endpoint chấp nhận không (năm thành phần, đúng mã hóa và giới hạn kích thước)?
2. Protected header có dùng đúng **`alg` và `enc` nằm trong danh sách cho phép** không?
3. Nếu chính sách yêu cầu Nested JWT, protected header có `cty: JWT` không?
4. `kid` có ánh xạ tới khóa giải mã trong **tập khóa recipient được quản lý sẵn** không?

Điểm tinh tế: Trước khi xác thực tag JWE, header được giải mã ra từ chuỗi token là **đầu vào chưa đáng tin**. Nó có thể hỗ trợ lựa chọn thuật toán/khóa từ một tập *đã cố định trước*, nhưng không được phép tự ý:

- Bật thêm thuật toán không được cấu hình.
- Chuyển sang phương thức xác minh yếu hơn.
- Đọc khóa từ một URL tùy ý do token chỉ định.
- Thay đổi issuer hoặc audience được kỳ vọng chỉ vì token yêu cầu.

Ở dạng Compact, protected header được bảo vệ tính toàn vẹn bởi JWE khi bước xác thực hoàn tất; việc đọc trước header để chọn khóa **không tương đương** tin header trước khi xác thực.

### 4.2. Bước bắt buộc thứ nhất: xác thực và giải mã JWE

Bên nhận dùng **khóa riêng giải mã của B** và thuật toán đã được cho phép để phục hồi khóa mã hóa nội dung, kiểm tra authentication tag, rồi mới chấp nhận plaintext.

Đối với ví dụ **A256GCM**, authentication tag ràng buộc ciphertext với dữ liệu xác thực của JWE, bao gồm protected header theo quy tắc JWE Compact. Nếu ciphertext, header được bảo vệ hoặc tag bị sửa sai, thao tác xác thực phải thất bại.

Một số API có thể cung cấp dữ liệu plaintext trong quá trình giải mã trước khi hoàn tất xác thực tag. Ứng dụng **không được sử dụng, ghi log hay chuyển tiếp plaintext như dữ liệu đáng tin** cho tới khi xác thực hoàn toàn thành công.

Nếu JWE bị lỗi, dừng xử lý. Không thử diễn giải token đó là JWS đơn lẻ để “cứu” một yêu cầu vốn bắt buộc phải có mã hóa.

### 4.3. Bước bắt buộc thứ hai: xác minh JWS bên trong

Sau khi giải mã JWE thành công, plaintext phải là **một JWS/JWT có định dạng đúng theo hợp đồng**. Với ví dụ này, yêu cầu JWS Compact gồm ba thành phần.

Kiểm tra:

1. Chỉ chấp nhận các thuật toán ký đã cấu hình, ví dụ **ES256**; không dựa hoàn toàn vào `alg` được token tự khai báo.
2. Chọn khóa xác minh chữ ký đã được tin cậy cho **issuer A**; `kid` chỉ là gợi ý trong tập khóa đó.
3. Xác minh chữ ký trên **đúng thông điệp được ký**.
4. Đảm bảo loại token đúng với bối cảnh, chẳng hạn `typ: invoice-access+jwt` được quy định ở JWS trong cùng.
5. Khi chữ ký đã hợp lệ, mới chấp nhận các claims như ứng viên dữ liệu đáng tin để kiểm tra chính sách tiếp theo.

**Phải xác minh toàn bộ các thao tác mật mã** trong Nested JWT, không được bỏ qua một lớp vì lớp khác đã thành công; đây là nguyên tắc trong [RFC 8725 §3.3](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.3).

Các hệ thống có thể cần đọc header hoặc một phần claims chưa xác minh để *định tuyến* đến tập khóa tin cậy, nhưng không được sử dụng các giá trị đó để cấp quyền hay chấp nhận khóa ngoài chính sách. Tính hợp lệ của chữ ký chỉ có ý nghĩa khi **khóa xác minh được ràng buộc với issuer được kỳ vọng**.

### 4.4. Bước bắt buộc thứ ba: kiểm tra claims và quyền

**Chữ ký đúng không có nghĩa yêu cầu được cho phép.** Sau khi hai lớp mật mã đã đạt yêu cầu, bên nhận tiếp tục:

| Điều kiện | Cách kiểm tra | Nếu sai |
|---|---|---|
| **Issuer (`iss`)** | Trùng issuer được chấp nhận, khóa xác minh thuộc đúng issuer đó. | Từ chối. |
| **Audience (`aud`)** | Có `invoice-api` hoặc audience chính sách của API hiện tại. | Từ chối, dù chữ ký đúng. |
| **Thời hạn (`exp`)** | Token chưa hết hạn; chỉ cho phép khoảng lệch đồng hồ nhỏ nếu chính sách quy định. | Từ chối token quá hạn. |
| **Chưa có hiệu lực (`nbf`)** | Thời điểm hiện tại không trước `nbf` (sau khi tính leeway nếu có). | Từ chối. |
| **Thời điểm phát hành (`iat`)** | Kiểm tra định dạng và các giới hạn tuổi hoặc thời gian phát hành theo chính sách ứng dụng. | Từ chối nếu không hợp lệ theo chính sách. |
| **Subject (`sub`)** | Có định danh hợp lệ trong hệ thống hoặc miền đối tượng dự kiến. | Từ chối hoặc không cấp quyền. |
| **Scope và tài nguyên** | Quyền `invoice:read` có cho phép truy cập đúng `invoice_id` này không? | Từ chối thao tác không được ủy quyền. |
| **Loại token** | Đúng profile/token type dành riêng cho endpoint. | Từ chối token dùng sai mục đích. |

Các hệ thống có yêu cầu **chống phát lại** có thể thêm `jti`, nonce, cơ chế phát hiện tái sử dụng hoặc token có ràng buộc với bên trình token. **Ký và mã hóa không tự làm bearer token trở nên chống phát lại.**

### 4.5. Mã giả xác minh hoàn chỉnh

~~~text
function validate_nested_jwt(token, request):
    # (0) Chính sách này do API cấu hình sẵn, không lấy từ token
    expected_issuer = "https://issuer.example.test"
    expected_audience = "invoice-api"
    expected_type = "invoice-access+jwt"
    expected_outer_alg = "RSA-OAEP-256"
    expected_outer_enc = "A256GCM"
    allowed_inner_alg = ["ES256"]

    # (1) Chỉ nhận JWE với nesting như hợp đồng
    require_jwe_compact_format_and_size_limit(token)
    outer_header = read_untrusted_protected_header(token)
    require_equal(outer_header.alg, expected_outer_alg)
    require_equal(outer_header.enc, expected_outer_enc)
    require_equal(outer_header.cty, "JWT")

    decryption_key = find_configured_recipient_key(outer_header.kid)

    # (2) Thao tác này phải xác thực tag JWE; lỗi là dừng ngay
    inner_jws_bytes = decrypt_and_authenticate_jwe(token, decryption_key)
    inner_jws = decode_utf8_as_expected_jws(inner_jws_bytes)

    # (3) Xác minh chữ ký bằng tập khóa issuer được phép
    require_jws_compact_format(inner_jws)
    inner_header = read_untrusted_jws_header(inner_jws)
    require_member(inner_header.alg, allowed_inner_alg)
    require_equal(inner_header.typ, expected_type)

    signing_key = find_configured_issuer_key(
        issuer = expected_issuer,
        key_id = inner_header.kid,
        allowed_algorithms = allowed_inner_alg
    )
    claims = verify_jws_signature_and_parse_claims(inner_jws, signing_key)

    # (4) Kiểm tra các điều kiện dùng token
    require_equal(claims.iss, expected_issuer)
    require_expected_audience(claims.aud, expected_audience)
    require_valid_time_window(claims.iat, claims.nbf, claims.exp)
    require_valid_subject(claims.sub)
    require_authorized_resource(
        subject = claims.sub,
        permissions = claims.scope,
        resource = request.invoice_id,
        action = "invoice:read"
    )

    return claims
~~~

Mã giả làm rõ **hợp đồng bảo mật và điểm dừng khi lỗi**; thư viện thực tế có thể gộp hoặc sắp xếp nội bộ các thao tác. Quan trọng nhất là **không sử dụng claims để đưa ra quyết định trước khi tất cả bước xác thực cần thiết hoàn tất**.

## 5. Thứ tự xử lý khi đổi chiều lồng nhau

Không phải mọi Nested JWT đều là JWE chứa JWS. Có thể lồng theo chiều khác:

| Cách tạo | Lớp ngoài | Thứ tự xử lý tại recipient | Đặc điểm đáng chú ý |
|---|---|---|---|
| **Ký → mã hóa**: `JWE(JWS(claims))` | JWE | **Giải mã/xác thực JWE → kiểm tra JWS → kiểm tra claims.** | JWS header, chữ ký và claims được che giấu bởi lớp mã hóa. |
| **Mã hóa → ký**: `JWS(JWE(claims))` | JWS | **Xác minh JWS → giải mã/xác thực JWE → kiểm tra claims.** | Chữ ký và header của lớp JWS ngoài có thể quan sát được; chữ ký bao bọc *bản mã*, nên cần chính sách rõ về ý nghĩa xác thực và quan hệ issuer–recipient. |

**Không được tự ý đổi thứ tự xử lý** để “thử cho đến khi token chạy được”. Endpoint nên định nghĩa trước cấu trúc JWT được chấp nhận và kiểm tra đúng các lớp theo cấu trúc đó.

Với sign-then-encrypt, chưa giải mã thì chưa có JWS đầy đủ để xác minh. Với encrypt-then-sign, JWS nằm ngoài nên bước kiểm tra chữ ký ở ngoài phải diễn ra trước khi tin payload của nó. Mọi cấu trúc lồng cần xác minh **đầy đủ từng lớp**, kể cả khi thư viện có khả năng tự phát hiện loại token.

## 6. Hai tình huống để hiểu đúng ranh giới tin cậy

### Tình huống A — Bên trung gian nhìn thấy token

A gửi JWE đã chứa JWS thông qua C đến B. C có thể nhìn thấy protected header JWE, ví dụ `alg`, `enc`, `cty`, `kid` và độ dài token, nhưng **không thể đọc claims bên trong** nếu không có khóa giải mã.

Khi B nhận token, B không nên tin `cty` hoặc `kid` chỉ vì đọc thấy chúng. B kiểm tra các giá trị này với chính sách rồi giải mã và xác thực thành công JWE. Sau đó B mới có JWS để xác minh issuer A.

Thứ tự này bảo vệ tính bí mật đối với trung gian nhưng **không loại bỏ nhu cầu TLS** để bảo vệ việc truyền tải, chống sửa đổi hoặc lộ metadata trong quá trình giao tiếp.

### Tình huống B — Một bên thứ ba tự tạo JWE cho B

Giả sử kẻ tấn công biết khóa công khai mã hóa của B. Họ có thể tạo một JWE mang payload tự chọn với `alg = RSA-OAEP-256` và `enc = A256GCM`, sao cho B giải mã và kiểm tra tag JWE thành công.

Nếu B **dừng ở bước giải mã** và tin claims, họ có thể chấp nhận nội dung không phải do A phát hành. Nếu B yêu cầu **JWS hợp lệ của A nằm bên trong**, nỗ lực này thất bại vì kẻ tấn công không thể tạo chữ ký hợp lệ của A nếu không có khóa ký.

Tình huống này cho thấy **xác thực bản mã JWE** và **xác thực issuer bằng JWS** là hai kiểm tra khác nhau.

## 7. Các lỗi thực thi nguy hiểm

| Lỗi triển khai | Vì sao nguy hiểm | Cách phòng tránh |
|---|---|---|
| Tin claims ngay khi giải mã JWE thành công. | Mã hóa bằng khóa công khai recipient không đủ chứng minh issuer. | Bắt buộc kiểm tra chữ ký JWS bên trong và ánh xạ issuer–khóa. |
| Kiểm tra chữ ký JWS nhưng bỏ qua kiểm tra tag hoặc lỗi của JWE. | Có thể dùng dữ liệu chưa được xác thực hoàn chỉnh, kể cả plaintext do thư viện trả dần. | Chỉ nhận plaintext sau khi giải mã **và** xác thực JWE thành công. |
| Dựa vào `alg`, `kid`, `jku`, `x5u` tùy ý trong token để chọn thuật toán hoặc tải khóa. | Dễ phát sinh algorithm confusion, key confusion hoặc truy cập mạng không mong muốn. | Cố định allowlist thuật toán và nguồn khóa tin cậy phía recipient/issuer. |
| Thiếu hoặc bỏ qua `cty: JWT` ở lớp ngoài. | Có thể xử lý sai loại nội dung lồng nhau và phá vỡ chính sách profile. | Yêu cầu `cty: JWT` đúng quy định khi Nested JWT. |
| Cho phép JWS đơn lẻ làm fallback khi JWE lỗi. | Có thể hạ cấp từ luồng có mã hóa sang không mã hóa. | Endpoint yêu cầu Nested JWT phải từ chối cấu trúc khác. |
| Chấp nhận JWS hợp lệ bất kể issuer, audience, token type. | Token dùng cho API khác có thể bị tái sử dụng sai mục đích. | Ràng buộc `iss`, `aud`, `typ`, scope, subject với từng ngữ cảnh. |
| Dùng chung hoặc quản lý nhầm khóa ký và khóa giải mã. | Tăng nguy cơ lộ khóa và nhầm mục đích khóa. | Phân tách vai trò, kho khóa, rotation và quyền truy cập. |
| Cho phép nesting không giới hạn hoặc token quá lớn. | Có thể bị lạm dụng tài nguyên trong giải mã, xác minh hoặc phân tích cú pháp. | Đặt giới hạn kích thước, số lớp nesting và tài nguyên. |
| Ghi log token nguyên vẹn hoặc plaintext sau khi giải mã. | Làm lộ nội dung, bearer token hoặc thông tin nhạy cảm. | Giảm log, che giá trị nhạy cảm, giới hạn quyền xem. |
| Coi token đã ký/mã hóa là không thể bị phát lại. | Token bearer bị đánh cắp vẫn có thể được trình lại khi còn hiệu lực. | Thời hạn ngắn, `jti`/nonce hoặc token binding khi mô hình đe dọa yêu cầu. |

Theo [RFC 8725 – JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html), cần chú ý đặc biệt đến việc xác thực mọi thao tác mật mã, danh sách thuật toán được phép, kiểm tra issuer/audience và ngăn nhầm lẫn giữa các loại JWT.

## 8. Checklist kiểm thử cho cấu trúc JWE chứa JWS

Bảng dưới đây dùng để **kiểm tra hành vi chấp nhận/từ chối** khi thiết kế hoặc đánh giá endpoint nhận Nested JWT:

| Trường hợp thử | Kết quả mong đợi |
|---|---|
| JWE hợp lệ, JWS bên trong được ký bởi issuer A, claims đúng audience/thời hạn/quyền. | **Chấp nhận** theo quyền được cấp. |
| Ciphertext hoặc authentication tag JWE bị sửa. | **Từ chối tại lớp JWE**. |
| JWE giải mã được nhưng plaintext không phải JWS đúng định dạng. | **Từ chối**. |
| JWE giải mã được nhưng chữ ký JWS bên trong sai. | **Từ chối tại lớp JWS**. |
| JWS có chữ ký hợp lệ bởi khóa của issuer khác ngoài danh sách tin cậy. | **Từ chối**. |
| JWS hợp lệ nhưng `aud` sai hoặc token đã hết hạn. | **Từ chối tại bước kiểm tra claims**. |
| Token JWS không mã hóa gửi thẳng vào endpoint yêu cầu Nested JWT. | **Từ chối định dạng**, không fallback. |
| JWE có `alg`/`enc` không nằm trong chính sách hoặc thiếu `cty: JWT`. | **Từ chối tại chính sách đầu vào**. |
| JWS bên trong dùng `alg: none` hoặc thuật toán không cho phép. | **Từ chối tại chính sách chữ ký**. |
| `kid` tham chiếu khóa ngoài tập cấu hình hoặc URL bên ngoài. | **Từ chối**; không tự nạp khóa từ nguồn không tin cậy. |
| Token hợp lệ về mật mã nhưng `scope` không cho phép hành động hiện tại. | **Từ chối theo ủy quyền**. |

Việc trả lỗi cho client nên tránh tiết lộ dữ liệu nhạy cảm. Các chi tiết kiểm tra nội bộ có thể được ghi nhận trong hệ thống giám sát được bảo vệ, với mức log hạn chế.

## 9. Những quyết định thiết kế cần thống nhất trước khi triển khai

Một giao thức có Nested JWT nên mô tả rõ những điều sau:

1. **Hình thức lồng:** Có yêu cầu `JWE(JWS(claims))` hay cấu trúc khác? Có chỉ chấp nhận Compact Serialization không?
2. **Danh sách thuật toán:** Tập `alg`/ `enc` cho JWE và `alg` cho JWS là gì? Khóa nào được phép dùng với thuật toán nào?
3. **Ranh giới tin cậy:** Ai là issuer được phép ký, ai giữ khóa giải mã, ai nhận token và có trung gian nào cần nhìn thấy nội dung không?
4. **Profile JWT:** Giá trị `cty` bắt buộc của lớp ngoài, `typ` cụ thể ở JWT trong cùng, cùng tập claims cần có.
5. **Chính sách chấp nhận:** Issuer, audience, thời hạn, độ lệch đồng hồ, scope, đối tượng tài nguyên và cơ chế chống phát lại.
6. **Vòng đời khóa:** Phân phối khóa công khai tin cậy, bảo vệ khóa riêng, `kid`, xoay vòng và xử lý khi khóa bị lộ.
7. **Giới hạn và lỗi:** Giới hạn độ lớn, độ sâu nesting, timeout/tài nguyên, cách từ chối và cách ghi log an toàn.

Nếu hệ thống không cần giữ kín claims trước các bên có thể nhìn thấy token, **JWS với chính sách xác minh tốt** có thể đủ. Nếu cần cả bí mật và chứng minh nguồn phát hành, **ký rồi mã hóa** thường là lựa chọn phù hợp. Không nên dùng nhiều lớp mật mã để thay thế việc giảm dữ liệu hoặc kiểm soát quyền.

## 10. Câu hỏi tự ôn tập

1. Vì sao với cấu trúc `JWE(JWS(claims))`, bên nhận bắt buộc phải giải mã JWE trước khi xác minh chữ ký JWS?
2. Authentication tag của JWE và chữ ký của JWS chứng minh những điều gì khác nhau?
3. Vì sao một JWE được tạo bằng khóa công khai của B vẫn có thể chứa claims do kẻ không đáng tin tạo ra?
4. Tại sao `kid` và `alg` được đọc từ header chỉ nên được dùng trong phạm vi chính sách đã cấu hình?
5. Một Nested JWT được giải mã và xác minh chữ ký thành công, nhưng `aud` sai. Endpoint phải xử lý thế nào?
6. Nếu đổi sang `JWS(JWE(claims))`, thứ tự xác minh thay đổi ra sao và cần cân nhắc ranh giới tin cậy nào?

## 11. Tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): JWT lồng nhau, cách xử lý `cty` (§5.2), quy trình xác minh (§7.2) và khuyến nghị thứ tự ký/mã hóa (§11.2).
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): định dạng JWS và kiểm tra chữ ký/MAC.
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): định dạng JWE, quản lý khóa, giải mã có xác thực và authentication tag.
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): thuật toán JWS/JWE như ES256, RSA-OAEP-256 và A256GCM.
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): kiểm tra mọi thao tác mật mã (§3.3), kiểm soát thuật toán (§3.1), kiểm tra issuer/audience (§3.8–3.9), explicit typing với Nested JWT (§3.11) và tách biệt quy tắc xác minh từng loại JWT (§3.12).

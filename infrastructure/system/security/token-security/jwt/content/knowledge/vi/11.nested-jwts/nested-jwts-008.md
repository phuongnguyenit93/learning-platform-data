# Ngăn bỏ qua lớp bảo vệ hoặc nhầm nội dung bên trong

> **Chương:** JWT lồng nhau  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Nội dung áp dụng cho hệ thống dùng JWT/JOSE nói chung, độc lập với ngôn ngữ lập trình và framework.

## 1. Rủi ro cốt lõi khi xử lý Nested JWT

Nested JWT có thể kết hợp nhiều lớp JWS và JWE. Mỗi lớp có một nhiệm vụ riêng: chữ ký/MAC bảo vệ tính toàn vẹn và xác thực theo quan hệ khóa tin cậy; JWE bảo vệ tính bí mật và tính toàn vẹn của ciphertext thông qua cơ chế mã hóa có xác thực.

Rủi ro xuất hiện khi bên nhận chỉ xử lý một lớp rồi **coi toàn bộ token đã hợp lệ**. Ví dụ:

- Giải mã JWE thành công nhưng bỏ qua chữ ký JWS bên trong.
- Xác minh JWS ngoài thành công nhưng mặc định claims bên trong do issuer gốc phát hành, dù signer thực tế là một gateway.
- Đọc `cty` hoặc `typ` rồi tin nội dung trước khi xác minh lớp đã bảo vệ header.
- Chấp nhận token đơn lẻ hoặc một thứ tự nesting khác khi cấu trúc Nested JWT mong đợi bị lỗi.
- Phân tích payload như Claims Set JSON trong khi payload thực tế còn là một JWT khác.

[RFC 8725 §3.3](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.3) yêu cầu xác minh tất cả thao tác mật mã được thực hiện trên JWT. Nếu token có nhiều lớp ký và mã hóa, mọi thao tác bắt buộc đều phải thành công. Một lớp hợp lệ không bù được cho lớp còn lại bị bỏ qua hoặc thất bại.

**Nguyên tắc:** xác định trước cấu trúc token mà endpoint chấp nhận; xác minh từng lớp theo đúng thứ tự; chỉ sử dụng nội dung của một lớp sau khi thao tác mật mã của lớp đó thành công.

## 2. Hiểu đúng hai cấu trúc phổ biến

### 2.1. Ký rồi mã hóa — `JWE(JWS(claims))`

Quy trình tạo:

1. Issuer tạo Claims Set.
2. Signer ký Claims Set thành JWS.
3. Encryptor mã hóa toàn bộ JWS thành JWE cho recipient.

Quy trình nhận:

1. Kiểm tra cấu trúc và chính sách JWE ngoài.
2. Giải mã và xác thực JWE.
3. Lấy JWS từ plaintext đã xác thực.
4. Xác minh chữ ký JWS bằng khóa của signer tin cậy.
5. Kiểm tra claims và quyền.

~~~mermaid
flowchart TD
    A["Nhận JWE ngoài"] --> B["Kiểm tra cấu trúc và allowlist"]
    B --> C["Giải mã + xác thực JWE"]
    C -->|Thất bại| X["Từ chối"]
    C -->|Thành công| D["Lấy JWS bên trong"]
    D --> E["Xác minh chữ ký JWS"]
    E -->|Thất bại| X
    E -->|Thành công| F["Kiểm tra claims, audience và quyền"]
    F -->|Không đạt| X
    F -->|Đạt| G["Chấp nhận"]
~~~

**Lớp JWE ngoài không thay thế chữ ký JWS trong.** Với mã hóa khóa công khai, bất kỳ bên nào có khóa công khai của recipient đều có thể tạo JWE gửi đến recipient. Giải mã và xác thực tag thành công không tự chứng minh claims do issuer tin cậy phát hành.

### 2.2. Mã hóa rồi ký — `JWS(JWE(claims))`

Quy trình tạo:

1. Issuer tạo Claims Set.
2. Encryptor mã hóa claims thành JWE.
3. Signer ký toàn bộ chuỗi JWE thành JWS.

Quy trình nhận:

1. Kiểm tra cấu trúc và chính sách JWS ngoài.
2. Xác minh chữ ký JWS.
3. Lấy JWE từ payload đã xác minh.
4. Giải mã và xác thực JWE.
5. Kiểm tra claims và quyền.

~~~mermaid
flowchart TD
    A["Nhận JWS ngoài"] --> B["Kiểm tra cấu trúc và allowlist"]
    B --> C["Xác minh chữ ký JWS"]
    C -->|Thất bại| X["Từ chối"]
    C -->|Thành công| D["Lấy JWE bên trong"]
    D --> E["Giải mã + xác thực JWE"]
    E -->|Thất bại| X
    E -->|Thành công| F["Kiểm tra claims, audience và quyền"]
    F -->|Không đạt| X
    F -->|Đạt| G["Chấp nhận"]
~~~

**Chữ ký JWS ngoài chỉ xác thực người ký đối tượng JWE.** Nếu signer là gateway khác issuer, chữ ký đó không tự chứng minh issuer trong claims đã phát hành nội dung. Recipient vẫn cần kiểm tra quan hệ signer–issuer hoặc cơ chế nguồn gốc đã được hợp đồng quy định.

### 2.3. So sánh thứ tự xác minh

| Cấu trúc | Lớp ngoài | Thao tác đầu tiên | Thao tác tiếp theo |
|---|---|---|---|
| `JWE(JWS(claims))` | JWE | Giải mã và xác thực JWE | Xác minh chữ ký JWS |
| `JWS(JWE(claims))` | JWS | Xác minh chữ ký JWS | Giải mã và xác thực JWE |

Không đảo thứ tự chỉ để thử làm token chạy được. Hợp đồng phải xác định chính xác lớp ngoài, lớp trong, thuật toán và khóa được phép.

## 3. Những cách bỏ qua lớp bảo vệ thường gặp

### 3.1. Giải mã JWE rồi bỏ qua JWS bên trong

Đây là lỗi nghiêm trọng với `JWE(JWS(claims))`.

Giả sử API yêu cầu token được ký bởi issuer A rồi mã hóa cho API. Kẻ tấn công có thể dùng khóa công khai của API để tạo một JWE mới chứa Claims Set do họ tự chọn. Nếu API chỉ giải mã JWE, kiểm tra tag rồi tin claims, token giả có thể được chấp nhận dù không có chữ ký của A.

**Cách phòng tránh:**

- Endpoint phải yêu cầu đúng JWE chứa JWS theo hợp đồng.
- Sau khi giải mã và xác thực JWE, bắt buộc parse nội dung thành JWS đúng định dạng.
- Xác minh chữ ký JWS bằng khóa được gắn với issuer/signer tin cậy.
- Kiểm tra claims `iss`, `aud`, thời hạn và quyền sau khi chữ ký hợp lệ.
- Nếu thiếu JWS, chữ ký sai hoặc loại token không đúng, từ chối toàn bộ Nested JWT.

### 3.2. Xác minh JWS ngoài rồi bỏ qua JWE bên trong

Với `JWS(JWE(claims))`, chữ ký ngoài có thể hợp lệ nhưng payload vẫn là JWE cần giải mã và xác thực.

Nếu endpoint yêu cầu claims bí mật và recipient cụ thể, chỉ xác minh chữ ký ngoài là chưa đủ. Hệ thống chưa đọc được claims và chưa kiểm tra được audience, thời hạn hoặc quyền bên trong. Một JWS hợp lệ có thể chứa JWE sai cấu trúc, không giải mã được hoặc được mã hóa cho recipient khác.

**Cách phòng tránh:**

- Sau khi xác minh JWS, kiểm tra payload là JWE theo đúng profile.
- Kiểm tra `alg`, `enc`, `kid` và cấu trúc JWE theo allowlist.
- Giải mã và xác thực authentication tag bằng khóa recipient được phép.
- Chỉ parse Claims Set sau khi JWE được xác thực hoàn toàn.
- Từ chối nếu JWE sai, tag sai hoặc plaintext không phải Claims Set theo profile.

### 3.3. Tin chữ ký gateway như chữ ký issuer

Trong `JWS(JWE(claims))`, signer ngoài có thể là gateway G, còn claims được phát hành bởi A.

Chữ ký của G chứng minh G đã ký đúng chuỗi JWE. Nếu G không xác minh nguồn gốc claims hoặc không được A ủy quyền, chữ ký đó không chứng minh A đã phát hành nội dung.

**Cách phòng tránh:**

- Xác định signer được mong đợi cho lớp JWS ngoài.
- Ràng buộc khóa xác minh với danh tính signer.
- Nếu signer khác issuer, kiểm tra quyền đại diện hoặc cơ chế xác thực nguồn gốc claims.
- Không lấy riêng giá trị `iss` trong plaintext làm bằng chứng.
- Nếu cần bằng chứng chữ ký của issuer gốc, giữ chữ ký đó ở lớp phù hợp và xác minh nó theo hợp đồng.

### 3.4. Bỏ qua authentication tag của JWE

Một số API giải mã có thể xử lý dữ liệu trung gian trước khi hoàn tất kiểm tra authentication tag. Nếu ứng dụng sử dụng plaintext trước khi tag hợp lệ, dữ liệu chưa được xác thực có thể đi vào parser hoặc logic nghiệp vụ.

**Cách phòng tránh:**

- Chỉ nhận plaintext từ thao tác JWE đã hoàn tất xác thực.
- Không log, parse claims, định tuyến nhạy cảm hoặc cấp quyền dựa trên plaintext trước khi tag được xác minh.
- Nếu thư viện trả dữ liệu theo luồng, phải bảo đảm ứng dụng không tiêu thụ dữ liệu như plaintext đáng tin trước khi xác thực hoàn tất.

### 3.5. Chỉ kiểm tra lớp ngoài cùng

Một token có thể có nhiều lớp. Nếu validator chỉ xác minh lớp đầu tiên rồi dừng, mọi bảo vệ ở lớp trong đều có thể bị bỏ qua.

**Cách phòng tránh:**

- Duyệt cấu trúc theo hợp đồng từ ngoài vào trong.
- Với mỗi lớp, thực hiện đúng thao tác JWS hoặc JWE.
- Khi lớp đã xác thực có `cty: "JWT"`, tiếp tục xử lý JWT bên trong.
- Chỉ dừng khi đạt Claims Set cuối cùng đúng profile.
- Từ chối nếu cấu trúc kết thúc sớm, có lớp thừa hoặc không đúng loại.

## 4. Ngăn nhầm lẫn nội dung bên trong

### 4.1. cty cho biết có JWT lồng bên trong

Theo [RFC 7519 §5.2](https://www.rfc-editor.org/rfc/rfc7519.html#section-5.2), khi một JWT bao bọc một JWT khác do thao tác ký hoặc mã hóa lồng nhau, JOSE Header của lớp bao bọc phải có:

~~~json
{
  "cty": "JWT"
}
~~~

Ví dụ:

- Với `JWE(JWS(claims))`, JWE ngoài có `cty: "JWT"`.
- Với `JWS(JWE(claims))`, JWS ngoài có `cty: "JWT"`.

Sau khi lớp hiện tại được xác thực, `cty: "JWT"` báo cho validator rằng message thu được phải được xử lý như một JWT khác. Nó không có nghĩa message đó đã hợp lệ.

**Không được:**

- Bỏ qua `cty` khi endpoint yêu cầu nesting.
- Đặt `cty` tùy ý để ép parser xử lý JSON như JWT.
- Tin `cty` trước khi xác thực lớp bảo vệ header.
- Tiếp tục xử lý nếu message bên trong không parse được thành JWT đúng định dạng.

Nếu profile không chấp nhận loại content type được khai báo, phải từ chối thay vì tự đoán.

### 4.2. typ phân biệt loại JWT

`typ` mô tả loại JWT theo profile. Ví dụ:

~~~json
{
  "typ": "billing-access+jwt"
}
~~~

Nếu hệ thống dùng explicit typing, giá trị `typ` cụ thể phải được kiểm tra ở JWT trong cùng chứa Claims Set, theo [RFC 8725 §3.11](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.11). Có thể lặp lại `typ` ở lớp ngoài nếu profile cần định danh cả Nested JWT, nhưng không được dùng giá trị ngoài thay cho kiểm tra type của JWT trong cùng.

Phân biệt:

| Header | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `cty: "JWT"` | Nội dung được bao bọc là một JWT khác. | Điều khiển việc tiếp tục xử lý lớp bên trong theo hợp đồng. |
| `typ: billing-access+jwt` | JWT thuộc loại/profile cụ thể. | Chọn đúng quy tắc xác minh và tránh nhầm token khác mục đích. |

`cty` và `typ` đều là JOSE Header Parameter, không phải claims. Chúng không thay thế chữ ký, authentication tag hay kiểm tra issuer/audience.

### 4.3. Không diễn giải payload theo phỏng đoán

Một payload có thể là:

- Claims Set JSON cuối cùng.
- Một JWS Compact hoàn chỉnh.
- Một JWE Compact hoàn chỉnh.
- Một nội dung khác được profile cho phép.

Validator không nên thử parse cùng một byte sequence theo nhiều cách cho đến khi một cách thành công. Hợp đồng cần xác định serialization và kiểu nội dung mong đợi ở từng lớp.

Ví dụ, nếu sau khi giải mã JWE ngoài, profile yêu cầu JWS Compact, nhưng plaintext là JSON Claims Set trực tiếp, phải từ chối. Không được tự động chấp nhận JSON chỉ vì parse thành công.

Với JWS, phải xác minh chữ ký trên đúng JWS Signing Input của token nhận được. Không parse payload rồi serialize lại JSON trước khi xác minh, vì việc thay đổi byte hoặc cách biểu diễn có thể làm thay đổi nội dung được ký. Sau khi xác minh thành công, chỉ sử dụng payload gắn với chính JWS đã xác minh.

## 5. Chống downgrade và layer stripping

**Downgrade** xảy ra khi hệ thống chấp nhận một dạng token có mức bảo vệ thấp hơn dạng endpoint yêu cầu. **Layer stripping** là trường hợp một lớp ký hoặc mã hóa bị loại bỏ nhưng bên nhận vẫn chấp nhận phần còn lại.

Ví dụ:

| Endpoint yêu cầu | Đầu vào bị hạ cấp | Rủi ro nếu chấp nhận |
|---|---|---|
| `JWE(JWS(claims))` | `JWE(claims)` | Bỏ qua chữ ký issuer bên trong. |
| `JWE(JWS(claims))` | `JWS(claims)` | Bỏ qua yêu cầu mã hóa/bí mật. |
| `JWS(JWE(claims))` | `JWS(claims)` | Chấp nhận token không có lớp mã hóa bắt buộc. |
| `JWS(JWE(claims))` | `JWE(claims)` | Bỏ qua chữ ký ngoài và danh tính signer. |
| `JWE(JWS(claims))` | `JWS(JWE(claims))` | Đảo thứ tự lớp so với hợp đồng. |

### 5.1. Dùng profile riêng cho từng endpoint

Mỗi endpoint nên định nghĩa:

- Serialization được chấp nhận.
- Lớp ngoài bắt buộc.
- Loại lớp trong và thứ tự nesting.
- Thuật toán và khóa được phép ở từng lớp.
- `cty` và `typ` bắt buộc.
- Issuer, audience và quyền được chấp nhận.

Nếu hệ thống cần hỗ trợ nhiều loại token, hãy sử dụng profile/endpoint tách biệt hoặc quy tắc xác minh loại trừ lẫn nhau. Không dùng một nhánh xác minh chung có thể tùy ý chấp nhận JWS, JWE và mọi kiểu nesting.

[RFC 8725 §3.12](https://www.rfc-editor.org/rfc/rfc8725.html#section-3.12) khuyến nghị các JWT có mục đích khác nhau phải có quy tắc xác minh riêng biệt, tránh việc một loại JWT được chấp nhận nhầm ở ngữ cảnh khác.

### 5.2. Không fallback khi lớp bắt buộc thất bại

Ví dụ, endpoint yêu cầu `JWE(JWS(claims))`. Nếu JWE giải mã thất bại hoặc plaintext không phải JWS, không thử:

- Parse plaintext như Claims Set JSON.
- Xem toàn bộ token như JWS đơn lẻ.
- Chuyển sang cấu trúc `JWS(JWE(...))`.
- Bỏ qua lớp trong vì lớp ngoài đã hợp lệ.

Tương tự, nếu endpoint yêu cầu `JWS(JWE(claims))`, chữ ký ngoài hợp lệ nhưng payload không phải JWE đúng định dạng thì phải từ chối.

Một lỗi ở bất kỳ lớp bắt buộc nào làm toàn bộ token không hợp lệ.

## 6. Chọn thuật toán và khóa đúng lớp

Nhầm thuật toán hoặc khóa có thể khiến validator xác minh sai đối tượng, sai danh tính hoặc sai mục đích.

### 6.1. Allowlist độc lập cho từng lớp

Với mỗi lớp:

- JWS kiểm tra `alg` theo allowlist chữ ký/MAC.
- JWE kiểm tra cả `alg` quản lý khóa và `enc` mã hóa nội dung.
- Khóa phải tương thích với thuật toán và đúng mục đích.
- Không tự động chuyển từ chữ ký bất đối xứng sang MAC.
- Không cho token tự bật thuật toán hoặc profile không được cấu hình.

### 6.2. Ràng buộc kid với ngữ cảnh

`kid` chỉ là gợi ý chọn khóa. Cùng một chuỗi `kid` có thể xuất hiện ở nhiều kho khóa khác nhau, nên cần phân biệt:

- JWS ngoài: khóa xác minh của signer ngoài.
- JWS trong: khóa xác minh của issuer/signer trong.
- JWE ngoài: khóa giải mã của recipient lớp ngoài.
- JWE trong: khóa giải mã của recipient tương ứng với lớp trong.

Không dùng `kid` để tự tải khóa từ URL không tin cậy. Không lấy `iss` chưa xác minh làm căn cứ duy nhất để tin một khóa. Sau khi xác minh chữ ký, kiểm tra `iss` khớp với danh tính được ràng buộc với khóa.

### 6.3. Xác thực đầy đủ từng thao tác mật mã

| Lớp | Điều kiện bắt buộc |
|---|---|
| JWS | Xác minh chữ ký/MAC thành công trên đúng JWS Signing Input. |
| JWE | Giải mã thành công và xác thực authentication tag hoặc cơ chế toàn vẹn tương ứng. |
| Nested JWT | Tất cả thao tác của mọi lớp đều thành công; không bỏ qua lớp trong hoặc lớp ngoài. |

Không sử dụng plaintext JWE trước khi xác thực hoàn tất. Không sử dụng payload JWS trước khi chữ ký/MAC hợp lệ. Không parse Claims Set để cấp quyền trước khi toàn bộ lớp bắt buộc được xác minh.

## 7. Kiểm tra claims sau khi mọi lớp hợp lệ

Sau khi xác minh từng lớp mật mã, validator mới kiểm tra ý nghĩa của Claims Set cuối cùng.

| Điều kiện | Câu hỏi |
|---|---|
| `iss` | Issuer có nằm trong danh sách được tin cậy và khớp với signer hoặc quan hệ ủy quyền đã cấu hình không? |
| `sub` | Subject có hợp lệ trong miền issuer không? |
| `aud` | Token có dành cho đúng API/recipient hiện tại không? |
| `exp` | Token còn hiệu lực không? |
| `nbf` | Token đã đến thời điểm được phép sử dụng chưa? |
| `iat` | Thời điểm phát hành có hợp lệ và nằm trong giới hạn tuổi token không? |
| `jti` | Có cần kiểm tra chống phát lại hoặc trạng thái đã sử dụng không? |
| `typ` | JWT trong cùng có đúng loại/profile mà endpoint yêu cầu không? |
| Scope/tài nguyên | Chủ thể có quyền thực hiện hành động trên tài nguyên hiện tại không? |

Chữ ký hợp lệ không tự cấp quyền. Token mã hóa thành công không chứng minh issuer. Claims đúng định dạng cũng không đủ nếu audience, thời hạn hoặc quyền không phù hợp.

## 8. Mã giả: xác minh đúng hợp đồng, không bỏ lớp

Mã giả dưới đây chỉ chấp nhận một profile cụ thể: `JWE(JWS(claims))`. Profile `JWS(JWE(claims))` cần một hợp đồng riêng với thứ tự thao tác tương ứng.

~~~text
function validate_signed_then_encrypted(token, policy):
    require_raw_token_size_within_limit(token, policy.max_token_bytes)

    # Endpoint này chỉ chấp nhận JWE Compact ở lớp ngoài.
    outer = parse_expected_jwe_compact(token)
    require_allowed_jwe_alg(outer.header.alg, policy.outer_jwe_alg)
    require_allowed_jwe_enc(outer.header.enc, policy.outer_jwe_enc)
    # Header chưa được xác thực: chỉ dùng cty để kiểm tra profile cố định,
    # chưa dùng nó để xử lý hoặc tin nội dung bên trong.
    require_equal(outer.header.cty, "JWT")

    recipient_key = resolve_recipient_key(
        expected_recipient = policy.recipient,
        kid = outer.header.kid,
        allowed_alg = policy.outer_jwe_alg
    )

    # Không sử dụng plaintext trước khi xác thực JWE hoàn tất.
    inner_jws_bytes = decrypt_and_authenticate_jwe(outer, recipient_key)
    require_size_within_limit(inner_jws_bytes, policy.inner_token_bytes)

    # cty đã xác thực cho biết nội dung phải là JWT; profile yêu cầu JWS.
    inner_jws = parse_expected_jws_compact(inner_jws_bytes)
    # Header JWS trong vẫn chưa đáng tin cho đến khi chữ ký được xác minh.
    require_allowed_jws_alg(inner_jws.header.alg, policy.inner_jws_alg)
    require_expected_type_if_configured(inner_jws.header.typ, policy.inner_typ)

    signing_key = resolve_trusted_issuer_key(
        expected_issuer = policy.issuer,
        kid = inner_jws.header.kid,
        allowed_alg = policy.inner_jws_alg
    )

    claims = verify_jws_and_parse_claims(inner_jws, signing_key)

    require_equal(claims.iss, policy.issuer)
    require_expected_audience(claims.aud, policy.audience)
    require_valid_time_window(claims.iat, claims.nbf, claims.exp)
    require_expected_subject(claims.sub, policy.subject_rules)
    require_authorized_scope_and_resource(claims, policy.request)

    return claims
~~~

Đây là mã giả mô tả hợp đồng, không phải API của thư viện cụ thể. Profile khác phải có quy trình riêng. Ví dụ, với `JWS(JWE(claims))`, xác minh JWS ngoài trước rồi mới giải mã JWE trong.

## 9. Ma trận kiểm thử chống bỏ lớp và nhầm nội dung

| Trường hợp | Kết quả mong đợi |
|---|---|
| JWE ngoài hợp lệ, JWS trong hợp lệ, claims đúng profile. | Chấp nhận theo quyền được cấp. |
| JWE ngoài hợp lệ nhưng plaintext là JSON claims thay vì JWS theo hợp đồng. | Từ chối. |
| JWE ngoài giải mã được nhưng JWS trong có chữ ký sai. | Từ chối. |
| JWE authentication tag sai. | Từ chối; không sử dụng plaintext. |
| JWS ngoài hợp lệ nhưng payload không phải JWE theo hợp đồng. | Từ chối. |
| JWS ngoài sai chữ ký nhưng payload là JWE hợp lệ. | Từ chối; không giải mã payload. |
| JWS ngoài hợp lệ do gateway ký nhưng gateway không được ủy quyền cho issuer trong claims. | Từ chối theo quan hệ signer–issuer. |
| Thiếu `cty: JWT` ở lớp bao bọc theo profile Nested JWT. | Từ chối. |
| Có `cty: JWT` nhưng message bên trong không parse được thành JWT đúng serialization. | Từ chối. |
| `typ` của JWT trong cùng không đúng profile. | Từ chối. |
| Token đơn lẻ gửi đến endpoint chỉ nhận Nested JWT. | Từ chối; không fallback. |
| Thứ tự nesting bị đảo. | Từ chối. |
| Thuật toán hoặc khóa của một lớp ngoài allowlist. | Từ chối tại lớp đó. |
| Chữ ký và mã hóa hợp lệ nhưng audience sai hoặc token hết hạn. | Từ chối ở bước claims. |
| Một lớp lồng bổ sung ngoài hợp đồng. | Từ chối. |

## 10. Cách xử lý lỗi và ghi log

Lỗi ở một lớp cần làm toàn bộ token thất bại. Tuy nhiên, phản hồi ra bên ngoài không nên tiết lộ chi tiết có thể giúp kẻ tấn công phân biệt khóa, chữ ký hoặc trạng thái giải mã.

Thực hành phù hợp:

- Trả lỗi xác thực chung theo giao thức và chính sách API.
- Ghi nhận loại lớp thất bại, mã lỗi nội bộ, correlation ID và thời điểm.
- Không ghi nguyên bearer token, khóa, CEK hoặc plaintext nhạy cảm.
- Giới hạn quyền truy cập log và thời gian lưu trữ.
- Có metric để phân biệt lỗi định dạng, lỗi chữ ký, lỗi giải mã, lỗi claims và lỗi authorization mà không tiết lộ bí mật cho client.
- Không tự động thử fallback hoặc cấu trúc khác khi gặp lỗi.

Không nên che giấu mọi lỗi trong hệ thống quan sát nội bộ. Cần đủ thông tin để điều tra nhưng không làm lộ dữ liệu mật mã hoặc token có thể sử dụng lại.

## 11. Checklist thiết kế

- [ ] Endpoint đã xác định chính xác cấu trúc Nested JWT được chấp nhận.
- [ ] Thứ tự JWS/JWE được cố định và không tự suy đoán.
- [ ] Mỗi lớp có allowlist thuật toán và khóa đúng mục đích.
- [ ] `cty: "JWT"` được yêu cầu ở lớp bao bọc JWT khác.
- [ ] `typ` của JWT trong cùng được kiểm tra nếu profile sử dụng explicit typing.
- [ ] Mọi chữ ký JWS đều được xác minh.
- [ ] Mọi JWE đều được giải mã và xác thực tag hoàn chỉnh.
- [ ] Không sử dụng payload/plaintext trước khi lớp tương ứng được xác thực.
- [ ] Không tin signer ngoài là issuer nếu không có ràng buộc/ủy quyền.
- [ ] Không fallback sang JWS/JWE đơn lẻ hoặc thứ tự nesting khác.
- [ ] Claims chỉ được kiểm tra sau khi toàn bộ lớp bắt buộc hợp lệ.
- [ ] Issuer, audience, thời hạn, token type và quyền được xác minh.
- [ ] Log không lưu nguyên token hoặc plaintext nhạy cảm.

## 12. Câu hỏi tự kiểm tra

1. Vì sao giải mã JWE thành công không đủ để chấp nhận `JWE(JWS(claims))`?
2. Trong `JWS(JWE(claims))`, chữ ký ngoài chứng minh điều gì và không chứng minh điều gì?
3. Vì sao phải xác minh authentication tag JWE trước khi sử dụng plaintext?
4. `cty: "JWT"` cho biết điều gì? Nó có chứng minh JWT bên trong hợp lệ không?
5. `typ` khác `cty` như thế nào?
6. Layer stripping và downgrade có thể xảy ra trong những trường hợp nào?
7. Vì sao endpoint không nên tự động fallback sang JWS/JWE đơn lẻ?
8. Khi signer là gateway khác issuer, cần kiểm tra thêm quan hệ nào?
9. Tại sao RFC 8725 yêu cầu xác minh mọi thao tác mật mã trong Nested JWT?
10. Vì sao phải kiểm tra claims và authorization sau khi các lớp mật mã đều thành công?

## 13. Tài liệu tham khảo

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): Nested JWT, `cty`, cách tạo và xác minh các lớp lồng nhau (§5.2, §7.1–7.2).
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JWS Compact Serialization, protected header, payload và xác minh chữ ký.
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): JWE Compact Serialization, giải mã và xác thực nội dung.
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): thuật toán ký, quản lý khóa và mã hóa nội dung.
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): tránh nhầm lẫn JWT (§2.3), xác minh mọi thao tác mật mã (§3.3), explicit typing (§3.11) và quy tắc xác minh loại trừ lẫn nhau (§3.12).

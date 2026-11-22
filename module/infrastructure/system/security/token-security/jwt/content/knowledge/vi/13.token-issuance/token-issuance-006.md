# Chọn khóa ký và gắn kid theo quy tắc quản lý khóa

> **Module:** `SECURITY_TOKEN_SECURITY_JWT` — **Security - JSON Web Token (JWT)**. **Chương:** Cấp phát token. Nội dung áp dụng cho hệ thống JWT nói chung, không phụ thuộc ngôn ngữ lập trình, thư viện hoặc framework.

## 1. Vì sao việc chọn khóa ký quan trọng?

JWT thường được truyền giữa nhiều thành phần: issuer tạo token, client chuyển token và resource server xác minh token. Với JWT ký theo JWS, chữ ký bảo vệ tính toàn vẹn và giúp bên nhận xác minh rằng token được ký bằng khóa tương ứng. Vì vậy, độ tin cậy của JWT phụ thuộc trực tiếp vào **khóa ký, thuật toán ký và cách bên nhận chọn khóa xác minh**.

Nếu issuer ký bằng khóa không đúng, khóa bị lộ hoặc bên nhận chọn nhầm khóa, các claim như `iss`, `sub`, `aud`, `exp` và `scope` có thể bị tin sai. Một chữ ký được kiểm tra thành công chỉ có ý nghĩa khi khóa xác minh được liên kết với issuer tin cậy và thuật toán được phép.

Trong JOSE, `kid` (Key ID) là tham số ở **protected header** giúp bên nhận xác định khóa nào trong tập khóa tin cậy có thể được dùng để xác minh chữ ký. `kid` là một gợi ý chọn khóa, **không phải bằng chứng về độ tin cậy của khóa** và không phải registered claim trong payload.

Cần tách bốn quyết định:

1. **Thuật toán:** loại thuật toán chữ ký nào được profile và các bên tham gia cho phép?
2. **Khóa ký:** khóa cụ thể nào thuộc issuer và còn được phép sử dụng?
3. **Định danh khóa (`kid`):** bên nhận tra cứu khóa tương ứng bằng cách nào?
4. **Vòng đời khóa:** tạo, phân phối, kích hoạt, luân chuyển, ngừng dùng, thu hồi và hủy khóa theo quy trình nào?

## 2. Chọn mô hình khóa phù hợp

Có hai nhóm thuật toán chữ ký phổ biến cho JWS: thuật toán dùng khóa bí mật chung (symmetric) và thuật toán dùng cặp khóa (asymmetric).

| Mô hình | Cách hoạt động | Ưu điểm | Rủi ro / giới hạn |
| --- | --- | --- | --- |
| Symmetric (ví dụ HS256) | Issuer và mọi bên xác minh dùng cùng một secret | Hiệu năng tốt, quản lý đơn giản khi có ít thành phần | Bất kỳ bên xác minh nào có secret đều có khả năng tạo chữ ký; khó giới hạn quyền chỉ xác minh |
| Asymmetric (ví dụ RS256, PS256, ES256, EdDSA) | Issuer ký bằng private key; bên nhận xác minh bằng public key | Có thể phân phối public key rộng hơn mà không trao quyền ký | Cần quản lý cặp khóa, metadata, rotation và phân phối public key đúng cách |

### 2.1. Khi nào dùng khóa đối xứng?

Với HS256, cùng một secret được dùng để tạo và xác minh HMAC. Mọi thành phần giữ secret đều có khả năng tạo token hợp lệ. Mô hình này có thể phù hợp khi issuer và verifier nằm trong một miền tin cậy nhỏ, quản lý secret tập trung và không cần phân tách quyền ký với quyền xác minh.

Khi nhiều API hoặc tổ chức độc lập cần xác minh token, việc chia sẻ cùng secret làm mở rộng phạm vi ảnh hưởng: một verifier bị xâm nhập có thể tạo JWT mà các verifier khác chấp nhận. Không dùng secret yếu, mật khẩu, chuỗi dễ nhớ hoặc giá trị cấu hình mặc định làm khóa HMAC. Secret phải có entropy đủ lớn, được lưu và luân chuyển như một khóa mật mã.

### 2.2. Khi nào dùng khóa bất đối xứng?

Với RS256, PS256, ES256 hoặc EdDSA, issuer giữ private key để ký; các resource server chỉ cần public key để xác minh. Mô hình này thường phù hợp khi có nhiều verifier hoặc cần tách biệt rõ quyền phát hành và quyền xác minh.

- Private key phải nằm trong miền kiểm soát của issuer và được bảo vệ chặt chẽ.
- Public key có thể phân phối qua JWKS hoặc kênh quản trị tin cậy.
- Verifier không được có khả năng suy ra private key từ public key.
- Nếu một verifier bị xâm nhập, kẻ tấn công không thể chỉ dùng public key để tạo chữ ký hợp lệ.

### 2.3. Chọn thuật toán từ profile và chính sách

Thuật toán phải được thống nhất giữa issuer và verifier theo profile token. Ví dụ:

| Thuật toán JWS | Họ mật mã | Lưu ý |
| --- | --- | --- |
| HS256 | HMAC với SHA-256 | Dùng secret chung đủ mạnh; mọi verifier giữ secret đều có quyền ký |
| RS256 | RSA PKCS#1 v1.5 với SHA-256 | Tương thích rộng; cần kích thước khóa và chính sách RSA phù hợp |
| PS256 | RSA-PSS với SHA-256 | Dùng padding PSS; phải bảo đảm các bên hỗ trợ cùng profile |
| ES256 | ECDSA trên P-256 với SHA-256 | Chữ ký JOSE có định dạng cố định; kiểm tra hỗ trợ và quy tắc mã hóa |
| EdDSA | Họ EdDSA, thường là Ed25519 theo cấu hình phù hợp | Thiết kế hiện đại; cần kiểm tra mức hỗ trợ của thư viện và profile |

Không có thuật toán duy nhất phù hợp mọi hệ thống. Lựa chọn cần dựa trên tiêu chuẩn hiện hành, mức hỗ trợ của hệ sinh thái, yêu cầu tương tác, hiệu năng và chính sách mật mã của tổ chức.

**Không cho request hoặc JOSE header tự quyết định thuật toán.** Issuer cấu hình allowlist thuật toán và liên kết thuật toán với loại khóa được phép. Verifier cũng có allowlist riêng; không chấp nhận thuật toán chỉ vì token tự khai trong trường `alg`.

Không dùng `none` cho token cần xác thực chữ ký. Không tự hạ cấp sang thuật toán khác khi xác minh thất bại. Không cho phép chuyển đổi tùy tiện giữa thuật toán đối xứng và bất đối xứng, vì cách diễn giải cùng dữ liệu khóa có thể dẫn tới algorithm confusion.

## 3. Chọn và bảo vệ khóa ký

### 3.1. Private key phải thuộc quyền kiểm soát của issuer

Khóa ký là tài sản bảo mật có giá trị cao. Người hoặc dịch vụ có quyền dùng private key có thể tạo JWT mang bất kỳ claim nào trong phạm vi mà verifier chấp nhận. Vì vậy, chỉ cấp quyền sử dụng khóa cho thành phần phát hành token được phép.

Các nguyên tắc bảo vệ:

- Ưu tiên kho khóa chuyên dụng, HSM hoặc dịch vụ quản lý khóa (KMS) khi mức rủi ro và hạ tầng cho phép.
- Giới hạn quyền ký theo service identity, môi trường, issuer và mục đích; verifier chỉ nhận public key nếu dùng mô hình bất đối xứng.
- Không nhúng private key hoặc secret vào mã nguồn, image container, file cấu hình công khai, log, repository hay client application.
- Bảo vệ backup, bản sao dự phòng và quy trình khôi phục; bản backup khóa phải có kiểm soát truy cập và audit tương đương khóa đang hoạt động.
- Dùng phân quyền tối thiểu, xác thực mạnh cho thao tác quản trị và phê duyệt phù hợp cho hành động nhạy cảm.
- Ghi nhận ai/điều gì đã dùng khóa, thời điểm, key identifier và mục đích; không ghi giá trị khóa.
- Phân tách khóa theo môi trường và miền bảo mật. Không dùng khóa production cho thử nghiệm.

### 3.2. Chọn khóa theo thuật toán và mục đích

Một khóa phải tương thích với thuật toán đã chọn và được đánh dấu cho mục đích ký/xác minh phù hợp. Khi dùng JWK, các trường như `kty`, `use`, `key_ops`, `alg` và tham số khóa cần nhất quán:

- `kty` xác định loại khóa (RSA, EC, OKP hoặc octet).
- `use` có thể chỉ ra khóa dùng cho chữ ký (`sig`) hoặc mã hóa (`enc`).
- `key_ops` mô tả các thao tác được phép, chẳng hạn `sign` hoặc `verify`.
- `alg` có thể gắn khóa với thuật toán dự kiến khi profile/metadata sử dụng trường này.
- Khóa EC/OKP phải dùng đường cong và tham số đúng với thuật toán.

Các metadata này hỗ trợ kiểm tra tính nhất quán; chúng không thay thế trust configuration. Với JWK đối xứng, trường `k` chứa secret và tuyệt đối không được xuất bản trong JWKS công khai.

### 3.3. Tách khóa ký với khóa mã hóa

Khóa ký JWS và khóa mã hóa JWE phục vụ mục đích khác nhau:

- Khóa ký tạo/xác minh chữ ký, bảo vệ tính toàn vẹn và nguồn phát hành.
- Khóa mã hóa bảo vệ tính bí mật của nội dung JWE.

Không dùng cùng một khóa cho cả hai mục đích nếu không có thiết kế mật mã và chính sách rõ ràng cho phép. Không đưa private key hoặc secret vào payload JWT. Chữ ký không mã hóa nội dung: payload của JWS thông thường có thể đọc được.

## 4. kid là gì và cách gắn kid

`kid` là tham số tùy chọn trong JOSE header, được định nghĩa để chỉ ra khóa tương ứng trong một tập khóa. Nó không nằm trong payload và không phải bí mật.

Ví dụ header đã giải mã của một JWS:

~~~json
{
  "alg": "RS256",
  "kid": "signing-2026-03",
  "typ": "JWT"
}
~~~

Trong đó:

- `alg` khai báo thuật toán ký của JWS.
- `kid` giúp bên nhận chọn khóa public tương ứng trong tập khóa tin cậy.
- `typ` có thể dùng để chỉ loại nội dung/token theo profile và phải được xử lý theo chính sách.

`kid` nên là chuỗi ngắn, ổn định trong vòng đời của khóa, không chứa bí mật, thông tin cá nhân hoặc dữ liệu nội bộ nhạy cảm. Có thể dùng ID ngẫu nhiên hoặc ID phiên bản theo quy tắc quản lý khóa. Tránh dùng giá trị có thể thay đổi trong khi khóa vẫn giữ nguyên, vì điều đó làm phức tạp cache và vận hành.

### 4.1. Quy tắc đặt kid

Một quy tắc thực tế:

1. Mỗi khóa ký có một `kid` riêng trong phạm vi issuer/key set.
2. Không tái sử dụng `kid` cho khóa khác khi token cũ còn có thể được xác minh hoặc metadata cũ còn được cache.
3. Khi thay khóa, tạo `kid` mới; không đổi nội dung khóa nhưng giữ nguyên `kid` nếu điều đó làm bên nhận không thể phân biệt hai phiên bản.
4. Quy định charset và độ dài rõ ràng; không cho phép `kid` chứa ký tự điều khiển hoặc chuỗi có thể gây injection.
5. `kid` không được dùng trực tiếp như tên file, câu truy vấn, URL hoặc đường dẫn không được kiểm soát.
6. Gắn `kid` vào protected header trước khi ký để header được bảo vệ bởi chữ ký.

Không có yêu cầu rằng `kid` phải là UUID hay phải chứa timestamp. Điều quan trọng là nó định danh ổn định một khóa trong tập khóa đã tin cậy và không gây nhầm lẫn trong thời gian chuyển tiếp.

### 4.2. kid không tạo ra trust

Header JOSE được đọc trước khi chữ ký được xác minh để chọn khóa ứng viên. Vì vậy, toàn bộ header ban đầu là dữ liệu **chưa đáng tin**. Verifier chỉ được dùng `kid` như một chỉ mục tra cứu trong key set đã được cấu hình tin cậy cho issuer tương ứng.

Không làm các việc sau:

- Không lấy `kid` làm URL để tải khóa.
- Không nối `kid` vào đường dẫn file hoặc câu truy vấn tùy ý.
- Không tin trường `jku` hoặc `x5u` từ token để tải JWKS/chứng thư tùy tiện.
- Không chấp nhận một khóa chỉ vì `kid` trùng; vẫn phải kiểm tra loại khóa, thuật toán, issuer, mục đích và chữ ký.
- Không để token tự chọn issuer hoặc nguồn JWKS tùy ý.

## 5. Công bố và phân phối public key qua JWKS

Với mô hình bất đối xứng, issuer có thể công bố các public key đang và sắp được sử dụng trong JSON Web Key Set (JWKS). JWKS là đối tượng JSON chứa mảng `keys` gồm các JWK. Verifier lấy JWKS từ endpoint được cấu hình theo issuer hoặc từ kênh tin cậy khác.

Một JWK RSA public minh họa:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "kid": "signing-2026-03",
  "n": "base64url-modulus",
  "e": "AQAB"
}
~~~

Các giá trị `n` và `e` trong ví dụ chỉ là placeholder, không phải khóa sử dụng thực tế.

JWKS công khai chỉ chứa thành phần public của khóa bất đối xứng. Không bao giờ xuất bản private exponent hoặc tham số bí mật. Với khóa đối xứng, không công bố JWK chứa trường `k` trên endpoint công khai.

### 5.1. Ràng buộc JWKS với issuer

Verifier phải biết trước issuer nào được chấp nhận và JWKS endpoint nào thuộc issuer đó. Trong hệ thống dùng OpenID Connect/OAuth, metadata discovery có thể công bố `jwks_uri`; verifier chỉ sử dụng metadata được lấy qua quy trình trust đã cấu hình, có xác minh TLS và kiểm tra issuer.

Không suy ra URL JWKS bằng cách nối chuỗi từ `iss` không đáng tin hoặc tải endpoint do token tự khai. Trường `jku` trong header không được quyền thay thế cấu hình trust của verifier.

### 5.2. Cache và cập nhật JWKS

JWKS thường được cache để giảm tải và độ trễ. Cache cần tuân theo HTTP cache metadata hoặc chính sách nội bộ, đồng thời hỗ trợ luân chuyển khóa:

- Lưu cache theo issuer và endpoint tin cậy, không gộp key set của các issuer khác nhau.
- Khi gặp `kid` chưa biết, có thể refresh JWKS một lần theo chính sách; giới hạn tần suất để chống request flood.
- Nếu refresh không thành công và không có khóa phù hợp đã cache, từ chối token; không thử khóa của issuer khác.
- Khi JWKS có nhiều khóa, chọn đúng khóa theo `kid` và kiểm tra metadata phù hợp.
- Không chấp nhận nhiều khóa khác nhau cùng `kid` trong một key set nếu điều đó tạo lựa chọn mơ hồ.
- Theo dõi thời điểm cache cập nhật, lỗi tải metadata và trường hợp unknown kid bất thường.

## 6. Chọn khóa xác minh an toàn

Quy trình xác minh phải bắt đầu từ chính sách tin cậy đã cấu hình:

1. Xác định loại token/profile mà resource server chấp nhận.
2. Đọc header/payload ở trạng thái chưa tin chỉ để lấy dữ liệu định tuyến hạn chế; không sử dụng claim để cấp quyền trước khi xác minh.
3. Chọn issuer ứng viên trong danh sách issuer đã đăng ký.
4. Lấy key set tin cậy gắn với issuer đó.
5. Dùng `kid` để tìm khóa ứng viên; nếu không có, refresh JWKS theo giới hạn.
6. Kiểm tra khóa phù hợp với thuật toán allowlist, loại khóa, mục đích và profile.
7. Xác minh chữ ký.
8. Sau khi chữ ký hợp lệ, kiểm tra `iss`, `aud`, thời gian, token type và các claim bắt buộc.
9. Chỉ sau tất cả bước trên mới dùng claim để đưa ra quyết định authorization.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Nhận JWS"] --> B["Đọc header chưa tin cậy"]
    B --> C["Chọn issuer từ trust configuration"]
    C --> D["Lấy JWKS tin cậy của issuer"]
    D --> E["Tra khóa ứng viên bằng kid"]
    E --> F{"Có đúng một khóa phù hợp?"}
    F -- "Không" --> X["Từ chối hoặc refresh JWKS có giới hạn"]
    F -- "Có" --> G["Kiểm tra alg, kty, use, key_ops"]
    G --> H["Xác minh chữ ký"]
    H --> I{"Chữ ký hợp lệ?"}
    I -- "Không" --> X
    I -- "Có" --> J["Kiểm tra iss, aud, exp, typ và profile"]
    J --> K{"Claims hợp lệ?"}
    K -- "Không" --> X
    K -- "Có" --> L["Tiếp tục authorization"]
~~~

**Không thử lần lượt mọi thuật toán hoặc mọi khóa đến khi một chữ ký khớp.** Cách làm đó dễ tạo đường đi vào algorithm confusion và làm tăng chi phí xử lý. Phải xác định thuật toán được phép trước, rồi chọn khóa phù hợp với thuật toán đó.

## 7. Luân chuyển khóa ký (key rotation)

Khóa ký cần được luân chuyển định kỳ theo chính sách hoặc khi có sự kiện bảo mật. Rotation đúng cách phải bảo đảm issuer bắt đầu ký bằng khóa mới, trong khi verifier vẫn có thể xác minh token cũ còn hiệu lực.

Một quy trình thông dụng:

1. **Generate:** tạo cặp khóa mới trong KMS/HSM hoặc môi trường bảo mật.
2. **Register:** gán `kid` mới và đăng ký public key trong JWKS/metadata.
3. **Pre-publish:** công bố public key mới trước khi dùng để ký, cho verifier thời gian cập nhật cache.
4. **Activate:** chuyển issuer sang ký bằng private key mới; header mang `kid` mới.
5. **Overlap:** giữ public key cũ trong JWKS trong thời gian token được ký bằng khóa cũ còn có thể hợp lệ.
6. **Retire:** ngừng công bố/không còn dùng khóa cũ sau khi hết thời gian chấp nhận token cũ và các cache đã được xử lý theo chính sách.
7. **Archive or destroy:** lưu trữ hoặc hủy khóa theo quy định, mục đích kiểm toán và khả năng khôi phục.

Thời gian overlap phải xét đến **TTL tối đa của token, clock skew, độ trễ phân phối JWKS và thời gian cache của verifier**. Nếu bỏ public key cũ quá sớm, token hợp lệ đã phát hành có thể bị từ chối. Nếu giữ khóa cũ quá lâu mà vẫn cho phép sử dụng, phạm vi rủi ro khi khóa cũ bị lộ tăng lên.

### 7.1. Dòng thời gian rotation minh họa

~~~text
T0            T1               T2                   T3
|-------------|----------------|--------------------|
Publish K2    Start signing    Old K1 tokens        Retire K1
in JWKS       with K2          still accepted       after expiry/cache
              kid=K2           using public K1      transition
K1 + K2       K1 + K2          K1 + K2              K2 only
~~~

Đây là mô hình minh họa. T0 cần đủ sớm để verifier cập nhật; T3 chỉ thực hiện khi mọi token được ký bằng K1 đã hết khả năng được chấp nhận theo chính sách.

### 7.2. Xử lý khóa cũ

Sau khi issuer ngừng ký bằng khóa cũ, verifier vẫn cần public key cũ để xác minh token đã phát hành trước đó. Không nhầm việc **ngừng ký** với **xóa ngay khóa xác minh**.

Khóa cũ có thể được giữ ở trạng thái verify-only trong giai đoạn overlap. Private key cũ nên bị vô hiệu hóa quyền ký sau khi chuyển đổi, đồng thời được lưu trữ/hủy theo quy trình quản lý khóa. Nếu khóa đã bị xâm phạm, quy trình khẩn cấp có thể phải loại bỏ ngay public key khỏi trust set và chấp nhận ảnh hưởng tới token hợp lệ.

## 8. Sự cố khóa bị lộ hoặc nghi bị xâm phạm

Nếu private key ký JWT bị lộ, kẻ tấn công có thể tự tạo token với claim giả mạo mà verifier vẫn chấp nhận cho đến khi khóa bị loại khỏi trust set hoặc có biện pháp chặn khác. Đây là sự cố nghiêm trọng hơn việc một token đơn lẻ bị lộ.

Quy trình ứng phó cần có:

1. **Containment:** ngừng sử dụng khóa bị nghi ngờ; khóa quyền ký hoặc cô lập dịch vụ/thiết bị bị ảnh hưởng.
2. **Replacement:** tạo khóa mới trong miền bảo mật, gán `kid` mới và cập nhật JWKS/metadata.
3. **Trust update:** phân phối public key mới và loại bỏ khóa bị xâm phạm khỏi tập khóa được tin cậy theo mức khẩn cấp.
4. **Token response:** đánh giá việc từ chối token đã ký bằng khóa bị lộ; không chỉ thu hồi một vài `jti` vì kẻ tấn công có thể tạo token mới tùy ý.
5. **Investigation:** xác định thời điểm lộ, phạm vi issuer, token/audience/scope có thể bị giả mạo và dấu hiệu sử dụng trái phép.
6. **Recovery:** khôi phục dịch vụ với khóa mới, xác minh các verifier đã cập nhật và theo dõi lỗi xác minh.
7. **Audit:** lưu lại quyết định, thời gian, key ID, người/phần mềm thực hiện và kết quả xử lý; không ghi private key.

Nếu một key set được nhiều issuer hoặc hệ thống dùng chung, phạm vi ứng phó có thể rộng hơn. Cần thiết kế phân tách khóa theo issuer, môi trường và mục đích để giới hạn blast radius.

## 9. Mã giả lựa chọn khóa và ký JWT

~~~text
function issueJwt(claims, issuerPolicy):
    algorithm = issuerPolicy.allowedSigningAlgorithm
    signingKey = trustedKeyStore.getActiveSigningKey(
        issuer = issuerPolicy.issuer,
        algorithm = algorithm
    )

    require signingKey.isActive
    require signingKey.permits("sign")
    require signingKey.algorithm == algorithm

    header = {
        "alg": algorithm,
        "kid": signingKey.keyId,
        "typ": issuerPolicy.tokenType
    }

    issuerPolicy.validateClaims(claims)
    return jws.sign(header, claims, signingKey.privateMaterial)
~~~

Issuer phải lấy thuật toán và khóa từ cấu hình tin cậy. Private material chỉ được truy cập qua cơ chế bảo vệ khóa; nếu KMS/HSM cung cấp thao tác ký từ xa, ứng dụng không cần xuất private key ra bộ nhớ của mình.

Mã giả xác minh:

~~~text
function verifyJwt(compactJws, verifierPolicy):
    untrustedHeader = parseProtectedHeader(compactJws)

    require untrustedHeader.alg in verifierPolicy.allowedAlgorithms
    issuer = verifierPolicy.resolveTrustedIssuerCandidate(compactJws)
    require issuer exists

    keySet = trustedJwksCache.get(issuer)
    key = keySet.findUniqueKey(untrustedHeader.kid)

    if key is absent:
        keySet = refreshTrustedJwksWithRateLimit(issuer)
        key = keySet.findUniqueKey(untrustedHeader.kid)

    require key exists
    require key.permitsVerificationFor(untrustedHeader.alg)

    verified = jws.verify(compactJws, key, verifierPolicy.allowedAlgorithms)
    require verified.signatureValid
    require verified.claims.iss == issuer.identifier
    require verifierPolicy.acceptsAudience(verified.claims.aud)
    require verifierPolicy.acceptsTokenType(verified.header.typ)

    return verified.claims
~~~

Đây là pseudocode mô tả các ranh giới tin cậy, không phải API cụ thể. Trong thực tế, cần dùng thư viện JOSE/JWT được kiểm chứng để xử lý serialization, chữ ký, kiểm tra thuật toán và các chi tiết định dạng. Việc phân tích token trước xác minh chỉ phục vụ chọn cấu hình/khóa ứng viên có giới hạn; không được dùng claim chưa xác minh để cấp quyền.

## 10. Các lỗi thường gặp và cách phòng ngừa

| Lỗi | Hậu quả | Cách phòng ngừa |
| --- | --- | --- |
| Dùng cùng secret HMAC cho nhiều verifier độc lập | Mỗi verifier có thể tạo token giả | Cân nhắc chữ ký bất đối xứng để tách quyền ký và xác minh |
| Để client quyết định `alg` | Algorithm confusion hoặc downgrade | Allowlist thuật toán ở issuer và verifier |
| Chọn khóa chỉ dựa trên `kid` mà không kiểm tra issuer | Nhầm khóa giữa các miền tin cậy | Tra trong key set gắn với issuer đã cấu hình |
| Tải `jku`/`x5u` tùy ý từ header | SSRF, tải khóa không tin cậy | Chỉ dùng endpoint JWKS đã cấu hình hoặc metadata tin cậy |
| Tái sử dụng `kid` cho khóa mới quá sớm | Cache có thể ánh xạ tới khóa cũ | Gán ID mới và có overlap rõ ràng |
| Xóa public key cũ ngay khi bắt đầu rotation | Token cũ hợp lệ bị từ chối | Giữ verify-only đến khi hết thời gian chấp nhận |
| Giữ khóa bị lộ trong trust set | Token giả mạo tiếp tục được chấp nhận | Thu hồi khóa khẩn cấp, rotate và điều tra |
| Công bố private key trong JWKS | Mất hoàn toàn khả năng bảo vệ chữ ký | Chỉ công bố public parameters |
| Dùng khóa ký cho mục đích mã hóa | Vi phạm phân tách mục đích | Quản lý key purpose riêng |
| Không giới hạn refresh JWKS khi gặp unknown kid | Bị lợi dụng gây request flood | Rate limit, cache và giới hạn refresh theo issuer |

## 11. Checklist quản lý khóa ký

**Trước khi phát hành:**

- [ ] Loại token/profile và thuật toán ký đã được xác định.
- [ ] Thuật toán nằm trong allowlist và tương thích với loại khóa.
- [ ] Khóa thuộc issuer và môi trường đúng; trạng thái đang active.
- [ ] Private key được bảo vệ bằng KMS/HSM hoặc cơ chế tương đương phù hợp rủi ro.
- [ ] Quyền ký chỉ cấp cho thành phần phát hành token.
- [ ] `kid` duy nhất trong phạm vi key set và được gắn vào protected header.
- [ ] Claim được kiểm tra theo profile trước khi ký.

**Đối với verifier:**

- [ ] Chỉ tin issuer và JWKS endpoint đã cấu hình.
- [ ] `kid` chỉ dùng để tìm khóa trong key set tin cậy.
- [ ] Kiểm tra `alg`, loại khóa, mục đích và chữ ký.
- [ ] Không tải khóa từ URL tùy ý trong header.
- [ ] Unknown `kid` được xử lý với refresh có giới hạn; không có khóa phù hợp thì từ chối.
- [ ] Xác minh claim issuer, audience, thời gian và token type sau chữ ký.

**Vòng đời khóa:**

- [ ] Có quy trình generate, register, pre-publish, activate, overlap và retire.
- [ ] Thời gian overlap bao phủ TTL tối đa, clock skew và cache propagation.
- [ ] Có quy trình ứng phó khi khóa bị lộ.
- [ ] Có audit, giám sát và kiểm tra quyền truy cập kho khóa.
- [ ] Có kế hoạch backup/restore hoặc hủy khóa an toàn.

## 12. Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, chữ ký JWS và tham số `kid`.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): mô hình khóa JSON, `kid`, `use`, `key_ops` và JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán chữ ký và mã hóa JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và cách JWT sử dụng JWS/JWE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm tra thuật toán, khóa, issuer, audience và phòng chống JWT confusion.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): cấu trúc JWE và sự khác biệt giữa mã hóa với ký.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): hướng dẫn vòng đời, bảo vệ và quản lý khóa mật mã.

**Ghi nhớ:** Issuer phải ký bằng khóa thuộc quyền kiểm soát và đúng mục đích; verifier phải xác minh bằng khóa lấy từ miền tin cậy đã cấu hình. `kid` giúp chọn khóa trong tập khóa đó, không tạo ra trust và không thay thế xác minh chữ ký. Rotation, overlap, thu hồi và ứng phó sự cố phải được thiết kế thành quy trình quản lý khóa xuyên suốt vòng đời token.


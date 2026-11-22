# at_hash và c_hash khi luồng giao thức yêu cầu

## 1. Mục đích của at_hash và c_hash

OpenID Connect (OIDC) sử dụng ID Token để truyền thông tin về sự kiện xác thực và chủ thể tới client. Trong một số luồng, Authorization Server trả ID Token cùng với Access Token hoặc Authorization Code ngay tại Authorization Endpoint. Khi các giá trị này đi qua cùng một phản hồi, client cần có cách kiểm tra rằng chúng thực sự thuộc cùng một giao dịch xác thực.

OIDC định nghĩa hai claim trong ID Token cho mục đích đó:

- **at_hash (Access Token hash):** ràng buộc ID Token với giá trị Access Token được trả cùng phản hồi.
- **c_hash (Code hash):** ràng buộc ID Token với giá trị Authorization Code được trả cùng phản hồi.

Hai claim này giúp client phát hiện tình huống một artifact bị thay thế bằng artifact lấy từ một giao dịch khác. Ví dụ, kẻ tấn công có thể cố ghép ID Token hợp lệ của người dùng A với Access Token của người dùng B, hoặc thay Authorization Code trong phản hồi. Nếu hash claim không khớp với giá trị thực tế nhận được, client phát hiện sự không nhất quán.

**at_hash và c_hash không phải là chữ ký của Access Token hay Authorization Code.** Chúng là các giá trị hash nằm trong ID Token đã được ký, qua đó ràng buộc artifact tương ứng với ID Token. Chúng cũng không thay thế việc xác minh chữ ký ID Token, kiểm tra issuer/audience/nonce, PKCE, state hoặc việc sử dụng Authorization Code đúng quy trình.

Nội dung này thuộc module Security - JSON Web Token (JWT), chương OAuth và OIDC. Các quy tắc áp dụng ở mức giao thức, không phụ thuộc Java, Spring Security hay một thư viện cụ thể.

## 2. Phân biệt hai claim

| Claim | Artifact được ràng buộc | Giá trị đầu vào để tính hash | Mục tiêu |
| --- | --- | --- | --- |
| **at_hash** | Access Token | Giá trị ASCII của Access Token | Phát hiện Access Token bị thay thế so với ID Token |
| **c_hash** | Authorization Code | Giá trị ASCII của Authorization Code | Phát hiện Authorization Code bị thay thế so với ID Token |

Cả hai claim được đặt trong **ID Token**, không phải trong Access Token. Client OIDC kiểm tra chúng khi xử lý phản hồi tương ứng.

Một số điểm cần nhớ:

- at_hash ràng buộc đúng giá trị Access Token được trả trong cùng phản hồi với ID Token đang kiểm tra.
- c_hash ràng buộc đúng Authorization Code được trả trong cùng phản hồi với ID Token đang kiểm tra.
- Không dùng Access Token hoặc Code từ một phiên, một lần refresh hay một phản hồi khác để kiểm tra.
- Không lấy hash của payload JWT, signature, JWT header hoặc chuỗi JSON phản hồi.
- Không dùng các claim này để xác định người dùng hoặc cấp quyền API.

## 3. Công thức tính at_hash và c_hash

OIDC Core định nghĩa cách tính giống nhau về cấu trúc cho cả hai claim. Khác biệt nằm ở giá trị đầu vào:

~~~text
digest = HASH(ASCII(artifact_value))
left_half = leftmost_half(digest)
hash_claim = BASE64URL(left_half)
~~~

Trong đó:

- Với at_hash, artifact_value là giá trị Access Token.
- Với c_hash, artifact_value là giá trị Authorization Code.
- HASH là hàm hash tương ứng với thuật toán JWS dùng để ký ID Token, theo ánh xạ thuật toán của JWA.
- Chỉ lấy **nửa bên trái** của digest, tính theo bit.
- BASE64URL là Base64 URL-safe theo JOSE, không có padding dấu bằng.

Ví dụ, nếu ID Token được ký bằng RS256, hàm hash là SHA-256. SHA-256 tạo digest 256 bit; lấy 128 bit đầu tiên rồi Base64URL-encode để tạo at_hash hoặc c_hash.

### 3.1. Ánh xạ thuật toán và độ dài kết quả

Một số nhóm thuật toán JWS thường gặp:

| JWS alg của ID Token | Hàm hash | Độ dài digest | Phần lấy bên trái |
| --- | --- | ---: | ---: |
| HS256, RS256, ES256, PS256 | SHA-256 | 256 bit | 128 bit |
| HS384, RS384, ES384, PS384 | SHA-384 | 384 bit | 192 bit |
| HS512, RS512, ES512, PS512 | SHA-512 | 512 bit | 256 bit |

Bảng này minh họa các thuật toán có ánh xạ hash tương ứng được định nghĩa trong JWA. Không tự suy ra hàm hash từ tên thuật toán theo quy tắc phỏng đoán. Với thuật toán chữ ký mở rộng không có ánh xạ tương thích được profile quy định, cần kiểm tra khả năng hỗ trợ và quy tắc liên thông trước khi sử dụng at_hash/c_hash; không lấy một hàm hash nội bộ của thuật toán chữ ký để tự thay thế.

### 3.2. Không dùng thuật toán của Access Token hoặc JWE

Hàm hash được chọn theo **alg của JWS ký ID Token**, không theo:

- Định dạng hoặc thuật toán nội bộ của Access Token.
- Thuật toán mã hóa nội dung của JWE.
- Thuật toán quản lý khóa JWE.
- Hàm hash mà ứng dụng tùy ý cấu hình riêng.

Nếu ID Token được ký rồi mã hóa (nested JWT), phải dùng thuật toán JWS của lớp ký ID Token. Không lấy alg hoặc enc của lớp JWE bên ngoài để tính hash claim.

### 3.3. Hash chính xác giá trị artifact

Phải hash đúng octet của biểu diễn ASCII của Access Token hoặc Authorization Code nhận được:

- Không URL-encode lại giá trị.
- Không thêm hoặc bỏ khoảng trắng.
- Không đổi chữ hoa/thường.
- Không parse Access Token rồi hash payload hoặc claims.
- Không hash chuỗi tên tham số, dấu bằng, dấu phân cách hay toàn bộ URL callback.
- Không giải mã Base64URL bên trong token trước khi hash.

Client cần lấy giá trị tham số sau khi giải mã đúng lớp serialization của phản hồi OAuth, rồi giữ nguyên giá trị artifact để tính hash. Các giá trị hash claim là chuỗi phân biệt chữ hoa/chữ thường.

## 4. Base64URL và so sánh kết quả

Sau khi lấy nửa digest bên trái, client phải mã hóa bằng Base64URL theo quy tắc JOSE:

- Dùng bảng ký tự URL-safe: dấu gạch ngang và gạch dưới thay cho dấu cộng và dấu gạch chéo.
- Bỏ padding dấu bằng ở cuối.
- Không chuyển chuỗi kết quả thành chữ thường hoặc chữ hoa.
- So sánh chính xác chuỗi nhận được trong ID Token với chuỗi tính lại.

Độ dài thường gặp:

| Hàm hash | Số byte lấy từ nửa digest | Độ dài Base64URL không padding |
| --- | ---: | ---: |
| SHA-256 | 16 byte | 22 ký tự |
| SHA-384 | 24 byte | 32 ký tự |
| SHA-512 | 32 byte | 43 ký tự |

Không so sánh bằng cách decode claim thành digest rồi bỏ qua các quy tắc encoding, trừ khi thư viện đã chuẩn hóa và kiểm tra định dạng đúng theo profile. Cách đơn giản là dùng thư viện OIDC/JOSE đã triển khai chính xác thuật toán và so sánh chuỗi theo quy tắc phân biệt hoa/thường.

## 5. Khi nào at_hash và c_hash bắt buộc?

Đây là điểm quan trọng nhất khi triển khai. at_hash và c_hash **không bắt buộc trong mọi ID Token**. OIDC Core quy định yêu cầu dựa trên luồng, response_type và endpoint trả ID Token.

### 5.1. Implicit Flow

Trong Implicit Flow, các token được trả trực tiếp từ Authorization Endpoint.

| response_type | Giá trị được trả | Quy tắc at_hash |
| --- | --- | --- |
| id_token token | ID Token và Access Token | at_hash REQUIRED trong ID Token |
| id_token | Chỉ ID Token | at_hash MAY NOT được sử dụng vì không có Access Token đi kèm |

Implicit Flow không trả Authorization Code, do đó c_hash không được dùng để ràng buộc code trong flow này.

Khi response_type là id_token token, client SHOULD tính lại at_hash từ Access Token trong phản hồi và so khớp với claim trong ID Token. Nếu giá trị không khớp, phản hồi phải bị từ chối.

### 5.2. Hybrid Flow: ID Token từ Authorization Endpoint

Trong Hybrid Flow, Authorization Endpoint luôn trả Authorization Code; tùy response_type, nó có thể trả thêm ID Token và Access Token.

| response_type | Artifact tại Authorization Endpoint | at_hash | c_hash |
| --- | --- | --- | --- |
| code id_token | Code + ID Token | OPTIONAL | REQUIRED |
| code id_token token | Code + ID Token + Access Token | REQUIRED | REQUIRED |
| code token | Code + Access Token, không có ID Token | Không áp dụng tại phản hồi này | Không áp dụng tại phản hồi này |

Với response_type code id_token, ID Token đi cùng Code nên c_hash bắt buộc; không có Access Token ở Authorization Endpoint nên at_hash không bắt buộc.

Với response_type code id_token token, cả Code và Access Token đều đi cùng ID Token, vì vậy cả c_hash và at_hash đều bắt buộc.

Với response_type code token, Authorization Endpoint không trả ID Token nên không có ID Token để chứa hai claim này. Nếu Token Endpoint sau đó trả ID Token, cần áp dụng quy tắc cho ID Token ở Token Endpoint như phần tiếp theo.

### 5.3. Authorization Code Flow: ID Token từ Token Endpoint

Trong Authorization Code Flow, Authorization Endpoint trả Authorization Code; client đổi code tại Token Endpoint và nhận Access Token cùng ID Token qua kết nối TLS.

Theo OIDC Core:

- at_hash trong ID Token từ Token Endpoint là **OPTIONAL**.
- Nếu ID Token có at_hash, client **MAY** dùng nó để kiểm tra Access Token được trả từ Token Endpoint.
- Quy tắc này không yêu cầu c_hash trong ID Token của Authorization Code Flow tại Token Endpoint.

Do phản hồi Token Endpoint được truyền trực tiếp qua TLS, OIDC Core không bắt buộc phải dùng at_hash để ràng buộc hai giá trị trong mọi trường hợp. Nếu triển khai sử dụng at_hash và claim có mặt, hãy tính lại bằng đúng Access Token trong chính Token Response.

### 5.4. Hybrid Flow: ID Token từ Token Endpoint

Hybrid Flow có thể trả một ID Token tại Authorization Endpoint và một ID Token khác tại Token Endpoint. OIDC Core cho phép ID Token từ Token Endpoint **bỏ at_hash và c_hash**, kể cả khi hai claim này có mặt trong ID Token từ Authorization Endpoint.

Lý do là ID Token và Access Token được trả từ Token Endpoint đã được ràng buộc với nhau bằng TLS của kết nối Token Endpoint. Quy tắc này không xóa yêu cầu hash claim trên ID Token từ Authorization Endpoint khi response_type yêu cầu chúng.

Nếu client nhận hash claim trong ID Token từ Token Endpoint và profile yêu cầu kiểm tra, phải đối chiếu với artifact thuộc đúng Token Response đó. Không lấy at_hash/c_hash của ID Token tại Authorization Endpoint rồi so với artifact của Token Endpoint.

### 5.5. Bảng tổng hợp

| Vị trí ID Token | Luồng/response_type | at_hash | c_hash |
| --- | --- | --- | --- |
| Authorization Endpoint | Implicit: id_token token | REQUIRED | Không dùng |
| Authorization Endpoint | Implicit: id_token | MAY NOT được sử dụng | Không dùng |
| Authorization Endpoint | Hybrid: code id_token | OPTIONAL | REQUIRED |
| Authorization Endpoint | Hybrid: code id_token token | REQUIRED | REQUIRED |
| Token Endpoint | Authorization Code Flow | OPTIONAL; client MAY dùng để kiểm tra Access Token | Không được yêu cầu bởi quy tắc này |
| Token Endpoint | Hybrid Flow | MAY omit dù ID Token ở Authorization Endpoint có hai claim | MAY omit dù ID Token ở Authorization Endpoint có hai claim |

Không được áp dụng quy tắc REQUIRED của Hybrid Authorization Endpoint cho mọi ID Token. Trước khi kiểm tra sự hiện diện của claim, client phải biết ID Token đến từ endpoint nào và response_type của giao dịch.

## 6. at_hash ngăn Access Token substitution như thế nào?

Giả sử client nhận một phản hồi có ID Token và Access Token. ID Token được ký bởi OpenID Provider và chứa at_hash. Nếu kẻ tấn công thay Access Token bằng một token khác nhưng giữ nguyên ID Token:

1. Chữ ký ID Token vẫn có thể hợp lệ vì ID Token chưa bị sửa.
2. Client lấy Access Token thực tế từ phản hồi.
3. Client tính lại hash theo thuật toán của ID Token.
4. Kết quả khác at_hash đã được ký trong ID Token.
5. Client phát hiện hai artifact không thuộc cùng một phản hồi xác thực và từ chối.

at_hash vì vậy cung cấp liên kết mật mã giữa Access Token và ID Token. Nó không chứng minh Access Token có quyền truy cập tài nguyên nào; resource server vẫn phải xác minh Access Token theo cơ chế và profile tương ứng.

## 7. c_hash ngăn Authorization Code substitution như thế nào?

Trong Hybrid Flow, Authorization Endpoint có thể trả Code cùng ID Token. Claim c_hash ràng buộc hai giá trị:

1. OpenID Provider tạo Authorization Code.
2. OpenID Provider tính c_hash từ chính giá trị Code.
3. c_hash được đưa vào ID Token và được bảo vệ bằng chữ ký của ID Token.
4. Client nhận Code và ID Token trong cùng phản hồi.
5. Client tính lại c_hash từ Code nhận được.
6. Nếu kết quả khác claim trong ID Token, client từ chối phản hồi.

Điều này giúp phát hiện việc thay Code bằng Code từ một giao dịch khác. Sau khi c_hash đạt, client vẫn phải gửi Code tới đúng Token Endpoint, dùng đúng redirect_uri và PKCE verifier nếu giao dịch sử dụng PKCE. Authorization Server vẫn phải kiểm tra Code hợp lệ, thuộc client, chưa sử dụng và được cấp cho đúng redirect URI.

## 8. Quy trình xác minh tại client

Client nên gắn việc kiểm tra hash với toàn bộ quy trình xác minh OIDC:

1. Lưu lại ngữ cảnh giao dịch: response_type, state, nonce, issuer dự kiến, client_id và các tham số liên quan.
2. Nhận phản hồi tại Redirect URI và parse đúng serialization.
3. Xác định ID Token đến từ Authorization Endpoint hay Token Endpoint.
4. Xác minh chữ ký hoặc giải mã ID Token theo cấu hình đã đăng ký; kiểm tra issuer, audience, thời gian và nonce theo OIDC Core.
5. Xác định at_hash/c_hash có bắt buộc trong đúng response_type và endpoint hay không.
6. Nếu at_hash áp dụng, tính lại từ Access Token thuộc cùng phản hồi.
7. Nếu c_hash áp dụng, tính lại từ Authorization Code thuộc cùng phản hồi.
8. Từ chối nếu claim bắt buộc bị thiếu hoặc giá trị hash không khớp.
9. Chỉ sau khi toàn bộ phản hồi hợp lệ mới sử dụng kết quả đăng nhập và tiếp tục xử lý Access Token/Code.

~~~mermaid
flowchart TD
    A["Nhận OIDC response"] --> B["Xác định flow, response_type và endpoint"]
    B --> C["Xác minh ID Token: chữ ký, iss, aud, exp, nonce"]
    C --> D{"ID Token hợp lệ?"}
    D -- "Không" --> X["Từ chối response"]
    D -- "Có" --> E["Xác định at_hash/c_hash có bắt buộc không"]
    E --> F{"at_hash áp dụng?"}
    F -- "Có" --> G["Hash Access Token cùng response và so khớp"]
    F -- "Không" --> H["Bỏ qua kiểm tra at_hash theo profile"]
    G --> I{"at_hash khớp?"}
    I -- "Không" --> X
    I -- "Có" --> J["Kiểm tra c_hash nếu áp dụng"]
    H --> J
    J --> K{"c_hash áp dụng?"}
    K -- "Có" --> L["Hash Authorization Code cùng response và so khớp"]
    K -- "Không" --> M["Hoàn tất kiểm tra artifact binding"]
    L --> N{"c_hash khớp?"}
    N -- "Không" --> X
    N -- "Có" --> M
    M --> O["Chấp nhận response nếu các kiểm tra OIDC khác đều đạt"]
~~~

Sơ đồ mô tả luồng khái quát. Một client có thể dùng thư viện OIDC để thực hiện các bước theo thứ tự chuẩn, nhưng phải bảo đảm thư viện biết chính xác nguồn ID Token và response_type để áp dụng đúng điều kiện REQUIRED/OPTIONAL.

## 9. Mã giả tính và kiểm tra hash claim

~~~text
function calculateOidcArtifactHash(artifactValue, idTokenSigningAlg):
    require artifactValue is the exact ASCII protocol value
    hashFunction = jwaHashForSigningAlgorithm(idTokenSigningAlg)
    require hashFunction is defined by the supported profile

    digest = hashFunction(ASCII(artifactValue))
    halfLength = lengthInBits(digest) / 2
    leftHalf = firstBits(digest, halfLength)

    return BASE64URL_WITHOUT_PADDING(leftHalf)

function validateAtHash(idToken, accessToken, flowContext):
    if not atHashRequiredOrPresent(idToken, flowContext):
        return NOT_APPLICABLE

    require accessToken exists in the same protocol response
    expected = calculateOidcArtifactHash(
        accessToken,
        signingAlgorithmOf(idToken)
    )
    require constantTimeStringMatch(idToken.at_hash, expected)
    return VALID

function validateCHash(idToken, authorizationCode, flowContext):
    if not cHashRequiredOrPresent(idToken, flowContext):
        return NOT_APPLICABLE

    require authorizationCode exists in the same protocol response
    expected = calculateOidcArtifactHash(
        authorizationCode,
        signingAlgorithmOf(idToken)
    )
    require constantTimeStringMatch(idToken.c_hash, expected)
    return VALID
~~~

Đây là pseudocode mô tả logic, không phải API của một thư viện cụ thể. Hàm signingAlgorithmOf phải lấy alg của JWS ký ID Token. Nếu ID Token được mã hóa lồng bên ngoài, cần lấy thuật toán ký của lớp JWS bên trong theo cấu trúc OIDC/JWE đã thương lượng.

Hàm atHashRequiredOrPresent và cHashRequiredOrPresent phải dựa trên response_type, nguồn ID Token và quy tắc OIDC Core. Không được chỉ kiểm tra “claim có mặt hay không” mà bỏ qua ngữ cảnh giao thức.

## 10. Ví dụ theo từng luồng

### 10.1. Implicit Flow trả Access Token và ID Token

Request sử dụng:

~~~text
response_type=id_token token
~~~

Authorization Endpoint trả:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "id_token": "SIGNED_ID_TOKEN"
}
~~~

Trong trường hợp này:

- ID Token phải chứa at_hash.
- Client xác minh chữ ký ID Token trước khi tin claim.
- Client tính lại at_hash từ ACCESS_TOKEN_VALUE.
- Nếu hash không khớp, từ chối phản hồi.
- Client vẫn phải kiểm tra state, nonce và các quy tắc OIDC khác.

### 10.2. Hybrid Flow trả Code và ID Token

Request sử dụng:

~~~text
response_type=code id_token
~~~

Authorization Endpoint trả:

~~~json
{
  "code": "AUTHORIZATION_CODE_VALUE",
  "id_token": "SIGNED_ID_TOKEN"
}
~~~

Trong trường hợp này:

- ID Token phải chứa c_hash.
- at_hash không bắt buộc vì Authorization Endpoint không trả Access Token.
- Client tính lại c_hash từ AUTHORIZATION_CODE_VALUE.
- Client từ chối nếu claim thiếu hoặc không khớp.
- Client tiếp tục đổi Code tại Token Endpoint theo quy tắc OAuth/OIDC, bao gồm PKCE nếu đã sử dụng.

### 10.3. Hybrid Flow trả Code, Access Token và ID Token

Request sử dụng:

~~~text
response_type=code id_token token
~~~

Authorization Endpoint trả:

~~~json
{
  "code": "AUTHORIZATION_CODE_VALUE",
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "id_token": "SIGNED_ID_TOKEN"
}
~~~

Trong trường hợp này:

- ID Token phải chứa cả at_hash và c_hash.
- at_hash phải khớp với ACCESS_TOKEN_VALUE trong phản hồi này.
- c_hash phải khớp với AUTHORIZATION_CODE_VALUE trong phản hồi này.
- Không thay Access Token bằng token nhận được từ một lần gọi khác khi tính at_hash.
- Không thay Code bằng Code đã lưu từ một phiên trước.

## 11. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi at_hash/c_hash luôn bắt buộc | Từ chối sai các phản hồi hợp lệ của Authorization Code Flow hoặc ID Token không có artifact tương ứng | Xác định endpoint và response_type trước |
| Bỏ qua claim dù flow yêu cầu | Không phát hiện artifact bị thay thế | Từ chối nếu claim REQUIRED bị thiếu |
| Chỉ kiểm tra claim có mặt | Token/code thay thế vẫn có thể lọt | Tính lại và so khớp giá trị |
| Hash toàn bộ JWT hoặc JSON response | Tạo kết quả khác chuẩn | Hash chính xác ASCII value của artifact |
| Hash chuỗi URL-encoded | Sai dữ liệu đầu vào | Dùng giá trị tham số sau khi parse response đúng cách |
| Dùng SHA-256 cố định | Sai với ID Token ký bằng thuật toán có hash khác | Chọn hash theo JWS alg của ID Token |
| Dùng alg/enc của JWE ngoài | Chọn sai hàm hash | Dùng alg của JWS ký ID Token |
| Lấy nửa phải của digest | Không khớp quy tắc OIDC | Lấy nửa trái theo bit |
| Dùng Base64 thường hoặc giữ padding | Sai biểu diễn | Base64URL không padding |
| So sánh không phân biệt hoa/thường | Chấp nhận chuỗi khác giá trị | So sánh chính xác, case-sensitive |
| Dùng Access Token từ response khác | Không còn ràng buộc đúng cặp artifact | Dùng token cùng phản hồi với ID Token |
| Coi c_hash thay thế PKCE | Không bảo vệ đầy đủ việc đổi Code | Vẫn kiểm tra PKCE verifier và Code theo OAuth |
| Coi at_hash xác minh Access Token | Bỏ qua validation Access Token | Resource server/flow phải kiểm tra Access Token riêng |
| Không phân biệt ID Token ở hai endpoint trong Hybrid | So sánh nhầm artifact hoặc áp dụng sai điều kiện REQUIRED | Gắn mỗi ID Token với đúng response và endpoint |

## 12. at_hash/c_hash và các cơ chế bảo vệ khác

Các cơ chế dưới đây giải quyết những ranh giới khác nhau:

| Cơ chế | Ràng buộc | Không thay thế |
| --- | --- | --- |
| **state** | Phản hồi authorization với request/session phía client | at_hash, c_hash, PKCE |
| **nonce** | ID Token với Authentication Request | at_hash, c_hash |
| **PKCE** | Authorization Code với client giữ code_verifier | c_hash |
| **at_hash** | Access Token với ID Token | Xác minh chữ ký/claims của Access Token |
| **c_hash** | Authorization Code với ID Token | PKCE và kiểm tra Code tại Token Endpoint |
| **TLS** | Bảo vệ kênh truyền và phản hồi Token Endpoint | Kiểm tra các artifact ở front channel khi flow yêu cầu |

Không nên bỏ PKCE chỉ vì ID Token có c_hash. c_hash là một liên kết trong ID Token đã ký; PKCE chứng minh client đổi Code có verifier phù hợp. Hai cơ chế có mục tiêu khác nhau và có thể cùng được sử dụng.

Tương tự, at_hash không chứng minh Access Token còn hiệu lực, chưa bị thu hồi hoặc có scope phù hợp. Nó chỉ ràng buộc giá trị Access Token với ID Token trong phản hồi OIDC.

## 13. Kiểm thử at_hash và c_hash

Nên có kiểm thử theo cả công thức mật mã và ngữ cảnh giao thức:

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Công thức | RS256/SHA-256, HS384/SHA-384, HS512/SHA-512 | Lấy đúng nửa digest trái và Base64URL |
| Artifact | Access Token/Code đúng giá trị | Hash khớp |
| Thay thế | Thay một ký tự Access Token hoặc Code | Hash không khớp, từ chối |
| Encoding | Base64 thường, padding, sai case | Không được chấp nhận như giá trị tương đương |
| Implicit | id_token token thiếu at_hash | Từ chối |
| Implicit | id_token có at_hash | Từ chối theo profile vì không có Access Token |
| Hybrid | code id_token thiếu c_hash | Từ chối |
| Hybrid | code id_token token thiếu một trong hai claim | Từ chối |
| Hybrid | code id_token có at_hash nhưng không có Access Token | Không yêu cầu at_hash; xử lý theo quy tắc OPTIONAL |
| Code Flow | Token Endpoint ID Token không có at_hash | Chấp nhận nếu các kiểm tra khác đạt |
| Code Flow | at_hash có mặt và khớp Access Token Token Response | Có thể xác minh theo OIDC Core |
| Hybrid Token Endpoint | ID Token bỏ at_hash/c_hash đã có ở Authorization Endpoint | Không từ chối chỉ vì thiếu hai claim này |
| Endpoint binding | Dùng Access Token của Token Endpoint để kiểm tra ID Token ở Authorization Endpoint | Phát hiện không khớp nếu hai Access Token khác nhau |
| Signature | at_hash/c_hash đúng nhưng chữ ký ID Token sai | Từ chối |
| Claims | Hash đúng nhưng issuer/audience/nonce sai | Từ chối |
| PKCE | c_hash đúng nhưng code_verifier sai | Token Endpoint phải từ chối Code exchange |

Nên dùng test vector OIDC và kiểm thử liên thông với OpenID Provider thực tế. Không chỉ kiểm tra trường hợp thành công; các ca thiếu claim, sai artifact và sai endpoint mới chứng minh client áp dụng đúng ngữ cảnh.

## 14. Checklist triển khai

1. [ ] Xác định chính xác flow, response_type và endpoint phát hành từng ID Token.
2. [ ] Chỉ yêu cầu at_hash/c_hash trong những trường hợp OIDC Core quy định REQUIRED.
3. [ ] Với Implicit id_token token, yêu cầu at_hash; với id_token-only, không chấp nhận at_hash.
4. [ ] Với Hybrid code id_token, yêu cầu c_hash; với code id_token token, yêu cầu cả c_hash và at_hash.
5. [ ] Với Authorization Code Flow Token Endpoint, coi at_hash là OPTIONAL và chỉ kiểm tra nếu client chọn sử dụng.
6. [ ] Áp dụng ngoại lệ Hybrid Token Endpoint: at_hash/c_hash có thể được bỏ qua tại ID Token này theo OIDC Core.
7. [ ] Tính hash từ đúng ASCII value của Access Token hoặc Authorization Code cùng phản hồi.
8. [ ] Chọn hash function theo JWS alg ký ID Token, không theo Access Token hay JWE outer header.
9. [ ] Lấy nửa digest bên trái và Base64URL-encode không padding.
10. [ ] So sánh chuỗi case-sensitive; mismatch phải làm phản hồi thất bại.
11. [ ] Xác minh chữ ký, issuer, audience, thời gian và nonce của ID Token độc lập với hash claims.
12. [ ] Không coi at_hash/c_hash thay thế state, nonce, PKCE, TLS hoặc validation Access Token.
13. [ ] Trong Hybrid Flow, gắn mỗi ID Token với đúng Code/Access Token ở đúng endpoint.
14. [ ] Có negative tests cho claim thiếu, artifact bị thay thế, encoding sai và token từ endpoint khác.

## 15. Tài liệu tiêu chuẩn liên quan

- **OpenID Connect Core 1.0 incorporating errata set 2:** định nghĩa at_hash trong Section 2; Access Token Validation và at_hash trong Section 3.2.2.9–3.2.2.10; Authorization Code Validation và c_hash trong Section 3.3.2.10–3.3.2.11; quy tắc Token Endpoint trong Section 3.1.3.6–3.1.3.8 và 3.3.3.6–3.3.3.7.
- **RFC 7515 — JSON Web Signature (JWS):** JOSE Header, thuật toán ký và Base64URL.
- **RFC 7518 — JSON Web Algorithms (JWA):** ánh xạ thuật toán JWS và hàm hash tương ứng.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Access Token và Token Endpoint.
- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE):** ràng buộc Authorization Code với code_verifier.

**Nguyên tắc ghi nhớ:** at_hash ràng buộc Access Token với ID Token; c_hash ràng buộc Authorization Code với ID Token. Cách tính luôn lấy nửa trái của hash trên ASCII value rồi Base64URL-encode, nhưng việc claim có bắt buộc hay không phụ thuộc flow, response_type và endpoint trả ID Token. Hãy xác minh đúng artifact trong cùng phản hồi và tiếp tục thực hiện đầy đủ các kiểm tra OIDC còn lại.

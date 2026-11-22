# JWKS và cách chọn đúng khóa để xác minh

Trong hệ thống **Security - JSON Web Token (JWT)**, một bên xác minh thường cần lấy public key của issuer để kiểm tra chữ ký. Khi issuer có nhiều khóa, thay khóa theo thời gian hoặc phục vụ nhiều loại token, việc chọn đúng khóa trở thành một phần quan trọng của ranh giới bảo mật. **JSON Web Key Set (JWKS)** cung cấp tập các JWK để trao đổi khóa; bên xác minh phải chọn khóa từ đúng nguồn tin cậy, kiểm tra metadata và loại khóa phù hợp, sau đó mới xác minh chữ ký và claims.

Bài này thuộc chương **Khóa và JWKS** của module **SECURITY_TOKEN_SECURITY_JWT**. Phạm vi là bảo mật JWT đa nền tảng, độc lập ngôn ngữ lập trình và framework.

## 1. Mục tiêu và nguyên tắc cốt lõi

Sau bài học, người đọc có thể:

1. Giải thích cấu trúc JWKS và mối quan hệ giữa issuer, metadata, JWKS URI và JWK.
2. Thiết lập nguồn JWKS dựa trên issuer đã tin cậy.
3. Chọn một JWK phù hợp với JWT dựa trên `kid`, `alg`, `kty`, `use`, `key_ops` và chính sách.
4. Xử lý đúng trường hợp thiếu `kid`, `kid` không tồn tại, trùng `kid`, cache cũ hoặc endpoint JWKS tạm thời không truy cập được.
5. Thiết kế rotation và thu hồi khóa mà không làm suy yếu xác minh chữ ký.

**Nguyên tắc xuyên suốt:** token có thể cung cấp gợi ý để tìm khóa, nhưng token không được tự quyết định nguồn khóa mà verifier sẽ tin. Chỉ khóa lấy từ nguồn đã được cấu hình tin cậy và phù hợp chính sách mới được dùng để xác minh.

## 2. JWKS là gì?

**JWK** là một đối tượng JSON biểu diễn một khóa cùng metadata liên quan. **JWKS** là một đối tượng JSON có member `keys`, chứa một mảng các JWK.

Ví dụ một JWKS có hai public RSA key:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "access-signing-2026-a",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_RSA_MODULUS_A>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "access-signing-2026-b",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_RSA_MODULUS_B>",
      "e": "AQAB"
    }
  ]
}
~~~

Các chuỗi `<BASE64URL_...>` chỉ là placeholder minh họa, không phải public key có thể sử dụng. Tập khóa có thể chứa nhiều JWK vì:

- Issuer đang rotation: khóa mới đã được công bố, khóa cũ vẫn còn cần để xác minh token chưa hết hạn.
- Issuer hỗ trợ nhiều thuật toán hoặc nhiều nhóm token.
- Issuer phục vụ nhiều loại client hoặc hệ thống xác minh với các khóa khác nhau.

JWKS là định dạng phân phối khóa. Nó **không** phải danh sách token hợp lệ, không lưu trạng thái phiên, không tự thu hồi JWT và không quyết định quyền truy cập của người dùng.

### 2.1. Những loại khóa có thể xuất hiện

JWK có thể biểu diễn RSA (`kty=RSA`), EC (`kty=EC`), OKP (`kty=OKP`) hoặc khóa đối xứng (`kty=oct`). Một endpoint JWKS công khai dùng cho xác minh chữ ký thông thường chỉ nên công bố **public material** của khóa bất đối xứng.

Không đưa các thành phần private như RSA `d`, `p`, `q`, `dp`, `dq`, `qi`, EC/OKP `d`, hoặc secret đối xứng `oct.k` lên JWKS công khai. Nếu các trường này bị công bố, phải xem đó là sự cố lộ khóa và thực hiện ứng cứu tương ứng.

### 2.2. JWKS không tự tạo ra sự tin cậy

Một attacker hoàn toàn có thể tạo một cặp khóa RSA của riêng họ, tạo JWK public và đưa nó vào một JWKS giả. Về mặt toán học, chữ ký do private key tương ứng tạo ra vẫn xác minh đúng bằng public key đó. Điều này không chứng minh token đến từ issuer hợp lệ.

Sự tin cậy phải đến từ **cấu hình issuer và nguồn JWKS đã xác thực**. Việc tìm thấy một khóa trong một JSON có cấu trúc đúng không đủ để chấp nhận khóa.

## 3. Xác lập nguồn JWKS đáng tin cậy

Trước khi xử lý `kid` hoặc chọn khóa, verifier phải xác định được issuer nào được phép phát hành loại token đang nhận.

Một cấu hình tin cậy thường gắn các thông tin:

| Thành phần | Vai trò |
| --- | --- |
| Issuer ID / `iss` | Định danh chính xác bên phát hành được phép. |
| Metadata endpoint hoặc JWKS URI | Nguồn lấy metadata và public keys của issuer. |
| Danh sách thuật toán cho phép | Giới hạn các thuật toán chữ ký được dùng cho issuer/token class. |
| Audience mong đợi | Xác định token được phát hành cho API hoặc client nào. |
| Token profile/type | Phân biệt access token, ID token, service token hoặc loại token khác. |
| Chính sách cache và rotation | Quy định thời hạn dùng cache và cách làm mới khóa. |

### 3.1. Cấu hình issuer trước, tra cứu JWKS sau

Ví dụ cấu hình minh họa:

~~~yaml
trustedIssuers:
  - issuer: "https://identity.example.test/"
    jwksUri: "https://identity.example.test/.well-known/jwks.json"
    allowedJwsAlgorithms:
      - "RS256"
    audiences:
      - "orders-api"
    tokenProfile: "access-token"
~~~

Đây là ví dụ cấu hình khái niệm; định dạng thực tế tùy hệ thống. Điểm quan trọng là `jwksUri` và allowlist thuật toán thuộc **cấu hình tin cậy** được quản trị, không được tự lấy từ một URL bất kỳ trong token.

Nếu dùng metadata discovery, verifier cần bắt đầu từ issuer đã biết, lấy metadata qua HTTPS và kiểm tra giá trị `issuer` trong metadata khớp chính xác với issuer mong đợi. `jwks_uri` được chấp nhận sau khi metadata đã được xác thực theo chính sách. Không cho một token tự khai báo issuer mới rồi kích hoạt discovery tùy ý.

### 3.2. Dùng `iss` chưa xác minh như thế nào?

Trong JWT, claim `iss` chỉ được xác minh sau khi chữ ký hợp lệ. Tuy nhiên, hệ thống nhiều issuer có thể cần đọc payload trước để biết cấu hình nào có thể áp dụng. Có thể dùng giá trị `iss` chưa xác minh **như khóa tra cứu trong danh sách issuer đã cấu hình sẵn**:

1. Đọc `iss` ở trạng thái chưa tin cậy.
2. Tìm chính xác issuer đó trong allowlist cục bộ hoặc registry tin cậy.
3. Nếu không có cấu hình tương ứng, từ chối token.
4. Nếu có, chỉ dùng JWKS URI và policy gắn với issuer đó.
5. Sau khi xác minh chữ ký, kiểm tra `iss` đã xác thực khớp chính xác issuer cấu hình.

Không được dùng `iss` chưa xác minh để tải metadata từ một domain tùy ý. `iss` chỉ giúp chọn trong các cấu hình đã được tin cậy, không cấp quyền tin cậy cho issuer mới.

### 3.3. Bảo vệ đường dẫn JWKS

- Dùng HTTPS và xác minh chứng chỉ máy chủ theo trust store phù hợp.
- Chỉ chấp nhận endpoint đã được cấu hình hoặc khám phá từ metadata tin cậy.
- Kiểm soát redirect; không để endpoint chuyển hướng đến host nội bộ hoặc nguồn ngoài allowlist.
- Áp dụng timeout, giới hạn kích thước response, giới hạn số lần thử và kiểm soát DNS/địa chỉ đích để giảm nguy cơ SSRF.
- Không cho header JWT `jku` hoặc `x5u` tự điều khiển request mạng nếu không có chính sách allowlist riêng.
- Theo dõi thay đổi JWKS bất thường và bảo vệ quy trình quản trị endpoint/metadata.

## 4. Header JWT chứa thông tin chọn khóa

Một JWS compact có header, payload và chữ ký. Header được giải mã trước khi xác minh để biết thuật toán và định danh khóa. Nhưng nội dung header do bên gửi token kiểm soát, vì vậy **mọi giá trị trong header đều chưa đáng tin cho đến khi chữ ký hợp lệ**.

Ví dụ:

~~~json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "access-signing-2026-b"
}
~~~

| Header parameter | Mục đích | Cách xử lý an toàn |
| --- | --- | --- |
| `alg` | Khai báo thuật toán JWS được token sử dụng. | Chỉ chấp nhận nếu nằm trong allowlist của issuer/profile và tương thích với JWK. |
| `kid` | Gợi ý định danh khóa trong JWKS. | Tra cứu chính xác trong tập khóa của issuer đã tin cậy. |
| `typ` | Gợi ý loại nội dung/token. | Có thể dùng để phân biệt profile, nhưng vẫn cần kiểm tra claims và ngữ cảnh. |
| `crit` | Khai báo extension header quan trọng mà verifier phải hiểu. | Nếu có extension bắt buộc mà verifier không hỗ trợ, từ chối token. |
| `jku` | URL của JWK Set. | Không tự động fetch URL do token cung cấp; chỉ dùng khi có cấu hình tin cậy/allowlist rõ ràng. |
| `jwk` | JWK nhúng trực tiếp trong header. | Không tin khóa do token tự mang theo để xác minh chính token đó, trừ profile có cơ chế xác thực nguồn khóa riêng. |
| `x5u` | URL của chứng chỉ X.509. | Không fetch tùy ý; có nguy cơ SSRF và thay thế nguồn khóa. |
| `x5c` | Chuỗi chứng chỉ X.509. | Cần xác minh chuỗi chứng chỉ và quan hệ với trust anchor; sự hiện diện của chứng chỉ không tự chứng minh tin cậy. |

### 4.1. Vì sao không lấy `jku` từ token để tải JWKS?

Nếu verifier tải URL do attacker đặt trong `jku`, attacker có thể:

- Trỏ request đến máy chủ của họ để cung cấp public key giả.
- Trỏ đến địa chỉ loopback, mạng nội bộ, metadata service hoặc dịch vụ quản trị để khai thác SSRF.
- Dùng redirect hoặc DNS rebinding để chuyển request đến đích không mong muốn.
- Tạo lượng lớn URL khác nhau để gây quá tải mạng và cache.

Với hệ thống có nhu cầu hỗ trợ nhiều endpoint, phải ánh xạ issuer/profile sang endpoint được cho phép từ cấu hình đáng tin cậy. Không biến header thành cơ chế khám phá nguồn tin cậy tùy ý.

### 4.2. `kid` không phải bằng chứng xác thực

Attacker có thể tự đặt `kid` bất kỳ trong JWT. `kid` chỉ có tác dụng chọn ứng viên **bên trong JWKS đã tin cậy**. Không được lấy `kid` làm tên file, câu truy vấn, URL, tên bảng hoặc lệnh hệ thống mà không xử lý như dữ liệu không đáng tin.

## 5. Quy trình chọn khóa tổng quát

Luồng an toàn gồm hai phần: **chọn ứng viên** và **xác minh token**. Chọn được JWK không có nghĩa token đã hợp lệ.

~~~mermaid
flowchart TD
    A["Nhận JWT"] --> B["Parse header/payload như dữ liệu chưa tin cậy"]
    B --> C["Xác định issuer trong danh sách đã cấu hình"]
    C --> D{"Issuer có được tin cậy?"}
    D -- Không --> X["Từ chối"]
    D -- Có --> E["Lấy JWKS từ nguồn gắn với issuer"]
    E --> F["Lọc theo kid và metadata khóa"]
    F --> G{"Có đúng một ứng viên phù hợp?"}
    G -- Không --> X
    G -- Có --> H["Kiểm tra alg allowlist và tương thích kty/curve"]
    H --> I{"Policy cho phép?"}
    I -- Không --> X
    I -- Có --> J["Xác minh chữ ký JWS"]
    J --> K{"Chữ ký hợp lệ?"}
    K -- Không --> X
    K -- Có --> L["Kiểm tra iss, aud, exp, nbf và token profile"]
    L --> M{"Claims và policy hợp lệ?"}
    M -- Không --> X
    M -- Có --> N["Chấp nhận token"]
~~~

Trình tự này là mô hình khái niệm. Có thể tối ưu cache hoặc thứ tự kiểm tra để giảm chi phí, nhưng không được bỏ bất kỳ điều kiện tin cậy nào.

## 6. Bước 1 — Chọn đúng issuer và JWKS

Verifier phải biết token thuộc miền tin cậy nào. Tùy kiến trúc, issuer có thể được xác định từ:

- Cấu hình endpoint hoặc API đang xử lý request.
- Client/tenant đã được xác thực ở tầng trước.
- Giá trị `iss` chưa xác minh, nhưng chỉ dùng để tra cứu trong allowlist issuer đã cấu hình.

Sau khi chọn được issuer, lấy JWKS từ đúng endpoint gắn với issuer đó. Không tìm kiếm khóa trên toàn bộ các JWKS mà hệ thống từng biết rồi chọn khóa có `kid` trùng đầu tiên.

**Ví dụ:** hai issuer A và B đều có khóa mang `kid="signing-01"`. Chuỗi `kid` giống nhau không làm hai khóa tương đương. Token của A chỉ được tra trong JWKS A; token của B chỉ được tra trong JWKS B, nếu B cũng được tin cậy.

## 7. Bước 2 — Lọc ứng viên bằng `kid`

Nếu JWT có `kid`, verifier tìm JWK có `kid` khớp chính xác trong JWKS của issuer đã chọn.

### 7.1. Quy tắc so khớp

- So khớp chuỗi chính xác, không tự chuyển chữ hoa/thường hoặc chuẩn hóa.
- Chỉ tìm trong tập khóa của đúng issuer và đúng profile.
- Không ghép `kid` từ token với khóa ở issuer khác.
- Không diễn giải `kid` thành URL hoặc đường dẫn.
- Nên yêu cầu `kid` duy nhất trong phạm vi tập khóa mà verifier sử dụng.

Nếu có hai JWK khác nhau cùng `kid` và cùng thỏa điều kiện, lựa chọn trở nên mơ hồ. Chính sách an toàn là từ chối cấu hình/tập khóa đó, phát cảnh báo và yêu cầu issuer sửa. Không chọn phần tử đầu tiên, phần tử cuối cùng hoặc thử ngẫu nhiên đến khi chữ ký khớp.

### 7.2. Nếu JWT không có `kid`

`kid` là thuộc tính tùy chọn của JWK và header JWT. Việc thiếu `kid` không tự động chứng minh token sai chuẩn. Tuy nhiên, verifier cần chính sách rõ ràng:

- Nếu sau khi lọc issuer, thuật toán, loại khóa và mục đích chỉ còn **một** ứng viên hợp lệ, có thể dùng ứng viên đó nếu profile cho phép token không có `kid`.
- Nếu còn nhiều ứng viên, không chọn tùy tiện. Từ chối vì không thể xác định khóa duy nhất, trừ khi profile có quy tắc chọn khóa khác được xác định rõ và an toàn.
- Không thử hàng loạt khóa không giới hạn để tìm khóa nào xác minh được; cách này gây tốn CPU và có thể tạo bề mặt DoS.

### 7.3. Nếu `kid` không tìm thấy

`kid` lạ có thể do issuer vừa rotation, verifier đang giữ JWKS cache cũ, hoặc token giả. Quy trình có kiểm soát:

1. Kiểm tra cache hiện tại và trạng thái tải JWKS.
2. Nếu chính sách cho phép, yêu cầu làm mới JWKS từ **endpoint đã tin cậy** một lần.
3. Giới hạn tần suất refresh, gộp các request đồng thời và áp dụng backoff.
4. Tìm lại `kid` trong JWKS mới.
5. Nếu vẫn không có đúng một khóa phù hợp, từ chối token và ghi nhận sự kiện phù hợp.

Không fallback sang khóa bất kỳ, không bỏ qua chữ ký và không tải URL từ header để tìm khóa thay thế.

## 8. Bước 3 — Kiểm tra metadata và loại khóa

Sau khi có ứng viên theo `kid`, kiểm tra JWK có phù hợp với thao tác xác minh chữ ký hay không.

| Thuộc tính JWK | Điều kiện thường dùng cho JWS verification | Cách xử lý khi không phù hợp |
| --- | --- | --- |
| `kty` | Phải là kiểu khóa tương thích với thuật toán được phép. | Từ chối ứng viên. |
| `use` | Nếu có, phải là `sig` cho mục đích chữ ký. | Không dùng khóa cho JWS. |
| `key_ops` | Nếu có, phải cho phép thao tác `verify`. | Không dùng khóa cho xác minh. |
| `alg` | Nếu có, phải khớp thuật toán JWS mà policy cho phép. | Từ chối khi không tương thích. |
| `crv` | Với EC/OKP, phải là curve được thuật toán và policy cho phép. | Từ chối curve không phù hợp. |
| Tham số vật liệu khóa | Phải hợp lệ và đủ cho phép xác minh. | Từ chối khóa sai định dạng hoặc không hợp lệ. |

Nếu cả `use` và `key_ops` cùng xuất hiện, chúng phải nhất quán. Ví dụ `use="enc"` không phù hợp với `key_ops=["verify"]` trong một JWK dùng cho xác minh chữ ký. Nếu một public RSA JWK chỉ có `key_ops=["sign"]`, không được coi nó là khóa xác minh.

Các trường này là metadata mô tả khóa, không thay thế quyền kiểm soát tại KMS/HSM hoặc allowlist của verifier. Nếu trường tùy chọn bị thiếu, áp dụng chính sách đã định nghĩa; có thể yêu cầu metadata đầy đủ hơn trong môi trường quản trị chặt.

### 8.1. Kiểm tra tham số theo thuật toán

Ví dụ các ràng buộc thường gặp:

| JWS `alg` | JWK phù hợp | Điều kiện quan trọng |
| --- | --- | --- |
| `HS256` | `kty=oct` | Secret đủ entropy và kích thước; chỉ dùng trong miền tin cậy chia sẻ bí mật. |
| `RS256` | `kty=RSA` | RSA public key hợp lệ, modulus đủ mạnh theo policy. |
| `PS256` | `kty=RSA` | RSA key hợp lệ và verifier hỗ trợ RSA-PSS theo profile. |
| `ES256` | `kty=EC` | Curve `P-256`, tọa độ hợp lệ. |
| `ES384` | `kty=EC` | Curve `P-384`, tọa độ hợp lệ. |
| `ES512` | `kty=EC` | Curve `P-521`, tọa độ hợp lệ. |
| `EdDSA` | `kty=OKP` | Curve EdDSA được hỗ trợ, ví dụ `Ed25519`. |

Không suy ra thuật toán chỉ từ `kty`. RSA có thể được dùng với nhiều họ thuật toán; EC có thể dùng nhiều curve; OKP có các curve cho mục đích khác nhau. Cặp thuật toán/khóa phải được giới hạn rõ.

## 9. Bước 4 — Áp dụng allowlist thuật toán

`alg` trong JWT header do người gửi cung cấp. Nó cho biết token **tuyên bố** dùng thuật toán nào, chứ không có quyền ra lệnh cho verifier sử dụng bất kỳ thuật toán nào.

Verifier cần:

1. Xác định allowlist từ cấu hình issuer và loại token.
2. Từ chối nếu header `alg` không nằm trong allowlist.
3. Kiểm tra `kty`, curve và tham số JWK tương thích với thuật toán.
4. Nếu JWK có member `alg`, kiểm tra giá trị này tương thích chính xác với thuật toán đang xác minh.
5. Dùng thư viện JOSE đáng tin cậy để xác minh đúng signing input và chữ ký.

### 9.1. Không chấp nhận `none` làm fallback

Nếu profile yêu cầu JWT có chữ ký, không chấp nhận `alg="none"` để bỏ qua xác minh. Khi thuật toán không được hỗ trợ hoặc không có khóa phù hợp, phải từ chối token.

### 9.2. Ngăn algorithm/key confusion

Một lỗi nghiêm trọng là dùng cùng một byte string theo cách khác nhau tùy `alg` trong token. Ví dụ verifier mong `RS256` nhưng cho phép token đổi sang `HS256` và dùng RSA public key làm HMAC secret. Attacker biết public key có thể tạo MAC giả.

Phòng tránh:

- Gắn allowlist thuật toán với issuer và token profile.
- Ràng buộc thuật toán với `kty` và tham số thực tế của JWK.
- Không dùng một khóa cho các thuật toán hoặc mục đích không tương thích.
- Không tự động thử thuật toán khác khi phép xác minh đầu tiên thất bại.

### 9.3. Phân biệt các loại JWT

Một issuer có thể phát hành nhiều loại JWT: access token, ID token, token cho dịch vụ nội bộ hoặc token cho quy trình đặc biệt. Chỉ xác minh chữ ký bằng khóa đúng vẫn chưa đủ nếu token bị dùng sai ngữ cảnh.

Nên tách policy theo token profile:

- Audience khác nhau.
- Loại token (`typ`) và claims bắt buộc khác nhau.
- Scope/permission và thời hạn khác nhau.
- Có thể dùng khóa hoặc nhóm khóa khác nhau để giảm rủi ro token substitution.

Không chỉ dựa vào `typ` vì đây vẫn là header chưa xác minh. Sau khi chữ ký hợp lệ, kiểm tra claims và profile đầy đủ để bảo đảm token được dùng đúng nơi.

## 10. Bước 5 — Xác minh chữ ký và kiểm tra claims

Khi đã chọn được đúng public key và thuật toán, verifier xác minh chữ ký trên **JWS signing input gốc**:

~~~text
ASCII(BASE64URL(protected-header) + "." + BASE64URL(payload))
~~~

Không parse JSON rồi serialize lại header hoặc payload để tự dựng signing input, vì thay đổi khoảng trắng, thứ tự member hoặc cách biểu diễn có thể làm dữ liệu khác với phần đã ký. Dùng thư viện JOSE xử lý chuẩn compact serialization.

Sau khi chữ ký hợp lệ, tiếp tục kiểm tra:

- `iss`: khớp chính xác issuer đã chọn.
- `aud`: chứa audience của API/client nhận token theo quy tắc của profile.
- `exp`: token chưa hết hạn, tính cả clock skew có giới hạn.
- `nbf`: token đã đến thời điểm được phép sử dụng.
- `iat`: hợp lý theo policy nếu hệ thống kiểm tra thời điểm phát hành.
- Token type/profile: đúng loại token API mong đợi.
- Các claims nghiệp vụ như scope, role, tenant, subject và trạng thái phiên theo yêu cầu.

Chữ ký hợp lệ chỉ chứng minh nội dung không bị thay đổi và được tạo bằng khóa tương ứng. Nó không tự chứng minh token còn hiệu lực, đúng audience hay được phép thực hiện hành động.

## 11. Cache JWKS và làm mới khóa

Tải JWKS cho mọi request vừa tăng độ trễ vừa tạo phụ thuộc mạng không cần thiết. Verifier thường cache JWKS, nhưng cache phải có giới hạn và cơ chế làm mới rõ ràng.

### 11.1. Chính sách cache

- Tôn trọng HTTP caching directives phù hợp như `Cache-Control`, `max-age`, `ETag` và `Last-Modified` nếu server cung cấp.
- Đặt giới hạn TTL tối đa theo policy của hệ thống; không giữ JWKS vô thời hạn.
- Dùng conditional request khi có thể để giảm băng thông.
- Giới hạn kích thước response, số JWK, số issuer và dung lượng cache.
- Gắn cache với issuer/JWKS URI cụ thể; không dùng chung cache key chỉ dựa trên `kid`.
- Có cơ chế làm mới chủ động và xử lý lỗi endpoint.

### 11.2. Unknown `kid` và chống DoS

Attacker có thể gửi hàng nghìn JWT với `kid` ngẫu nhiên để buộc verifier gọi JWKS liên tục. Vì vậy:

1. Chỉ refresh từ endpoint đã tin cậy.
2. Giới hạn tần suất refresh theo issuer, không theo từng token riêng lẻ.
3. Gộp nhiều request đồng thời thành một lần refresh (request coalescing).
4. Áp dụng negative cache ngắn có giới hạn cho `kid` không tồn tại để tránh lặp request.
5. Có backoff khi endpoint lỗi và giới hạn số request ra ngoài.
6. Từ chối token nếu không tìm được khóa hợp lệ sau quy trình refresh cho phép.

Negative cache không được giữ quá lâu đến mức làm chậm việc nhận khóa mới sau rotation. TTL của nó cần cân bằng giữa khả năng chống DoS và tốc độ cập nhật khóa.

### 11.3. Khi JWKS endpoint không truy cập được

Chính sách cần phân biệt:

- **Khóa đã có trong cache còn trong thời hạn tin cậy:** có thể tiếp tục xác minh theo chính sách stale-cache đã định, nếu không có tín hiệu thu hồi hoặc sự cố bảo mật.
- **Khóa mới chưa có trong cache:** không thể xác minh token cần khóa đó; từ chối thay vì bỏ qua chữ ký.
- **Có thông báo khóa bị lộ/thu hồi:** không tiếp tục tin khóa cũ chỉ vì cache còn hạn; kích hoạt cơ chế chặn/refresh khẩn cấp.

Đặt giới hạn tối đa cho thời gian dùng cache cũ khi endpoint lỗi. Không cấu hình fallback vô thời hạn, vì verifier có thể tiếp tục tin khóa đã bị rút khỏi JWKS từ lâu.

## 12. Rotation và thời gian giữ khóa cũ trong JWKS

Trong rotation bình thường, issuer cần công bố public key mới trước khi ký token bằng private key mới. Trong thời gian chuyển tiếp, JWKS có thể chứa cả public key mới và cũ.

~~~mermaid
sequenceDiagram
    participant I as Issuer
    participant J as JWKS endpoint
    participant V as Verifier
    I->>J: Công bố public key B cùng public key A
    V->>J: Tải JWKS, cache A và B
    I->>I: Chuyển ký từ private A sang private B
    I->>V: Token mới mang kid B
    V->>V: Xác minh token A/B bằng đúng public key
    I->>J: Sau cửa sổ chuyển tiếp, rút public key A
    V->>J: Refresh và loại A khỏi cache tin cậy
~~~

### 12.1. Trình tự rotation

1. Sinh khóa B và bảo vệ private material.
2. Gán `kid` mới cho B; không tái sử dụng `kid` của A.
3. Thêm public JWK B vào JWKS trong khi A vẫn còn.
4. Chờ verifier có cơ hội tải JWKS mới; kiểm tra cache, độ trễ và consumer quan trọng.
5. Chuyển issuer sang ký bằng B; ngừng ký token mới bằng A.
6. Giữ public key A để xác minh token A còn hiệu lực.
7. Sau cửa sổ chấp nhận, rút A khỏi JWKS và làm mới cache.
8. Thu hồi quyền ký, xử lý backup và hủy private A theo quy trình.

### 12.2. Ước lượng thời gian giữ public key cũ

Đặt:

- `T_stop`: thời điểm issuer thực sự ngừng ký bằng A.
- `L_max`: tuổi thọ tối đa của token ký bằng A.
- `S`: clock skew được chấp nhận.
- `B`: bộ đệm vận hành có cơ sở cho độ trễ phát hành/phân phối.

Mốc tham khảo cho rotation bình thường:

~~~text
T_remove_A >= T_stop + L_max + S + B
~~~

Điều kiện là issuer thật sự đã ngừng ký bằng A, verifier cưỡng chế giới hạn `L_max`, và không có loại token/offline workflow đặc biệt kéo dài hơn. Cache JWKS cũng phải được tính vào kế hoạch phân phối và loại bỏ. Không dùng công thức này để trì hoãn thu hồi khi private key bị lộ.

### 12.3. Vì sao cần pre-publish?

Nếu issuer bắt đầu ký bằng B trước khi verifier biết public key B, token mới có thể bị từ chối do `kid` chưa tồn tại trong cache. Công bố public key trước và xác nhận consumer đã tải được giúp giảm lỗi xác minh trong thời điểm chuyển đổi.

## 13. Thu hồi khẩn cấp và khóa bị xâm phạm

Khi private key bị lộ hoặc có dấu hiệu bị sử dụng trái phép, rotation bình thường không đủ. Mục tiêu là **ngừng tin cậy khóa bị ảnh hưởng càng sớm càng tốt**.

Quy trình ứng cứu có thể gồm:

1. Xác định issuer, `kid`, loại khóa, môi trường và các verifier bị ảnh hưởng.
2. Thu hồi quyền gọi ký hoặc cô lập HSM/KMS/account đã bị xâm phạm.
3. Dừng phát hành token bằng khóa bị lộ.
4. Cấm `kid` bị ảnh hưởng tại verifier; đẩy cập nhật khẩn, làm mới cache hoặc vô hiệu hóa cache cũ theo cơ chế vận hành.
5. Sinh khóa thay thế từ môi trường tin cậy, công bố public key và chuyển ký.
6. Xử lý token đã ký bằng khóa bị lộ: từ chối chúng theo chính sách ngay cả khi `exp` chưa đến, hoặc yêu cầu xác thực lại.
7. Điều tra nguyên nhân, kiểm tra bản sao/backup, thu hồi thông tin xác thực liên quan và lưu bằng chứng kiểm toán.

**Chỉ xóa JWK khỏi JWKS chưa chắc đã thu hồi tức thời.** Verifier có thể giữ bản cache cũ hoặc dùng khóa được cấu hình cục bộ. Cần có cơ chế khẩn cấp để phát tín hiệu thu hồi đến các consumer quan trọng.

Một `kid` bị cấm nên được quản lý như trạng thái tin cậy riêng, có thể áp dụng ngay cả khi JWK vẫn còn trong cache. Không tái sử dụng cùng `kid` cho khóa thay thế.

## 14. Nhiều issuer, tenant và miền tin cậy

Hệ thống đa tenant hoặc liên kết nhiều identity provider dễ gặp lỗi chọn nhầm khóa nếu chỉ tìm theo `kid`.

Ví dụ:

| Issuer | `kid` | Public key | Được hệ thống tin cậy? |
| --- | --- | --- | --- |
| `https://id-a.example.test/` | `key-01` | Key A | Có |
| `https://id-b.example.test/` | `key-01` | Key B | Có |
| `https://attacker.example.test/` | `key-01` | Key X | Không |

`kid` giống nhau giữa issuer A và B là có thể xảy ra. Verifier phải phân vùng cache và lookup theo **issuer + JWKS nguồn + kid** (và profile nếu cần), không dùng `kid` làm định danh toàn cục.

Các nguyên tắc:

- Chỉ cho phép issuer được đăng ký và quản trị.
- Gắn mỗi issuer với JWKS URI, audience, thuật toán và profile riêng.
- Không cho một tenant tự thay JWKS URI của tenant khác.
- Kiểm tra `iss` cuối cùng sau khi xác minh chữ ký.
- Giữ tách biệt khóa giữa production, staging, test và các miền tin cậy khác nhau.
- Không cho token của issuer A được xác minh bằng khóa issuer B chỉ vì chữ ký hoặc `kid` có vẻ khớp.

## 15. JWS và JWE: chọn khóa theo đúng mục đích

JWKS có thể chứa khóa phục vụ nhiều mục đích JOSE. Cần xác định token đang xử lý là JWS (chữ ký/MAC) hay JWE (mã hóa) trước khi chọn thao tác.

| Mục đích | Metadata liên quan | Thao tác điển hình |
| --- | --- | --- |
| Xác minh JWS | `use="sig"`, `key_ops` có `verify`, `alg` phù hợp | Dùng public key hoặc secret được phép để xác minh chữ ký/MAC. |
| Giải mã JWE | `use="enc"`, `key_ops` có thao tác phù hợp như `decrypt` hoặc `unwrapKey` | Dùng private key hoặc secret để giải mã/giải bọc theo thuật toán. |
| Tạo JWS | `use="sig"`, `key_ops` có `sign` | Chỉ issuer/dịch vụ ký được quyền sử dụng private key hoặc secret. |

Không lấy khóa `enc` để xác minh chữ ký, hoặc lấy khóa `sig` để giải mã chỉ vì kiểu khóa trùng. Với một khóa có thể tham gia nhiều thao tác theo thiết kế đặc biệt, metadata và policy phải xác định rõ; nên tách khóa theo mục đích khi có thể để giảm nhầm lẫn.

## 16. Pseudocode chọn khóa và xác minh

Pseudocode dưới đây mô tả logic tổng quát, không phụ thuộc thư viện hay ngôn ngữ:

~~~text
function verifyJwt(token, trustedIssuerRegistry):
    header, untrustedClaims = parseJwtWithoutTrust(token)

    issuerValue = untrustedClaims.iss
    issuerConfig = trustedIssuerRegistry.findExact(issuerValue)
    if issuerConfig is null:
        reject("issuer is not trusted")

    if header.alg is missing:
        reject("missing signing algorithm")
    if header.alg not in issuerConfig.allowedAlgorithms:
        reject("algorithm is not allowed")
    if header.alg == "none":
        reject("unsigned token is not accepted")

    jwks = cache.getOrLoad(issuerConfig.jwksUri)
    if jwks cannot be loaded and no acceptable trusted cache exists:
        reject("trusted JWKS unavailable")

    if header.kid exists:
        candidates = jwks.keys with exact kid match
    else:
        candidates = jwks.keys matching the configured no-kid policy

    candidates = filter candidates by:
        compatible kty and valid key parameters
        use absent or use == "sig"
        key_ops absent or includes "verify"
        alg absent or alg == header.alg
        curve and other constraints allowed by policy
        key is not revoked and belongs to this issuer/profile

    if candidates is empty and kid was supplied:
        refresh trusted JWKS once, subject to rate limits
        repeat candidate selection

    key = require exactly one candidate
    if key is not unique:
        reject("missing or ambiguous signing key")

    if not verifyJwsSignature(token.originalSigningInput, key, header.alg):
        reject("invalid signature")

    claims = parseVerifiedClaims(token)
    require claims.iss exactly equals issuerConfig.issuer
    validate audience, expiration, not-before and token profile
    validate application permissions and session policy
    accept(claims)
~~~

Pseudocode chỉ để giải thích quyết định. Trong triển khai, dùng thư viện JWT/JOSE được duy trì; cấu hình rõ issuer, audience, thuật toán, key resolver và chính sách cache. Không tự viết phép toán chữ ký.

## 17. Tình huống thực tế và cách xử lý

| Tình huống | Nguyên nhân có thể | Hành động đúng |
| --- | --- | --- |
| JWT có `kid` mới, cache chưa có | Issuer vừa rotation. | Refresh JWKS tin cậy có giới hạn; nếu vẫn không có khóa thì từ chối. |
| JWT có `kid` không tồn tại sau refresh | Token giả, sai issuer hoặc publisher chưa đồng bộ. | Từ chối, ghi nhận sự kiện; không thử khóa khác. |
| JWKS có hai key cùng `kid` | Cấu hình publisher mơ hồ. | Từ chối ứng viên mơ hồ và cảnh báo publisher. |
| JWT không có `kid`, JWKS có nhiều key | Không xác định duy nhất khóa. | Chỉ chấp nhận nếu policy xác định đúng một ứng viên; nếu không, từ chối. |
| `alg` là `HS256`, JWK là RSA | Không tương thích kiểu khóa hoặc có dấu hiệu confusion. | Từ chối theo allowlist và ràng buộc key type. |
| JWK có `use="enc"` | Khóa dành cho mã hóa. | Không dùng cho xác minh JWS. |
| JWK có `key_ops=["sign"]` | Metadata không cho phép verify. | Không dùng làm khóa xác minh. |
| Endpoint JWKS tạm lỗi, key đã cache | Sự cố mạng hoặc publisher. | Dùng cache cũ chỉ trong giới hạn policy và nếu chưa bị thu hồi. |
| Endpoint JWKS tạm lỗi, `kid` mới chưa biết | Không có public key đáng tin để xác minh. | Từ chối token; không bỏ qua chữ ký. |
| Khóa bị lộ nhưng vẫn nằm trong cache | Cache chưa nhận cập nhật thu hồi. | Kích hoạt denylist/thu hồi khẩn và vô hiệu hóa tin cậy khóa. |
| JWT chứa `jku` trỏ đến địa chỉ nội bộ | Có thể là SSRF hoặc nguồn khóa giả. | Không fetch URL tùy ý từ header; chỉ dùng endpoint tin cậy. |
| Hai issuer có cùng `kid` | `kid` chỉ có phạm vi theo tập khóa. | Lookup và cache theo issuer, không theo `kid` toàn cục. |

## 18. Các lỗi thiết kế thường gặp

### Chỉ tìm `kid` mà không kiểm tra issuer

Hậu quả là khóa cùng tên từ issuer khác có thể bị chọn nhầm. Luôn xác định issuer và nguồn JWKS trước, rồi mới tra `kid`.

### Tin `alg` trong JWT

Hậu quả là attacker có thể chuyển thuật toán hoặc khai thác nhầm lẫn giữa khóa đối xứng và bất đối xứng. Luôn dùng allowlist từ cấu hình tin cậy.

### Tải `jku`/`x5u` trực tiếp

Hậu quả là SSRF, truy cập nguồn khóa do attacker kiểm soát hoặc vượt qua ranh giới mạng. Chỉ sử dụng endpoint đã được cấu hình/allowlist.

### Khi không tìm thấy khóa thì thử mọi khóa

Hậu quả là tốn CPU, hành vi mơ hồ và tăng khả năng DoS. Chọn khóa bằng quy tắc xác định; yêu cầu đúng một ứng viên.

### Không làm mới cache khi rotation

Hậu quả là token mới bị từ chối dù issuer đã công bố khóa. Có pre-publish, TTL và refresh có kiểm soát.

### Cache vô thời hạn

Hậu quả là verifier tiếp tục tin khóa cũ đã bị rút hoặc xâm phạm. Giới hạn TTL/staleness và hỗ trợ thu hồi khẩn cấp.

### Cho phép khóa public và private lẫn trong JWKS công khai

Hậu quả là lộ private key hoặc secret đối xứng. Kiểm tra schema công bố và chỉ xuất public material.

### Xác minh chữ ký nhưng bỏ qua claims

Hậu quả là token từ issuer/audience sai hoặc token hết hạn vẫn được chấp nhận. Luôn kiểm tra claims và token profile sau xác minh.

## 19. Checklist triển khai JWKS verifier

**Nguồn tin cậy**

- [ ] Issuer nằm trong danh sách cấu hình tin cậy.
- [ ] JWKS URI lấy từ cấu hình hoặc metadata đã xác thực.
- [ ] HTTPS, redirect, DNS, timeout và kích thước response được kiểm soát.
- [ ] Không fetch `jku`/`x5u` tùy ý từ JWT.

**Chọn khóa**

- [ ] `kid` được so khớp chính xác trong JWKS của đúng issuer.
- [ ] Không có nhiều ứng viên cùng thỏa điều kiện.
- [ ] Nếu thiếu `kid`, có policy xác định; không chọn khóa đầu tiên.
- [ ] `kty`, curve, tham số khóa, `use`, `key_ops`, `alg` phù hợp.
- [ ] Khóa chưa bị thu hồi và thuộc đúng token profile.

**Xác minh token**

- [ ] `alg` nằm trong allowlist; từ chối `none` trong profile yêu cầu chữ ký.
- [ ] Không fallback sang thuật toán/khóa khác khi verify thất bại.
- [ ] Chữ ký được xác minh trên signing input gốc bằng thư viện JOSE đáng tin.
- [ ] Kiểm tra `iss`, `aud`, `exp`, `nbf`, token type và quyền nghiệp vụ.

**Vận hành**

- [ ] Cache có TTL, giới hạn staleness và hỗ trợ conditional request.
- [ ] Unknown `kid` refresh có rate limit, coalescing và backoff.
- [ ] Rotation có pre-publish và cửa sổ giữ khóa cũ rõ ràng.
- [ ] Có đường thu hồi khẩn cấp và cơ chế cấm `kid` ngay cả khi cache chưa cập nhật.
- [ ] Log có issuer/`kid`/lý do từ chối phù hợp, không chứa private key hoặc token nhạy cảm.

## 20. Tài liệu chuẩn tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): định nghĩa JWK, JWKS và cách lựa chọn khóa theo ngữ cảnh.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, JWS signing input và chữ ký.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE và quan hệ với kiểu khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): quy tắc xác minh JWT, algorithm confusion và token substitution.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata của authorization server, bao gồm cách quảng bá endpoint khóa trong hệ sinh thái OAuth.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): cơ chế discovery issuer và metadata trong OpenID Connect.

**Ghi nhớ:** xác định issuer tin cậy trước; lấy JWKS từ nguồn gắn với issuer; chọn đúng một JWK bằng `kid` và metadata tương thích; áp dụng allowlist thuật toán; xác minh chữ ký; cuối cùng kiểm tra claims và token profile. Cache, rotation và thu hồi phải được thiết kế như một phần của cùng cơ chế tin cậy.

# Token không chữ ký, sai chữ ký hoặc không đúng định dạng mong đợi

## 1. Vì sao Resource Server phải từ chối các token này?

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, HTTP client thường gửi access token dưới dạng Bearer credential:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
```

Nếu API được cấu hình để nhận **JWT access token có chữ ký JWS**, chuỗi token phải thỏa nhiều điều kiện độc lập:

1. Được trình bày theo **định dạng** mà Resource Server mong đợi.
2. Sử dụng **thuật toán chữ ký được chấp nhận** và khóa xác minh từ nguồn đáng tin cậy.
3. Có **chữ ký hợp lệ** trên đúng dữ liệu đã phát hành.
4. Có **claim hợp lệ**, chẳng hạn issuer, audience, thời hạn và loại token phù hợp.
5. Mang **quyền truy cập** mà endpoint yêu cầu.

Một token không chữ ký, có chữ ký sai hoặc không đúng định dạng cần bị từ chối **trước khi ứng dụng dựa vào claim của nó để xác thực hoặc cấp quyền**. Chỉ đọc được payload JSON, chỉ thấy `sub` hoặc `scope`, hoặc chỉ nhận ra token “trông giống JWT” đều chưa chứng minh token đáng tin.

Ba nhóm lỗi gần nhau nhưng khác bản chất:

| Nhóm | Bản chất | Ví dụ | Kết quả với JWT Resource Server yêu cầu JWS hợp lệ |
| --- | --- | --- | --- |
| **Không chữ ký** | Không có bằng chứng mật mã được yêu cầu để bảo vệ nội dung. | JWT dạng unsecured với `alg: none`; JWS cần `RS256` nhưng phần signature trống. | Từ chối. |
| **Sai chữ ký** | Có trường signature nhưng phép xác minh không thành công. | Payload bị sửa; token ký bằng khóa khác; public key không tương ứng. | Từ chối. |
| **Không đúng định dạng mong đợi** | Token không thể được parser/decoder xử lý theo loại token đã cấu hình. | Opaque token đưa vào JWT decoder; JWE năm phần; chuỗi lỗi Base64URL/JSON. | Từ chối hoặc chuyển sang **cơ chế phù hợp** nếu API chủ động hỗ trợ dạng token đó. |

> **Phạm vi:** Bài học tập trung vào JWT được bảo vệ bằng JWS và cách Spring Security Servlet Resource Server xử lý. Token ví dụ chỉ minh họa cấu trúc, không chứa credential dùng được. **OIDC ID token** và **OAuth 2.0 access token** có thể đều là JWT nhưng không hoán đổi mục đích: API phải nhận access token phù hợp chính Resource Server của mình.

## 2. Nhận diện JWS Compact và hiểu chữ ký bảo vệ phần nào

JWT được ký thông dụng sử dụng **JWS Compact Serialization**, gồm ba đoạn nối bằng dấu chấm:

```text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
```

Ví dụ minh họa cấu trúc:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0.
eyJpc3MiOiJodHRwczovL2xvZ2luLmV4YW1wbGUudGVzdCJ9.
<base64url-encoded-signature>
```

Ở giao thức thực, tất cả nằm trên **một dòng**, không chứa dấu xuống dòng hoặc dấu ngoặc nhọn placeholder. Protected header có thể được giải mã thành:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "key-1"
}
```

Payload minh họa:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1893452400,
  "exp": 1893456000
}
```

Chữ ký bảo vệ chuỗi **signing input**:

```text
signingInput =
  BASE64URL(protected-header) + "." + BASE64URL(payload)
```

Với thuật toán bất đối xứng như `RS256`:

```text
signature = SIGN(issuerPrivateKey, signingInput)
valid     = VERIFY(issuerPublicKey, signingInput, signature)
```

Với thuật toán đối xứng như `HS256`, thao tác ký và kiểm tra đều dùng **cùng khóa bí mật HMAC**, không dùng cặp private/public key:

```text
signature = HMAC-SHA256(sharedSecret, signingInput)
valid     = VERIFY_MAC(sharedSecret, signingInput, signature)
```

**Không được nhầm Base64URL với mật mã:** Header và payload có thể được giải mã để đọc nội dung mà không cần khóa. Phải xác minh **chữ ký trên đúng phần header và payload đã nhận**, rồi mới xem những claim là dữ liệu đáng tin cậy.

### 2.1. Quy trình xử lý token tin cậy

```mermaid
flowchart TD
    R["HTTP request chứa Bearer token"] --> X{"Token được Bearer resolver chấp nhận?"}
    X -- "Không" --> E1["Lỗi truyền credential hoặc không có token"]
    X -- "Có" --> P{"Parser nhận ra JWS Compact phù hợp?"}
    P -- "Không" --> E2["Từ chối: malformed / unexpected format"]
    P -- "Có" --> A{"Thuật toán + khóa có được phép?"}
    A -- "Không" --> E3["Từ chối: alg/key không phù hợp"]
    A -- "Có" --> S{"Chữ ký xác minh thành công?"}
    S -- "Không" --> E4["Từ chối: signature invalid"]
    S -- "Có" --> C{"Các claim và token profile hợp lệ?"}
    C -- "Không" --> E5["Từ chối: issuer/audience/time/type..."]
    C -- "Có" --> Z["Tạo Authentication"]
    Z --> O{"Có quyền trên endpoint?"}
    O -- "Không" --> E6["403 hoặc access denied"]
    O -- "Có" --> OK["Cho phép tới xử lý nghiệp vụ"]
```

Đây là sơ đồ **khái niệm**: thư viện JOSE có thể kết hợp hoặc sắp xếp một số thao tác parser/validator khác nhau. Điều quan trọng là **không dùng claim chưa được xác minh làm quyết định truy cập**.

## 3. Trường hợp 1: token không có chữ ký

### 3.1. JWT với `alg: none`

Theo chuẩn JWT/JWS có khái niệm **Unsecured JWT**: protected header chỉ định thuật toán `none` và signature là chuỗi rỗng. Ví dụ:

```text
eyJhbGciOiJub25lIn0.eyJzdWIiOiJhbGljZSJ9.
```

Giải mã header và payload:

```json
{ "alg": "none" }
```

```json
{ "sub": "alice" }
```

JWT dạng này **không có xác thực mật mã** cho nội dung. Chuẩn có biểu diễn unsecured JWT cho những ngữ cảnh được bảo vệ bởi cơ chế ngoài khác, nhưng một OAuth 2.0 Resource Server được cấu hình **yêu cầu JWT access token có chữ ký** phải **từ chối `alg: none`**. Tuyệt đối không cho phép `none` chỉ để tránh phải quản lý khóa.

Nếu bất kỳ client nào có thể tự tạo:

```json
{
  "sub": "admin",
  "scope": "orders:write"
}
```

và API chấp nhận payload không chữ ký làm người dùng/quyền đã xác thực, attacker có thể tự gán vai trò hay scope của mình. Đây là lỗi nghiêm trọng ở **ranh giới xác thực token**.

### 3.2. Header khai thuật toán ký nhưng chữ ký vắng mặt

Ví dụ chuỗi có dạng:

```text
BASE64URL({"alg":"RS256"}).BASE64URL({"sub":"user-123"}).
```

Ví dụ này dùng ký hiệu biểu diễn cho dễ hiểu, **không phải chuỗi Base64URL thực**. Header nói dùng `RS256` nhưng phần signature trống. Token không thể vượt qua việc kiểm tra chữ ký RSA theo chính sách của một JWT Resource Server.

Không nên nhầm **signature rỗng của unsecured JWT** với **signature rỗng trong token khai thuật toán có chữ ký**:

- `alg: none` là kiểu JWS không chữ ký được định nghĩa riêng nhưng **không được chấp nhận** trong API yêu cầu JWS có chữ ký.
- `alg: RS256`, `PS256`, `ES256`, `HS256`... mà không có signature cần thiết thì **không hợp lệ**.

### 3.3. Vì sao không nên có “chế độ bỏ qua verify”?

Một số đoạn code minh họa JWT trên mạng chỉ Base64URL-decode payload hoặc gọi parser trong chế độ **không xác minh** để in claim. Cách này có thể hữu ích khi **quan sát định dạng trong môi trường kiểm thử**, nhưng không phải thao tác authentication.

Không được viết:

```java
// SAI: không có bước xác minh chữ ký / issuer / audience.
String[] pieces = bearerToken.split("\\.");
String payloadJson = new String(
        Base64.getUrlDecoder().decode(pieces[1]),
        StandardCharsets.UTF_8);
// Tiếp tục tin "scope", "sub" trong payloadJson để cấp quyền: KHÔNG AN TOÀN.
```

Token do attacker tự tạo có thể chứa JSON trông hoàn toàn hợp lệ. **Sự tồn tại của claim không chứng minh issuer đã cấp quyền đó.** Trong Spring Security Resource Server, hãy để `JwtDecoder` xác minh token trước khi xây dựng principal và authorities.

## 4. Trường hợp 2: có chữ ký nhưng xác minh không thành công

Đây là tình huống token có đầy đủ ba đoạn, nhưng chữ ký không vượt qua phép kiểm tra bằng khóa và thuật toán được tin cậy.

### 4.1. Payload bị thay đổi sau khi ký

Giả sử issuer phát access token với:

```json
{ "scope": "orders:read" }
```

Client hoặc attacker đổi payload thành:

```json
{ "scope": "orders:write" }
```

Nếu chỉ thay đoạn Base64URL(payload) mà giữ signature cũ, signing input đã đổi, chữ ký sẽ **không còn khớp**. Một API xác minh JWS đúng cách phải từ chối token trước khi coi `orders:write` là quyền.

Tương tự, việc sửa `iss`, `aud`, `sub` hay `exp` trong payload cũng làm thay đổi signing input. Không thể kéo dài tuổi thọ token bằng cách sửa `exp` rồi giữ nguyên signature.

### 4.2. Token được ký bằng khóa không tương ứng

Ví dụ issuer ký bằng private key A, nhưng Resource Server thử public key B. Nếu A/B không cùng key pair, chữ ký sẽ thất bại. Nguyên nhân có thể là:

- API cấu hình sai issuer hoặc JWKS URL.
- Authorization Server đã **xoay khóa**, nhưng public key mới chưa được Resource Server lấy/cập nhật.
- Token bị phát hành bằng khóa thử nghiệm hoặc một key pair khác.
- Các bên dùng khóa cùng tên nhưng thực tế là hai vật liệu khóa khác nhau.
- Client gửi token từ một môi trường khác, ví dụ staging token vào production API.

**Không khắc phục bằng cách bỏ xác minh chữ ký.** Cần tìm issuer, key ID và nguồn khóa chính xác.

### 4.3. Thuật toán và loại khóa không phù hợp

Ví dụ token khai `alg: HS256` nhưng Resource Server chỉ tin JWT ký bằng `RS256`. Hai thuật toán này có mô hình khóa hoàn toàn khác nhau:

| JWS `alg` | Vật liệu bên phát hành dùng để ký | Vật liệu Resource Server cần để xác minh |
| --- | --- | --- |
| `HS256` | Khóa bí mật HMAC dùng chung. | **Chính secret HMAC** đó. |
| `RS256` | RSA private key. | RSA public key tương ứng. |
| `PS256` | RSA private key với thuật toán RSASSA-PSS. | RSA public key tương ứng, đúng PSS parameters/profile. |
| `ES256` | EC P-256 private key. | EC P-256 public key tương ứng. |
| `EdDSA` | Private key thuộc EdDSA profile được hỗ trợ. | Public key EdDSA phù hợp. |
| `none` | Không có chữ ký. | **Không chấp nhận** khi hợp đồng yêu cầu access token ký. |

Token tự khai `alg` trong header. **Đây là thông tin đầu vào chưa xác thực**; Resource Server phải có **chính sách thuật toán cho phép ở phía server**. Không được suy ra một thuật toán tùy ý từ chuỗi token rồi tự chuyển cơ chế xác minh để phù hợp.

Một lỗi kiểu **algorithm confusion** từng gặp ở các bộ xác minh tự triển khai là chấp nhận JWT tự khai `HS256` nhưng lấy RSA public key làm secret HMAC. Vì public key vốn công khai, attacker có thể tự tạo MAC giả nếu verifier dùng sai khóa. Hãy sử dụng thư viện JOSE đáng tin cậy và ràng buộc chặt thuật toán với đúng loại khóa.

### 4.4. JWT đã được ký hợp lệ nhưng gửi sai Resource Server

Ví dụ issuer phát JWT ký đúng, nhưng `aud` là `payments-api` trong khi API đang kiểm tra token dành cho `orders-api`. Ở đây:

- **Chữ ký có thể hoàn toàn hợp lệ**.
- **Claim validation thất bại** vì token không hướng tới Resource Server này.

Đừng gọi tất cả phản hồi 401 là “chữ ký sai”. Chữ ký sai và claim sai có thể cùng được báo tới client là `invalid_token` nhưng có hướng điều tra khác nhau.

## 5. Trường hợp 3: token không đúng định dạng mong đợi

Resource Server phải biết loại credential nó xử lý. Một API được cấu hình JWT sẽ dự kiến một **JWS/JWT với cấu trúc và header phù hợp**, còn API dùng opaque token sẽ có cơ chế introspection riêng.

### 5.1. Những lỗi cấu trúc thường gặp

| Ví dụ đầu vào | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| `abc.def` | Chỉ hai đoạn. | Không có đủ ba đoạn cho JWS Compact. |
| `abc.def.ghi.jkl` | Bốn đoạn. | Không khớp cấu trúc JWS Compact ba đoạn hay JWE Compact năm đoạn. |
| `abc.def.ghi` | Có ba đoạn nhưng có thể không phải JWT. | **Số đoạn chưa đủ**: cần Base64URL hợp lệ, JSON hợp lệ, JOSE header, chữ ký và claims đúng. |
| `abc.def.ghi.jkl.mno` | Năm đoạn. | Có thể là **JWE Compact**, không phải JWS ba đoạn; cần cơ chế giải mã JWE riêng nếu được hỗ trợ. |
| `randomOpaqueToken123` | Không có cấu trúc JWS. | Có thể là opaque access token; phải introspect theo hợp đồng provider thay vì cố JWT-decode. |
| Chuỗi chứa ký tự không được chấp nhận trong Base64URL | Decode/parser thất bại. | Không thể xem như JWT hợp lệ. |
| Header/payload decode được nhưng không phải JSON phù hợp | Không đáp ứng JSON structure/profile. | Từ chối tại parser/decoder. |
| JSON header thiếu `alg` khi chữ ký bắt buộc | Không thể xác định JWS algorithm theo yêu cầu. | Từ chối; không tự chọn thuật toán dựa trên payload. |
| Header khai `alg: none` nhưng API chỉ nhận JWT ký. | Không có bảo vệ chữ ký theo chính sách. | Từ chối. |
| Signature thiếu hoặc bị cắt ngắn | Không thể xác minh chữ ký đúng. | Từ chối. |

Một JWT được ký thông dụng phải có **hai dấu chấm** phân cách ba đoạn, nhưng không nên tự viết rule “đếm hai dấu chấm là token hợp lệ”. Chính thư viện JOSE phải parse và xác minh format, algorithm, key và signature.

### 5.2. Opaque access token được gửi đến JWT decoder

Authorization Server có thể phát access token như:

```text
Xg32sAj4hQ9m...opaque-value...
```

Resource Server cấu hình `oauth2ResourceServer().jwt()` sẽ cố xử lý nó như JWT/JWS và thường từ chối vì không đúng định dạng. **Opaque token không sai chỉ vì không phải JWT**: nó có thể là credential hoàn toàn hợp lệ với Authorization Server, nhưng cần **token introspection** hoặc cơ chế xác thực phù hợp.

Trong Spring Boot Resource Server, hai kiểu cấu hình điển hình:

**JWT access token:**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
```

**Opaque access token:**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: resource-server
          client-secret: replace-with-secure-secret
```

Đây là **hai lựa chọn cấu hình minh họa**, không phải hai khối luôn đặt đồng thời để Spring tự đoán loại token. Credential introspection phải được lấy từ secret manager hoặc môi trường an toàn khi vận hành thật.

Khi cần chấp nhận cả hai định dạng trong cùng hệ thống, phải chủ động xác định **luồng xác thực và ranh giới tin cậy**: tách Resource Server/endpoint/filter chain hoặc thiết kế `AuthenticationManagerResolver`/cơ chế lựa chọn đáng tin cậy. Không chỉ thêm cả JWT và opaque provider vào một `ProviderManager` rồi giả định thứ tự fallback bảo đảm an toàn.

### 5.3. JWT được mã hóa bằng JWE

JWT có thể được bảo vệ bằng **JWE (JSON Web Encryption)**. JWE Compact thường có **năm phần**, khác với JWS Compact ba phần:

```text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
```

Một API chỉ có **JWT signature decoder** sẽ không tự hiểu một JWE token năm đoạn, dù JWE hợp lệ theo ngữ cảnh phát hành. Nếu có yêu cầu nhận encrypted JWT, cần triển khai hỗ trợ giải mã JWE với khóa/quy tắc phù hợp và thực thi các kiểm tra bảo vệ, issuer, audience và claims theo hợp đồng. Nếu hệ thống dùng **nested JWT**, phải xử lý đúng thứ tự ký/mã hóa và validate từng lớp theo profile.

**Không chuyển sang decode bằng chuỗi thủ công** hoặc bỏ qua lớp bảo vệ để “lấy payload”. Sự khác biệt giữa JWS và JWE là một thay đổi quan trọng của hợp đồng access token.

### 5.4. Bỏ nhầm tiền tố `Bearer` vào decoder

Header HTTP hợp lệ:

```http
Authorization: Bearer eyJ...signed.jwt...
```

`JwtDecoder` nhận **chuỗi token** đã được trích ra, không nhận nguyên nội dung `"Bearer eyJ..."`. Trong Spring Security, `BearerTokenAuthenticationFilter` và `BearerTokenResolver` thường xử lý việc tách scheme. Nếu tự viết code gọi decoder bằng nguyên header, parser có thể báo token sai định dạng.

Đây là lý do nên dùng cơ chế Resource Server sẵn có thay vì tự parse header `Authorization` trong controller.

### 5.5. JSON hợp lệ chưa chắc đúng token profile

Token có thể là một JWS hợp lệ, được issuer ký đúng, nhưng không phải **loại access token mà API chấp nhận**:

- **OIDC ID token** có `aud` là OIDC client ID, không phải resource API.
- Access token thuộc resource khác có `aud` khác.
- JWT chứa claim quyền sai kiểu hoặc thiếu claim bắt buộc.
- Token có `typ` hoặc các claim không đáp ứng profile đã được thỏa thuận, ví dụ một hệ thống yêu cầu JWT Access Token Profile.

Khi đó định dạng JOSE có thể đúng nhưng **hợp đồng token** sai. Hệ thống phải phân biệt **lỗi parse**, **lỗi chữ ký**, **lỗi claim** và **lỗi authorization**.

## 6. Kiểm tra `alg`, `kid` và JWKS đúng cách

Một JWS protected header điển hình:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "rsa-2026-02"
}
```

Header `typ: at+jwt` là ví dụ theo hướng **OAuth 2.0 JWT Access Token Profile**; không phải mọi JWT access token của mọi issuer đều có giá trị `typ` này. Chính sách bắt buộc về `typ` phải dựa trên profile/hợp đồng issuer đã công bố.

Để xác minh JWS, Resource Server cần:

1. Có danh sách **issuer đáng tin cậy** và **thuật toán cho phép**.
2. Lấy **JWKS từ endpoint đã cấu hình/tìm qua discovery đáng tin cậy**, không từ URL do token tùy ý chỉ định.
3. Dùng `kid` (nếu có) làm **gợi ý tìm khóa** trong tập khóa của issuer phù hợp, cùng điều kiện loại khóa và thuật toán.
4. Kiểm tra chữ ký bằng public key tương ứng (hoặc shared secret nếu mô hình HMAC đã được thiết kế).
5. Sau đó áp dụng issuer, audience, thời hạn, token profile và quyền.

`kid` không phải chứng chỉ tin cậy và không tự chứng minh token do issuer phát hành. Attacker có thể tạo header tùy ý với `kid: "admin"` hoặc `jku: "https://attacker.example/keys"`. Resource Server không được dùng `kid` làm tên file/đường dẫn tùy ý hoặc tự tải `jku`, `x5u` từ token chưa xác thực mà không có kiểm soát nguồn nghiêm ngặt.

### 6.1. Hiện tượng sau khi xoay khóa

Giả sử issuer ký token cũ bằng private key A, mới bằng private key B. JWKS công bố các public key A và B trong một khoảng chuyển tiếp:

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS
    participant API as Resource Server
    AS->>JWKS: Công bố public key B bên cạnh A
    AS-->>API: JWT mới (kid=B), ký bằng private key B
    API->>JWKS: Tải/làm mới public keys theo chính sách cache
    JWKS-->>API: Public key A và B
    API->>API: Chọn B và xác minh chữ ký
    API->>API: Kiểm tra claims/quyền
```

Nếu API chưa lấy được key B do cache, network hoặc issuer chưa công bố đúng JWKS, token mới có thể bị từ chối dù issuer ký hợp lệ. Hướng xử lý là đồng bộ key rotation, cache và cấu hình JWKS. Không nên tự động chấp nhận signature chưa xác minh chỉ vì header có `kid` mới.

Ngược lại, xóa public key A quá sớm có thể làm token cũ **chưa hết hạn** bị từ chối. Kế hoạch xoay khóa cần xét thời hạn access token, thời gian cache, độ lệch đồng hồ và thời gian phân phối.

### 6.2. Khóa xác minh khác khóa ký

| Thuật toán | Bên phát hành ký bằng | Resource Server xác minh bằng | Có an toàn nếu công khai vật liệu xác minh? |
| --- | --- | --- | --- |
| `RS256` / `PS256` | RSA private key | RSA public key | Có, sau khi gắn với issuer được tin cậy. |
| `ES256` | EC private key | EC public key | Có, sau khi gắn với issuer được tin cậy. |
| `HS256` | Shared HMAC secret | Cùng shared HMAC secret | **Không**, vì biết secret đồng nghĩa có khả năng tạo MAC. |

Nếu API xác minh `RS256`, nó **không cần giữ private key của Authorization Server**. Nếu API xác minh `HS256`, nó giữ secret bí mật và quyền tạo chữ ký về mặt mật mã không thể tách khỏi quyền xác minh. Không công bố HMAC secret trong public JWKS.

## 7. Spring Security xử lý token lỗi trong Servlet Resource Server

Một cấu hình API tối thiểu:

```java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Với JWT Resource Server, luồng thường là:

```mermaid
sequenceDiagram
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as JwtAuthenticationProvider
    participant D as JwtDecoder
    participant A as AuthorizationFilter
    C->>F: Authorization: Bearer <token>
    F->>F: Trích xuất Bearer credential
    F->>M: authenticate(BearerTokenAuthenticationToken)
    M->>P: Chuyển tới JWT provider phù hợp
    P->>D: decode(token)
    alt Malformed, alg none, wrong signature, invalid claims
        D-->>P: JwtException / validation failure
        P-->>F: AuthenticationException
        F-->>C: 401 và WWW-Authenticate Bearer
    else JWT được xác minh
        D-->>P: Jwt
        P-->>F: Authentication đã xác thực
        F->>A: SecurityContext
        A-->>C: Cho phép hoặc 403 theo quyền
    end
```

`BearerTokenAuthenticationFilter` không phải bộ giải mã JWT. Nó nhận credential và gọi `AuthenticationManager`. `JwtAuthenticationProvider` sử dụng `JwtDecoder` để parse, xác minh và validate JWT. Nếu thất bại, Spring Security chuyển lỗi xác thực thành phản hồi Bearer tương ứng.

### 7.1. Cấu hình decoder và validator rõ ràng

Ví dụ API chỉ nhận JWT có chữ ký `RS256` từ một issuer, audience `orders-api`:

```java
@Configuration
class JwtDecoderConfig {

    private static final String ISSUER =
            "https://login.example.test/realms/demo";
    private static final String JWKS =
            "https://login.example.test/realms/demo/protocol/openid-connect/certs";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(JWKS)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Token audience is not this API",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));

        return decoder;
    }
}
```

Ví dụ sử dụng các API như `NimbusJwtDecoder`, `SignatureAlgorithm`, `JwtValidators`, `OAuth2TokenValidator`, `OAuth2TokenValidatorResult`, `DelegatingOAuth2TokenValidator` và `OAuth2Error`. Các import được lược bớt; cần đối chiếu package/builder với phiên bản Spring Security thực tế. JWKS URL là **ví dụ theo kiểu provider**, đường dẫn chính xác phải lấy từ metadata/hợp đồng issuer đáng tin cậy. Nếu đã có bean `JwtDecoder` riêng, cấu hình Boot tự động có thể không còn quyết định decoder; hãy quản lý rõ chính bean được dùng.

Điểm đáng chú ý:

- `withJwkSetUri(...)` trỏ đến **nguồn khóa xác minh đáng tin cậy**; không lấy từ token chưa xác thực.
- `jwsAlgorithm(SignatureAlgorithm.RS256)` ràng buộc algorithm được chấp nhận theo ví dụ.
- `JwtValidators.createDefaultWithIssuer(...)` bao gồm các validator mặc định tương ứng cùng kiểm tra issuer; không chỉ xác minh signature.
- Validator audience chỉ chấp nhận token có `aud` hướng đến `orders-api`.
- Sau khi decoder thành công, authorization vẫn cần kiểm tra `SCOPE_orders:read` và các điều kiện dữ liệu.

Không được bỏ audience validator để chữa tình trạng ID token có chữ ký đúng nhưng API trả 401. OIDC ID token được cấp cho client và không thay access token để gọi resource API.

### 7.2. Nếu dùng HMAC `HS256`

Nếu hợp đồng token thực sự yêu cầu `HS256`, decoder cần **shared secret** đủ mạnh thay vì JWKS chứa public key RSA:

```java
@Bean
JwtDecoder hmacJwtDecoder(SecretKey sharedSecret) {
    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withSecretKey(sharedSecret)
                    .macAlgorithm(MacAlgorithm.HS256)
                    .build();

    decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(
                    "https://issuer.example.test"));
    return decoder;
}
```

Đây là **phương án thay thế** cho JWT decoder bất đối xứng, không nên đăng ký cả hai bean decoder như ví dụ độc lập mà không có cơ chế lựa chọn cụ thể. Shared secret phải được tạo ngẫu nhiên đủ mạnh, bảo vệ bằng secret manager và được cấp quyền tối thiểu. Ví dụ HMAC cũng cần **audience validator** riêng nếu API yêu cầu, tương tự mục 7.1; đừng chỉ kiểm tra issuer.

### 7.3. Khi nào dùng JwtDecoder và khi nào dùng introspection?

| Điều Authorization Server phát hành | Cơ chế Resource Server thường dùng |
| --- | --- |
| JWT access token ký JWS, có JWKS/public keys hoặc HMAC secret phù hợp | `JwtDecoder` và validators. |
| Opaque access token | `OpaqueTokenIntrospector`/token introspection. |
| Encrypted JWT (JWE) | Bộ giải mã JWE được thiết kế/cho phép theo hợp đồng; không phải mặc định JWT signature decoder. |
| OIDC ID token | OIDC Client xác minh để xử lý đăng nhập; **không** là Bearer access token API. |

Một chuỗi token không đúng định dạng JWT **không tự chứng minh token giả mạo**; nó có thể là token hợp lệ nhưng được đưa sai loại Resource Server. Trong mọi trường hợp, API không nên chấp nhận token nếu chưa có cơ chế xác minh đúng hợp đồng.

## 8. Lỗi 401, 400 và 403: đừng đánh đồng

Theo OAuth 2.0 Bearer Token Usage, phản hồi khác nhau tùy giai đoạn:

| Tình huống | Kết quả điển hình | `WWW-Authenticate` điển hình |
| --- | --- | --- |
| Không gửi Bearer credential và endpoint yêu cầu đăng nhập | **401 Unauthorized** | `Bearer`, thường không có `error`. |
| Có JWT nhưng `alg: none` khi API bắt buộc ký | **401 Unauthorized** | `Bearer error="invalid_token"`. |
| Có JWT chữ ký sai/hết hạn | **401 Unauthorized** | `Bearer error="invalid_token"`. |
| Có Bearer token nhưng JWT decoder không parse được | **401 Unauthorized** | `Bearer error="invalid_token"`. |
| Sai cú pháp phương thức gửi Bearer credential hoặc dùng nhiều cách truyền token trong ngữ cảnh bị cấm | Thường **400 Bad Request** | `Bearer error="invalid_request"`. |
| Access token được xác minh nhưng thiếu scope endpoint | **403 Forbidden** | Có thể có `Bearer error="insufficient_scope"`. |

Ví dụ một token sai chữ ký:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Server có thể thêm mô tả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The token is invalid"
```

`error_description` là thông tin tùy chọn và không nên được client phụ thuộc theo đúng từng chữ. Việc phản hồi chi tiết “signature mismatch”, “unknown key ID” hoặc “issuer X not trusted” cho bên ngoài có thể gây rò rỉ thông tin bảo mật. API thường trả mã lỗi tổng quát; chi tiết kỹ thuật được ghi vào log nội bộ đã kiểm soát.

**Với `permitAll()`:** Trong cùng SecurityFilterChain, endpoint công khai có thể cho phép request **không có token** nhưng vẫn trả 401 khi client **gửi một Bearer token lỗi**: Bearer filter có thể từ chối credential trước bước phân quyền. `permitAll()` không mặc nhiên tắt bộ lọc xác thực.

## 9. Phân biệt lỗi parser, chữ ký, claims và authorization

Khi xử lý thực tế, ghi nhớ **bốn lớp trách nhiệm**:

| Lớp | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Parsing/format** | Chuỗi có hai đoạn, payload JSON lỗi, token JWE gửi vào JWS decoder. | Không thể xây JWT theo định dạng được phép, từ chối credential. |
| **Signature/JOSE** | `alg: none`, thuật toán không cho phép, `kid` không tìm được khóa, signature mismatch. | Không xác minh được nguồn phát hành/tính toàn vẹn, từ chối. |
| **Claim/profile validation** | `iss` sai, `aud` khác resource, `exp` quá hạn, ID token thay access token. | Chữ ký có thể đúng nhưng token vẫn không được chấp nhận. |
| **Authorization** | Token được xác minh nhưng thiếu `orders:write` hoặc không có quyền tenant. | Thông thường 403 hoặc quyết định từ chối theo chính sách dữ liệu. |

Spring Security Resource Server có thể gộp nhiều lỗi của ba lớp đầu thành `AuthenticationException` và phản hồi HTTP `401 invalid_token`. Muốn tìm nguyên nhân, cần quan sát **nguồn exception phù hợp** trong môi trường kiểm soát mà không tiết lộ token.

### 9.1. Những exception thường gặp trong hệ sinh thái Spring

| Kiểu exception | Gợi ý ý nghĩa |
| --- | --- |
| `JwtException` | Họ lỗi JWT ở decoder/validation. |
| `BadJwtException` | JWT không được chấp nhận, có thể do cấu trúc, chữ ký hoặc lý do JWT không hợp lệ khác. |
| `JwtValidationException` | Claim validators từ chối token; thường có các `OAuth2Error` giải thích lỗi validation. |
| `OAuth2AuthenticationException` | Lỗi trong quá trình authentication OAuth 2.0/Bearer. |
| `BearerTokenError` | Chứa thông tin lỗi Bearer như `invalid_token` hoặc `invalid_request` ở lớp tương ứng. |

Không nên viết logic business dựa trên đúng thông điệp exception của thư viện JOSE; thông điệp có thể thay đổi giữa phiên bản. Phân loại dựa trên **giai đoạn xử lý, exception type và error code được chuẩn hóa**, cùng log chi tiết nội bộ được kiểm soát.

## 10. Các ví dụ HTTP dùng để phân biệt lỗi

Các request sau giả định:

- API được cấu hình JWT Resource Server.
- Issuer tin cậy là `https://login.example.test`.
- Audience bắt buộc là `orders-api`.
- Chỉ `RS256` được cho phép trong ví dụ.
- Endpoint `GET /api/orders` yêu cầu `SCOPE_orders:read`.

### Tình huống A: không gửi token

```bash
curl -i https://api.example.test/api/orders
```

Phản hồi thường là `401` với Bearer challenge không có `invalid_token`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

### Tình huống B: gửi token không chữ ký

```bash
curl -i \
  -H 'Authorization: Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJhbGljZSJ9.' \
  https://api.example.test/api/orders
```

Token ví dụ có `alg: none`; API yêu cầu `RS256` nên phải từ chối, điển hình `401 invalid_token`.

### Tình huống C: chuỗi không phải JWT/JWS mong đợi

```bash
curl -i \
  -H 'Authorization: Bearer not-a-jws' \
  https://api.example.test/api/orders
```

Khi Bearer resolver nhận chuỗi credential và chuyển cho JWT decoder, nó không thể giải mã thành JWS/JWT được chấp nhận. Kết quả điển hình là `401 invalid_token`. Nếu request sai cú pháp ở **mức truyền Bearer token**, loại lỗi có thể khác.

### Tình huống D: token ký đúng, nhưng sai audience

Client gửi một JWT `RS256` hợp lệ từ issuer đáng tin cậy, nhưng `aud: ["payments-api"]`. Signature pass, audience validator fail → **401 invalid_token**. Không nên chấp nhận token chỉ vì decoder đã tải đúng JWKS.

### Tình huống E: access token đúng nhưng thiếu scope

JWT `RS256` hợp lệ, `aud: ["orders-api"]`, nhưng scope chỉ là `orders:read`; client gọi `POST /api/orders` yêu cầu `orders:write`. Authentication thành công rồi authorization từ chối → thường **403 insufficient_scope**. Đổi JWT decoder không cấp thêm quyền cho token.

### Tình huống F: client gửi ID token

Client đã đăng nhập OIDC và gửi `id_token` thay vì `access_token` đến API. ID token có thể được ký bằng cùng JWKS, nhưng `aud` thường là OIDC client ID. API phải từ chối nếu không phù hợp audience/token profile. Client cần lấy **access token đúng resource**, không sửa validation để nhận ID token.

## 11. Kiểm thử đúng điều mình cần kiểm tra

Một test parser và một test security endpoint kiểm tra những lớp khác nhau. Với JWT Resource Server, có thể tổ chức tình huống kiểm thử như sau:

| Kiểm thử | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Unsigned token | JWS với `alg: none`, signature rỗng. | Từ chối authentication. |
| Empty signature | Header khai `RS256` nhưng không có signature. | Từ chối authentication. |
| Tampered payload | Token `RS256` được ký hợp lệ, sau đó thay đổi payload nhưng giữ signature cũ. | Từ chối chữ ký. |
| Tampered header | Thay `alg` hoặc `kid` sau khi ký mà không ký lại. | Từ chối do algorithm/key/signature validation. |
| Wrong public key | Token ký bằng private key A, API chỉ có public key B. | Từ chối chữ ký. |
| Unexpected algorithm | API cho phép `RS256` nhưng token ký bằng `HS256` hoặc `ES256`. | Từ chối theo allowlist. |
| Malformed compact token | Token thiếu dấu chấm, sai Base64URL hoặc JSON. | Từ chối parser/decoder. |
| Opaque token vào JWT decoder | Token opaque từ issuer. | Từ chối JWT decoder; nếu hệ thống hỗ trợ opaque, xử lý ở luồng introspection riêng. |
| JWE vào JWS decoder | JWE Compact năm đoạn. | Từ chối nếu không có JWE profile/decoder phù hợp. |
| Valid signature, wrong issuer | JWT có chữ ký xác minh được nhưng `iss` sai. | Từ chối validator. |
| Valid signature, wrong audience | JWT cho resource khác. | Từ chối validator. |
| Valid signature, expired token | `exp` quá hạn. | Từ chối validator. |
| Valid access token, missing scope | Token hợp lệ nhưng thiếu authority endpoint. | Xác thực thành công, authorization từ chối. |

### 11.1. Phân biệt test mock JWT và test xác minh chữ ký thật

`spring-security-test` cung cấp các tiện ích MockMvc như `jwt()` để gắn một `JwtAuthenticationToken` giả lập vào request. Chúng rất hữu ích để kiểm tra **authorization dựa trên authorities/claims đã được giả lập**, nhưng **không phải lúc nào cũng đi qua JwtDecoder và xác minh chữ ký JWS thật**.

Vì thế:

- Dùng `jwt()` trong MockMvc khi muốn thử endpoint yêu cầu `SCOPE_orders:read` hay role cụ thể.
- Muốn chứng minh **`alg: none`, signature mismatch, malformed JWT bị từ chối**, phải kiểm thử đường xác thực thực tế với `JwtDecoder`/filter chain hoặc test đơn vị decoder sử dụng token được dựng/ký tương ứng.
- Test nên có **key pair thử nghiệm**, public JWKS/decoder cấu hình đúng và token cố ý ký sai hoặc bị sửa.
- Không dùng khóa production hoặc access token của người dùng thật trong fixture.

Ví dụ **kiểm tra quyền bằng MockMvc** (minh họa authorization, không khẳng định đã test decoder):

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
```

Trong một bài kiểm thử signature thực sự, không được dùng ví dụ `jwt()` trên làm bằng chứng endpoint từ chối token không chữ ký: test đang đưa authentication giả lập vào request.

## 12. Chẩn đoán trong vận hành

Khi API nhận 401, trước tiên xác định request thuộc trường hợp **thiếu credential, sai format, sai chữ ký hay sai claim**:

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| Request không có `Authorization` | Client có gắn header đúng không? Proxy/gateway có chuyển tiếp không? |
| Header có Bearer nhưng API báo không decode được JWT | Token có đúng là JWT access token? Có đang gửi opaque/JWE/ID token hoặc cả chữ `Bearer` vào decoder không? |
| JWT có ba đoạn nhưng decoder báo malformed | Header/payload có Base64URL/JSON hợp lệ không? Token có bị cắt, thêm ký tự hoặc hỏng trong quá trình truyền không? |
| Token có `alg: none` | Vì sao client dùng unsecured JWT? API phải giữ policy yêu cầu token ký. |
| JWT ký đúng tại issuer nhưng API báo signature fail | So sánh issuer, JWKS URL, `kid`, key rotation, môi trường, thuật toán và dữ liệu token có bị sửa không. |
| Lỗi chỉ xuất hiện sau xoay khóa | Public key mới đã công bố trước khi issuer ký chưa? Cache JWKS có làm mới đúng không? |
| JWT signature pass nhưng API vẫn 401 | Xem validator của issuer, audience, `exp`/`nbf`, token type và các claim bắt buộc. |
| JWT pass authentication nhưng API trả 403 | Scope/authority mapping, method security và policy tenant/ownership. |
| Một endpoint công khai trả 401 khi client gửi Bearer token hỏng | Bearer authentication filter có đang xử lý token trước `permitAll()` không? |

Có thể bật log phục vụ chẩn đoán **trong môi trường kiểm soát**:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Với production, cần chính sách log phù hợp. Không ghi **nguyên access token**, ID token, refresh token, private key, shared HMAC secret hoặc toàn bộ claim chứa dữ liệu nhạy cảm vào log. Nên dùng request ID, loại lỗi, issuer đã xác minh, key ID đã thẩm định và mã kết quả đã chuẩn hóa khi cần.

### 12.1. Hướng xử lý theo từng nguyên nhân

| Nguyên nhân | Biện pháp đúng |
| --- | --- |
| Client gửi nhầm ID token | Lấy access token có audience/scope đúng API. |
| Client nhận opaque token, API cấu hình JWT | Thống nhất loại access token với issuer hoặc cấu hình introspection phù hợp. |
| JWT bị sửa trong transit/storage | Sửa luồng truyền/lưu token; không bỏ verify. |
| JWT ký bằng khóa mới, API chưa có public key | Sửa JWKS/key rotation và đồng bộ cache. |
| Thuật toán issuer thay đổi | Cập nhật hợp đồng và allowlist thuật toán an toàn theo kế hoạch; không chấp nhận mọi `alg` do token đưa ra. |
| JWT có `alg: none` | Cấu hình issuer phát signed access token hợp lệ; giữ chính sách từ chối unsigned. |
| JWT đúng chữ ký nhưng `aud` sai | Xin token dành cho đúng resource; giữ audience validation. |
| JWT đúng nhưng `scope` không đủ | Xin/cấp scope hợp lệ hoặc xử lý quy tắc phân quyền; không thay decoder. |

Không nên tạo vòng lặp **401 → refresh → 401** khi nguyên nhân là sai định dạng hay sai audience. Refresh chỉ có ích khi token đã hết hạn và client có quyền sử dụng refresh flow; nó không tự sửa hợp đồng token hoặc cấu hình JWKS.

## 13. Những anti-pattern bảo mật cần tránh

### 13.1. Chỉ `decode` payload để tạo user

Đọc JSON từ Base64URL không xác thực chữ ký. Code ứng dụng không được lấy `sub`/`scope` chưa được xác minh để tạo `Authentication` có `authenticated=true`.

### 13.2. Chấp nhận `alg: none` để hỗ trợ “token phát từ nội bộ”

Không có chữ ký nghĩa là payload có thể bị thay đổi mà không bị phát hiện. Trong API nhận Bearer JWT qua mạng, phải yêu cầu chữ ký và thuật toán đã phê duyệt.

### 13.3. Tin mọi `kid`, `jku` hay URL key trong header

Header JWT do phía gửi kiểm soát trước khi xác minh. Chỉ chọn khóa trong tập tin cậy gắn với issuer đã cấu hình, không tải khóa tùy ý từ URL được token đề xuất.

### 13.4. Tự động chấp nhận cả HMAC và RSA bằng cùng dữ liệu key

HMAC secret và RSA public key có ý nghĩa khác nhau. Nhầm lẫn thuật toán/loại khóa có thể dẫn đến **algorithm confusion**.

### 13.5. Bỏ audience validation vì chữ ký đã hợp lệ

Issuer có thể ký token cho nhiều client và resource. ID token hoặc access token của API khác có thể mang chữ ký hợp lệ nhưng vẫn không được phép vào API hiện tại.

### 13.6. Fallback sang “cho truy cập ít quyền” khi không verify được token

Một token sai chữ ký không chứng minh bất kỳ danh tính hay quyền nào. Nếu endpoint thực sự công khai, hãy thiết kế quy tắc cho anonymous request rõ ràng; đừng tạo principal từ token không đáng tin rồi tự cấp quyền dự phòng.

### 13.7. Bỏ qua lỗi decoder và để controller tự đọc claims

Khi `JwtDecoder` ném exception, đó là tín hiệu token không được chấp nhận. Không bắt lỗi rồi tiếp tục với payload đã decode thủ công; cách đó vô hiệu hóa security boundary.

### 13.8. Tự ghi nguyên token vào log hoặc URL để debug

Bearer token là credential: ai sở hữu token còn hiệu lực có thể dùng nó trong phạm vi cấp phép. Tránh log, query string và hệ thống theo dõi lỗi không được bảo vệ; dùng dữ liệu đã rút gọn và kiểm soát truy cập.

## 14. Tình huống thực hành tổng hợp

### A. “Tôi nhìn thấy đúng claim scope, sao API vẫn trả 401?”

Developer decode JWT qua công cụ chỉ đọc payload và thấy:

```json
{ "scope": "orders:read", "aud": "orders-api" }
```

Nhưng client đã vô tình sửa một ký tự trong payload sau khi token được ký. Chữ ký không còn hợp lệ. API phải trả 401; việc scope nhìn đúng không có giá trị vì payload chưa được chứng thực.

### B. “Token có dấu chấm nên chắc là JWT”

API nhận chuỗi có ba phần nhưng header không phải JSON hợp lệ. Đếm dấu chấm không kiểm tra được cấu trúc JOSE. Decoder từ chối là đúng; client phải gửi token đúng loại do Authorization Server cấp.

### C. “Issuer vừa đổi key; tất cả API báo signature invalid”

Authorization Server dùng private key B để ký nhưng JWKS chưa công bố public key B hoặc resource server đang cache A. Việc này cần điều chỉnh lịch công bố key, JWKS cache, `kid` và cửa sổ chuyển đổi. Không nên rollback bằng cách tắt verify.

### D. “JWT hợp lệ từ một OpenID Provider nhưng không gọi API được”

Client dùng ID token từ OIDC login, `aud=web-client`. Resource Server yêu cầu access token có `aud=orders-api`. Token bị từ chối dù chữ ký được cùng OP ký là hành vi đúng.

### E. “API dùng opaque token mà developer cố giải mã JWT”

Authorization Server trả opaque access token; `JwtDecoder` không nhận diện được ba đoạn JWS. Hệ thống cần chọn đúng cơ chế `OpaqueTokenIntrospector` khi đã cấu hình quyền introspection, không phân tích cấu trúc bằng mẹo string.

### F. “JWT đã được xác minh nhưng POST vẫn trả 403”

JWT đúng chữ ký, đúng issuer/audience và còn hạn, nhưng chỉ có `orders:read`. Authentication đã thành công; `POST /api/orders` yêu cầu `orders:write` nên authorization từ chối. Đây không phải lỗi chữ ký.

## 15. Câu hỏi tự kiểm tra

**1. Base64URL-decode được payload có chứng minh JWT được issuer ký không?** Không. Decode chỉ chuyển đổi cách biểu diễn, không xác minh tính toàn vẹn hay nguồn phát hành.

**2. JWT với `alg: none` có phù hợp API yêu cầu signed access token không?** Không. Unsecured JWT không cung cấp bằng chứng chữ ký theo hợp đồng đó.

**3. JWT có ba đoạn là chắc chắn hợp lệ?** Không. Còn phải parse header/payload, xác minh thuật toán, khóa, signature và claims.

**4. `RS256` ký bằng khóa nào và xác minh bằng khóa nào?** Issuer ký bằng RSA private key; Resource Server xác minh bằng public key đáng tin cậy.

**5. JWT signature hợp lệ nhưng `aud` sai có dùng được không?** Không. Token không được phát hành cho resource API đó.

**6. Resource Server JWT có tự xác minh opaque token không?** Không. Opaque token cần cơ chế introspection hoặc giải pháp xác thực tương ứng.

**7. JWE năm phần có phải JWS ba phần bị lỗi không?** Không nhất thiết. JWE là định dạng mã hóa khác; API phải hỗ trợ đúng profile nếu được giao nhận JWE.

**8. Khi gặp 401, có phải luôn do chữ ký sai không?** Không. 401 có thể do thiếu token, sai định dạng, issuer/audience, expiration, signature hoặc token profile.

**9. Khi nào dùng 403?** Thông thường khi token được xác thực hợp lệ nhưng người gọi thiếu scope/quyền cần thiết.

**10. MockMvc `jwt()` đã chứng minh Spring từ chối chữ ký sai chưa?** Chưa. Nó có thể tạo authentication giả lập để test authorization mà không chạy giải mã chữ ký thực.

## 16. Tài liệu chuẩn liên quan

- **RFC 7515 — JSON Web Signature (JWS):** signed/unsecured JWS, JWS Compact Serialization và protected header.
- **RFC 7518 — JSON Web Algorithms (JWA):** các thuật toán JOSE như `none`, `HS256`, `RS256`, `PS256` và `ES256`.
- **RFC 7519 — JSON Web Token (JWT):** JWT, các claim chuẩn và khái niệm unsecured JWT.
- **RFC 7516 — JSON Web Encryption (JWE):** định dạng JWT mã hóa và cấu trúc JWE Compact.
- **RFC 7517 — JSON Web Key (JWK):** JWK/JWKS và quản lý khóa xác minh.
- **RFC 8725 — JWT Best Current Practices:** chống algorithm confusion, tách loại token, ràng buộc issuer/audience và thuật toán.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile dành cho OAuth 2.0 JWT access token khi hệ thống áp dụng.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer challenge, `invalid_token`, `invalid_request` và `insufficient_scope`.
- **Spring Security — OAuth 2.0 Resource Server JWT:** `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, `JwtDecoder`, `NimbusJwtDecoder` và cấu hình xác thực access token.

**Nguyên tắc ghi nhớ:** Một JWT được phép dùng cho API chỉ khi **đúng định dạng đã cam kết, có cơ chế bảo vệ chữ ký được chấp nhận, xác minh chữ ký thành công, qua các validator claims/token profile và đáp ứng quyền truy cập**. Token không chữ ký, sai chữ ký hoặc không đúng định dạng phải bị từ chối; việc khắc phục nằm ở luồng phát hành/chọn token và cấu hình xác minh, không phải bỏ qua bước xác thực.

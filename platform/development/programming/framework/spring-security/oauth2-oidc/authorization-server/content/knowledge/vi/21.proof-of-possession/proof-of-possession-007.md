# Tác động của DPoP đến refresh token và vòng đời khóa client

## Mục tiêu bài học

Trong chương **DPoP** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này phân tích mối liên hệ giữa **Demonstrating Proof of Possession (DPoP)**, **refresh token** và vòng đời của cặp khóa do client quản lý. Nội dung đặt trong bối cảnh thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**.

DPoP ràng buộc token với khóa công khai của client. Client phải chứng minh đang giữ private key tương ứng khi xin token hoặc gọi Resource Server. Vì vậy, vòng đời private key ảnh hưởng trực tiếp đến khả năng tiếp tục sử dụng access token và refresh token. Đặc biệt, RFC 9449 quy định khác nhau đối với **public client** và **confidential client** khi refresh token được cấp.

Sau bài học, bạn có thể:

- Giải thích DPoP proof JWT, public key, private key và thumbprint `cnf.jkt`.
- Phân biệt DPoP key với client authentication credential, khóa ký của Authorization Server và khóa PKCE.
- Mô tả request refresh token có `DPoP` header và lý do public client phải dùng lại đúng key đã ràng buộc refresh token.
- Phân biệt quy tắc refresh token cho public client với confidential client theo RFC 9449 mục 5.
- Lập kế hoạch tạo, lưu, backup, rotate, revoke và khôi phục DPoP key trên từng thiết bị/client installation.
- Hiểu tác động của refresh token rotation, replay detection, mất key và key compromise.
- Tích hợp DPoP với Spring Authorization Server/Spring Security đúng phiên bản, kiểm tra access token ở Resource Server.
- Xây dựng test matrix cho key continuity, key rotation, refresh token reuse, nonce, nhiều thiết bị và lỗi bảo mật.

> **Tình huống xuyên suốt:** Ứng dụng native `employee-mobile` dùng Authorization Code + PKCE và DPoP. Khi đổi authorization code, client gửi proof ký bằng khóa riêng của lần cài đặt ứng dụng. Authorization Server cấp DPoP-bound access token và, nếu policy cho phép, refresh token. Sau vài tháng, ứng dụng cần xoay khóa hoặc người dùng mất thiết bị. Hệ thống phải quyết định token nào còn dùng được và cần yêu cầu người dùng xác thực lại khi nào.

## 1. DPoP ràng buộc token với khóa client như thế nào?

DPoP là cơ chế sender-constraining ở tầng ứng dụng theo **RFC 9449**. Client tạo một cặp khóa bất đối xứng và dùng private key để ký **DPoP proof JWT** cho từng HTTP request. Public key được gửi trong JOSE header của proof dưới dạng JWK công khai.

Authorization Server xác minh proof ở Token Endpoint. Khi hợp lệ, server có thể ràng buộc access token với public key đó. Resource Server sau này yêu cầu client gửi access token cùng proof mới cho request hiện tại; việc chỉ đánh cắp chuỗi access token sẽ không đủ để sử dụng token.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Tạo DPoP proof bằng private key K1
    C->>AS: Token request + DPoP header (public K1)
    AS->>AS: Xác minh proof, tính JWK thumbprint
    AS->>AS: Ràng buộc access token với thumbprint K1
    AS-->>C: access_token + token_type=DPoP
    C->>C: Tạo proof mới cho API request
    C->>RS: Authorization: DPoP token + DPoP proof
    RS->>RS: Kiểm signature, htm, htu, jti, ath và cnf.jkt
    RS-->>C: Cho phép nếu mọi kiểm tra hợp lệ
~~~

Khác biệt với Bearer token:

| Bearer token | DPoP-bound access token |
|---|---|
| Bên giữ token có thể thử sử dụng token. | Bên gọi còn phải chứng minh đang giữ private key đã ràng buộc. |
| Request thường gửi `Authorization: Bearer <token>`. | Request gửi `Authorization: DPoP <token>` và header `DPoP` chứa proof mới. |
| Không có proof-of-possession ở tầng ứng dụng. | Proof được ký và gắn với method, URI, thời điểm và token hash khi gọi Resource Server. |
| Token bị lộ có thể bị replay trong thời hạn và phạm vi của nó. | Token bị lộ riêng lẻ khó sử dụng nếu attacker không có private key. |

**DPoP không phải phương thức xác thực client.** Nó chứng minh quyền sở hữu private key cho request. Confidential client vẫn phải xác thực bằng phương thức đã đăng ký như `client_secret_basic`, `private_key_jwt` hoặc mTLS. DPoP có thể kết hợp với các phương thức này.

### 1.1. Cặp khóa nào thuộc client?

Bài học phân biệt ba nhóm khóa:

| Khóa | Chủ thể giữ | Dùng để làm gì? |
|---|---|---|
| **DPoP client key** | Client/thiết bị | Ký proof JWT; ràng buộc access token và trong trường hợp public client, refresh token. |
| **Authorization Server signing key** | Authorization Server/KMS/HSM | Ký JWT access token, ID Token hoặc dữ liệu do AS phát hành. |
| **Client authentication key/secret** | Confidential client | Xác thực client với Token Endpoint, ví dụ private_key_jwt hoặc shared secret. |

Một client có thể dùng private key khác nhau cho DPoP và `private_key_jwt`. Tách hai mục đích giúp xoay vòng, audit và giới hạn phạm vi compromise. Không gửi DPoP private key lên Authorization Server; proof chỉ chứa public JWK.

**DPoP key cũng không phải PKCE verifier.** PKCE bảo vệ việc đổi authorization code; DPoP ràng buộc token với key. Một Authorization Code + PKCE flow có thể dùng đồng thời PKCE và DPoP.

## 2. Cấu trúc DPoP proof JWT

Mỗi HTTP request cần một proof mới. Header JOSE của proof phải có:

- `typ` bằng `dpop+jwt`.
- `alg` là thuật toán chữ ký bất đối xứng được chấp nhận; không dùng `none` hoặc thuật toán MAC đối xứng.
- `jwk` chứa **public key** của client, không chứa private key.

Payload có các claims cơ bản:

| Claim | Ý nghĩa |
|---|---|
| `jti` | ID duy nhất cho proof, dùng hỗ trợ phát hiện replay. |
| `htm` | HTTP method của request, ví dụ `POST` hoặc `GET`. |
| `htu` | HTTP target URI của request, không gồm query và fragment. |
| `iat` | Thời điểm tạo proof. |
| `nonce` | Có mặt khi server yêu cầu nonce và client phải đưa nonce gần nhất vào proof. |
| `ath` | Hash access token; bắt buộc khi proof đi kèm access token ở Protected Resource request. |

Ví dụ cấu trúc rút gọn:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "PUBLIC_X_COORDINATE",
    "y": "PUBLIC_Y_COORDINATE"
  }
}
.
{
  "jti": "a-unique-random-proof-id",
  "htm": "POST",
  "htu": "https://auth.example.com/oauth2/token",
  "iat": 1794859200
}
~~~

Các giá trị trong ví dụ là placeholder. Proof được ký bằng private key tương ứng với public JWK trong header. Server phải kiểm tra chữ ký, loại proof, thuật toán, URI, method, thời gian, nonce nếu có và khả năng replay.

### 2.1. Vì sao proof ở Token Endpoint khác proof gọi API?

Khi refresh token tại Token Endpoint, request không gửi access token để truy cập Resource Server. Vì vậy proof của request refresh **không cần `ath`**. Proof vẫn phải có `htm`, `htu`, `iat`, `jti` và `nonce` nếu server đã yêu cầu.

Khi gọi API bằng DPoP-bound access token, proof phải thêm `ath` bằng Base64URL(SHA-256(ASCII(access_token))). Resource Server xác minh hash này khớp với access token trong Authorization header và public key trong proof khớp với binding của token.

Không dùng lại một proof cho nhiều request. `jti` phải có xác suất trùng cực thấp; server có thể lưu dấu proof đã dùng trong một khoảng thời gian để chống replay.

### 2.2. DPoP nonce

Authorization Server hoặc Resource Server có thể gửi header `DPoP-Nonce` để yêu cầu client dùng nonce đó trong proof tiếp theo. Nếu nhận lỗi `use_dpop_nonce` cùng nonce mới, client cần:

1. Đọc nonce từ response header.
2. Tạo proof JWT mới, ký lại bằng private key tương ứng.
3. Gắn nonce mới vào claim `nonce`.
4. Sinh `jti` mới và `iat` mới.
5. Gửi lại request theo quy tắc retry của server.

Không gửi lại nguyên proof cũ chỉ vì nonce bị thiếu. Nonce là một phần của proof và phải được ký.

## 3. DPoP tác động đến refresh token ra sao?

Refresh token cho phép client xin access token mới sau khi access token hiện tại hết hạn mà không phải thực hiện lại toàn bộ authorization flow. Với DPoP, cần phân biệt **public client** và **confidential client**.

### 3.1. Public client: refresh token gắn với DPoP key

Theo RFC 9449 mục 5, khi Authorization Server cấp refresh token cho **public client** có gửi DPoP proof hợp lệ tới Token Endpoint, refresh token đó **MUST được ràng buộc với public key trong proof**. Khi refresh token được dùng lại, server **MUST kiểm tra binding**. Client phải gửi proof được ký bằng **cùng private key** đã dùng để nhận refresh token.

Nói cách khác, public client không thể chỉ giữ refresh token rồi tùy ý đổi sang DPoP key mới. Refresh token là credential dài hạn và bị ràng buộc với key của lần cấp phát ban đầu.

### 3.2. Confidential client: refresh token được ràng buộc bằng client authentication

RFC 9449 quy định refresh token cấp cho **confidential client** không bị ràng buộc trực tiếp với DPoP proof public key. Lý do: refresh token đã được sender-constrain thông qua client identity và yêu cầu confidential client xác thực lại khi sử dụng refresh token.

Điều này cho phép confidential client thay DPoP key để cấp access token mới, miễn là client vẫn xác thực hợp lệ theo phương thức đã đăng ký và server chấp nhận proof mới. Access token mới sẽ được ràng buộc với DPoP key trong proof của request đó.

| Chủ thể | Binding của refresh token | Key nào phải dùng khi refresh? |
|---|---|---|
| Public client được cấp DPoP-bound refresh token | Gắn với DPoP public key đã gửi khi nhận refresh token. | **Bắt buộc cùng DPoP key** cho mỗi lần refresh token đó được sử dụng. |
| Confidential client | Gắn với client theo cơ chế xác thực client OAuth2. | Phải xác thực client; DPoP proof có thể dùng key mới để ràng buộc access token mới. |
| Public client nhận refresh token nhưng access token response có `token_type=Bearer` | Refresh token vẫn có thể được DPoP-bound nếu server đã cấp nó cho public client có proof hợp lệ. | Vẫn phải dùng cùng key để refresh. |

**Không nhầm token type của access token với binding của refresh token.** `token_type=Bearer` báo rằng access token không được DPoP-bound trong response đó. Nó không tự chứng minh refresh token của public client không có binding DPoP.

### 3.3. Spring Authorization Server có nhất thiết cấp refresh token cho public client không?

Không. RFC 9449 quy định cách ràng buộc **khi server cấp refresh token**; nó không bắt buộc mọi public client phải được cấp refresh token. Tài liệu Spring Authorization Server 1.5.8 về cấu hình SPA public client nêu rõ cấu hình hướng dẫn không cấp refresh token cho public client và khuyến nghị mô hình Backend for Frontend (BFF) khi phù hợp.

Vì vậy, khi thiết kế phải xác định rõ:

- Client có phải public hay confidential?
- Grant và policy của server có cho phép refresh token không?
- Server có hỗ trợ DPoP proof tại Token Endpoint không?
- Nếu cấp refresh token cho public client, binding và kiểm tra cùng key có được triển khai đầy đủ không?
- Nếu không cấp refresh token, client phải thực hiện lại authorization flow khi access token hết hạn theo thiết kế.

Đừng suy luận rằng chỉ cần thêm header `DPoP` thì một public client mặc định sẽ nhận refresh token.

## 4. Refresh request phải dùng DPoP proof như thế nào?

Ví dụ public client gửi refresh token đã được ràng buộc với key `K1`:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: <FRESH_PROOF_SIGNED_WITH_K1>

grant_type=refresh_token&
client_id=employee-mobile&
refresh_token=<REFRESH_TOKEN_BOUND_TO_K1>
~~~

`<FRESH_PROOF_SIGNED_WITH_K1>` là proof mới được ký bằng private key K1. Mỗi lần refresh phải tạo `jti` mới. Nếu Authorization Server đã gửi `DPoP-Nonce`, proof cần chứa nonce đó.

Nếu client gửi proof bằng key K2 trong khi refresh token ràng buộc K1, Authorization Server phải từ chối request theo chính sách/token error phù hợp. Không được âm thầm chuyển binding của refresh token sang K2 chỉ vì proof mới có chữ ký hợp lệ.

### 4.1. Confidential client kết hợp DPoP

Confidential client vẫn phải xác thực client. Ví dụ minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <CLIENT_AUTHENTICATION>
Content-Type: application/x-www-form-urlencoded
DPoP: <FRESH_PROOF_SIGNED_WITH_CURRENT_DPOP_KEY>

grant_type=refresh_token&
refresh_token=<REFRESH_TOKEN>
~~~

`<CLIENT_AUTHENTICATION>` đại diện cho phương thức client authentication đã đăng ký; không phải DPoP proof. Khi thay DPoP key, confidential client vẫn cần credential hợp lệ. Nếu dùng `private_key_jwt` hoặc mTLS, việc rotation credential xác thực client là một quy trình riêng.

### 4.2. Response và key binding

Nếu Authorization Server cấp DPoP-bound access token, response dùng `token_type` là `DPoP`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<NEW_DPOP_BOUND_ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 300,
  "refresh_token": "<ROTATED_REFRESH_TOKEN>"
}
~~~

`refresh_token` chỉ có nếu grant và policy thực sự cấp/rotate nó. Với public client, refresh token mới trong chuỗi rotation tiếp tục được ràng buộc với cùng DPoP key theo yêu cầu RFC. Không coi việc server trả một refresh token mới là dấu hiệu key binding đã thay đổi.

### 4.3. Binding được lưu ở đâu?

Với JWT access token, public key thumbprint được biểu diễn trong claim:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": "inventory-api",
  "exp": 1794861000,
  "cnf": {
    "jkt": "BASE64URL_JWK_SHA256_THUMBPRINT"
  }
}
~~~

`cnf.jkt` là JWK SHA-256 thumbprint của public key DPoP. Với opaque access token, Resource Server có thể nhận binding tương ứng qua Token Introspection response.

**Refresh token binding không bắt buộc phải nằm trong chuỗi refresh token dưới dạng JWT hoặc claim công khai.** RFC để cách triển khai binding refresh token cho Authorization Server quyết định; server có thể lưu thumbprint hoặc metadata tương ứng trong authorization/token state. Không decode refresh token để suy luận key nếu định dạng không quy định điều đó.

## 5. Vòng đời DPoP key ở phía client

DPoP key là một phần của trạng thái bảo mật của client installation. Nếu key mất, client có thể mất khả năng dùng access token đang ràng buộc và refresh token đã gắn với key đó.

### 5.1. Tạo khóa theo installation

Đối với public native client, nên tạo key riêng cho từng installation hoặc security context theo chính sách sản phẩm:

- Sinh khóa bằng CSPRNG/secure platform API; dùng thuật toán chữ ký bất đối xứng được server hỗ trợ.
- Ưu tiên hardware-backed/non-exportable key khi nền tảng có hỗ trợ và phù hợp UX.
- Tách key theo ứng dụng/installation để giảm phạm vi compromise và khả năng liên kết hoạt động giữa các ứng dụng.
- Không dùng chung một DPoP key cho tất cả thiết bị của cùng một người dùng.
- Lưu public key metadata hoặc thumbprint cùng session/authorization record phía client để biết token nào thuộc key nào.
- Private key không được gửi tới Authorization Server, Resource Server, analytics hoặc logging service.

Một người dùng có điện thoại và tablet có thể có hai authorization session, hai DPoP key và hai refresh token riêng. Không sao chép refresh token từ thiết bị này sang thiết bị khác nếu private key tương ứng không được quản lý trong cùng security boundary.

### 5.2. Lưu private key bền vững

| Nền tảng | Nơi lưu phù hợp | Lưu ý |
|---|---|---|
| Android | Android Keystore, ưu tiên hardware-backed khi khả dụng. | Lưu key alias/metadata, không export private key nếu không cần. |
| iOS/iPadOS | Secure Enclave/Keychain theo loại key và khả năng API. | Ràng buộc access control, device passcode/biometric theo UX. |
| Browser SPA | Web Crypto API với non-extractable CryptoKey khi phù hợp. | XSS vẫn có thể gọi thao tác ký trong runtime; DPoP không thay thế chống XSS. |
| CLI/Desktop | OS credential store, TPM/keystore hoặc file mã hóa với quyền truy cập hẹp. | Không để private key trong repo, home folder đồng bộ công khai hoặc command history. |
| Backend service | KMS/HSM hoặc secret/key store có IAM. | Tách key DPoP khỏi khóa ký JWT của Authorization Server. |

Nếu ứng dụng lưu DPoP key chỉ trong memory và sinh lại sau mỗi lần restart, refresh token của public client sẽ không thể sử dụng sau restart vì key mới có thumbprint khác. Key phải tồn tại lâu ít nhất bằng thời gian client cần dùng các token bị ràng buộc với nó.

### 5.3. Key và refresh token phải được lưu nhất quán

Client cần lưu một bộ trạng thái có thể phục hồi:

| Dữ liệu | Mục đích |
|---|---|
| Private DPoP key handle | Tạo proof cho access token/refresh token đang dùng. |
| Public JWK/thumbprint | Nhận diện binding và debug trạng thái mà không tiết lộ private key. |
| Access token + expiry | Gọi Resource Server và lên lịch refresh. |
| Refresh token + expiry/metadata | Xin access token mới nếu grant/policy cho phép. |
| DPoP nonce theo server | Tạo proof tiếp theo khi AS/RS yêu cầu nonce. |
| Issuer/client/authorization session ID | Tránh dùng nhầm key/token giữa nhiều issuer hoặc installation. |

Lưu cập nhật refresh token mới **bền vững ngay sau khi refresh thành công**. Nếu server đã rotate refresh token nhưng client crash trước khi ghi token mới, refresh token cũ có thể đã bị vô hiệu hóa. Client cần xử lý lỗi mất response theo chiến lược phục hồi an toàn; không retry vô hạn với token cũ.

## 6. Xoay vòng DPoP key ở public client

Đây là phần có ảnh hưởng trực tiếp nhất tới refresh token.

Giả sử public client đã có refresh token `RT1` ràng buộc với key `K1`. Sau một thời gian, client muốn đổi sang key `K2`.

### 6.1. Không thể đổi proof sang key mới rồi tiếp tục dùng refresh token cũ

~~~mermaid
sequenceDiagram
    participant C as Public Client
    participant AS as Authorization Server
    Note over C,AS: RT1 được ràng buộc với K1
    C->>AS: POST refresh_token + proof(K1)
    AS-->>C: access token mới, RT2 vẫn ràng buộc K1
    Note over C: Client tạo K2 nhưng giữ RT2
    C->>AS: POST refresh_token + proof(K2)
    AS-->>C: Từ chối vì binding không khớp
~~~

Khi client thay K1 bằng K2:
- Access token DPoP-bound với K1 không dùng được bằng proof K2.
- Refresh token public client đã ràng buộc K1 phải tiếp tục được chứng minh bằng K1.
- Server không có nghĩa vụ chuyển binding RT1/RT2 sang K2.
- RFC 9449 không định nghĩa một endpoint chuẩn để client “rebind” refresh token sang public key mới.

Nếu vẫn còn K1 và refresh token hợp lệ, client có thể tiếp tục dùng session cũ bằng K1 trong thời gian chuyển tiếp. Nếu muốn dùng K2, cần tạo authorization session mới theo flow được hỗ trợ, gửi DPoP proof K2 và nhận token set mới gắn với K2. Sau khi session mới hoạt động, client có thể thu hồi authorization/refresh token cũ theo policy.

### 6.2. Quy trình rotation chủ động

1. **Tạo K2:** sinh key mới và lưu an toàn trước khi thay thế key hiện tại.
2. **Khởi tạo authorization mới:** dùng Authorization Code + PKCE (hoặc grant phù hợp) và DPoP proof ký bằng K2.
3. **Nhận token set mới:** kiểm tra `token_type`/binding; nếu public client được cấp refresh token, xác nhận session mới thuộc K2.
4. **Lưu trạng thái mới:** ghi token, key handle và thumbprint K2 bền vững.
5. **Chuyển traffic:** request mới dùng access token và proof K2; không dùng token K1 với proof K2.
6. **Thu hồi session cũ:** revoke RT/authorization cũ khi đã chuyển thành công và theo policy.
7. **Xóa K1:** chỉ xóa private key cũ khi không còn token/session hợp lệ nào cần nó và quy trình rollback không cần nữa.

Nếu client không thể chạy hai session song song, cần thiết kế khoảng gián đoạn và UX xác thực lại rõ ràng. Không xóa K1 trước khi đã xác minh session mới K2 hoạt động.

### 6.3. Xoay vòng do hết hạn chứng thư hay thay thuật toán

DPoP key thường là key ứng dụng, không nhất thiết có certificate như mTLS. Tuy vậy, nền tảng có thể yêu cầu thay key do thuật toán bị loại bỏ, thiết bị đổi phần cứng hoặc chính sách mật mã mới. Các tình huống này vẫn cần xử lý như thay key: tạo authorization/token set mới, không giả định refresh token public client có thể tự chuyển binding.

## 7. Vòng đời DPoP key ở confidential client

Confidential client có thêm cơ chế sender-constraining qua client authentication. Theo RFC 9449, refresh token cấp cho confidential client được ràng buộc với client authentication mechanism, không bị ràng buộc trực tiếp với DPoP proof public key.

Điều này tạo khác biệt khi xoay DPoP key:

| Thành phần | Khi confidential client đổi DPoP key |
|---|---|
| Refresh token | Vẫn thuộc client theo cơ chế OAuth2 client authentication. |
| Client authentication credential | Vẫn phải hợp lệ; nếu cũng rotate thì xử lý theo registration/overlap riêng. |
| Access token cũ | Vẫn ràng buộc với DPoP key cũ đến khi hết hạn hoặc bị revoke. |
| Refresh request tiếp theo | Có thể dùng DPoP proof ký bằng key mới nếu AS chấp nhận; access token mới được ràng buộc với key trong proof mới. |
| Resource Server | Phải xác minh từng token theo đúng thumbprint, không chấp nhận proof từ key mới cho token cũ. |

Ví dụ: backend `billing-service` dùng `client_secret_basic` để xác thực và DPoP key K1 cho access token. Khi rotate sang K2, backend vẫn gửi refresh token với client authentication hợp lệ nhưng tạo DPoP proof bằng K2. Nếu AS hỗ trợ và chấp nhận, access token mới được ràng buộc K2. Access token cũ vẫn cần proof K1 cho đến khi hết hạn/revoke.

### 7.1. Tách rotation của DPoP key và client authentication

Không gộp các thao tác sau thành một thay đổi:

- Xoay DPoP signing key.
- Xoay `client_secret`.
- Xoay key dùng `private_key_jwt`.
- Thay client certificate cho mTLS.
- Thay Authorization Server signing key.

Mỗi loại có đối tượng xác minh, metadata và ảnh hưởng đến token khác nhau. Nếu xoay đồng thời, phải có kế hoạch overlap/rollback cho từng cơ chế và test từng tổ hợp.

## 8. Tích hợp với Spring Authorization Server và Spring Security

Tài liệu **Spring Authorization Server 1.5.8** có mục DPoP-bound Access Tokens trong Protocol Endpoints. Token request tới Token Endpoint có thể mang header `DPoP`; sau khi proof hợp lệ, Authorization Server ràng buộc access token với public key của proof. Response dùng `token_type=DPoP` khi access token được DPoP-bound.

Spring Security Resource Server có tài liệu riêng về xác minh DPoP-bound access token. Cần đối chiếu phiên bản dependency đang dùng vì hỗ trợ DPoP, API cấu hình và khả năng client integration có thể khác giữa các dòng Spring Security/Spring Authorization Server.

### 8.1. Request tại Token Endpoint

Ví dụ refresh request ở mức giao thức:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: <PROOF_SIGNED_BY_THE_REQUIRED_CLIENT_KEY>

grant_type=refresh_token&
refresh_token=<REFRESH_TOKEN>
~~~

Với public client, nếu refresh token đã DPoP-bound, proof phải dùng cùng key. Với confidential client, request vẫn phải có client authentication theo registration. Proof ở Token Endpoint dùng `htu` là public token endpoint URI và `htm=POST`; không thêm `ath` cho request refresh này.

### 8.2. Ví dụ tạo proof cho Token Endpoint bằng Spring Security JOSE

Đoạn code minh họa client tạo proof JWT bằng `NimbusJwtEncoder`. `clientDpopJwk` là JWK do **client giữ**, có private key trong keystore/secure storage. Không đặt JWK này ở Authorization Server và không đưa private key vào header proof.

~~~java
import java.time.Instant;
import java.util.UUID;

import com.nimbusds.jose.jwk.ECKey;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

final class DpopProofFactory {

    private final ECKey clientDpopJwk;
    private final JwtEncoder jwtEncoder;

    DpopProofFactory(ECKey clientDpopJwk) {
        this.clientDpopJwk = clientDpopJwk;

        JWKSource<SecurityContext> keySource =
                (selector, context) ->
                        selector.select(new JWKSet(clientDpopJwk));

        this.jwtEncoder = new NimbusJwtEncoder(keySource);
    }

    String createTokenEndpointProof(
            String publicTokenEndpointUri,
            String nonce) {

        JwsHeader jwsHeader = JwsHeader
                .with(SignatureAlgorithm.ES256)
                .type("dpop+jwt")
                .jwk(clientDpopJwk.toPublicJWK().toJSONObject())
                .build();

        JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
                .issuedAt(Instant.now())
                .claim("htm", "POST")
                .claim("htu", publicTokenEndpointUri)
                .id(UUID.randomUUID().toString());

        if (nonce != null && !nonce.isBlank()) {
            claims.claim("nonce", nonce);
        }

        return jwtEncoder.encode(
                JwtEncoderParameters.from(jwsHeader, claims.build())
        ).getTokenValue();
    }
}
~~~

Đây là ví dụ cho proof gửi **Token Endpoint**:
- `publicTokenEndpointUri` phải là URL HTTPS công khai mà client thực sự gọi, không chứa query hoặc fragment.
- `clientDpopJwk` phải có private key để ký, nhưng JOSE header chỉ chứa `toPublicJWK()`.
- `jti` mới được sinh cho mỗi request; không cache hoặc tái sử dụng proof.
- `nonce` chỉ đưa vào khi server yêu cầu hoặc trả nonce.
- Cần giới hạn thuật toán, bảo vệ key source, đồng bộ thời gian và xử lý exception/nonce retry.
- Ví dụ dùng ES256/P-256; thuật toán thực tế phải nằm trong tập thuật toán DPoP mà Authorization Server công bố/chấp nhận.

Không dùng đoạn code này như một cấu hình Authorization Server. Đây là code **phía client** để ký proof. Phần kiểm tra proof, lưu binding refresh token và phát access token phải do Authorization Server hỗ trợ DPoP thực hiện.

### 8.3. Resource Server xác minh access token

Khi gọi API, client gửi:

~~~http
GET /api/inventory HTTP/1.1
Host: inventory-api.example.com
Authorization: DPoP <DPOP_BOUND_ACCESS_TOKEN>
DPoP: <FRESH_PROOF_WITH_ATH>
~~~

Proof ở đây phải có `ath` là SHA-256 hash của access token. Resource Server xác minh:
- Chữ ký proof và public JWK.
- `typ=dpop+jwt` và asymmetric `alg` được cho phép.
- `htm`, `htu`, `iat`, `jti` và nonce khi áp dụng.
- `ath` khớp access token được gửi.
- Public key thumbprint của proof khớp `cnf.jkt` trong JWT access token hoặc binding trong introspection response.
- Access token còn hạn, đúng issuer/audience/scope và được phép truy cập tài nguyên.

DPoP proof không thay thế kiểm tra authorization nghiệp vụ. Có proof hợp lệ không có nghĩa client được phép gọi mọi API.

### 8.4. Những gì cần kiểm tra theo phiên bản

| Thành phần | Câu hỏi khi triển khai |
|---|---|
| Spring Authorization Server | Phiên bản có hỗ trợ DPoP tại Token Endpoint chưa? Có kiểm tra proof cho refresh request không? |
| Refresh token provider | Với public client được cấp RT, server lưu và xác minh DPoP key binding thế nào? |
| Registered client policy | Public client có được cấp refresh token không? Nếu có, điều kiện và TTL là gì? |
| Spring Security Resource Server | Có hỗ trợ DPoP authentication scheme và kiểm `ath`/`cnf.jkt` không? |
| Client SDK | Có tạo proof riêng mỗi request, xử lý nonce và dùng đúng key khi refresh không? |
| Gateway/proxy | Public URL dùng để tính `htu` có khớp URL mà server kiểm tra không? |

Không tự thêm custom claim `cnf.jkt` vào JWT rồi coi đó là hỗ trợ DPoP hoàn chỉnh. Phải có kiểm proof, replay protection, binding trong refresh token (nếu áp dụng), và Resource Server validation.

## 9. Refresh token rotation, replay và concurrency

DPoP key binding và refresh token rotation giải quyết hai vấn đề liên quan nhưng khác nhau:

- **DPoP binding:** refresh token public client chỉ dùng được khi client chứng minh giữ đúng private key.
- **Refresh token rotation:** mỗi lần refresh có thể phát token mới và vô hiệu hóa token cũ theo policy, giúp phát hiện reuse/replay.

Một hệ thống có thể triển khai cả hai. Với public client, refresh token mới vẫn phải gắn với DPoP key của chuỗi token. Đổi chuỗi refresh token không đồng nghĩa đổi key binding.

### 9.1. Cập nhật refresh token sau mỗi lần rotate

Nếu server cấu hình rotation, client phải:
1. Chỉ cho một refresh operation chạy cho mỗi authorization session tại một thời điểm.
2. Gửi refresh token hiện tại cùng DPoP proof đúng key.
3. Nhận response và xác nhận access token/token type/expiry.
4. Ghi refresh token mới một cách bền vững trước khi đánh dấu request hoàn tất.
5. Cập nhật metadata expiry/nonce theo response.
6. Không dùng lại refresh token cũ sau khi server đã rotate.

Nếu nhiều thread cùng refresh một token, một request có thể thành công trong khi request còn lại bị coi là reuse/replay. Client nên dùng single-flight/lock theo session và token family, tránh retry song song.

### 9.2. DPoP không thay thế replay protection

Server cần phát hiện DPoP proof replay bằng `jti` trong một cửa sổ thời gian phù hợp. Refresh token rotation lại phát hiện reuse refresh token theo authorization/token family. Hai cơ chế nên được kiểm thử độc lập.

| Tình huống | Bảo vệ cần có |
|---|---|
| Attacker chỉ đánh cắp access token | DPoP proof và key binding ngăn sử dụng token nếu không có private key. |
| Attacker chỉ đánh cắp public-client refresh token | DPoP refresh-token binding yêu cầu private key tương ứng. |
| Attacker đánh cắp DPoP private key | Binding không còn bảo vệ trước attacker có thể ký proof; cần revoke và reauthorize. |
| Proof bị capture rồi gửi lại | `jti`, thời gian hợp lệ, nonce/replay cache và request binding. |
| Refresh token cũ bị dùng lại sau rotation | Server áp dụng replay/reuse detection và chính sách revoke token family. |
| Hai refresh request chạy đồng thời | Client serialization và server-side atomic state update. |

## 10. Mất key, hỏng thiết bị và key compromise

### 10.1. Client mất private key

Với public client có refresh token DPoP-bound:
- Client không thể tạo proof cùng key nên không thể refresh.
- Access token DPoP-bound đang còn hạn cũng không dùng được nếu không thể ký proof.
- Không có cách chuẩn để suy ra hoặc tải lại private key từ Authorization Server.
- Client cần bắt đầu authorization mới, tạo key mới và nhận token set mới.
- Authorization Server có thể cần thu hồi refresh token/authorization cũ nếu còn trạng thái.

Nếu client có backup key an toàn và có thể khôi phục đúng key material, session cũ có thể tiếp tục theo policy. Nhưng backup làm tăng rủi ro key bị sao chép; phải đánh giá encryption, device binding, access control và khả năng revoke.

### 10.2. DPoP key bị lộ

Nếu attacker có private key cùng token, DPoP không thể ngăn attacker tạo proof hợp lệ. Cần xử lý như sự cố credential:

1. Đánh dấu key/session liên quan bị compromise trong client.
2. Ngừng sử dụng key cũ và tạo key mới trong secure storage.
3. Revoke refresh token/authorization tương ứng tại AS nếu có endpoint/quy trình.
4. Đánh giá access token đã phát; JWT xác minh offline có thể còn hiệu lực đến `exp` nếu không có cơ chế revoke tập trung.
5. Thu hồi/denylist/introspection hoặc giảm TTL theo kiến trúc để giảm cửa sổ rủi ro.
6. Thực hiện authorization mới với key sạch.
7. Kiểm tra logs, thiết bị, malware, backup và phạm vi dữ liệu có thể đã bị truy cập.

Không chỉ đổi DPoP key ở client rồi tiếp tục dùng refresh token public client cũ; server phải xác minh binding và từ chối key không khớp.

### 10.3. Key hết hạn theo policy hoặc thuật toán bị loại bỏ

DPoP key thường không có expiry claim riêng như access token. Tuy nhiên tổ chức có thể đặt tuổi thọ tối đa cho key theo chính sách mật mã. Khi đến hạn:
- Tạo key mới trước khi key cũ bị ngừng.
- Public client phải tạo authorization session/token set mới nếu refresh token gắn với key cũ.
- Confidential client có thể dùng refresh token theo client authentication và proof key mới nếu server hỗ trợ.
- Giữ key cũ đủ lâu cho token/session cũ hoặc revoke chúng theo kế hoạch.
- Không để key hết hạn policy nhưng vẫn ký proof mà server không còn chấp nhận thuật toán.

## 11. Kiểm thử DPoP và vòng đời refresh token

Kiểm thử chỉ một lần lấy access token là chưa đủ. Cần xác minh hành vi qua nhiều chu kỳ refresh và thay đổi vòng đời key.

### 11.1. Ma trận public client

| Tình huống | Kết quả mong đợi |
|---|---|
| Public client gửi proof K1 và được cấp refresh token | AS lưu binding RT với public key K1 theo RFC 9449. |
| Refresh RT bằng proof K1 hợp lệ | AS xác minh binding và có thể cấp access token mới. |
| Refresh RT bằng proof K2 | Bị từ chối; không tự đổi binding sang K2. |
| Proof sai chữ ký hoặc thiếu claim bắt buộc | Từ chối với lỗi DPoP phù hợp, ví dụ `invalid_dpop_proof`. |
| Proof có `jti` đã dùng | Replay bị phát hiện theo cửa sổ kiểm tra của server. |
| Server trả `DPoP-Nonce` | Client tạo proof mới với nonce và `jti` mới. |
| Refresh token rotate | Refresh token mới vẫn gắn với K1; token cũ không được tái sử dụng theo policy. |
| Client restart | Nạp lại đúng private key K1 và tiếp tục refresh được. |
| Client mất K1 | Không refresh được; cần authorization mới hoặc phục hồi key an toàn. |
| Client chủ động đổi K1 sang K2 | Cần authorization/token set mới cho K2; RT cũ vẫn cần K1. |

### 11.2. Ma trận confidential client

| Tình huống | Kết quả mong đợi |
|---|---|
| Confidential client xác thực hợp lệ và gửi DPoP proof K1 | Access token có thể được ràng buộc K1. |
| Refresh token được cấp cho confidential client | RT được sender-constrain bằng client authentication theo RFC 9449, không ràng buộc trực tiếp với DPoP key K1. |
| Refresh bằng client auth hợp lệ và proof K2 | AS có thể cấp access token mới ràng buộc K2 nếu policy/version hỗ trợ. |
| Client secret/private_key_jwt credential sai | Từ chối client authentication, dù DPoP proof hợp lệ. |
| DPoP key đổi nhưng client authentication vẫn hợp lệ | Access token cũ cần K1; access token mới có thể dùng K2. |
| Client authentication credential rotate | Xử lý theo registration và overlap credential riêng, không suy ra từ DPoP key rotation. |

### 11.3. Kiểm thử Resource Server

- Gửi token DPoP-bound với proof đúng key và `ath` đúng: request được phép nếu scope/authorization hợp lệ.
- Gửi token với proof key khác: từ chối.
- Gửi token DPoP-bound bằng `Authorization: Bearer`: không coi như DPoP proof hợp lệ.
- Thiếu `ath` hoặc `ath` sai: từ chối.
- `htm` hoặc `htu` không khớp request: từ chối.
- Proof quá cũ, `jti` replay hoặc nonce sai: từ chối.
- Token sai issuer/audience/expiry/scope: từ chối dù proof hợp lệ.

### 11.4. Kiểm thử integration và persistence

1. Tạo authorization cho public client với key K1.
2. Lấy access token/refresh token theo policy.
3. Restart client và nạp lại K1 từ secure storage.
4. Refresh thành công bằng K1; kiểm tra token rotation nếu bật.
5. Thử proof K2 với refresh token cũ và xác nhận bị từ chối.
6. Tạo authorization mới bằng K2; xác minh access token mới.
7. Chạy hai refresh request đồng thời để kiểm tra replay/atomicity.
8. Restart/scale-out Authorization Server; xác minh binding refresh token được đọc nhất quán giữa các instance.
9. Mô phỏng server nonce và retry bằng proof mới.
10. Revoke session cũ và kiểm tra access/refresh token theo chính sách.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Refresh token hợp lệ nhưng nhận lỗi khi đổi key | Public-client refresh token bound với key cũ. | Dùng lại key cũ hoặc thực hiện authorization mới với key mới. |
| Token Endpoint trả `invalid_dpop_proof` | Proof sai chữ ký, alg, typ, htm, htu, iat, jti hoặc nonce. | Kiểm tra proof generator, URL công khai, clock và nonce. |
| Resource Server trả 401 với access token mới | DPoP proof key không khớp `cnf.jkt` hoặc `ath` sai. | Kiểm thumbprint, token hash và proof mới. |
| Client dùng lại proof sau timeout | Proof cũ có thể bị replay hoặc đã hết cửa sổ thời gian. | Tạo proof mới với `jti` mới; xử lý idempotency của request grant riêng. |
| Refresh token bị invalid sau khi app crash | Server đã rotate nhưng client chưa lưu refresh token mới. | Lưu token response bền vững, single-flight và thiết kế phục hồi/reauthorization. |
| Public client không nhận refresh token | Server policy không cấp RT cho public client. | Kiểm grant/registration/version; không mặc định DPoP tự cấp RT. |
| Confidential client bị từ chối dù proof đúng | Client authentication thất bại hoặc registration sai. | Kiểm secret/private_key_jwt/mTLS độc lập với DPoP. |
| Proof hỏng sau reverse proxy | `htu` được tạo từ internal URL hoặc proxy rewrite sai. | Dùng public HTTPS URI nhất quán và cấu hình trusted proxy headers. |
| Client mất key sau reinstall | Key không nằm trong persistent secure storage hoặc bị xóa cùng app data. | Thiết kế key lifecycle/backup; chuẩn bị reauthorization khi mất key. |
| Refresh token bị reuse detection | Hai thread dùng cùng token hoặc client retry token đã rotate. | Serialize refresh, lưu token mới nguyên tử, xử lý race. |
| DPoP không ngăn được attacker sau XSS | Malicious code có thể gọi private-key signing operation trong context client. | Chống XSS, CSP, dependency hygiene, giảm token exposure; DPoP không thay thế bảo vệ runtime. |

## 13. Bài tập thực hành

**Bối cảnh:** `employee-mobile` là public native client dùng Authorization Code + PKCE, DPoP và refresh token theo policy riêng. Mỗi installation có một DPoP key. Người dùng đổi điện thoại sau ba tháng và muốn tiếp tục phiên đăng nhập mà không giảm mức bảo vệ.

Yêu cầu:

1. Thiết kế key store cho Android/iOS, tạo key riêng theo installation và lưu key handle bền vững.
2. Thực hiện Authorization Code + PKCE, gửi DPoP proof tới Token Endpoint và kiểm tra `token_type`/binding.
3. Xác định server có cấp refresh token cho public client hay không; nếu có, ghi rõ binding theo RFC 9449.
4. Tạo refresh request bằng cùng key, xử lý `DPoP-Nonce` và refresh token rotation.
5. Thử refresh bằng key mới K2 với refresh token bound K1; ghi nhận server từ chối.
6. Thực hiện authorization mới bằng K2, nhận token set mới và chuyển traffic.
7. Thu hồi session/refresh token K1 khi chuyển đổi hoàn tất.
8. Mô phỏng mất private key và key compromise; viết runbook reauthorization/revocation.
9. Kiểm thử Resource Server với `Authorization: DPoP`, `ath`, `cnf.jkt` và nonce.
10. Kiểm thử restart ứng dụng, reinstall, backup/restore, nhiều thiết bị và hai refresh request đồng thời.

**Tiêu chí hoàn thành:** client biết refresh token thuộc key nào, không dùng key sai, refresh rotation không làm mất trạng thái, key mới tạo session mới cho public client, và server/resource server xác minh DPoP binding đúng chuẩn.

## 14. Checklist trước khi triển khai

- [ ] Đã phân biệt DPoP key với AS signing key, client authentication key và PKCE verifier.
- [ ] Proof JWT có `typ=dpop+jwt`, asymmetric `alg`, public `jwk`, `jti`, `htm`, `htu` và `iat`.
- [ ] Không gửi private key trong proof, header, logs hoặc telemetry.
- [ ] Token Endpoint proof không thêm `ath`; Resource Server proof có `ath` đúng access token.
- [ ] Client dùng `Authorization: DPoP` cho DPoP-bound access token.
- [ ] Resource Server xác minh `cnf.jkt`/introspection binding, proof key, token hash và claims.
- [ ] Đã phân biệt public client RT binding với confidential client sender-constraining bằng client authentication.
- [ ] Public client được cấp RT phải giữ đúng DPoP key cho mọi lần refresh.
- [ ] Không giả định Spring Authorization Server cấp refresh token cho public client theo mặc định.
- [ ] Refresh token rotation và DPoP binding được kiểm thử cùng nhau.
- [ ] Client có secure storage và key persistence qua restart.
- [ ] Multi-device có key/session riêng theo policy.
- [ ] Key rotation public client có quy trình authorization mới, chuyển token và revoke session cũ.
- [ ] Confidential client tách DPoP key rotation khỏi client credential rotation.
- [ ] Có quy trình mất key, compromise, revoke, reauthorization và recovery.
- [ ] Nonce, jti replay detection, clock skew và reverse-proxy htu được kiểm thử.
- [ ] Refresh operation được serialize; token mới được lưu bền vững ngay sau response.
- [ ] Logs/traces không chứa private key, refresh token, access token hoặc proof JWT raw.

## Tổng kết

DPoP làm vòng đời refresh token phụ thuộc vào loại client. Khi Authorization Server cấp refresh token cho **public client** cùng một DPoP proof hợp lệ, RFC 9449 yêu cầu ràng buộc refresh token với public key đó và xác minh cùng key ở mọi lần refresh. Vì vậy, mất hoặc thay DPoP key có thể khiến refresh token cũ không còn dùng được; public client cần giữ key an toàn hoặc thực hiện authorization mới để nhận token set gắn với key mới.

Với **confidential client**, refresh token được sender-constrain qua client authentication, không bị ràng buộc trực tiếp với DPoP proof key. Client vẫn phải xác thực bằng credential đã đăng ký, nhưng có thể thay DPoP key cho access token mới nếu server hỗ trợ. Dù thuộc loại client nào, DPoP không thay thế TLS, client authentication, PKCE, refresh-token rotation, replay protection hoặc authorization kiểm tra tại Resource Server.

## Tài liệu tham khảo

1. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): DPoP proof JWT, token endpoint, public-client refresh token binding, confidential-client exception, nonce, key thumbprint và protected resource access.
2. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): DPoP-bound access token request và Token Endpoint.
3. [Spring Security 7.1 — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): proof generation, `cnf.jkt`, `ath` và Resource Server validation.
4. [Spring Authorization Server 1.5.8 — Authenticate using a Single Page Application with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): cấu hình public client và chính sách không cấp refresh token cho SPA public client trong hướng dẫn.
5. [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html): cách tính JWK SHA-256 thumbprint.
6. [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JOSE header và chữ ký JWT.
7. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): biểu diễn public/private key.
8. [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): refresh token grant và client authentication.
9. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token protection, rotation và replay detection.


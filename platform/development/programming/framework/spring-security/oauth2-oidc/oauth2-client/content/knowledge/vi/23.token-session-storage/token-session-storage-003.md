# 23.3. Mã hóa token khi lưu và quản lý khóa mã hóa

## 1. Vì sao OAuth2 Client cần mã hóa token khi lưu?

Trong **Spring Security OAuth 2.0 OIDC Client**, ứng dụng thường nhận **Access Token** sau một lần ủy quyền và có thể nhận thêm **Refresh Token** để duy trì quyền truy cập đến API khi Access Token hết hạn. Khi dùng `OAuth2AuthorizedClientManager`, Spring Security có thể tải lại hoặc cập nhật `OAuth2AuthorizedClient` từ một kho lưu trữ như HTTP session, in-memory service hoặc database.

Việc lưu token làm ứng dụng hoạt động thuận tiện hơn, nhưng cũng tạo ra một **kho credential** có giá trị cao. Ai đọc được token còn hiệu lực có thể gửi nó đến Resource Server như một Bearer Token nếu không có thêm cơ chế ràng buộc người gửi. Đối với Refresh Token, hậu quả có thể kéo dài hơn: kẻ tấn công có thể xin Access Token mới cho đến khi token bị thu hồi, hết hạn hoặc chính sách của Authorization Server ngăn chặn.

Ví dụ một hệ thống kết nối lịch của nhân viên:

~~~text
Người dùng Alice
   |
   | OIDC/OAuth2 Login + calendar.read
   v
Spring Boot OAuth2 Client
   |
   +-- Access Token: gọi Calendar API
   +-- Refresh Token: xin Access Token mới khi cần
   |
   v
OAuth2AuthorizedClientService
   |
   v
Database / backup / replica
~~~

Nếu database lưu token **dạng rõ (plaintext)**, một bản backup bị lộ hoặc tài khoản SQL có quyền SELECT có thể đủ để đánh cắp credential. Vì vậy, nhiều hệ thống cần mã hóa token **trước khi ghi vào persistence layer**, cùng một quy trình quản lý khóa tách biệt với database.

**Mục tiêu của bài học:**

- Hiểu token nào cần bảo vệ và những đối thủ nào cơ chế mã hóa khi lưu có thể chống lại.
- Phân biệt mã hóa token ở tầng ứng dụng với HTTPS, TDE, hash, JWT signing và session cookie security.
- Thiết kế **authenticated encryption (AEAD)** với AES-GCM, nonce/IV duy nhất và **Additional Authenticated Data (AAD)**.
- Quản lý **Data Encryption Key (DEK)** và **Key Encryption Key (KEK)** qua KMS/HSM, lưu `keyId` hoặc `keyVersion` với ciphertext.
- Tích hợp mã hóa vào `OAuth2AuthorizedClientService` / repository mà không phá cơ chế refresh, principal ownership hoặc OIDC Login.
- Tổ chức **key rotation**, migration dữ liệu cũ, re-encryption, xử lý mất khóa, audit và incident response.
- Có ví dụ Java 17, định dạng lưu trữ, bảng lựa chọn, sơ đồ và kịch bản kiểm thử.

> **Nguyên tắc nền tảng:** đừng tự phát minh thuật toán mã hóa. Sử dụng primitive chuẩn, thư viện được duy trì và dịch vụ quản lý khóa của hạ tầng. Ví dụ Java bên dưới minh họa **cách dùng JCA AES-GCM và thiết kế boundary**; production cần review cryptography, key management, threat model và tích hợp KMS theo hạ tầng cụ thể.

## 2. Những credential thường tồn tại trong OAuth2/OIDC Client

| Loại dữ liệu | Được dùng ở đâu? | Vì sao phải bảo vệ? |
| --- | --- | --- |
| **Access Token** | Gửi đến Resource Server để truy cập API | Có thể bị dùng để gọi API đến khi token không còn hiệu lực |
| **Refresh Token** | Gửi đến Authorization Server Token Endpoint | Có thể tạo Access Token mới; thường có giá trị dài hạn hơn |
| **Client Secret** | Client authentication ở Token Endpoint | Có thể cho phép machine/client xin token khi kết hợp client ID và grant |
| **Private key cho private_key_jwt** | Ký JWT client assertion | Nếu bị lộ có thể cho phép impersonate confidential client |
| **ID Token** | OIDC client dùng để xác thực thông tin đăng nhập | Chứa claims danh tính, thường nhạy cảm; không dùng thay Access Token |
| **Authorization code** | Đổi lấy token một lần tại Token Endpoint | Nhạy cảm trong quá trình callback; không cần lưu dài hạn như token |
| **Session ID/cookie** | Liên kết browser với phiên đăng nhập | Nếu bị đánh cắp có thể làm mất session security |

### 2.1. Bearer Token đặc biệt nhạy cảm

Với OAuth2 Bearer Token:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

ai có được token có thể thử sử dụng nó. Scope, audience, expiry, sender constraint hoặc các biện pháp xác thực bổ sung có thể giảm tác hại, nhưng **không thể coi Access Token là dữ liệu công khai**.

### 2.2. Refresh Token cần ưu tiên bảo vệ

Refresh Token thường không được gửi đến API nghiệp vụ; nó chỉ nên được dùng ở Token Endpoint. Trong nhiều hệ thống, nó sống qua nhiều lần Access Token hết hạn. Vì thế, đánh cắp Refresh Token có thể nguy hiểm hơn đánh cắp Access Token ngắn hạn.

Authorization Server có thể triển khai **refresh token rotation**, sử dụng sender-constrained tokens hoặc chính sách phát hiện replay. Các biện pháp đó hữu ích nhưng **không thay thế bảo vệ Refresh Token khi lưu**.

### 2.3. ID Token có cần được mã hóa khi lưu không?

ID Token có thể chứa thông tin cá nhân, group và claims nhạy cảm. Nếu ứng dụng lưu ID Token lâu dài, cần xem xét confidentiality, retention và mục đích sử dụng. Tuy nhiên, `OAuth2AuthorizedClient` chuẩn của Spring Security tập trung vào Access Token và Refresh Token; ID Token thuộc một phần khác của OIDC authentication state.

Không mặc định chỉ mã hóa `OAuth2AuthorizedClient` là đã bảo vệ tất cả `OidcUser`, ID Token hoặc session authentication được serialize ở một kho khác.

## 3. Threat model: cơ chế mã hóa bảo vệ trước điều gì?

Một thiết kế đúng bắt đầu bằng **đối thủ, bề mặt dữ liệu và giới hạn bảo vệ**, chứ không chỉ chọn AES-256.

| Kịch bản | Mã hóa ở tầng ứng dụng có ích? | Giới hạn |
| --- | --- | --- |
| Đọc trộm bản backup database | **Có**, nếu khóa giải mã không nằm trong backup | Nếu backup cũng có key hoặc service credentials mạnh, lớp bảo vệ yếu đi |
| SQL account bị lạm dụng để SELECT bảng token | **Có**, nếu app mã hóa trước khi INSERT và DB không có khóa | Kẻ tấn công có thể phá hoại/xóa dữ liệu, ghi đè ciphertext |
| Lộ database snapshot/replica | **Có** | Metadata không mã hóa vẫn có thể bị lộ |
| Disk/volume bị mất | Có; disk encryption/TDE cũng có vai trò | Cần phối hợp với encryption at rest của hạ tầng |
| Kẻ tấn công có remote code execution trong app | **Không bảo đảm**, vì app có thể gọi decrypt | Cần runtime isolation, egress policy, secret management và monitoring |
| Tài khoản cloud có quyền dùng KMS decrypt + đọc database | Bảo vệ hạn chế | Cần phân quyền độc lập và cảnh báo bất thường |
| Token bị ghi vào HTTP/application log | **Không**, mã hóa DB không che được log plaintext | Phải redact/không log credential |
| Browser bị XSS và lấy cookie phiên | Không trực tiếp | Phải dùng HttpOnly/Secure/SameSite, CSP và session security |
| Resource Server chấp nhận token sai audience | Không | Phải validate issuer/audience/scope tại API |
| Refresh Token bị replay | Không hoàn toàn | Cần rotation, revocation và sender-constraining nếu có |

### 3.1. Những gì phải bảo vệ

Các vị trí thường chứa bản sao token:

~~~text
Spring Security OAuth2AuthorizedClient
  |
  +-- JDBC database / ORM entity
  +-- HTTP session state / Redis
  +-- distributed cache
  +-- backups, replicas, snapshots
  +-- migration/export scripts
  +-- application logs, traces, APM  <-- nên không có token
  +-- heap dumps / crash artifacts   <-- cần chính sách hạn chế
  +-- support/debug screenshots       <-- nên không có token
~~~

Mã hóa ở tầng ứng dụng hiệu quả khi được đặt **trước các nơi lưu bền vững hoặc chia sẻ**, và key management không cho phép cùng một đối tượng tùy ý lấy cả ciphertext lẫn decryption key.

### 3.2. Không hứa điều mã hóa không làm được

Mã hóa token khi lưu **không**:

- Ngăn code ứng dụng hợp lệ đọc token sau khi giải mã.
- Ngăn kẻ tấn công có RCE trong app cố sử dụng khả năng giải mã của app.
- Tự thu hồi OAuth2 token đã bị đánh cắp trước đó.
- Kiểm tra scope/audience của Access Token.
- Thay thế session authorization, access control, MFA hay API security.
- Bảo đảm an toàn nếu khóa, ciphertext và quyền decrypt đều nằm cùng một bản backup.

Vì vậy, một hệ thống tốt thường dùng **phòng thủ nhiều lớp (defense in depth)**.

## 4. Mã hóa token khác hash, JWT signature, TLS và TDE

### 4.1. Hash không đáp ứng mục đích gọi API

Nếu ứng dụng cần gửi Access Token đến Resource Server hoặc Refresh Token đến Authorization Server, nó phải **khôi phục giá trị token gốc**. Hash một chiều như SHA-256 không cho phép khôi phục dữ liệu.

~~~text
Token -> SHA-256 -> digest
              |
              +-- không khôi phục token để gọi API
~~~

Hash/HMAC có thể hữu ích khi **chỉ cần so khớp token** hoặc tạo fingerprint không lộ giá trị (chẳng hạn HMAC keyed fingerprint cho audit chống trùng). Nhưng nó không thay được **reversible encryption** cho token cần tái sử dụng.

Không dùng hash ngắn/truncate tùy tiện để log nhận dạng token nếu hệ thống không có chính sách chống lộ/tương quan; thậm chí fingerprint cũng có thể là dữ liệu nhạy cảm.

### 4.2. JWT được ký không có nghĩa nội dung được mã hóa

Nhiều Access Token hoặc ID Token có dạng JWT/JWS:

~~~text
header.payload.signature
~~~

Signature cho phép phát hiện sửa đổi và xác minh bên phát hành theo thuật toán/trust key phù hợp. **Payload thường có thể được base64url decode và đọc**; JWT ký không mặc định bảo mật nội dung.

Mã hóa JWT theo JWE là một cơ chế khác. Nếu provider phát hành JWT/JWS, ứng dụng vẫn có thể cần **mã hóa nó khi lưu ở database**, đặc biệt vì credential value có thể bị dùng lại.

### 4.3. HTTPS/TLS bảo vệ trên đường truyền

HTTPS bảo vệ token khi trao đổi với Token Endpoint và Resource Server, nếu hostname/certificate validation đúng. Tuy nhiên TLS **không mã hóa một cột token đã được ghi vào database**.

### 4.4. Database TDE và disk encryption

**Transparent Data Encryption (TDE)**, encrypted volumes và backup encryption bảo vệ chủ yếu ở lớp thiết bị hoặc storage. Nhưng một process có quyền truy vấn database có thể nhận **giá trị cột plaintext**.

**Application-level encryption** làm database chỉ nhận ciphertext:

~~~text
App memory: Access Token plaintext
     |
     | AES-GCM encrypt
     v
DB column: encrypted payload
~~~

Hai lớp có thể bổ trợ nhau: TDE bảo vệ storage còn application encryption bảo vệ trường nhạy cảm trước quyền đọc DB quá rộng.

## 5. Sơ đồ kiến trúc: mã hóa trước khi save và giải mã sau khi load

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application Service
    participant M as OAuth2AuthorizedClientManager
    participant Vault as Encrypted Authorized Client Store
    participant KMS as KMS/HSM
    participant DB as Token Database
    participant AS as Authorization Server
    App->>M: authorize(registrationId, principal)
    M->>Vault: loadAuthorizedClient(registrationId, principal)
    Vault->>DB: SELECT encrypted record
    DB-->>Vault: ciphertext + metadata + keyId
    Vault->>KMS: unwrap/resolve đúng data key (nếu cần)
    KMS-->>Vault: key material hoặc crypto operation
    Vault->>Vault: AEAD decrypt + verify tag/AAD
    Vault-->>M: OAuth2AuthorizedClient
    alt Cần refresh hoặc cấp mới
        M->>AS: Token Endpoint grant request
        AS-->>M: New Access Token / optional Refresh Token
        M->>Vault: saveAuthorizedClient(new client)
        Vault->>KMS: generate/unwrap data key theo thiết kế
        Vault->>Vault: AEAD encrypt payload + nonce + AAD
        Vault->>DB: UPSERT ciphertext, metadata, key references
    end
    M-->>App: Authorized client phù hợp
~~~

Trong hệ thống **envelope encryption**, việc lấy data key có thể diễn ra qua một lần `GenerateDataKey` hoặc thao tác unwrap DEK. KMS có thể trả plaintext data key cho process được phép, hoặc thực thi operation bên trong hardware/service tùy sản phẩm. Sơ đồ không yêu cầu gửi **raw OAuth2 token** đến KMS; ứng dụng có thể dùng DEK local trong memory để mã hóa payload.

### 5.1. Chỗ mã hóa nên nằm ở đâu?

Thông thường:

~~~text
OAuth2AuthorizedClientManager
  -> OAuth2AuthorizedClientService / Repository
      -> Encrypted persistence adapter
          -> DAO / JDBC / Redis / session serializer
~~~

Đặt mã hóa ở tầng **persistence adapter** khiến ứng dụng gọi manager như bình thường. Không bắt từng controller mã hóa token bằng tay.

### 5.2. Không tạo một kho plaintext song song

Thiết kế không nên:

~~~text
Manager -> Default JdbcOAuth2AuthorizedClientService -> plaintext DB
                     |
                     +-- custom audit store -> encrypted copy
~~~

vì bản plaintext vẫn còn. Cần bảo đảm **đường save thực sự được Spring Security sử dụng** đi qua lớp mã hóa, và không có repository/session store khác vẫn persist plaintext ngoài ý muốn.

## 6. Thuật toán phù hợp: Authenticated Encryption with Associated Data (AEAD)

### 6.1. Vì sao chỉ “mã hóa” là chưa đủ?

Một kẻ tấn công đọc được database có thể không biết plaintext, nhưng vẫn có thể **thay ciphertext hoặc hoán đổi bản ghi**. Nếu dùng kiểu mã hóa không bảo vệ integrity, ứng dụng có nguy cơ xử lý dữ liệu bị chỉnh sửa.

AEAD cung cấp hai tính chất:

1. **Confidentiality:** không thể đọc plaintext nếu không có key.
2. **Integrity/authenticity:** ciphertext hoặc dữ liệu liên kết bị sửa thì giải mã thất bại.

Trong Java JCA, thuật toán phổ biến:

~~~java
Cipher.getInstance("AES/GCM/NoPadding");
~~~

AES-GCM hỗ trợ **authentication tag** thường dài 128 bit và **nonce/IV** thường dài 96 bit.

### 6.2. Các thông số khuyến nghị trong ví dụ

| Tham số | Lựa chọn trong bài | Ý nghĩa |
| --- | --- | --- |
| Thuật toán | AES-GCM | Mã hóa có kiểm tra toàn vẹn |
| AES key | 256 bit nếu policy/JRE/KMS hỗ trợ | Khóa đối xứng cho record/token |
| Nonce/IV | 96 bit = 12 byte | Phải khác nhau giữa các lần encrypt **dưới cùng key** |
| Tag | 128 bit | Phát hiện dữ liệu bị sửa |
| AAD | registration/principal/tenant/token kind/record context | Ràng buộc ciphertext vào đúng vị trí |
| Key reference | `keyId` / `keyVersion` | Giải mã record cũ sau rotation |
| Format version | Ví dụ `v1` | Cho phép thay định dạng/thuật toán có kiểm soát |

### 6.3. Nonce không phải mật khẩu hay secret

Nonce/IV thường được lưu cùng ciphertext:

~~~text
version | keyId | nonce | ciphertext_and_tag
~~~

Nonce **không cần bí mật** nhưng **không được tái sử dụng cho hai plaintext khác nhau với cùng AES-GCM key**. Tái sử dụng nonce trong GCM có thể phá nghiêm trọng tính bảo mật và tính toàn vẹn.

Với lưu lượng thông thường, nonce 96-bit sinh bằng `SecureRandom` là cách triển khai phổ biến. Với key dùng mã hóa khối lượng rất lớn, cần chính sách **giới hạn số lần mã hóa trên mỗi key**, key rotation và/hoặc cơ chế cấp nonce bảo đảm uniqueness. Đừng dùng timestamp, user ID hay cùng một IV cố định.

### 6.4. Mỗi lần cập nhật token phải mã hóa lại bằng nonce mới

Refresh Token rotation:

~~~text
Record hiện tại:
  accessToken = A1
  refreshToken = R1

Authorization Server refresh thành công:
  accessToken = A2
  refreshToken = R2

Persistence:
  mã hóa payload mới với nonce MỚI
  ghi ciphertext mới trong một operation/transaction phù hợp
~~~

Không dùng lại nonce cũ chỉ vì vẫn đang cập nhật cùng một hàng database.

## 7. AAD: ràng buộc ciphertext với đúng chủ sở hữu

**Additional Authenticated Data (AAD)** là dữ liệu không nhất thiết bị mã hóa nhưng được đưa vào phép tính authentication tag. Nếu AAD khi decrypt khác AAD lúc encrypt, AEAD verification thất bại.

Trong OAuth2 Client, AAD có thể bao gồm:

~~~text
application-domain
format-version
key-id
tenant-id
client-registration-id
principal-name
token-kind
stable-record-id (nếu hệ thống có)
~~~

Ví dụ:

~~~text
AAD của Access Token Alice:
  tenant=company-a
  registration=calendar
  principal=alice-sub-123
  kind=access-token

AAD của Refresh Token Bob:
  tenant=company-a
  registration=calendar
  principal=bob-sub-456
  kind=refresh-token
~~~

Một ciphertext của Alice **không thể chỉ bị copy** sang hàng của Bob rồi giải mã hợp lệ nếu application tái tạo AAD từ identity đã được xác minh.

### 7.1. AAD phải được tạo theo quy tắc ổn định

Không ghép các trường bằng dấu phân cách mơ hồ:

~~~text
tenant + "|" + registration + "|" + principal
~~~

nếu bản thân các giá trị có thể chứa dấu phân cách hoặc khác biệt Unicode encoding/canonicalization. Trong ví dụ Java, dùng **UTF-8 có length-prefix** cho từng trường để tránh ambiguity.

### 7.2. AAD không tự xác thực danh tính request

Nếu code cho browser tự đưa `principalName="admin"` hoặc `tenantId="other-tenant"` để lấy token từ database, AAD không giải quyết **authorization bug** đó. AAD chỉ ràng buộc cryptographic; quyền truy cập record phải được kiểm tra **trước khi load/decrypt**.

### 7.3. Khi thay đổi principal hoặc registration

Nếu AAD bao gồm principal name, đổi khóa định danh user sẽ khiến ciphertext cũ không decrypt được với AAD mới. Điều này là **thiết kế có chủ đích**, không phải lỗi ngẫu nhiên.

Khi cần migrate identity:

1. Đọc bản ghi bằng **AAD cũ** theo nguồn identity đáng tin.
2. Decrypt bằng key cũ hợp lệ.
3. Encrypt lại bằng **AAD mới** và nonce mới.
4. Ghi record mới atomically/kiểm soát version.
5. Xóa hoặc vô hiệu hóa record cũ theo migration policy.

Với OIDC, một định danh user bền vững thường dựa trên **issuer + subject** thay vì email hiển thị có thể thay đổi.

## 8. Cấu trúc dữ liệu mã hóa và key version

Không nên chỉ lưu một Base64 string rồi đoán thuật toán khi decrypt. Một envelope có metadata rõ sẽ giúp upgrade an toàn:

~~~json
{
  "formatVersion": 1,
  "algorithm": "AES-256-GCM",
  "keyId": "token-store-key-v3",
  "nonce": "BASE64URL_NONCE",
  "ciphertext": "BASE64URL_CIPHERTEXT_AND_TAG"
}
~~~

Đây là **format minh họa**, không phải schema Spring Security có sẵn. Metadata public này không chứa plaintext token. Nếu dùng encryption envelope với DEK riêng:

~~~json
{
  "formatVersion": 2,
  "algorithm": "AES-256-GCM",
  "kekId": "kms-key-reference",
  "wrappedDek": "BASE64URL_ENCRYPTED_DATA_KEY",
  "nonce": "BASE64URL_NONCE",
  "ciphertext": "BASE64URL_CIPHERTEXT_AND_TAG"
}
~~~

### 8.1. Cái gì được phép để rõ?

Tùy threat model, database có thể cần các cột sau để tìm record:

~~~text
registration_id
principal_key
tenant_id
key_id
format_version
ciphertext
updated_at
row_version
~~~

Ngay cả khi token value được mã hóa, **principal ID, tenant, registration và timestamps có thể vẫn là metadata nhạy cảm**. Cần kiểm soát quyền đọc, retention, masking hoặc pseudonymization theo yêu cầu.

### 8.2. Không chỉ mã hóa token value rồi bỏ metadata không xác thực

Nếu database lưu:

~~~text
access_token_value -> encrypted
access_token_expires_at -> plaintext, không được ràng buộc
access_token_scopes -> plaintext, không được ràng buộc
~~~

kẻ tấn công có quyền sửa database có thể thay `expiresAt` hoặc `scopes` nếu ứng dụng tin chúng. Giải pháp:

- Mã hóa **toàn bộ token payload/metadata liên quan** trong một AEAD envelope; hoặc
- Ràng buộc các metadata quan trọng vào AAD theo một serialization ổn định và kiểm tra khi decrypt.

Trong bài này, ví dụ Java mã hóa **byte[] plaintext**; application nên đóng gói Access Token, Refresh Token và metadata cần bảo vệ thành một record/DTO an toàn trước khi encrypt.

### 8.3. Access Token và Refresh Token có thể mã hóa riêng không?

Có, nếu có lý do về dữ liệu/rotation, nhưng mỗi trường cần **nonce riêng** và AAD phân biệt token kind:

~~~text
access_ciphertext  -> AAD(..., kind=access_token)
refresh_ciphertext -> AAD(..., kind=refresh_token)
~~~

Phải cập nhật hai trường nhất quán khi Refresh Token được xoay vòng. Một cách giảm complexity là **mã hóa một bundle** chứa cả Access Token, Refresh Token và metadata của một authorized client, sau đó update bundle atomically.

## 9. Java 17: triển khai lớp AES-GCM có AAD và key version

Đoạn dưới đây là ví dụ **thuần Java Cryptography Architecture (JCA)**, độc lập với cụ thể Redis/JDBC/Spring Security. Nó mô tả ranh giới:

- `KeyProvider`: cung cấp khóa hiện hành để encrypt và resolve khóa cũ khi decrypt; **implementation production phải tích hợp KMS/HSM/envelope policy**.
- `TokenContext`: thông tin trusted dùng để tạo AAD.
- `AeadTokenCipher`: mã hóa/giải mã byte[] với AES-GCM; không tự lưu token vào DB.
- Ciphertext có dạng `v1.{base64url(keyId)}.{base64url(nonce)}.{base64url(ciphertextAndTag)}`.

**Không hard-code key vào source code.** Ví dụ cố ý **không có class production tự đọc AES key từ application.yml**, vì quản lý khóa là phần cần được tích hợp vào KMS của mỗi hệ thống.

### 9.1. KeyProvider và TokenContext

~~~java
package com.example.security.crypto;

import java.util.Objects;
import javax.crypto.SecretKey;

public interface KeyProvider {

    // Trả key version hiện tại cho lần mã hóa MỚI.
    ActiveKey currentKey();

    // Giải quyết phiên bản key cũ để đọc dữ liệu đã lưu.
    // Nếu bị revoke/mất key, phải fail closed.
    SecretKey keyById(String keyId);

    record ActiveKey(String keyId, SecretKey key) {
        public ActiveKey {
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(key);
        }
    }
}
~~~

~~~java
package com.example.security.crypto;

import java.util.Objects;

public record TokenContext(
        String tenantId,
        String registrationId,
        String principalName,
        String tokenKind) {

    public TokenContext {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(registrationId);
        Objects.requireNonNull(principalName);
        Objects.requireNonNull(tokenKind);

        if (tenantId.isBlank()
                || registrationId.isBlank()
                || principalName.isBlank()
                || tokenKind.isBlank()) {
            throw new IllegalArgumentException(
                "Token context must contain nonblank identity fields");
        }
    }
}
~~~

Các class/interface này được đặt ở **file Java riêng** theo quy định Java về public top-level types. `tenantId` và `principalName` phải lấy từ ứng dụng/authentication/store đã được xác thực, không phải query parameter do caller tự đưa.

### 9.2. AeadTokenCipher

~~~java
package com.example.security.crypto;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Objects;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AeadTokenCipher {

    private static final String VERSION = "v1";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int TAG_BYTES = TAG_BITS / 8;
    private static final int MAX_ENVELOPE_LENGTH = 256_000;

    private final KeyProvider keys;
    private final SecureRandom random = new SecureRandom();
    private final Base64.Encoder encoder =
        Base64.getUrlEncoder().withoutPadding();
    private final Base64.Decoder decoder =
        Base64.getUrlDecoder();

    public AeadTokenCipher(KeyProvider keys) {
        this.keys = Objects.requireNonNull(keys);
    }

    public String encrypt(byte[] plaintext, TokenContext context) {
        Objects.requireNonNull(plaintext);
        Objects.requireNonNull(context);

        KeyProvider.ActiveKey current = keys.currentKey();
        String keyId = current.keyId();
        SecretKey key = current.key();

        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce); // IV mới mỗi lần encrypt

        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(context, keyId));

            // JCA GCM trả ciphertext cùng authentication tag.
            byte[] ciphertextAndTag = cipher.doFinal(plaintext);

            return VERSION + "."
                + encode(keyId.getBytes(StandardCharsets.UTF_8)) + "."
                + encode(nonce) + "."
                + encode(ciphertextAndTag);
        } catch (GeneralSecurityException ex) {
            throw new TokenCryptoException(
                "Could not encrypt token payload", ex);
        }
    }

    public byte[] decrypt(String envelope, TokenContext context) {
        Objects.requireNonNull(envelope);
        Objects.requireNonNull(context);

        if (envelope.length() > MAX_ENVELOPE_LENGTH) {
            throw new TokenCryptoException(
                "Invalid encrypted token envelope");
        }

        try {
            String[] parts = envelope.split("\\.", -1);
            if (parts.length != 4 || !VERSION.equals(parts[0])) {
                throw new IllegalArgumentException("Bad envelope version");
            }

            String keyId = new String(
                decoder.decode(parts[1]),
                StandardCharsets.UTF_8);
            byte[] nonce = decoder.decode(parts[2]);
            byte[] ciphertextAndTag = decoder.decode(parts[3]);

            if (keyId.isBlank()
                    || nonce.length != NONCE_BYTES
                    || ciphertextAndTag.length < TAG_BYTES) {
                throw new IllegalArgumentException(
                    "Malformed encrypted token");
            }

            // KeyProvider phải từ chối keyId không được phép,
            // không có fallback key mặc định.
            SecretKey key = keys.keyById(keyId);
            if (key == null) {
                throw new IllegalStateException("Unknown key version");
            }

            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, nonce));
            cipher.updateAAD(aad(context, keyId));

            // Nếu ciphertext, nonce, key hoặc AAD sai:
            // doFinal thất bại, không trả plaintext.
            return cipher.doFinal(ciphertextAndTag);
        } catch (GeneralSecurityException
                | IllegalArgumentException
                | IllegalStateException ex) {
            throw new TokenCryptoException(
                "Could not decrypt encrypted token payload", ex);
        }
    }

    private String encode(byte[] value) {
        return encoder.encodeToString(value);
    }

    private static byte[] aad(
            TokenContext context,
            String keyId) {

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream data = new DataOutputStream(buffer)) {
            writeField(data, "oauth2-authorized-client-store");
            writeField(data, VERSION);
            writeField(data, keyId);
            writeField(data, context.tenantId());
            writeField(data, context.registrationId());
            writeField(data, context.principalName());
            writeField(data, context.tokenKind());
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Could not encode encryption context", ex);
        }

        return buffer.toByteArray();
    }

    private static void writeField(
            DataOutputStream data,
            String text) throws IOException {

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        data.writeInt(bytes.length);
        data.write(bytes);
    }
}
~~~

### 9.3. Exception không chứa plaintext token

~~~java
package com.example.security.crypto;

public final class TokenCryptoException extends RuntimeException {

    public TokenCryptoException(String message) {
        super(message);
    }

    public TokenCryptoException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Không đính plaintext, raw token response hoặc full envelope vào exception message. Trong production, khi log/cung cấp API error, **không tự động in toàn bộ exception chain** nếu KMS/client library có thể đưa chi tiết nhạy cảm vào cause. Thiết kế mã lỗi nội bộ và log đã được lọc.

### 9.4. Cách dùng

~~~java
TokenContext context = new TokenContext(
    "company-a",
    "calendar",
    "issuerA-sub123",
    "authorized-client-payload");

byte[] serializedPayload =
    /* byte[] từ serializer DTO đã được kiểm soát */;

String encrypted = tokenCipher.encrypt(
    serializedPayload, context);

// DB lưu encrypted (không lưu serializedPayload).

byte[] restored = tokenCipher.decrypt(encrypted, context);
// Dùng restored để khôi phục OAuth2AuthorizedClient.
~~~

Đây là **mẫu tích hợp**, với `tokenCipher` và serializer do ứng dụng cung cấp. Không dùng phép `new String(restored)` rồi log. Khi xử lý byte[] có thể xóa buffer sau khi dùng bằng `Arrays.fill(...)` nếu cấu trúc code cho phép, nhưng Java không bảo đảm xóa mọi bản sao trong heap và Spring Security token values thường được biểu diễn bằng `String` bất biến.

### 9.5. Vì sao thiết kế này phù hợp hơn hard-code key?

Code crypto không chứa key value. KeyProvider có thể:

- Resolve key đang hoạt động từ KMS-backed key registry.
- Decrypt wrapped DEK theo cấu trúc envelope encryption.
- Từ chối key version không được phép.
- Hỗ trợ giai đoạn đọc old key và ghi bằng new key.
- Ghi audit decryption operations ở tầng KMS mà không log token.

Đoạn mã **không được hiểu là đã triển khai KMS**, và không có tác dụng bảo vệ nếu `KeyProvider` thực tế chỉ trả một AES key hard-code, lưu cùng database hoặc commit trong source repository.

## 10. Không sử dụng một khóa bí mật cố định trong source hoặc config file

Một phản ví dụ:

~~~java
// PHẢN VÍ DỤ: tuyệt đối không commit khóa AES vào source.
byte[] keyBytes =
    "0123456789abcdef0123456789abcdef"
        .getBytes(StandardCharsets.UTF_8);
~~~

Dù 32 byte có vẻ đủ dài cho AES-256, đây là giá trị dễ đoán, xuất hiện trong source và có thể được nhiều môi trường cùng dùng.

Một phản ví dụ khác:

~~~yaml
security:
  token-store:
    encryption-key: "base64:REAL_PRODUCTION_KEY_HERE"
~~~

Nếu cấu hình được commit hoặc lưu trong database cùng token, cơ chế bảo vệ trước lộ source/backup rất yếu.

**Lựa chọn thích hợp hơn:** dùng cloud KMS/HSM, secret manager được bảo vệ hoặc mô hình quản lý khóa tập trung; ứng dụng lấy quyền sử dụng key bằng workload identity/role ngắn hạn, không chứa raw key trong repository.

### 10.1. Biến môi trường có đủ không?

Environment variable có thể tốt hơn hard-code trong source, nhưng **không mặc nhiên** tương đương KMS:

- Giá trị có thể bị đưa vào process dump hoặc diagnostic output.
- Người có quyền xem cấu hình deployment có thể đọc nó.
- Mọi instance có thể dùng chung key không được versioning.
- Rotation và revoke khó audit nếu thiếu một key-management lifecycle.

Trong môi trường có yêu cầu bảo mật cao, ưu tiên key hierarchy, KMS authorizations và tách quyền đọc database khỏi quyền giải mã.

## 11. Envelope encryption: DEK và KEK

**Envelope encryption** là một kiến trúc phổ biến để quản lý nhiều ciphertext mà không phải gửi mọi payload lớn vào KMS.

- **DEK (Data Encryption Key):** khóa đối xứng thực sự mã hóa payload token bằng AES-GCM.
- **KEK (Key Encryption Key):** khóa dùng để **wrap/encrypt DEK**; thường do KMS/HSM bảo vệ và không xuất raw KEK cho ứng dụng.
- **Wrapped DEK:** bản DEK đã được mã hóa, có thể lưu cạnh ciphertext mà không lộ DEK plaintext.

### 11.1. Sơ đồ envelope encryption

~~~mermaid
flowchart TB
    A["OAuth2AuthorizedClient chứa token"] --> B["Serialize payload"]
    C["KMS/HSM: KEK được quản lý"] --> D["GenerateDataKey / wrap DEK"]
    D --> E["Plaintext DEK tạm thời trong app memory"]
    D --> F["Wrapped DEK"]
    B --> G["AES-256-GCM encrypt với DEK + nonce + AAD"]
    E --> G
    G --> H["Ciphertext + nonce + auth tag"]
    F --> I["Database record"]
    H --> I
    I --> J["Lúc load: lấy wrapped DEK và ciphertext"]
    J --> K["KMS unwrap DEK theo key policy"]
    K --> L["AES-GCM decrypt + verify AAD"]
    J --> L
    L --> M["OAuth2AuthorizedClient tại app memory"]
~~~

Trong một số KMS, `GenerateDataKey` trả **plaintext DEK và encrypted DEK** cho principal đã được cấp quyền; ứng dụng sử dụng DEK trong memory rồi hạn chế thời gian tồn tại của buffer. Hệ thống khác có thể dùng `Encrypt`/`Decrypt` hoặc HSM operations. API, encryption context, limits và key policies cần theo đúng provider.

### 11.2. Vì sao không mã hóa token trực tiếp bằng KEK ở KMS?

Có thể dùng KMS encrypt trực tiếp cho dữ liệu nhỏ ở một số hạ tầng, nhưng:

- Các KMS APIs có giới hạn payload size.
- Mỗi mã hóa/giải mã có chi phí, latency, quota và phụ thuộc network.
- Việc gửi raw token qua KMS request cần đánh giá logging/telemetry và trust boundary.
- Key rotation/per-record isolation có thể cần kiểm soát riêng.

Envelope encryption cho phép data plane mã hóa ở application memory và KMS tập trung vào việc bảo vệ DEK/KEK.

### 11.3. Một DEK cho mỗi record hay nhiều records?

| Mô hình | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Mỗi record một DEK | Hạn chế phạm vi ảnh hưởng khi lộ một DEK, không lo nonce reuse giữa records dưới cùng key | Nhiều wrapped DEKs, KMS/caching overhead |
| Mỗi tenant một DEK | Có thể tách blast radius theo tenant | Quản lý key lifecycle phức tạp hơn |
| Một DEK chung theo service/key version | Đơn giản, ít wrapped keys | Phải quản lý chặt nonce uniqueness và số lần mã hóa; blast radius lớn hơn |
| Per-field DEK | Tách riêng Access/Refresh Token | Nhiều keys, metadata và operations hơn |

Không có một mô hình duy nhất phù hợp cho mọi dự án. Với Refresh Token có giá trị cao, per-record DEK hoặc tenant isolation có thể hữu ích. Nếu dùng DEK chung, cần key usage limits, rotation và monitoring đáng tin cậy.

### 11.4. Plaintext DEK sống ở đâu?

Trong envelope encryption, plaintext DEK có thể tồn tại tạm thời trong process memory. Cần:

- Không log key hoặc dump object của KeyProvider.
- Chỉ giữ buffer trong thời gian cần thiết.
- Giới hạn quy trình lấy/decrypt key theo authorization.
- Cân nhắc zeroing byte[] khi API cho phép, nhưng không hứa Java loại bỏ mọi bản sao.
- Không ghi DEK plaintext vào Redis, database, file cấu hình hoặc exception.

## 12. KMS/HSM: tách quyền truy cập ciphertext và quyền dùng key

### 12.1. Hai nhóm quyền không nên trùng nhau tùy tiện

~~~text
Database reader
   -> SELECT ciphertext
   -> KHÔNG tự gọi KMS Decrypt

Application runtime
   -> SELECT ciphertext
   -> gọi KMS unwrap/decrypt theo workload identity

Key administrator
   -> quản trị version/rotation/policy
   -> không mặc định có quyền đọc bảng token
~~~

Đây là nguyên tắc **separation of duties**. Nếu một tài khoản cloud có thể đọc database, tải mọi backup và gọi KMS decrypt không giới hạn, mã hóa ở tầng ứng dụng bị suy yếu đáng kể.

### 12.2. Các chính sách cần có

1. **Least privilege:** chỉ service được phép mới decrypt key phục vụ token store của nó.
2. **Workload identity:** ưu tiên role/service account/mTLS identity tạm thời, không commit key access credentials.
3. **Environment isolation:** production/staging/development dùng keys và permissions riêng.
4. **Tenant isolation** nếu threat model yêu cầu.
5. **Audit trail:** ghi hoạt động sử dụng key, thay policy và rotation; không ghi plaintext token.
6. **Key lifecycle:** active, decrypt-only, disabled, retired, destroyed.
7. **Break-glass control:** truy cập khẩn cấp phải được duyệt, giám sát và thu hồi.
8. **Regional/availability design:** KMS outage cần fail closed và có khả năng phục hồi.

### 12.3. KMS encryption context

Một số KMS hỗ trợ **encryption context** — các cặp key-value được xác thực cùng thao tác wrap/unwrap key. Có thể ràng buộc:

~~~text
application=oauth2-token-store
environment=production
tenant=company-a
purpose=authorized-client-dek
~~~

Không đưa Access Token, Refresh Token, Client Secret hoặc thông tin cá nhân không cần thiết vào encryption context; nó có thể xuất hiện trong KMS audit logs hoặc policy metadata. Context khi unwrap phải khớp với khi wrap.

**KMS encryption context** và **AES-GCM AAD** có thể được dùng cùng nhau, nhưng là hai cơ chế ở hai tầng: context ràng buộc wrapped DEK tại KMS, còn AAD ràng buộc ciphertext token vào record identity trong application.

### 12.4. Đừng dùng JWT signing key làm AES storage key

OIDC Provider công bố **public signing keys** qua JWKS để client xác minh ID Token/JWT. Những keys đó không phải key bí mật của ứng dụng để mã hóa token khi lưu.

Phân biệt:

~~~text
OIDC JWKS public key
  -> verify ID Token signature

Application token-store encryption key
  -> AES-GCM encrypt/decrypt stored credentials

OAuth2 client private key
  -> sign private_key_jwt client assertion
~~~

Không dùng một key cho ba mục đích khác nhau chỉ vì chúng cùng thuộc "security".

## 13. Spring Security lưu authorized client ở đâu?

Với Servlet OAuth2 Client:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository
~~~

Với Reactive:

~~~java
org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService
org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository
~~~

### 13.1. Những implementation thường gặp

| Lớp lưu trữ | Ví dụ | Điểm cần lưu ý |
| --- | --- | --- |
| Memory của process | `InMemoryOAuth2AuthorizedClientService` | Không persistent qua restart, nhưng token vẫn có thể ở heap dumps |
| Servlet HTTP session | `HttpSessionOAuth2AuthorizedClientRepository` | Serialized session/replication/Redis có thể chứa token |
| JDBC service | `JdbcOAuth2AuthorizedClientService` | Cần kiểm soát cách các token values được ghi vào bảng |
| Servlet repository adapter | `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Có thể delegate vào service cho authenticated user |
| Reactive service | `InMemoryReactiveOAuth2AuthorizedClientService` hoặc custom service | Chú ý reactive storage semantics và non-blocking I/O |
| Reactive server repository | `ServerOAuth2AuthorizedClientRepository` implementation | Có thể lưu qua WebSession hoặc delegate |

**Spring Security không mặc định có một công tắc chung để mã hóa mọi OAuth2 token ở mọi kho lưu.** Không chỉ bật JDBC/TDE hoặc `oauth2Client()` rồi giả định Access Token/Refresh Token đã được application encrypt trước khi lưu.

### 13.2. Vị trí tích hợp tốt

Thiết kế có thể là:

~~~text
DefaultOAuth2AuthorizedClientManager
  -> OAuth2AuthorizedClientRepository
     -> AuthorizedClientService-backed repository
        -> EncryptedOAuth2AuthorizedClientService (custom)
           -> EncryptedAuthorizedClientDao
              -> database
~~~

Trong Reactive:

~~~text
DefaultReactiveOAuth2AuthorizedClientManager
  -> ServerOAuth2AuthorizedClientRepository
     -> custom reactive encrypted store
        -> nonblocking DAO / Redis / R2DBC
~~~

**Không chỉ decorate một service mà manager không thực sự sử dụng.** Cần xác minh wiring của OAuth2 Login, client manager, repository, HTTP session và background jobs.

### 13.3. Nếu dùng HttpSession/Redis

Ứng dụng có thể không ghi bảng `oauth2_authorized_client` nào nhưng Access Token vẫn được serialize trong session. Nếu Redis session là shared store, cần:

- Kiểm soát Redis ACL, TLS, authentication, network isolation.
- Xác định Redis persistence snapshots/AOF/backups có chứa serialized token không.
- Cân nhắc mã hóa payload session/token ở tầng serializer hoặc dùng repository với encrypted service.
- Đặt session TTL, cookie security và quy trình session invalidation.

**Mã hóa JDBC token table không tự bảo vệ token của một HTTP session được serialize ở Redis.**

## 14. Ví dụ persistence adapter: mã hóa toàn bộ token bundle

Một lựa chọn dễ hiểu là serialize **token state cần thiết** vào DTO, mã hóa toàn bộ payload bằng AES-GCM, và chỉ lưu ciphertext cùng khóa định danh đã kiểm soát.

### 14.1. DTO chứa dữ liệu trước khi mã hóa

~~~java
package com.example.security.store;

import java.time.Instant;
import java.util.Set;

public record AuthorizedClientPayload(
    String tokenType,
    String accessTokenValue,
    Instant accessIssuedAt,
    Instant accessExpiresAt,
    Set<String> accessScopes,
    String refreshTokenValue,
    Instant refreshIssuedAt,
    Instant refreshExpiresAt) {
}
~~~

**DTO này chứa plaintext credentials khi ở memory** và **không được log, serialize ra HTTP response hoặc lưu nguyên vào database**. Nếu `refreshTokenValue` là null, nghĩa là provider không cấp Refresh Token.

Đối với JPA/JDBC, entity dùng để lưu nên chỉ có **encrypted payload**, key reference, record identity, version và metadata đã được duyệt, chứ không persist riêng DTO plaintext.

### 14.2. DAO chỉ nhìn ciphertext

Giao diện minh họa:

~~~java
package com.example.security.store;

import java.util.Optional;

public interface EncryptedAuthorizedClientDao {

    Optional<EncryptedRow> find(
        String registrationId,
        String principalName);

    void save(
        String registrationId,
        String principalName,
        String encryptedPayload);

    void remove(
        String registrationId,
        String principalName);
}
~~~

~~~java
package com.example.security.store;

public record EncryptedRow(
    String registrationId,
    String principalName,
    String encryptedPayload) {
}
~~~

Các interfaces/records này là **application types tự định nghĩa**, không phải class có sẵn của Spring Security. Chúng minh họa rằng DAO không cần biết token value. Production DAO phải thêm transaction/concurrency control, tenant key, ownership validation, row version, data migration và error handling.

### 14.3. Adapter cho OAuth2AuthorizedClientService

Ứng dụng có thể tự triển khai:

~~~java
public interface OAuth2AuthorizedClientService {

    <T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
        String clientRegistrationId,
        String principalName);

    void saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal);

    void removeAuthorizedClient(
        String clientRegistrationId,
        String principalName);
}
~~~

Đây là **tóm lược chữ ký** để giải thích contract của Spring Security, không phải yêu cầu khai báo lại interface framework. Implementation custom:

~~~text
saveAuthorizedClient(client, authentication)
  -> xác minh registration và principal đáng tin
  -> chuyển token + metadata thành AuthorizedClientPayload
  -> JSON/CBOR serializer có schema version
  -> AeadTokenCipher.encrypt(payloadBytes, TokenContext)
  -> dao.save(ciphertext, metadata, rowVersion)

loadAuthorizedClient(registrationId, principalName)
  -> kiểm tra quyền đọc đúng principal/tenant
  -> dao.find(record)
  -> AeadTokenCipher.decrypt(ciphertext, TokenContext)
  -> parse payload theo schema version
  -> tạo OAuth2AccessToken / OAuth2RefreshToken
  -> tạo OAuth2AuthorizedClient với ClientRegistration đã biết

removeAuthorizedClient(registrationId, principalName)
  -> dao.remove đúng record, audit theo policy
~~~

Điểm quan trọng: **mã hóa phải xảy ra trước dao.save** và **giải mã sau dao.find**, còn Spring Security vẫn làm việc với `OAuth2AuthorizedClient` khi cần gọi API hoặc refresh token.

### 14.4. Chuyển token object sang DTO

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

static AuthorizedClientPayload toPayload(
        OAuth2AuthorizedClient client) {

    OAuth2AccessToken access = client.getAccessToken();
    OAuth2RefreshToken refresh = client.getRefreshToken();

    return new AuthorizedClientPayload(
        access.getTokenType().getValue(),
        access.getTokenValue(),
        access.getIssuedAt(),
        access.getExpiresAt(),
        access.getScopes(),
        refresh == null ? null : refresh.getTokenValue(),
        refresh == null ? null : refresh.getIssuedAt(),
        refresh == null ? null : refresh.getExpiresAt());
}
~~~

Hàm này dùng `AuthorizedClientPayload` application record ở trên, thuộc cùng package/import tùy dự án. Giá trị plaintext chỉ tồn tại trong application memory/serializer tạm thời.

### 14.5. Khôi phục OAuth2AuthorizedClient

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

static OAuth2AuthorizedClient fromPayload(
        AuthorizedClientPayload payload,
        ClientRegistration registration,
        String principalName) {

    if (!"Bearer".equalsIgnoreCase(payload.tokenType())) {
        throw new IllegalStateException(
            "Unsupported token type in encrypted store");
    }

    OAuth2AccessToken access = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        payload.accessTokenValue(),
        payload.accessIssuedAt(),
        payload.accessExpiresAt(),
        payload.accessScopes());

    OAuth2RefreshToken refresh = null;
    if (payload.refreshTokenValue() != null) {
        refresh = new OAuth2RefreshToken(
            payload.refreshTokenValue(),
            payload.refreshIssuedAt(),
            payload.refreshExpiresAt());
    }

    return new OAuth2AuthorizedClient(
        registration, principalName, access, refresh);
}
~~~

Lưu ý: `ClientRegistration` nên được lấy từ **repository cấu hình tin cậy** theo registration ID trong row key, không deserialize một registration hoàn chỉnh do DB có thể bị sửa. Cần kiểm tra schema version, required fields và token timestamps khi đọc payload.

### 14.6. Serializer cũng là một phần bảo mật

Nếu dùng JSON, cấu hình Jackson/serializer:

- Không enable unsafe polymorphic default typing cho dữ liệu không đáng tin.
- Chỉ serialize DTO có schema giới hạn, không serialize tùy ý `Authentication` graph.
- Hỗ trợ `Instant`, `Set<String>` và các kiểu metadata qua modules phù hợp.
- Giới hạn kích thước payload/envelope để tránh memory exhaustion.
- Phân biệt **lỗi AEAD authentication** với **lỗi schema/migration** ở tầng vận hành, không lộ nội dung ciphertext/token.

Encrypt rồi lưu; khi decrypt phải **xác minh AEAD tag trước khi tin dữ liệu**. Không parse nội dung bị sửa như thể là một token object hợp lệ.

### 14.7. Tránh mã hóa hai lần không kiểm soát

Nếu persistence adapter đã encrypt, đừng để một tầng khác tự encrypt cùng plaintext bằng key khác mà không có metadata version/ownership. Double encryption vô tình làm migration, backup recovery và troubleshooting khó khăn.

Ngược lại, TDE ở dưới app encryption không phải “double encryption lỗi”: nó là một lớp storage khác và có thể được giữ theo policy.

## 15. Đừng chỉ wrap JdbcOAuth2AuthorizedClientService rồi nghĩ đã mã hóa

`JdbcOAuth2AuthorizedClientService` trong Spring Security cung cấp persistence JDBC cho authorized clients. Một wrapper kiểu:

~~~java
delegate.saveAuthorizedClient(authorizedClient, principal);
~~~

vẫn có thể **đưa plaintext token cho delegate**. Nếu delegate mặc định ghi token value vào cột, việc mã hóa một bản sao ở wrapper khác **không giải quyết plaintext ở DB**.

Để bảo đảm mã hóa trước khi lưu, cần một trong các phương án:

1. **Custom `OAuth2AuthorizedClientService`** xử lý encrypt/decrypt trước DAO.
2. **Custom JDBC mapper/parameters strategy** nếu implementation/version cung cấp đúng extension point để mã hóa token bytes cả ở write và read.
3. **Persistence layer encryption** được tích hợp đúng entity/serializer và được kiểm tra rằng **tất cả** token fields đều đi qua đường mã hóa.
4. **Custom repository/session serializer** nếu token chủ yếu được lưu ở WebSession/HTTP session.

Không tự cho rằng JPA `@Convert` trên một entity không được Spring Security sử dụng sẽ mã hóa token ở bảng JDBC của Spring Security.

### 15.1. Với OAuth2AuthorizedClientManager

Một manager thường có **success handler mặc định** gọi save sau khi cấp/refresh thành công:

~~~text
Manager.authorize(...)
  -> Token Endpoint cấp/refresh token
  -> OAuth2AuthorizationSuccessHandler
  -> authorizedClientService.saveAuthorizedClient(...)
  -> custom encrypted DAO
~~~

Nếu custom success handler chỉ log mà không delegate save, token mới có thể không được lưu. Điều này đặc biệt nguy hiểm khi Refresh Token được **xoay vòng**: một token cũ bị giữ lại có thể dẫn đến `invalid_grant` trong lần refresh sau.

### 15.2. Đừng ghi lại plaintext token vào cache debug

Khi chuyển sang encrypted store, phải rà soát:

- `@Cacheable` hoặc Caffeine/Redis caches giữ token object.
- HTTP session serializer.
- Tracing/metrics interceptors.
- SQL parameter logging.
- Exception handling và debug endpoints.
- Job exports/backups.

Nếu cache chỉ giữ data trong memory thì vẫn cần hạn chế heap dumps, memory inspection và key lifetime; nếu cache persistent/distributed cần xác định nó có lưu plaintext token không.

## 16. Session cookie và session store: hai bề mặt khác nhau

Trong một web application dùng OIDC Login, browser thường nhận một **session cookie** trong khi token có thể nằm server-side:

~~~text
Browser:
  Cookie: SESSION=<opaque session identifier>

Server:
  WebSession/HttpSession -> OAuth2 Authentication
  Authorized Client Store -> Access/Refresh Tokens
~~~

Không nên mặc định gửi Access Token/Refresh Token vào cookie chỉ vì muốn giảm lưu database.

### 16.1. Bảo vệ cookie

Cookie phiên cần được cấu hình theo chính sách:

- `Secure` trên HTTPS.
- `HttpOnly` khi JavaScript không cần đọc cookie.
- `SameSite` phù hợp browser/callback mode và CSRF policy.
- Domain/path hẹp hợp lý.
- Session rotation/fixation protection, TTL, logout invalidation.

Cookie flags **không mã hóa token trong Redis/session store**. Ngược lại, mã hóa token ở DB **không thay** CSRF/session security.

### 16.2. Token trong session serialization

Nếu Redis-backed sessions lưu serialized `Authentication` hoặc authorized clients, một Redis snapshot có thể chứa sensitive data. Hãy xác định:

1. Token thực sự nằm trong session hay authorized client service?
2. Có bao nhiêu bản sao/replicas/backups?
3. Serializer có mã hóa payload nhạy cảm trước khi Redis nhận không?
4. Session hết hạn có thật sự xóa persistent token ở nơi khác không?

### 16.3. Không tự tạo cookie chứa encrypted Refresh Token nếu không cần

Dù một cookie chứa Refresh Token được mã hóa, browser vẫn có thể mang nó trong mọi request phù hợp domain/path, chịu giới hạn kích thước và có rủi ro replay nếu cookie bị đánh cắp. Với BFF/backend OAuth2 Client, **lưu Refresh Token server-side** thường dễ kiểm soát hơn.

## 17. Quản lý khóa: tạo, sử dụng, rotation, thu hồi và hủy

Một khóa không chỉ có trạng thái “có hoặc không”. Hệ thống cần **key lifecycle**:

~~~mermaid
flowchart LR
    A["Create key / version"] --> B["Active: encrypt + decrypt"]
    B --> C["Decrypt-only: không ghi ciphertext mới"]
    C --> D["Retired: chỉ còn nếu dữ liệu/backup cần"]
    D --> E["Disabled theo policy"]
    E --> F["Destroy sau khi được phép và không còn dữ liệu cần đọc"]
~~~

Việc disable/destroy key **có thể làm tất cả ciphertext phụ thuộc key không thể giải mã**. Đây là hành động có rủi ro lớn, phải có inventory các bản ghi và backup trước khi xóa key material.

### 17.1. Key ID/version phải lưu cùng ciphertext

~~~text
Record 1001: keyId = k3
Record 1002: keyId = k2
Record 1003: keyId = k1
~~~

Sau rotation, app có thể **ghi bằng k3** nhưng vẫn **giải mã bằng k1/k2** trong thời gian migration. Không được thay `keyId` trong database mà không thực hiện cryptographic re-encryption/rewrap tương ứng.

### 17.2. Rotation do chính sách hay do sự cố?

Hai tình huống khác nhau:

- **Planned rotation:** khóa chưa bị nghi lộ; có thể chuyển dần, giữ old key decrypt-only, kiểm soát rate limit và rollback.
- **Compromise-driven rotation:** khóa nghi bị lộ; cần incident response, hạn chế quyền, xác định data exposure, phát hành key mới, **re-encrypt**, đồng thời đánh giá **revoke OAuth2 tokens** đã có nguy cơ bị đánh cắp.

Chỉ rotate encryption key **không vô hiệu hóa Access Token/Refresh Token** mà attacker đã kịp lấy plaintext.

### 17.3. Thời hạn giữ khóa cũ

Không thể chọn TTL old key chỉ dựa vào Access Token expiry nếu:

- Refresh Token sống nhiều tháng.
- Backup cũ vẫn cần restore.
- Có record ít được đọc (lazy re-encryption).
- Một instance cũ chưa được rollout.

Key retirement phải dựa trên **data inventory và backup retention**, không chỉ “đã qua 30 ngày”.

## 18. Hai kiểu rotation: rewrap và re-encrypt

### 18.1. Rewrap DEK

Trong envelope encryption:

~~~text
KEK v1 -> wrapped DEK -> AES-GCM ciphertext

Rotate KEK:
  unwrap DEK bằng KEK v1
  wrap cùng DEK bằng KEK v2
  ciphertext token có thể giữ nguyên
~~~

Ưu điểm: không cần giải mã/mã hóa lại toàn bộ token payload trong database khi chỉ đổi **KEK**. Nhưng cần hiểu:

- Nếu **DEK** đã bị lộ, rewrap cùng DEK **không xử lý** sự cố đó.
- Nếu chính sách yêu cầu thay **data encryption key** thì phải re-encrypt payload.
- Wrapped DEK cũ và mới có thể cần cùng tồn tại trong giai đoạn rollout có kiểm soát.

### 18.2. Re-encrypt payload bằng DEK mới

~~~text
Ciphertext cũ -> decrypt bằng old DEK và old AAD
              -> encrypt lại bằng new DEK, new nonce và AAD
              -> ghi record mới với key version mới
~~~

Đây là cách **thay data key thực sự**. Cần transaction/concurrency control để không ghi đè một Refresh Token mới vừa được manager refresh.

### 18.3. Read-old, write-new

Một chiến lược migration phổ biến:

1. App mới được cấu hình **current key = k3**.
2. Decrypt vẫn hỗ trợ k1/k2 theo policy.
3. Mọi lần **save mới** dùng k3.
4. Job migration đọc các bản ghi k1/k2, decrypt, encrypt với k3.
5. Sau khi hết bản ghi cũ và backup policy cho phép, mới disable/hủy old keys.

**Không re-encrypt cùng lúc mọi record bằng một job không giới hạn concurrency** khi KMS có quota. Dùng batches, rate limits, checkpoint, retry có giới hạn và giám sát.

### 18.4. Lazy rotation và eager rotation

| Phương án | Cách làm | Ưu/nhược |
| --- | --- | --- |
| Lazy re-encrypt | Khi đọc record cũ, mã hóa lại bằng key mới | Giảm migration load nhưng record ít dùng có thể mãi còn key cũ |
| Eager migration | Batch quét records và re-encrypt | Hoàn tất có thể đo lường, cần xử lý concurrency/quota |
| Hybrid | Ghi mới bằng key mới + lazy + batch cho record cũ | Thường linh hoạt nhưng phải có telemetry/key inventory |

Nếu tổ chức cần **revoke key cũ gấp** vì compromise, lazy-only có thể không đáp ứng thời gian xử lý sự cố.

## 19. Race condition với refresh token rotation và key rotation

Một trường hợp khó:

~~~mermaid
sequenceDiagram
    autonumber
    participant R as OAuth2 Refresh Worker
    participant M as Key Migration Worker
    participant DB as Encrypted Client DB
    participant OP as Token Endpoint
    R->>DB: Read record version 7 (refreshToken R1)
    M->>DB: Read record version 7
    R->>OP: Refresh Token R1
    OP-->>R: Access Token A2, Refresh Token R2
    R->>DB: Save R2 encrypted, version 8
    M->>DB: Write re-encrypted stale version 7
    Note over DB: Nếu blind update, R2 có thể bị ghi đè bởi R1
~~~

Đây là **lost update**, không phải lỗi AES-GCM. Mã hóa dữ liệu không giải quyết concurrency ở DB.

### 19.1. Optimistic locking / compare-and-swap

Record nên có `row_version` hoặc một concurrency token:

~~~sql
-- Minh họa SQL, chưa phải migration production.
UPDATE oauth2_authorized_client_secure
SET encrypted_payload = :new_ciphertext,
    key_id = :new_key_id,
    row_version = row_version + 1
WHERE registration_id = :registration_id
  AND principal_key = :principal_key
  AND row_version = :expected_version;
~~~

Nếu update ảnh hưởng **0 rows**, có ai đó đã thay record hoặc record không tồn tại. Migration worker phải **đọc lại, xác minh và quyết định retry**, không ghi đè ciphertext cũ lên token mới.

### 19.2. Concurrency sau refresh thất bại

Nếu Request A refresh thành công, Request B dùng Refresh Token cũ và nhận `invalid_grant`, failure handler của B không được xóa nhầm bản ghi R2 mới của A. Cần đánh giá conditional delete/version hoặc cơ chế single-flight theo `registrationId + principalName`.

### 19.3. Tách encryption rotation khỏi OAuth2 authorization

Rotation job **không nên gọi Token Endpoint để refresh mọi user token chỉ để thay encryption key**. Nó chỉ cần decrypt/re-encrypt dữ liệu đã có; hoạt động OAuth2 grant là trách nhiệm khác và có thể gây rate limit hoặc làm thay Refresh Token ngoài ý muốn.

## 20. Migration từ plaintext database sang encrypted store

Nhiều ứng dụng bắt đầu với `JdbcOAuth2AuthorizedClientService` hoặc một custom table lưu token rõ. Chuyển sang mã hóa phải có kế hoạch không làm mất tất cả connections đang hoạt động.

### 20.1. Không thể chỉ thay column type

Nếu code cũ đang đọc:

~~~text
access_token_value = "eyJ..."
refresh_token_value = "opaque-value..."
~~~

còn code mới chỉ biết giải mã envelope `v1....`, deploy trực tiếp có thể khiến mọi record cũ không load được.

### 20.2. Quy trình migration gợi ý

1. **Inventory:** xác định mọi nơi lưu token: JDBC, Redis, sessions, replicas, exports và backups.
2. **Thiết kế schema:** thêm encrypted payload, key/version metadata, row version và schema version phù hợp.
3. **Cấp KMS policy:** app được encrypt/decrypt đúng key; migration worker có quyền tối thiểu.
4. **Đọc dữ liệu cũ qua luồng tin cậy:** không export plaintext ra file chung.
5. **Encrypt từng record:** dùng AAD đúng registration/principal/tenant, nonce mới.
6. **Ghi có kiểm soát:** transaction hoặc optimistic locking, giữ token pair nhất quán.
7. **Rollout code đọc cả hai định dạng trong giai đoạn ngắn được phê duyệt**, nhưng mọi save mới phải ghi encrypted.
8. **Đo tiến độ:** số records còn plaintext, failed conversions, key versions còn tồn tại.
9. **Tắt plaintext fallback:** sau khi migration xong và được xác minh.
10. **Xử lý bản plaintext cũ trong snapshots/backups** theo retention/secure deletion policy; không giả định DROP COLUMN xóa ngay mọi backup.

### 20.3. Nguy cơ “dual-write”

Một cơ chế dual-write kéo dài:

~~~text
save client
  -> plaintext table
  -> encrypted table
~~~

vẫn giữ một kho plaintext. Nếu cần migration song song, phải giới hạn thời gian, quyền truy cập và kế hoạch xóa, đồng thời đảm bảo không có instance cũ tiếp tục ghi plaintext sau cutover.

### 20.4. Không tự nhận dạng định dạng bằng “token có dấu chấm”

JWT và ciphertext đều có thể chứa dấu chấm hoặc chuỗi base64url tùy format. Hãy dùng **format/version field rõ ràng**, không đoán record đã mã hóa hay chưa bằng việc kiểm tra token bắt đầu bằng `eyJ` hoặc độ dài.

## 21. Kiểm thử mã hóa: những tính chất phải được bảo đảm

Việc có AES-GCM code không có nghĩa hệ thống đã bảo vệ đúng token. Cần kiểm tra các thuộc tính cryptographic và persistence behavior ở đúng lớp.

### 21.1. Bảng tình huống kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Encrypt rồi decrypt với cùng context/key | Khôi phục đúng byte[] gốc |
| Encrypt hai lần cùng plaintext/context | Ciphertext thường khác vì **nonce mới** |
| Ciphertext bị sửa 1 byte | Decrypt thất bại, không trả plaintext |
| Tag bị sửa hoặc thiếu | Decrypt thất bại |
| Nonce sai kích thước | Reject envelope |
| Key ID không tồn tại | Fail closed, không thử một fallback key tùy ý |
| Key ID bị đổi | Decrypt thất bại hoặc key lookup bị từ chối |
| Principal Alice đổi thành Bob | AAD mismatch, decrypt thất bại |
| Registration `calendar` đổi `billing` | AAD mismatch |
| Tenant A đổi Tenant B | AAD mismatch |
| Token kind đổi `access` sang `refresh` | AAD mismatch |
| Key rotation: ghi k2, vẫn đọc k1 | Đọc được record cũ theo policy |
| Disable key k1 khi còn record cần k1 | Lỗi được phân loại và cảnh báo, không trả token giả |
| Migration bị race với refresh | CAS ngăn ghi đè Refresh Token mới |
| Database ghi lỗi sau encrypt | Không log payload, không đánh dấu persisted thành công |
| Ciphertext rất dài/malformed | Giới hạn kích thước, reject an toàn |
| Login của Alice và Bob | Không hoán đổi authorized clients |
| Logging SQL/HTTP bật | Không có plaintext token/secret |
| Restore backup | Key material/version cần thiết vẫn được quản lý an toàn |

### 21.2. Unit test JCA AES-GCM với key chỉ dùng cho test

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AeadTokenCipherTest {

    @Test
    void encryptionRoundTripAndContextBinding() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey testKey = generator.generateKey();

        KeyProvider keys = new KeyProvider() {
            @Override
            public ActiveKey currentKey() {
                return new ActiveKey("unit-test-v1", testKey);
            }

            @Override
            public SecretKey keyById(String keyId) {
                if (!"unit-test-v1".equals(keyId)) {
                    throw new IllegalStateException("Unknown test key");
                }
                return testKey;
            }
        };

        AeadTokenCipher cipher = new AeadTokenCipher(keys);
        TokenContext alice = new TokenContext(
            "test-tenant", "calendar", "alice", "refresh");
        TokenContext bob = new TokenContext(
            "test-tenant", "calendar", "bob", "refresh");

        byte[] plaintext =
            "TEST_ONLY_REFRESH_TOKEN".getBytes(StandardCharsets.UTF_8);

        String first = cipher.encrypt(plaintext, alice);
        String second = cipher.encrypt(plaintext, alice);

        assertNotEquals(first, second);
        assertArrayEquals(plaintext, cipher.decrypt(first, alice));
        assertThrows(
            TokenCryptoException.class,
            () -> cipher.decrypt(first, bob));

        Arrays.fill(plaintext, (byte) 0);
    }
}
~~~

Đoạn test dùng key sinh ngẫu nhiên **chỉ trong memory/test**, không lưu vào production config. `assertNotEquals` hai ciphertext là kỳ vọng thực tế vì nonce ngẫu nhiên, nhưng không phải bằng chứng toán học rằng một RNG luôn không thể trùng nonce: production cần giới hạn usage/rotation và thiết kế nonce uniqueness phù hợp.

### 21.3. Test tampering

Trong test, có thể giải mã envelope thành các thành phần, sửa một byte ciphertext hoặc tag rồi encode lại, sau đó assert decrypt thất bại. Không nên chỉ sửa một ký tự Base64url cuối cùng nếu ký tự đó không ảnh hưởng bytes do encoding/canonicalization.

### 21.4. Test KMS và application authorization

Unit test AES-GCM **không chứng minh** KMS policy hoặc workload identity đã đúng. Cần integration tests:

- Service production role chỉ có decrypt đúng key.
- Migration role không thể đọc toàn bộ dữ liệu ngoài phạm vi.
- Staging không decrypt được production ciphertext/key.
- KMS unavailable làm application **fail closed**.
- Old key được disable đúng lúc không còn records/backups cần đọc.
- Key usage được audit mà không có plaintext token.

## 22. Key rotation runbook dành cho vận hành

Một quy trình có thể được viết thành runbook như sau:

### Trước rotation

- Thống kê records theo `keyId`/`formatVersion`.
- Xác nhận có bản backup và khả năng phục hồi **key + ciphertext** theo policy.
- Kiểm tra KMS quotas, latency, role permissions.
- Đảm bảo migration code có optimistic locking.
- Xác định thời điểm rollout các service instances.
- Chuẩn bị monitoring: decrypt failure, KMS failure, number of old-key records.

### Trong rotation

1. Tạo/activate new key version, đặt làm `currentKey` cho encryption.
2. Giữ old key **decrypt-only** trong giai đoạn chuyển đổi.
3. Canary rollout và kiểm tra token read/write.
4. Batch rewrap hoặc re-encrypt theo mục tiêu cụ thể.
5. Theo dõi records còn old key, lỗi AEAD/KMS và token refresh rates.
6. Không xóa old key chỉ vì canary đã pass vài requests.

### Sau rotation

- Xác nhận mọi live records cần thiết đã chuyển version.
- Xử lý rollback plan và các bản backup còn old version.
- Chỉ retire/disable key khi policy cho phép và khôi phục dữ liệu vẫn khả thi.
- Lưu audit: ai rotate, khi nào, key versions nào, số records được xử lý.
- Kiểm tra không có credential bị in vào migration logs.

### 22.1. Khi KMS bị gián đoạn

Nếu hệ thống không thể decrypt token:

~~~text
Database row có ciphertext
  -> KMS / key provider unavailable
  -> không được tạo plaintext giả
  -> trả lỗi phụ thuộc có kiểm soát / tạm dừng job
  -> alert + retry theo loại lỗi, có giới hạn
~~~

Không fallback bằng cách dùng một hard-coded emergency key trong source hoặc lưu unencrypted token “cho chắc chạy được”. Điều đó phá threat model.

### 22.2. Caching DEK

Để giảm KMS latency, một số hệ thống cache plaintext DEK trong memory với TTL và giới hạn kích thước. Nhưng phải đánh giá:

- Khả năng lộ key qua process compromise.
- Thời gian cache tồn tại sau khi KMS revoke quyền.
- Số records cùng DEK, blast radius.
- Cơ chế invalidation/rotation và bounded memory.

Không cache plaintext DEK hoặc token trong một **persistent distributed cache** không được bảo vệ tương xứng.

## 23. Ứng phó khi nghi ngờ khóa hoặc token đã bị lộ

### 23.1. Khi lộ ciphertext nhưng chưa có bằng chứng lộ key

1. Khoanh vùng database/snapshot/backup bị truy cập.
2. Xác minh ciphertext được mã hóa đúng AES-GCM và key lưu tách biệt.
3. Kiểm tra KMS audit logs xem có decryption bất thường không.
4. Hạn chế quyền đọc DB và ngăn tiếp diễn sự cố.
5. Đánh giá metadata bị lộ (tenant/principal/registration).
6. Quyết định rotation/re-encryption theo threat assessment và policy.

Không tự tuyên bố “không ảnh hưởng vì AES-256” nếu key storage, AAD, nonce uniqueness hoặc runtime compromise chưa được điều tra.

### 23.2. Khi nghi bị lộ encryption key

1. Kích hoạt quy trình incident response.
2. Cô lập credentials/roles có thể đã dùng key bất thường.
3. Xem xét disable key **theo kế hoạch bảo toàn khả năng khôi phục**, không phá hủy dữ liệu đột ngột.
4. Cấp DEK/KEK mới và re-encrypt những records bị ảnh hưởng.
5. Điều tra có ai đã lấy được **plaintext Refresh Token/Access Token** hay không.
6. Cân nhắc revoke/reset OAuth2 connections qua Authorization Server nếu token có khả năng bị lộ.
7. Bắt đầu lại OAuth2 authorization cho người dùng/service khi cần.
8. Thực hiện hậu kiểm và cập nhật key policy/monitoring.

**Chỉ re-encrypt database bằng key mới không xóa khả năng attacker sử dụng token plaintext đã đánh cắp.**

### 23.3. Khi mất key không có bản sao phục hồi

AEAD không có backdoor hợp lệ: nếu mất khóa cần để decrypt, token có thể **không thể khôi phục**. Giải pháp nghiệp vụ thường là xóa records không đọc được và yêu cầu cấp quyền lại hoặc xin token mới, tùy grant:

- Authorization Code/OIDC: người dùng có thể cần re-consent.
- Client Credentials: service có thể xin Access Token mới nếu client credentials vẫn còn hợp lệ.
- Refresh Token đã mất: không tự lấy lại bằng cách đoán/đảo hash.

Đó là lý do key backup, access policy và retention phải được thiết kế **trước khi** sử dụng encryption trong production.

## 24. Bảo vệ quyền truy cập và vòng đời authorized client

### 24.1. Encryption không thay principal ownership

Hệ thống vẫn phải ràng buộc:

~~~text
(tenantId, clientRegistrationId, principalName)
    -> đúng encrypted authorized client record
~~~

Trong một hệ thống nhiều IdP, `principalName` có thể dựa trên issuer + subject hoặc internal identity đã liên kết đáng tin cậy. Không dùng email chưa xác minh làm khóa toàn cục cho nhiều tenants.

### 24.2. Không dùng Client Credentials token thay delegated user token

Machine token có thể mang quyền của ứng dụng. Nếu backend dùng token đó để phục vụ user, backend phải áp dụng authorization của user/tenant trước khi gọi API. Việc machine token đã được mã hóa an toàn trong DB **không hợp thức hóa** hành vi confused-deputy hoặc bypass phân quyền.

### 24.3. Không ghi token sau khi user disconnect

Một job đồng bộ có thể vẫn đang chạy lúc user thu hồi kết nối. Cần thiết kế:

- Xác nhận connection còn active trước khi dùng token.
- Xử lý in-flight requests và race với disconnect.
- Xóa local encrypted record theo chính sách.
- Gọi Token Revocation Endpoint nếu provider hỗ trợ và ứng dụng có nghĩa vụ revoke.
- Không tự khôi phục record token đã bị disconnect chỉ vì có bản backup.

### 24.4. Data minimization

Không lưu mọi OAuth2/OIDC claim “đề phòng sau này cần”. Chỉ lưu Access Token, Refresh Token và metadata thiết yếu cho lifecycle. Các claims trong ID Token/UserInfo nên có retention và mục đích riêng, đặc biệt khi chứa PII.

## 25. Những lỗi triển khai thường gặp

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Lưu token plaintext trong JDBC | SQL reader/backup có thể lấy credential | Encrypt trước save, tách key khỏi DB |
| Nghĩ TDE đã đủ | SELECT vẫn trả plaintext cho DB account có quyền | Application-level encryption khi threat model cần |
| Hash Refresh Token cần dùng lại | Không khôi phục giá trị để refresh | Dùng reversible authenticated encryption |
| Hard-code AES key trong Java/YAML | Source/config leak làm lộ key | KMS/HSM/secret manager, workload identity |
| AES-CBC không có MAC hoặc ECB | Không cung cấp authenticated encryption đúng | Dùng AEAD như AES-GCM |
| AES-GCM nonce cố định hoặc tái sử dụng | Có thể phá nghiêm trọng bảo mật | Nonce mới/unique theo key, giới hạn key usage |
| Cùng AAD cho mọi user/tenant | Ciphertext có thể bị hoán đổi giữa rows | Bind tenant, registration, principal, token purpose |
| AAD dựa trên input user chưa xác minh | Không bảo đảm quyền truy cập record | Authorization server-side trước decrypt |
| Lưu `keyId` nhưng không giữ old keys | Không đọc được records cũ sau rotation | Read-old/write-new, inventory |
| Rotate KEK nhưng coi như DEK đã thay | Nếu DEK bị lộ, rủi ro còn | Re-encrypt bằng new DEK nếu cần |
| Disable key cũ trước khi migration/backups xong | Mất dữ liệu token không phục hồi | Lập kế hoạch key retirement |
| Mã hóa Access Token nhưng để Refresh Token rõ | Lộ credential dài hạn nhất | Mã hóa toàn bộ sensitive token payload |
| Metadata expiry/scope không được xác thực | DB tampering có thể thay behavior | Encrypt metadata hoặc bind vào AAD |
| DAO có thêm một cột plaintext debug | Vẫn lộ token | Không tạo bản sao plaintext persistent |
| Migration ghi đè Refresh Token mới | Client mất khả năng refresh | Version/CAS hoặc per-record locking |
| Key và ciphertext chung một backup | Key separation mất ý nghĩa | Tách key management và data backups |
| KMS error -> fallback plaintext save | Phá confidentiality khi hệ thống lỗi | Fail closed, alert |
| Log ciphertext kèm plaintext/token | Giải pháp bảo mật bị bỏ qua | Redact, structured safe metadata |
| Mã hóa DB nhưng để Redis session plaintext | Token còn lộ qua session store | Kiểm kê mọi persistence paths |
| Giả định encryption = revocation | Token đã lộ vẫn có thể dùng | Token revoke/rotation theo incident response |
| Dùng JWT signing key để mã hóa storage | Key purpose/trust boundary sai | Tách keys theo mục đích |
| Không test restore backup cùng key version | Disaster recovery có thể thất bại | Restore drills có kiểm soát |

## 26. Các tình huống thực hành

### Tình huống A — Bảo vệ Refresh Token trong JDBC

Một portal OIDC giữ Refresh Token của hàng nghìn users trong bảng JDBC; backup đi qua nhiều hệ thống.

**Thiết kế:** custom `OAuth2AuthorizedClientService` mã hóa token bundle trước INSERT/UPDATE, lưu ciphertext cùng key version, KMS key tách khỏi DB backup, hạn chế SELECT và audit decrypt.

### Tình huống B — Dùng TDE nhưng tài khoản BI có thể SELECT token

Database bật TDE, nhưng một tài khoản phân tích dữ liệu có quyền đọc bảng `oauth2_authorized_client`.

**Vấn đề:** database đã giải mã dữ liệu cho SQL reader. **Giải pháp:** application-level encryption, column/table privileges, view masking, tách quyền decrypt ở KMS.

### Tình huống C — KMS rotation khiến token cũ không đọc được

App deploy key v3 và tắt key v2 ngay khi deploy, trong khi nhiều rows vẫn mang `keyId=v2`.

**Giải pháp:** read-old/write-new; re-encrypt/rewrap theo kế hoạch, inventory records và backups trước khi retire v2.

### Tình huống D — Refresh Token rotation cùng key migration

Migration worker đang re-encrypt row cũ, đồng thời user request refresh token và lưu một token mới.

**Giải pháp:** optimistic locking/CAS, retry migration dựa trên record mới; không blind update bằng ciphertext của stale row.

### Tình huống E — Một token được copy từ user A sang user B

Kẻ có quyền sửa DB đổi ciphertext của Alice vào hàng của Bob.

**Giải pháp:** AEAD AAD phải gắn principal/tenant/registration. Decrypt với AAD Bob thất bại, application không dùng token Alice cho Bob.

### Tình huống F — Scheduled job dùng Client Credentials

Job chỉ giữ Access Token ngắn hạn và có thể xin token mới bất cứ lúc nào.

**Thiết kế:** nếu persistence không cần thiết, cân nhắc in-memory store với least privilege và process isolation. Nếu cần shared token cache hoặc audit, dùng encrypted store, key management và TTL phù hợp; không cấp Refresh Token tùy tiện.

### Tình huống G — Token trong Redis session snapshot

Đội ngũ đã mã hóa JDBC nhưng vẫn có session chứa authorized client ở Redis.

**Giải pháp:** xác định thực tế Spring Security lưu token ở repository/service nào, mã hóa session payload/token fields hoặc chuyển sang encrypted repository phù hợp; bảo vệ Redis snapshots/AOF.

### Tình huống H — Key provider bị outage

Database và API đều hoạt động nhưng KMS không trả data key.

**Hành vi đúng:** fail closed, báo service degradation, retry có giới hạn cho lỗi hạ tầng, không ghi token plaintext hoặc dùng emergency key hard-code.

### Tình huống I — Encrypt bằng key tĩnh và IV bằng timestamp

Một developer dùng `System.currentTimeMillis()` làm IV để dễ debug.

**Vấn đề:** trong nhiều instances, IV có thể trùng dưới cùng key; rất nguy hiểm với AES-GCM. **Giải pháp:** sử dụng nonce uniqueness strategy và cryptographic random, theo dõi giới hạn số lần mã hóa trên key.

### Tình huống J — JWT token đã được ký nên không mã hóa storage

Team cho rằng JWT có signature thì attacker không đọc được.

**Vấn đề:** JWS payload thường đọc được và bearer token còn có thể bị dùng. **Giải pháp:** tách signing/integrity và storage confidentiality; mã hóa khi lưu theo threat model.

### Tình huống K — Thay email người dùng làm mất token

AAD gắn principal=email, email của user đổi, decrypt bằng email mới thất bại.

**Giải pháp:** dùng principal ID ổn định; nếu identity key phải thay, migration bằng old context rồi re-encrypt với context mới.

### Tình huống L — Lộ cả ciphertext và KMS decrypt quyền

Một service account bị chiếm có quyền đọc DB và decrypt mọi wrapped DEKs.

**Giải pháp:** incident response đầy đủ, giới hạn IAM, audit usages, rotate/re-encrypt keys và cân nhắc revoke OAuth2 tokens bị ảnh hưởng; không chỉ tuyên bố database đã mã hóa nên an toàn.

### Tình huống M — Store mã hóa token nhưng logging vẫn lộ

Khi lỗi refresh, application log toàn bộ `OAuth2AuthorizedClient` để hỗ trợ.

**Giải pháp:** không log token object, redaction ở HTTP client/SQL/APM, audit metadata không nhạy cảm. Encryption at rest không ngăn lộ token đã giải mã trong process.

## 27. Checklist thiết kế trước production

| Câu hỏi | Điều cần có |
| --- | --- |
| Token được lưu ở những đâu? | Inventory JDBC, session, cache, backup, replicas, logs |
| Token nào nhạy cảm nhất? | Access/Refresh Tokens, ID Token khi cần, client credentials |
| Threat model là gì? | DB dump, backup theft, SQL insider, runtime compromise |
| Dùng thuật toán gì? | AEAD được review: AES-GCM hoặc alternative phù hợp |
| Nonce có unique dưới mỗi key? | RNG/nonce allocation và key usage limits |
| AAD gồm những gì? | Application domain, version, tenant, registration, principal, token purpose |
| Key có bị hard-code không? | Không; KMS/HSM/secret manager và workload identity |
| Key version ở đâu? | Lưu đủ metadata để decrypt và rotate |
| DEK/KEK được quản lý thế nào? | Envelope design, permissions, TTL, wrapped data keys |
| App có thể đọc token của user khác? | Ownership check, principal namespace và tenant isolation |
| Token metadata có được xác thực? | Encrypt bundle hoặc AAD bao gồm critical metadata |
| Spring Security dùng đúng encrypted store? | Wiring manager/repository/service thực tế |
| Session store có plaintext bản sao không? | Serializer, Redis, snapshots, retention |
| Refresh Token rotation có atomic không? | CAS/transaction, tránh stale writes |
| Rotation có rollback không? | Read-old/write-new, inventory, backups, runbook |
| Key mất/disabled thì sao? | Fail closed, alert, recovery/reauthorization |
| KMS unavailable thì sao? | Degradation policy, bounded retries, không plaintext fallback |
| Logs/APM có lộ token không? | Redaction, no raw tokens in error messages |
| Token revoke lúc disconnect/incident? | Local delete khác provider revocation |
| Test encryption và storage ra sao? | Tampering, context mismatch, key rotation, concurrency |

## 28. Tài liệu tham khảo

- Spring Security — OAuth2 Client (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — OAuth2 Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — `OAuth2AuthorizedClientService` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html
- Spring Security — `OAuth2AuthorizedClientRepository` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html
- Spring Security — `ReactiveOAuth2AuthorizedClientService` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientService.html
- Spring Security — `OAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Java Cryptography Architecture / Cipher: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html
- Java `GCMParameterSpec` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html
- NIST SP 800-38D — Galois/Counter Mode (GCM): https://csrc.nist.gov/pubs/sp/800/38/d/final
- NIST SP 800-57 Part 1 — Recommendation for Key Management: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- OWASP Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Token Revocation — RFC 7009: https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700

## 29. Tổng kết: mã hóa token và quản lý key là hai nửa không thể tách rời

~~~text
Authorization Server
    |
    | Access Token / Refresh Token
    v
OAuth2AuthorizedClientManager
    |
    v
Custom encrypted authorized client store
    |
    +-- Serialize token payload + metadata thiết yếu
    |
    +-- Xác định AAD:
    |     tenant / registration / principal / token purpose
    |
    +-- AES-GCM encrypt:
    |     key/dek + nonce MỚI + AAD
    |
    +-- KMS/HSM:
    |     key lifecycle, KEK, wrapped DEK, audit, access policy
    |
    v
Database:
    ciphertext + nonce + key version + wrapped DEK (nếu có)
    KHÔNG có plaintext tokens
    |
    | load + verify AAD/tag + decrypt với đúng key
    v
OAuth2AuthorizedClient trong app memory
    |
    +-- Access Token -> gọi Resource Server đúng scope/audience
    +-- Refresh Token -> Token Endpoint khi cần refresh
~~~

**Năm nguyên tắc cần nhớ:**

1. **Mã hóa trước khi lưu, không chỉ mã hóa ổ đĩa.** Access Token và đặc biệt Refresh Token cần được bảo vệ tại các persistence paths mà ứng dụng thực sự sử dụng: JDBC, session, Redis hoặc custom store.
2. **Dùng AEAD chuẩn như AES-GCM với nonce không tái sử dụng và AAD ràng buộc record.** Nhờ đó ciphertext không chỉ khó đọc mà còn bị từ chối khi sửa hoặc hoán đổi principal/tenant/registration.
3. **Quản lý khóa tách khỏi database.** KMS/HSM, DEK/KEK, key versions, least privilege và audit quan trọng không kém thuật toán mã hóa. Hard-code key trong source làm mất ý nghĩa của thiết kế.
4. **Rotation phải có migration và concurrency control.** Read-old/write-new, rewrap hoặc re-encrypt theo mục tiêu, optimistic locking tránh ghi đè Refresh Token mới và chỉ retire old key khi không còn dữ liệu cần decrypt.
5. **Encryption không thay token authorization hay incident response.** Resource Server vẫn phải kiểm tra issuer/audience/scope; mã hóa không ngăn lộ token qua log/runtime; re-encrypt không revoke token plaintext đã bị đánh cắp.

Khi triển khai đúng crypto boundary, key lifecycle và integration với Spring Security authorized client storage, ứng dụng có thể tái sử dụng OAuth2/OIDC tokens mà vẫn giảm đáng kể rủi ro từ database snapshots, backups và việc truy cập dữ liệu ngoài ý muốn, đồng thời giữ khả năng vận hành và xoay khóa an toàn trong dài hạn.

# Mã hóa token khi lưu

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **mã hóa token khi lưu (encryption at rest)** bảo vệ điều gì, trong những mô hình đe dọa nào, và vì sao nó **không thay thế** TLS, xác minh JWT, kiểm soát truy cập hoặc thu hồi token.
- Phân biệt **mã hóa có thể giải mã**, **băm một chiều**, **HMAC/token fingerprint**, **JWS**, **JWE** và mã hóa toàn bộ ổ đĩa/cơ sở dữ liệu.
- Thiết kế nơi lưu **access token** và đặc biệt **refresh token** dựa trên **AEAD**, khóa được quản lý an toàn và cơ chế **envelope encryption/KMS**.
- Hiểu các ràng buộc quan trọng của **AES-GCM**: khóa được bảo vệ, **nonce/IV không được dùng lại với cùng khóa**, authentication tag và **AAD**.
- Xây dựng quy trình cấp phát, mã hóa, giải mã tối thiểu, xoay vòng khóa, xử lý refresh token rotation, xóa/thu hồi và bảo vệ backup/log.
- Xác định khi nào **chỉ lưu giá trị băm của token** phù hợp hơn việc lưu ciphertext, và kiểm thử những trường hợp thất bại phổ biến.

## 1. Vì sao token phải được bảo vệ cả khi không truyền trên mạng?

Trong hệ thống dùng OAuth 2.0/OpenID Connect (OIDC), token có thể đi qua nhiều trạng thái:

~~~text
Authorization Server cấp token
    -> client nhận qua TLS
    -> client cất vào memory hoặc storage
    -> client lấy ra để gọi API hoặc token endpoint
    -> token bị thay mới, thu hồi hoặc hết hạn
    -> dữ liệu cũ được dọn dẹp theo chính sách
~~~

**TLS bảo vệ token khi truyền qua một kết nối đã được xác minh.** Nhưng sau khi request đến đích, token có thể xuất hiện trong cơ sở dữ liệu, file, backup, Redis, crash dump hoặc snapshot. Những nơi này không tự được TLS bảo vệ ở trạng thái lưu trữ.

Ví dụ một Backend-for-Frontend (BFF) lưu refresh token để duy trì phiên:

~~~text
session_id    = "session-92"
user_id       = "user-42"
refresh_token = "EXAMPLE_REFRESH_TOKEN_VALUE"
~~~

Đây là dữ liệu giả. Nếu database hoặc backup bị xuất trái phép, bên lấy được **refresh_token** có thể thử gửi nó tới token endpoint để xin access token mới, miễn token còn hiệu lực và các ràng buộc client/sender khác không ngăn được.

**Mã hóa khi lưu** biến giá trị token thành ciphertext. Bên chỉ đọc được ciphertext nhưng **không có quyền sử dụng khóa giải mã** sẽ gặp thêm rào cản trước khi dùng credential.

Ngược lại, nếu attacker đã chiếm backend và có quyền gọi KMS decrypt, mã hóa ở rest có thể **không đủ** ngăn sử dụng token. Vì vậy, câu hỏi quan trọng là **ai có thể lấy khóa, ai được gọi giải mã, và plaintext xuất hiện ở đâu?**

> Mã hóa at rest là một lớp trong mô hình bảo mật token, không phải bằng chứng rằng token không thể bị đánh cắp.

## 2. Phân loại token và nhu cầu lưu trữ

| Dữ liệu | Mục đích | Có cần lưu bền vững không? | Rủi ro khi lộ bản rõ |
| --- | --- | --- | --- |
| **Access token (AT)** | Gọi Resource Server theo audience/scope. | Thường chỉ cần cache ngắn hạn; tùy kiến trúc. | Bị dùng để thử gọi API trong thời gian còn hiệu lực. |
| **Refresh token (RT)** | Gửi tới token endpoint để xin AT mới. | Có thể cần để duy trì phiên qua restart nếu AS cấp RT. | Bị dùng để thử tiếp tục xin token mới. |
| **ID token (OIDC)** | Client xác minh thông tin xác thực End-User. | Chỉ khi thật sự cần; tránh giữ claims cá nhân không cần thiết. | Rò rỉ claims hoặc bị dùng sai mục đích. |
| **Authorization code** | Credential ngắn hạn để đổi token, thường dùng một lần. | Không nên lưu lâu dài. | Có thể bị đổi sai nếu thiếu PKCE và ràng buộc đúng. |
| **Session cookie/ID** | Liên kết trình duyệt với phiên ứng dụng. | Tùy mô hình phiên. | Chiếm phiên hoặc gửi request trái phép. |
| **Client secret/private key** | Xác thực confidential client/ký proof. | Có, nhưng cần kho bí mật và quản lý khóa riêng. | Giả mạo client hoặc lạm dụng khóa. |

Mục tiêu không phải **mã hóa mọi dữ liệu bằng mọi giá**. Nếu ứng dụng không cần lưu một AT sau khi sử dụng, **không lưu** có thể tốt hơn mã hóa.

Trước khi lưu RT, cần xác định client có thực sự cần nó không. Ví dụ với **client_credentials**, client có thể xin AT mới bằng credential của chính mình; RFC 6749 nêu AS **SHOULD NOT** đưa RT vào phản hồi của grant đó.

## 3. Mô hình đe dọa: at rest có tác dụng ở đâu?

Một biện pháp chỉ hiệu quả nếu hiểu đối thủ có quyền gì.

| Tình huống | Mã hóa token at rest có ích? | Điều còn cần bảo vệ |
| --- | --- | --- |
| Kẻ tấn công tải được DB chỉ chứa ciphertext. | **Có**, khi khóa được giữ riêng và không bị lộ. | KMS, quyền giải mã, backup, logs. |
| File backup bị lộ, khóa mã hóa vẫn do KMS riêng kiểm soát. | **Có thể giảm thiệt hại đáng kể**. | Khóa backup, quyền restore, retention. |
| Người dùng có quyền đọc DB nhưng không có quyền decrypt. | **Có**, nếu phân quyền thật sự tách biệt. | Quyền gọi API giải mã và dữ liệu tạm. |
| SQL injection chỉ trích xuất cột ciphertext. | **Giảm nguy cơ trích xuất credential** nếu không trích được khóa. | SQLi, DB authorization, các đường lộ khác. |
| Backend bị chiếm và có quyền đọc DB, gọi KMS decrypt. | **Không đủ**. | Least privilege, workload identity, egress, giám sát và thu hồi. |
| XSS trong SPA, script có quyền gọi hàm giải mã RT. | **Không bảo đảm chống được**. | Phòng XSS, BFF, sender-constraining và giảm lifetime. |
| Token bản rõ bị ghi vào access log. | **Không**, nếu log không được bảo vệ cùng lớp. | Redaction, log retention/access. |
| Token bị nghe lén qua HTTP. | **Không**. | HTTPS/TLS cho mọi kết nối mang token. |

Ba trạng thái cần phân biệt:

1. **At rest:** token nằm trong DB, file, backup, snapshot, hàng đợi hoặc cache bền vững.
2. **In transit:** token đi qua mạng giữa client, Authorization Server (AS), Resource Server (RS) và các proxy.
3. **In use:** token được giải mã trong memory hoặc đưa vào HTTP request hợp lệ.

Mã hóa at rest chủ yếu nhắm trạng thái đầu tiên, dù một số kiến trúc có thể bảo vệ dữ liệu ở nhiều lớp khác nhau.

## 4. Mã hóa, băm, chữ ký JWT và TLS khác nhau

| Kỹ thuật | Khôi phục token gốc? | Mục đích chính |
| --- | --- | --- |
| **AES-GCM / AEAD** | Có, với khóa phù hợp. | Giữ bí mật và kiểm toàn vẹn dữ liệu cần dùng lại. |
| **SHA-256/HMAC** | Không phải cơ chế giải mã. | So khớp credential khi không cần khôi phục bản gốc. |
| **JWS (JWT ký số)** | Nội dung payload thường vẫn đọc được. | Xác minh tính toàn vẹn/nguồn phát hành token. |
| **JWE** | Có thể giải mã bằng khóa theo profile. | Giữ bí mật nội dung token. |
| **TLS/HTTPS** | Dữ liệu được giải mã tại endpoint kết nối. | Bảo vệ đường truyền và xác thực endpoint. |
| **Full-disk encryption** | Có, sau khi máy mở khóa ổ đĩa. | Giảm rủi ro lộ dữ liệu trên ổ/bản sao vật lý. |
| **Transparent Database Encryption (TDE)** | DB engine có thể đọc dữ liệu khi hoạt động. | Bảo vệ file DB/log ở tầng lưu trữ, không nhất thiết chống người có quyền SQL SELECT. |

**JWT đã ký không phải token đã được mã hóa.** Người có bản sao JWT dạng JWS có thể thường xuyên đọc claims trong payload mà không cần khóa ký. Việc ký giúp RS phát hiện sửa đổi trái phép; nó không giữ bí mật giá trị bearer token.

**JWE** có thể giữ bí mật claims của token, nhưng không tự sửa vấn đề mã độc ở client có quyền giải mã hoặc sử dụng token. Dù token được mã hóa hay ký, RS vẫn phải kiểm **issuer, audience, exp/nbf, scope và quyền theo tài nguyên**.

## 5. Không lưu nếu không cần lưu

Một lỗi thiết kế là lưu mọi AT vào database “để tiện tra cứu”, dù backend chỉ cần AT trong một request.

Hãy hỏi:

- Có thể chỉ giữ AT trong **memory** tới khi request hoàn tất hoặc token hết hạn không?
- Có thể dùng BFF để browser không trực tiếp giữ OAuth token thô không?
- Có thực sự cần RT bền vững qua server restart không?
- Có thể chỉ lưu **mã tham chiếu session opaque** ở browser thay vì RT không?
- Có thể dùng credential dành cho workload và AT ngắn hạn thay RT phiên cá nhân trong automation không?
- Có thể giảm bản sao trong log, backup, snapshot và cache không?

**Data minimization đi trước encryption:** nếu không có bản sao credential, bản sao đó không thể bị đánh cắp.

## 6. Nếu cần giải mã lại: sử dụng AEAD thay vì tự chế crypto

Một OAuth client/BFF cần gửi nguyên RT tới token endpoint. Nếu lưu bền vững, nó thường cần **mã hóa có thể giải mã**. Hướng phổ biến là **Authenticated Encryption with Associated Data (AEAD)** thông qua thư viện được kiểm chứng.

**AES-GCM** có các thành phần:

- **K – encryption key:** khóa bí mật được quản lý an toàn.
- **Nonce/IV:** giá trị riêng cho mỗi lần mã hóa dưới cùng khóa.
- **P – plaintext:** token gốc.
- **AAD – associated authenticated data:** metadata được bảo vệ về tính toàn vẹn nhưng không được mã hóa.
- **C – ciphertext:** dữ liệu sau mã hóa.
- **Tag:** bằng chứng xác thực giúp phát hiện việc ciphertext, nonce hoặc AAD bị sửa.

Một bản ghi có thể trông như:

~~~text
cipher_version  = 1
key_id          = "kek-2026-07"
nonce           = <12 bytes>
ciphertext      = <encrypted token bytes>
authentication_tag = <tag bytes>
aad_context     = <metadata from trusted server context>
~~~

Đây là mô hình **minh họa**, không phải format chuẩn. Nhiều thư viện trả ciphertext và tag gộp trong một mảng bytes.

### 6.1 Nonce không được lặp với cùng key

Với GCM, **tái sử dụng nonce/IV cùng key** có thể phá vỡ nghiêm trọng tính bí mật và toàn vẹn.

Những cách sinh nonce không nên dùng:

~~~text
nonce = 000000000000
nonce = hash(userId)        // Cố định theo user
nonce = currentUnixSecond  // Nhiều encrypt trong một giây dễ trùng
nonce = "fixed-nonce"       // Hardcode
~~~

Một cách minh họa là dùng IV **96-bit được sinh ngẫu nhiên bằng SecureRandom**, đồng thời giới hạn số lần mã hóa theo một DEK và quản lý nguy cơ collision. Hệ thống tải lớn có thể cần chiến lược **bảo đảm tính duy nhất** (ví dụ phân vùng/counter theo thiết kế) hoặc rotation DEK theo giới hạn của GCM.

**Nonce không cần giữ bí mật**, nhưng phải đáp ứng yêu cầu duy nhất với key. Đừng nghĩ “nonce ngẫu nhiên” đồng nghĩa rủi ro trùng bằng 0 nếu sử dụng cùng key quá nhiều lần.

### 6.2 Authentication tag phải được xác minh

Nếu attacker sửa ciphertext, nonce hoặc AAD, giải mã phải **thất bại** khi authentication tag không hợp lệ.

Không được:

- Bỏ qua lỗi xác thực rồi dùng plaintext chưa đáng tin.
- Cố “khắc phục” bằng cách bỏ kiểm tag hoặc giải mã fallback.
- Dùng cơ chế mã hóa không xác thực và mặc định rằng ciphertext không thể bị sửa có chủ đích.
- Trả dữ liệu giải mã chưa được xác thực cho business logic.

Một tính chất quan trọng của AEAD là **confidentiality + integrity**, trong phạm vi giả định và cách dùng thuật toán đúng.

### 6.3 AAD ràng buộc token với ngữ cảnh

Ví dụ AAD theo phiên:

~~~text
purpose    = "oauth-refresh-token"
issuer     = "https://identity.example.test"
client_id  = "dashboard-bff"
session_id = "session-92"
tenant_id  = "tenant-blue"   // Khi tenant là ngữ cảnh ổn định
version    = 1
~~~

Nếu một attacker copy ciphertext RT của phiên A sang record phiên B, giải mã với AAD của B có thể thất bại vì tag không khớp.

Lưu ý:

- AAD **không được mã hóa**, tránh đặt dữ liệu cá nhân không cần thiết vào đó.
- AAD phải được xây dựng từ **ngữ cảnh server đáng tin**, không lấy tự do từ request của client.
- Cần định dạng AAD xác định, tránh khác thứ tự/encoding khi mã hóa và giải mã.
- Nếu metadata cần đổi, phải có quy trình migration/re-encryption phù hợp.
- AAD không thay thế authorization check trước khi gọi decrypt.

## 7. Envelope encryption: tách khóa khỏi dữ liệu

**Mã hóa token rồi lưu khóa ngay cạnh ciphertext trong cùng DB** làm giảm mạnh tác dụng bảo vệ khi DB bị xuất.

**Envelope encryption** tách khóa:

- **DEK – Data Encryption Key:** dùng AES-GCM để mã hóa dữ liệu token.
- **KEK – Key Encryption Key:** khóa ở KMS/HSM quản lý việc wrap/unwrap DEK hoặc thực hiện thao tác tương đương.

~~~mermaid
sequenceDiagram
    participant App as Token Manager
    participant KMS as KMS / HSM
    participant DB as Encrypted Token Store
    participant AS as Authorization Server

    App->>KMS: Lấy DEK mới theo quyền workload
    KMS-->>App: DEK tạm + encrypted DEK
    App->>App: AES-GCM mã hóa RT với nonce và AAD
    App->>DB: Lưu ciphertext, nonce, tag, encrypted DEK, version
    Note over App: Không ghi RT/DEK ra log
    App->>DB: Đọc record khi cần refresh
    DB-->>App: Ciphertext, metadata, encrypted DEK
    App->>KMS: Unwrap DEK theo quyền được cấp
    KMS-->>App: DEK trong ngữ cảnh tạm
    App->>App: Xác minh tag và giải mã RT
    App->>AS: HTTPS POST /token với RT theo client binding
    AS-->>App: AT mới (+ RT mới nếu AS rotation)
    App->>App: Mã hóa RT mới với nonce mới
    App->>DB: Lưu thay thế theo generation
~~~

Tùy KMS, ứng dụng có thể dùng API mã hóa trực tiếp dữ liệu nhỏ hoặc KMS chỉ bảo vệ DEK. Chọn theo hợp đồng và giới hạn dịch vụ; không mặc định phải có RPC tới KMS trên mọi request.

### Phân quyền KMS và database

| Quyền | Bên nên sở hữu | Rủi ro khi mở quá rộng |
| --- | --- | --- |
| Đọc ciphertext | Token manager và workload thật sự cần. | Trích xuất dữ liệu hàng loạt. |
| Gọi KMS decrypt/unwrap | Workload được phép sử dụng RT. | Có thể giải mã hàng loạt nếu kết hợp DB read. |
| Sửa/xóa bản ghi RT | Token manager và luồng revocation kiểm soát. | Trộn phiên, ghi đè RT mới, phá rotation. |
| Rotate/disable KEK | Quản trị khóa qua kiểm soát phù hợp. | Mất khả năng decrypt hoặc thay đổi trust boundary. |
| Xem KMS audit | Security/operations theo least privilege. | Lộ thông tin vận hành, metadata nhạy cảm. |

Không cấp quyền giải mã cho mọi service chỉ vì chúng cùng chạy trong Kubernetes/VPC. Workload identity và KMS policy phải giới hạn theo **dịch vụ, môi trường và mục đích**.

### Mã hóa ở cấp storage có đủ không?

**TDE/disk encryption** hữu ích khi ổ đĩa hoặc file DB bị lấy trái phép, nhưng người có quyền truy vấn DB thường có thể thấy nội dung DB đã được giải mã bởi engine. Nếu muốn tách người có quyền DB read khỏi người được dùng RT, **application-layer encryption với KMS độc lập** thường có giá trị hơn.

Nhiều lớp encryption chỉ tạo thêm giá trị nếu có **ranh giới khóa và quyền độc lập thực chất**.

## 8. Thiết kế schema token store

Một mô hình tham khảo cho backend/BFF:

~~~text
OAuthSessionToken
    id                   UUID, primary key
    session_id           opaque session reference
    principal_id         trusted internal principal
    issuer_id            trusted AS identifier
    client_id            registered OAuth client
    tenant_id            tenant context if relevant
    token_kind           REFRESH_TOKEN
    cipher_version       1
    key_id               "kek-2026-07"
    encrypted_dek        byte[]
    nonce                byte[12]
    ciphertext_and_tag   byte[]
    generation           integer
    expires_at           timestamp when known and trustworthy
    status               ACTIVE | REVOKED | EXPIRED
    last_rotated_at      timestamp
~~~

Đây là **schema khái niệm**, không phải định dạng bắt buộc của OAuth.

- **Dùng session ID làm index:** không cần giải mã tất cả RT để tìm phiên.
- **Ràng buộc identity:** issuer/client/session/user/tenant phải khớp ngữ cảnh đã xác thực.
- **Version hóa:** lưu key_id và cipher_version để migration/rotation.
- **Không lưu key rõ cùng record:** encrypted_dek có thể lưu cạnh ciphertext, nhưng KEK phải nằm ở key service độc lập.
- **Không giữ cột RT plaintext song song:** dọn dữ liệu cũ trong quá trình migration.
- **Không coi status ACTIVE local là bằng chứng AS còn chấp nhận RT.** AS là bên quyết định hiệu lực RT.
- **Xác định retention:** dữ liệu bị thu hồi/hết hạn phải được dọn theo policy, kể cả bản sao và backup.

Trường **expires_at** không được suy đoán bằng cách tự parse RT opaque nếu AS không cung cấp hợp đồng tương ứng.

## 9. Khi nào lưu hash/HMAC tốt hơn lưu ciphertext?

Có hai vai trò khác nhau:

**A. OAuth client/BFF giữ RT do Authorization Server cấp.** Client cần gửi lại **RT gốc** tại token endpoint. Với RT dạng chuỗi bearer, client thường phải có cách **khôi phục plaintext**, vì vậy mã hóa có thể giải mã là lựa chọn phù hợp.

**B. Authorization Server lưu dấu vết RT mà chính nó phát hành.** AS nhận RT do client trình ra và muốn đối chiếu với credential đã cấp. Nếu RT là chuỗi ngẫu nhiên có **entropy cao** và AS không cần khôi phục bản gốc, nó có thể lưu **hash/HMAC** làm chỉ mục thay vì lưu RT có thể giải mã.

~~~text
OAuth Client / BFF:
    store ciphertext(RT)
    -> decrypt -> original RT -> POST /token

Authorization Server:
    store lookup_fingerprint(RT)
    -> receive RT -> calculate fingerprint -> lookup
~~~

Ví dụ fingerprint ở AS:

~~~text
lookup_key = HMAC_SHA256(server_secret_lookup_key, raw_refresh_token)
store lookup_key, grant_id, client_id, expires_at, status
~~~

Đây là một mô hình triển khai, không phải định dạng bắt buộc của giao thức.

### SHA-256 hay HMAC?

Với token ngẫu nhiên entropy đủ cao, **SHA-256** có thể làm dấu vết một chiều thích hợp vì rất khó đoán token để đảo hash. **HMAC-SHA-256** bổ sung bí mật server vào phép tạo fingerprint, hữu ích trong một số threat model nếu DB bị lộ nhưng HMAC key được giữ riêng.

Nếu dùng HMAC, key phải được bảo vệ như secret; rotate key có thể ảnh hưởng lookup, cần chiến lược key version/migration. Không dùng tên fingerprint để vô tình tiết lộ RT nguyên gốc trong log.

**Mật khẩu do người dùng chọn** có entropy thấp cần password hashing chuyên dụng với salt/cost thích hợp; không áp dụng máy móc lập luận “SHA-256 đủ” cho password. **RT phải được AS cấp với entropy mạnh**, không phải chuỗi tự chọn dễ đoán.

### OAuth client chỉ lưu hash thì có refresh được không?

Thông thường **không** nếu AS yêu cầu đúng RT gốc. Hash không thể giải mã để lấy RT. Chỉ dùng hash thay cho RT gốc nếu giao thức/profile riêng định nghĩa rõ cơ chế khác.

## 10. Ví dụ Java: AES-GCM bảo vệ một chuỗi token

Đoạn code này minh họa **lớp mã hóa/giải mã**. Nó **không triển khai KMS, xử lý OAuth, schema DB, policy hoặc key rotation production**. Khóa được truyền vào dưới dạng SecretKey từ thành phần quản lý khóa bên ngoài; không hardcode khóa trong code.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class TokenAtRestCrypto {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    public record EncryptedToken(
            String nonceBase64,
            String cipherAndTagBase64) {}

    public static EncryptedToken encrypt(
            String rawToken, SecretKey dek, String trustedContext
    ) throws Exception {
        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(
                trustedContext.getBytes(StandardCharsets.UTF_8));

        byte[] ciphertextAndTag = cipher.doFinal(
                rawToken.getBytes(StandardCharsets.UTF_8));

        return new EncryptedToken(
                Base64.getEncoder().encodeToString(nonce),
                Base64.getEncoder().encodeToString(ciphertextAndTag));
    }

    public static String decrypt(
            EncryptedToken record, SecretKey dek, String trustedContext
    ) throws Exception {
        byte[] nonce = Base64.getDecoder().decode(
                record.nonceBase64());
        if (nonce.length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid nonce length");
        }

        byte[] ciphertextAndTag = Base64.getDecoder().decode(
                record.cipherAndTagBase64());

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(
                trustedContext.getBytes(StandardCharsets.UTF_8));

        // doFinal phải từ chối nếu authentication tag không hợp lệ.
        byte[] plaintext = cipher.doFinal(ciphertextAndTag);
        return new String(plaintext, StandardCharsets.UTF_8);
    }

    private TokenAtRestCrypto() {}
}
~~~

### Những giới hạn quan trọng khi chuyển thành code thật

1. **Nonce:** ví dụ dùng 96-bit random IV để dễ hiểu. Với nhiều lần mã hóa dưới cùng DEK, cần chính sách giới hạn/rotation hoặc chiến lược cấp nonce đảm bảo tính duy nhất theo yêu cầu GCM; không xem SecureRandom như đảm bảo trùng bằng 0.
2. **Key management:** DEK phải được sinh và phân phối an toàn qua KMS/HSM/secret manager phù hợp, không nằm cùng DB plaintext hoặc trong source.
3. **AAD:** trustedContext cần lấy từ dữ liệu server đã xác minh, format chuẩn hóa; không tin chuỗi từ request bên ngoài.
4. **Integrity:** lỗi xác thực tag phải làm giải mã thất bại; không fallback sang cipher không xác thực.
5. **Memory:** String và bản sao byte[] có thể tồn tại lâu hơn mong đợi trong JVM; ví dụ dùng String cho dễ dạy. Giảm vòng đời plaintext, không log/heap dump token.
6. **Transport:** RT sau giải mã chỉ được gửi qua TLS tới token endpoint đúng issuer, cùng client authentication/binding khi áp dụng.
7. **Authorization:** chỉ caller được phép quản lý phiên mới có quyền yêu cầu decrypt.
8. **Versioning:** lưu key_id, cipher_version, AAD version và metadata cần thiết cùng ciphertext.

**Không dùng code minh họa này thay một hệ thống KMS/policy production đầy đủ.**

## 11. Giải mã ít nhất có thể và ngăn bản sao plaintext

Một lỗi phổ biến: RT được mã hóa đúng trong DB nhưng bị ghi vào log ngay sau khi giải mã.

~~~text
[DEBUG] Sending refresh request:
    refresh_token=EXAMPLE_REAL_REFRESH_TOKEN
~~~

Hoặc response từ AS bị dump:

~~~text
[INFO] Token endpoint response:
    access_token=...
    refresh_token=...
~~~

Những bản sao này **không được bảo vệ bởi mã hóa cột ciphertext**.

Cần kiểm:

- HTTP client logger, reverse proxy, gateway, service mesh có ghi request body/header không?
- Exception handler có in RT, client secret, key hoặc response token không?
- Tracing spans, APM, analytics có chứa Authorization header/token endpoint body không?
- Cache tạm, queue và retry job có giữ plaintext RT không?
- Crash report và heap dump có được phân quyền và giữ theo thời hạn an toàn không?
- Có endpoint debug trả decrypted RT ra frontend không?

Chỉ giải mã **khi thật sự cần dùng**, trong thành phần token manager chuyên trách. Không giải mã RT chỉ để hiển thị trong admin dashboard.

### Có xóa hoàn toàn RT khỏi Java heap được không?

Có thể xóa byte[] do ứng dụng kiểm soát sau khi dùng, nhưng Java String bất biến và GC/JVM có thể giữ bản sao. Không nên hứa xóa sạch mọi dấu vết trong heap bằng cách set một biến thành null. Giảm lifetime, tránh copy token, hạn chế heap dump và bảo vệ memory access vẫn quan trọng.

## 12. Key rotation khác refresh token rotation

| Hoạt động | Thay đổi gì? | Ai thực hiện? | Không tự làm được |
| --- | --- | --- | --- |
| **KEK/DEK rotation** | Khóa dùng bảo vệ dữ liệu at rest. | KMS/token manager/operations. | Không vô hiệu bản sao RT đã bị lấy ở dạng rõ. |
| **RT rotation** | AS phát RT mới và vô hiệu RT cũ theo profile. | Authorization Server và OAuth client. | Không tự xoay khóa mã hóa DB. |
| **Token revocation** | Hủy hiệu lực RT/AT theo AS/RS và profile. | AS hoặc trạng thái tương ứng. | Không tự xóa mọi ciphertext/backup. |
| **Logout** | Kết thúc phiên ứng dụng/IdP tùy thiết kế. | Client/BFF/AS. | Không bảo đảm mọi JWT AT tự mất hiệu lực ngay. |

Ví dụ:

~~~text
BFF lưu ciphertext(RT-1) bằng DEK-7.
AS rotate RT-1 -> RT-2.
BFF mã hóa RT-2 và cập nhật bản ghi.

Sau đó security rotate KEK-A -> KEK-B.
BFF có thể rewrap DEK-7 bằng KEK-B.
Bản thân RT-2 không thay đổi do rotate KEK.
~~~

Nếu DEK hoặc RT plaintext đã bị lộ, **chỉ rewrap** có thể không đủ. Cần đánh giá **re-encrypt bằng DEK mới** và/hoặc **thu hồi RT ở AS**.

### Kế hoạch xoay khóa

- Lưu **key_id/version** trên từng record.
- Có thể decrypt bản ghi dùng key cũ trong giai đoạn migration có kiểm soát.
- Ghi mới bằng key hiện hành.
- Rewrap DEK hoặc re-encrypt dữ liệu cũ có checkpoint và kiểm thử.
- Giám sát số record còn dùng key cũ.
- Chỉ disable/delete key cũ khi không còn dữ liệu/backup cần decrypt bằng key đó, hoặc đã áp dụng quy trình crypto-shredding có chủ đích.
- Diễn tập restore và kiểm KMS downtime.

Không bao giờ tạo một **fallback hardcoded key** để cứu lỗi KMS trong production.

## 13. Refresh token rotation và consistency ở encrypted store

~~~mermaid
sequenceDiagram
    participant M as Token Manager
    participant DB as Encrypted Store
    participant AS as Authorization Server

    M->>DB: Load RT ciphertext thế hệ 1
    DB-->>M: ciphertext, nonce, key version, generation=1
    M->>M: Authorize session và decrypt RT-1
    M->>AS: HTTPS POST /token với RT-1
    AS->>AS: Validate và vô hiệu RT-1 theo policy
    AS-->>M: AT-2 + RT-2 khi rotate
    M->>M: Encrypt RT-2 bằng nonce mới
    M->>DB: CAS generation=1 -> generation=2
    DB-->>M: Commit bản ghi mới
    Note over M,DB: Lần refresh sau dùng RT-2
~~~

**CAS (compare-and-swap)** hoặc optimistic locking giúp tránh request cũ ghi đè RT mới. Nhưng:

- Mutex trong một process không bảo đảm nhiều instance backend được đồng bộ; có thể cần distributed lock hoặc token manager tập trung.
- Nếu AS đã rotate mà response bị mất, client không thể tự đoán RT mới. Retry RT cũ có thể kích hoạt reuse detection; phải xử lý theo policy AS.
- Nếu ghi ciphertext mới thất bại sau khi AS rotate, RT cũ có thể không dùng được; cần phục hồi hợp lệ hoặc yêu cầu đăng nhập lại.
- Local generation là metadata đồng bộ, **không thay thế trạng thái RT family ở AS**.
- Chỉ dùng plaintext RT trong thời gian refresh cần thiết, không giữ bản sao trong queue/log.

Mã hóa và rotation phải cùng nằm trong quy trình quản lý phiên.

## 14. Multi-tenant: mã hóa không tự ngăn lấy nhầm RT

Giả sử token manager lưu:

~~~text
tenant-blue  -> user-42 -> ciphertext(RT-A)
tenant-green -> user-91 -> ciphertext(RT-B)
~~~

Nếu endpoint nhận **record_id** do client tùy ý đưa và giải mã bất kỳ bản ghi nào, user-42 có thể yêu cầu record của user-91. Token được mã hóa đúng vẫn có thể bị lộ sau khi service hợp lệ giải mã.

Cần:

1. Truy vấn theo **session/principal/tenant đáng tin**, không chỉ record ID từ client.
2. Kiểm authorization **trước** khi decrypt hoặc gọi KMS.
3. Dùng AAD phù hợp để bind ciphertext với session, issuer, client và ngữ cảnh ổn định.
4. Chỉ đưa RT tới token endpoint của issuer/client đã đăng ký, không lấy URL đích từ request tự khai.
5. Phân quyền KMS theo workload và khi rủi ro cao cân nhắc phân tách key theo tenant.
6. Audit thao tác giải mã bằng metadata cần thiết, không lưu plaintext token.

**AAD là lớp kiểm toàn vẹn ngữ cảnh, không thay thế kiểm quyền nghiệp vụ hoặc phòng IDOR.**

## 15. Browser: mã hóa token trong localStorage có chống được XSS?

Một SPA có thể làm:

~~~text
localStorage["refresh_token"] = AES_GCM_encrypt(RT, key)
JavaScript bundle có key hoặc có thể gọi decrypt(key, ciphertext)
~~~

Nếu XSS chạy cùng origin và sử dụng được khóa/hàm giải mã, nó có thể lấy RT hoặc kích hoạt refresh ngay trong phiên hợp lệ. **Ciphertext và khóa cùng ngữ cảnh script** thường không tạo ranh giới bảo mật độc lập.

| Cơ chế | Lợi ích | Giới hạn |
| --- | --- | --- |
| **Memory** | Giảm lưu bền vững sau reload. | XSS runtime vẫn có thể dùng chức năng của app. |
| **localStorage/sessionStorage** | Dễ sử dụng. | Script cùng origin có thể đọc dữ liệu. |
| **IndexedDB** | Lưu bền vững, hỗ trợ dữ liệu có cấu trúc. | JS cùng origin có thể truy cập theo permission của app. |
| **WebCrypto non-extractable key** | Giảm khả năng xuất raw key qua API chuẩn. | Mã độc có thể tận dụng các thao tác mật mã mà origin được phép. |
| **HttpOnly cookie + BFF** | OAuth RT được giữ phía backend, ngoài khả năng JS trực tiếp đọc cookie/RT. | Vẫn cần CSRF/XSS, session protection và kiểm quyền backend. |

**Mã hóa ở browser không làm cho môi trường JavaScript bị XSS trở thành tin cậy.**

Với web có backend, mô hình **BFF** thường đáng cân nhắc để giữ RT ở server-side encrypted token store; browser giữ session cookie có các thuộc tính **Secure, HttpOnly, SameSite** theo chính sách. HttpOnly hạn chế đọc cookie, nhưng XSS có thể gọi API bằng phiên và CSRF cần được xử lý riêng.

## 16. Mobile/desktop: dùng cơ chế bảo vệ khóa của hệ điều hành

### Mobile

**iOS Keychain** và **Android Keystore** hỗ trợ các cách bảo vệ credential hoặc khóa:

- Trên iOS, ứng dụng có thể lưu RT trong Keychain với accessibility/access control phù hợp; cần quyết định dữ liệu có được backup/đồng bộ không.
- Trên Android, Keystore chủ yếu bảo vệ **khóa**; RT thường được bảo vệ bằng khóa đó rồi lưu ciphertext ở nơi thích hợp. Không mặc định Keystore là một bảng lưu trực tiếp mọi chuỗi RT.
- Secure Enclave/TEE/StrongBox có thể hỗ trợ phần cứng tùy thiết bị và cấu hình.
- Root/jailbreak/malware hoặc runtime bị chiếm vẫn tạo rủi ro vì ứng dụng hợp lệ phải có khả năng dùng RT.
- Khi sender-constraining dùng khóa của thiết bị, phải bảo vệ khóa và thiết kế phục hồi khi mất/đổi thiết bị.

### Desktop/CLI

Ưu tiên OS credential store khi khả thi:

- Windows Credential Manager/DPAPI.
- macOS Keychain.
- Keyring/Secret Service phù hợp trên Linux.

Không coi file **.env**, JSON config, shell history hoặc folder home được phân quyền mặc định là một secret vault. Với CI/CD, nên dùng workload identity/client credentials phù hợp thay vì RT phiên cá nhân lưu trong artifact.

### Backup và restore

Một RT mã hóa bằng khóa chỉ có trên thiết bị cũ có thể không giải mã được sau restore sang máy mới. Đó có thể là thuộc tính bảo mật mong muốn, nhưng cần quy trình đăng nhập lại rõ ràng. Tránh copy cả ciphertext và key sang thiết bị khác nếu chính sách yêu cầu token không thể di chuyển.

## 17. Backup, replica, snapshot và recovery

| Nơi lưu/bản sao | Rủi ro | Biện pháp |
| --- | --- | --- |
| **Database backup** | Có thể chứa ciphertext, metadata hoặc plaintext từ migration cũ. | Mã hóa backup, phân quyền, retention/xóa theo policy. |
| **Snapshot VM/container/volume** | Cache, temporary files, thậm chí memory có credential. | Hạn chế snapshot, mã hóa và kiểm retention. |
| **Read replica** | Dữ liệu lan sang hệ thống có người vận hành khác. | Cô lập quyền, audit và bảo vệ transport. |
| **Redis/cache** | RT có thể bị lưu dạng rõ để “tối ưu”. | Hạn TTL, hạn quyền, hạn plaintext hoặc mã hóa theo policy. |
| **Queue/worker** | Job chứa nguyên RT truyền tới service khác. | Gửi tham chiếu có kiểm soát hoặc ciphertext, hạn chế số nơi có credential. |
| **Log/APM/traces** | Token plaintext lọt vào telemetry. | Redaction trước khi ghi, test loại bỏ credential. |
| **Key backup** | Mất key gây mất khả năng decrypt; lộ key làm yếu ciphertext. | DR cho KMS/HSM, quyền độc lập và audit. |

Một tình huống DR thường bị quên: restore DB backup cũ nhưng **KEK version dùng để wrap DEK đã bị xóa**. Khi đó backup dù hợp lệ cũng không thể giải mã RT. Phải cân bằng việc giữ key cho khôi phục với hạn retention và mục tiêu xóa bí mật.

**Xóa ciphertext hiện tại không tự xóa mọi bản sao trong backup.** Crypto-shredding (hủy key cần thiết) có thể làm ciphertext không thể giải mã nếu không còn bản sao key, nhưng cũng có thể ảnh hưởng nhiều bản ghi dùng chung key. Và **xóa local ciphertext không tự thu hồi RT ở AS**.

## 18. Ứng phó sự cố: lộ ciphertext khác với lộ plaintext

**Tình huống A – chỉ lộ ciphertext, KMS key không bị truy cập**

- Đánh giá AEAD, nonce policy, AAD, access controls và phạm vi DB dump.
- Kiểm tra audit KMS xem có decrypt bất thường không.
- Xem xét key rotation và token revocation theo chính sách rủi ro, không khẳng định mọi RT đã lộ plaintext.

**Tình huống B – lộ ciphertext cùng DEK hoặc quyền unwrap**

- Coi RT tương ứng có nguy cơ bị khôi phục.
- Thu hồi RT/grant/session bị ảnh hưởng ở AS; đánh giá AT đã được cấp.
- Re-encrypt với DEK mới, rotate/disable quyền key phù hợp.
- Kiểm tra audit giải mã và hoạt động token endpoint.

**Tình huống C – lộ RT plaintext trong logs**

- **Key rotation không làm bản sao RT trong log hết hiệu lực.**
- Thu hồi RT/phiên, đánh giá token family và reuse detection.
- Hạn chế/xóa log, điều tra nguyên nhân, bổ sung redaction và kiểm thử.

**Tình huống D – KMS không khả dụng**

- Không trả ciphertext cho client để dùng như token, không bật chế độ “không mã hóa tạm”.
- Xử lý fail-safe, theo chính sách có thể báo lỗi hoặc yêu cầu đăng nhập lại.
- Phục hồi KMS từ kịch bản DR; không hardcode fallback key.

## 19. Kiểm thử bảo mật mã hóa token at rest

Chỉ test **encrypt rồi decrypt được** là không đủ.

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Round-trip | Encrypt RT giả và decrypt bằng đúng key/AAD. | Phục hồi chính xác RT giả. |
| Ciphertext bị sửa | Đổi một byte ciphertext hoặc tag. | AEAD xác thực thất bại, không trả plaintext. |
| Dùng key khác | Dùng DEK không đúng. | Decrypt thất bại. |
| AAD sai | Đổi session/issuer/client trong AAD. | Tag check thất bại. |
| Nonce sai | Thiếu/sai độ dài nonce. | Từ chối schema; không đoán nonce. |
| Nonce uniqueness | Mã hóa nhiều record dưới cùng key. | Không reuse nonce; tuân giới hạn vận hành. |
| Key rotation | Đọc record mã hóa bằng key version cũ. | Chỉ được trong giai đoạn cho phép, migrate an toàn. |
| Key đã bị disable | KMS từ chối unwrap. | Lỗi kiểm soát, không fallback key mặc định. |
| DB-only breach | Có ciphertext, không có quyền KMS. | Không lấy plaintext chỉ từ DB dump. |
| Wrong tenant | User A yêu cầu decrypt record user B. | Bị từ chối **trước khi decrypt**. |
| Concurrent refresh | Hai request cùng muốn ghi RT mới. | Generation/CAS ngăn ghi đè RT mới bởi RT cũ. |
| Lost refresh response | AS rotate thành công nhưng response mất. | Không retry RT cũ vô hạn; phục hồi theo AS policy. |
| KMS outage | KMS không phản hồi. | Không tự cấp quyền/tiết lộ token do fallback. |
| Log leak | Request refresh/error/debug đi qua nhiều lớp. | RT/AT/secret không xuất hiện trong log/traces. |
| Backup restore | Restore ciphertext và key version tương thích. | Khôi phục theo quy trình, có audit và quyền phù hợp. |
| Revoked RT | RT decrypt được nhưng AS đã thu hồi. | Refresh bị từ chối; decrypt không chứng minh RT còn hiệu lực. |
| Wrong audience | AT sau refresh có aud sai API. | Resource Server từ chối theo policy. |

### Test AAD ngăn chuyển ciphertext giữa phiên

~~~text
1. Tạo RT giả.
2. Encrypt dưới DEK-A, AAD của session-blue.
3. Lưu ciphertext vào DB test.
4. Copy nguyên ciphertext sang record session-green.
5. Gọi decrypt với AAD session-green.

Kỳ vọng: authentication tag không hợp lệ; không có plaintext RT.
~~~

Bài test này chứng minh **AAD binding** trong layer mã hóa; vẫn cần test riêng để xác nhận user tenant-green không có quyền gọi decrypt trên record của tenant-blue ngay từ đầu.

Với Java, dùng test framework có assertion thực; không chỉ dựa vào câu lệnh **assert** có thể bị vô hiệu theo cấu hình JVM. Cần kiểm thêm key/cipher version không được chọn tùy ý từ dữ liệu record chưa được xác thực.

## 20. Bài tập tình huống

**Bài 1 – Mã hóa có key ngay trong DB.** Backend lưu ciphertext và AES key trong hai cột cùng bảng. Khi DB dump bị lấy, token có còn được bảo vệ tốt không?

**Phân tích:** Khó có ranh giới bảo vệ thực tế vì người lấy DB cũng có key. Cần tách key ra KMS/secret manager, phân quyền độc lập.

**Bài 2 – JWT ký số.** Một backend ghi nguyên JWS access token vào bảng session và nói rằng chữ ký JWT đã là encryption.

**Phân tích:** Sai. Chữ ký không giấu payload và bản sao bearer token vẫn có thể bị sử dụng. Cần không lưu khi không cần, hoặc bảo vệ at rest phù hợp.

**Bài 3 – SELECT được DB, không có KMS decrypt.** Người ngoài lấy ciphertext, nonce, encrypted DEK nhưng không có key unwrap.

**Phân tích:** Envelope encryption đúng có thể giảm nguy cơ lộ RT plaintext. Vẫn phải đánh giá crypto, nonce, AAD, logs và các đường truy cập khác.

**Bài 4 – AES-CBC không MAC.** Nhóm phát triển chỉ mã hóa bằng CBC rồi không kiểm toàn vẹn khi decrypt.

**Phân tích:** Cần authenticated encryption hoặc thiết kế kiểm toàn vẹn đúng bằng thư viện an toàn. Chỉ mã hóa không xác thực có rủi ro dữ liệu bị sửa.

**Bài 5 – localStorage và XSS.** SPA mã hóa RT bằng WebCrypto nhưng cùng origin có thể gọi hàm decrypt. XSS xảy ra.

**Phân tích:** Mã hóa không tạo trust boundary độc lập. Cần phòng XSS, cân nhắc BFF, giảm RT tồn tại và bảo vệ rotation/sender binding theo profile.

**Bài 6 – Rotate KEK nhưng RT đã lộ plaintext.** Nhóm bảo mật xoay KMS key nhưng không thu hồi RT từng được log.

**Phân tích:** RT đã lộ có thể vẫn được AS chấp nhận. Cần thu hồi token/phiên và xử lý nguồn lộ ngoài việc đổi key.

**Bài 7 – Sai tenant.** Ciphertext của RT tenant-blue bị chuyển sang record tenant-green.

**Phân tích:** Nếu AAD buộc vào tenant/session đáng tin, decrypt sai ngữ cảnh sẽ thất bại. Vẫn phải kiểm permission trước decrypt để phòng IDOR.

## 21. Checklist trước khi triển khai

- **Nhu cầu:** Có thật sự phải lưu RT/AT bền vững không? Có thể thay bằng BFF hoặc session reference không?
- **Threat model:** Muốn chống DB dump, backup leak, insider hay ứng dụng bị chiếm? Lớp mã hóa đang giải quyết đúng mô hình nào?
- **Crypto:** Có dùng AEAD với key/tag/nonce phù hợp qua thư viện tin cậy không?
- **Nonce:** Có đảm bảo không reuse IV dưới cùng DEK và có giới hạn lượng mã hóa/rotation không?
- **AAD:** Có bind vào purpose, issuer, client, session và metadata đáng tin, ổn định không?
- **KMS:** KEK/DEK có tách khỏi DB, cấp qua workload identity và least privilege không?
- **Versioning:** Có key_id, cipher_version, schema AAD và lộ trình migration không?
- **Authorization:** Có kiểm session/user/tenant **trước khi** decrypt? Ai được phép gọi KMS?
- **Hash vs encrypt:** Đã phân biệt AS chỉ cần lookup với OAuth client phải khôi phục RT gốc chưa?
- **Memory:** Có giới hạn plaintext lifetime, không log/trace/cache token không cần thiết không?
- **Network:** Refresh qua TLS, đúng token endpoint/issuer và client authentication/binding phù hợp không?
- **Copies:** Backup, replica, queue, snapshot, logs và crash report có được kiểm soát không?
- **Key rotation:** Có kế hoạch rewrap/re-encrypt, giữ key cũ khi cần restore và thu hồi khi bị compromise không?
- **Token lifecycle:** RT rotation, concurrency, logout/revocation và TTL có phối hợp với encrypted store không?
- **Incident response:** Có phân biệt lộ ciphertext với lộ DEK hoặc lộ plaintext để phản ứng đúng không?
- **Test:** Có test tag/key/AAD sai, nonce, wrong tenant, KMS outage, backup restore và concurrency không?

## Kết luận

**Mã hóa token khi lưu** giúp giảm nguy cơ khi credential trong database, file, backup hoặc storage bị đọc trái phép. Với token client cần **sử dụng lại** như refresh token, **AEAD cùng KMS/envelope encryption, nonce không trùng, authentication tag và AAD** là những thành phần quan trọng. Với token do Authorization Server phát hành mà chỉ cần **so khớp**, lưu hash/HMAC có thể phù hợp hơn giữ dữ liệu có thể giải mã.

Tuy nhiên, at-rest encryption **không thay thế** TLS, xác minh issuer/audience, scope, exp/nbf, phân quyền theo tài nguyên, refresh token rotation và revocation. Nó cũng không ngăn một backend bị chiếm quyền dùng API decrypt mà backend sở hữu, hoặc token đã lọt vào log và runtime.

Một kiến trúc token security đúng phải trả lời: **Có cần lưu token không? Ai có quyền giải mã? Nếu token bị lộ, hệ thống giới hạn và chấm dứt khả năng dùng nó như thế nào?** Quản lý khóa và toàn bộ vòng đời token mới biến mã hóa at rest thành biện pháp bảo vệ thực chất.

### Tài liệu tham khảo

- [NIST SP 800-38D — Recommendation for Block Cipher Modes of Operation: GCM and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final)
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)

# Credential storage

**Credential storage** là cách hệ thống tạo, lưu, truy xuất, bảo vệ, luân chuyển và thu hồi các dữ liệu dùng để chứng minh danh tính hoặc quyền truy cập. Credential có thể là password verifier, refresh token, API key, TOTP seed, recovery code, private key hoặc khóa/certificate gắn với thiết bị. Mỗi loại có đặc tính khác nhau: có loại chỉ cần lưu giá trị để so sánh khi xác minh; có loại phải khôi phục được để ký, giải mã hoặc tạo mã xác thực; có loại nên nằm trong phần cứng bảo mật và không bao giờ xuất ra dạng rõ.

Một thiết kế lưu trữ credential an toàn bắt đầu bằng câu hỏi: **hệ thống cần làm gì với credential sau khi nhận nó?** Nếu chỉ cần kiểm tra password, hãy lưu password hash có salt thay vì password có thể giải mã. Nếu cần dùng lại TOTP seed hoặc client secret, hãy mã hóa bằng khóa được quản lý riêng. Nếu cần ký bằng private key, ưu tiên giữ khóa trong HSM, Secure Enclave hoặc Android Keystore. Nếu credential có entropy cao và chỉ cần đối chiếu, có thể lưu hash/fingerprint thay vì raw value.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Module giúp người học hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản; đồng thời mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập. Trong chương **Lưu trữ credential**, bài này trình bày nguyên tắc lựa chọn cách lưu theo loại credential, threat model và vòng đời vận hành.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt password verifier, bearer token, shared secret, private key, public key và certificate.
2. Chọn giữa hashing, encryption, secure hardware storage và secret manager dựa trên cách credential được sử dụng.
3. Giải thích salt, password hashing, pepper và vì sao không lưu password dạng rõ hoặc mã hóa có thể giải mã.
4. Thiết kế nơi lưu refresh token, API key, client secret, TOTP seed, recovery code và session ID.
5. Mô tả envelope encryption, KMS/HSM, key hierarchy và rotation.
6. Áp dụng least privilege, workload identity, separation of duties và audit cho việc đọc secret.
7. Bảo vệ credential trong log, crash dump, backup, CI/CD, môi trường runtime và thiết bị mobile.
8. Xây dựng quy trình phát hành, phân phối, sử dụng, rotate, revoke và hủy credential.
9. Xử lý sự cố khi database, secret manager, thiết bị hoặc private key bị lộ.
10. Thiết kế kiểm thử chứng minh credential không bị lưu hoặc sử dụng sai ranh giới tin cậy.

## 2. Credential không phải một loại dữ liệu duy nhất

Từ credential thường được dùng cho nhiều loại thông tin. Cách lưu đúng phụ thuộc vào việc hệ thống cần xác minh, gửi đi, ký, giải mã hay chỉ tra cứu credential đó.

| Loại credential | Ví dụ | Cách lưu thường phù hợp | Vì sao |
| --- | --- | --- | --- |
| Password | Mật khẩu đăng nhập | Password hashing chuyên dụng, salt riêng từng tài khoản | Server chỉ cần xác minh password; không cần khôi phục password gốc. |
| High-entropy bearer token | Refresh token, session ID ngẫu nhiên | Hash hoặc keyed fingerprint nếu chỉ cần đối chiếu; mã hóa nếu cần gửi lại nguyên vẹn | Giảm rủi ro khi kho dữ liệu bị đọc. |
| API key | Key tích hợp đối tác | Lưu hash của phần secret; hiển thị secret một lần | Server cần xác minh key, không cần đọc lại secret. |
| Shared secret cần dùng lại | TOTP seed, OAuth client secret | Mã hóa có xác thực bằng khóa được quản lý riêng | Server cần lấy lại secret để tính mã hoặc xác thực client. |
| Private key | Khóa ký, khóa DPoP, khóa thiết bị | HSM, Secure Enclave, Keychain/Keystore; ưu tiên non-exportable | Cần thực hiện phép ký nhưng thường không cần xuất key ra ngoài. |
| Public key | WebAuthn credential public key | Lưu trực tiếp cùng metadata | Public key không phải secret; dùng để xác minh chữ ký. |
| Certificate | X.509 public certificate | Lưu trực tiếp; bảo vệ tính toàn vẹn và chain metadata | Certificate thường chứa public key và thông tin định danh, không chứa private key. |
| Recovery code | Mã khôi phục một lần | Hash từng mã, đánh dấu đã sử dụng | Chỉ cần xác minh mã nhập vào; mỗi mã chỉ được dùng một lần. |
| Biometric template | Mẫu vân tay/khuôn mặt | Để hệ điều hành hoặc authenticator quản lý | Ứng dụng không nên thu thập hoặc tự lưu mẫu sinh trắc học. |

Không áp dụng một quy tắc duy nhất như “mã hóa mọi thứ” hoặc “hash mọi thứ”. Hash password cần thuật toán chậm, có salt và cấu hình phù hợp. Hash token ngẫu nhiên có thể dùng thuật toán hash mật mã nhanh vì token có entropy cao. TOTP seed cần mã hóa vì server phải dùng lại seed để xác minh mã. Private key nên được giữ trong vùng thực thi an toàn nếu kiến trúc hỗ trợ.

## 3. Mô hình hóa ranh giới tin cậy

Trước khi chọn công nghệ, hãy vẽ đường đi của credential và xác định nơi nào có thể nhìn thấy plaintext.

~~~mermaid
flowchart TD
    U[Người dùng / Thiết bị] -->|Nhập hoặc tạo credential| C[Client / Mobile App]
    C -->|TLS, credential cần thiết| A[Authentication Service]
    A -->|Hash hoặc encrypted secret| D[(Credential Database)]
    A -->|Yêu cầu mã hóa / giải mã| K[KMS / HSM]
    A -->|Audit metadata, không có raw secret| L[Audit / Security Monitoring]
    K -->|Key operation| A
    D -->|Backup đã mã hóa| B[(Encrypted Backup)]
    S[Secret Manager] -->|Secret ngắn hạn / workload identity| A
    A -->|Access token| R[Resource Server]
~~~

Các vùng tin cậy cần xem xét:

- **Client/device:** có thể bị mất, root/jailbreak, malware, debug build hoặc backup ngoài ý muốn.
- **Network:** có thể bị nghe lén, thay đổi hoặc chuyển hướng nếu TLS, certificate validation hay endpoint trust sai.
- **Application runtime:** process có thể có plaintext credential trong memory trong lúc sử dụng.
- **Credential database:** có thể bị đọc, sửa, xóa hoặc khôi phục từ backup bởi người có quyền quá rộng.
- **KMS/HSM/Keystore:** bảo vệ key material và thao tác mật mã; vẫn cần kiểm soát ai được gọi operation.
- **Secret manager:** nơi lưu và cấp secret cho workload; bản thân nó là hệ thống đặc quyền cao.
- **Logs/telemetry/analytics:** thường có nhiều người và hệ thống truy cập; tuyệt đối không biến chúng thành kho credential.
- **Build/deploy pipeline:** source code, artifact, CI variables và deployment configuration có thể làm lộ secret.

Hãy ghi rõ:
1. Ai tạo credential?
2. Ai được phép đọc hoặc sử dụng credential?
3. Credential có cần xuất ra plaintext không?
4. Plaintext tồn tại ở đâu và trong bao lâu?
5. Khi credential bị lộ, có thể thu hồi ở đâu?
6. Backup, replica và log có chứa credential hay bản sao của nó không?
7. Quyền quản trị database có đồng thời cho phép giải mã secret không?

Mục tiêu là giảm số thành phần có thể nhìn thấy raw secret và giảm thời gian credential tồn tại ở dạng có thể sử dụng.

## 4. Password storage: lưu verifier, không lưu password

Khi người dùng đăng ký hoặc đổi password, server cần lưu một password verifier. Khi đăng nhập, server nhận password qua kênh bảo mật, chạy cùng quy trình hashing và so sánh với verifier đã lưu.

### 4.1. Password hashing chuyên dụng

Dùng password hashing function được thiết kế để chống dò password offline, ví dụ Argon2id. Các lựa chọn khác có thể gồm scrypt, bcrypt hoặc PBKDF2 trong môi trường có yêu cầu tương thích/compliance. Chọn thuật toán theo hướng dẫn bảo mật hiện hành, khả năng thư viện và yêu cầu hệ thống; không tự viết hàm hash.

Password hash cần có:
- **Salt ngẫu nhiên, riêng cho mỗi password:** ngăn hai tài khoản cùng password có cùng verifier và làm giảm hiệu quả precomputed lookup.
- **Work factor/cost:** khiến mỗi lần thử password tốn tài nguyên đáng kể; với Argon2id còn có memory cost và parallelism.
- **Thông tin thuật toán và tham số:** lưu cùng verifier để có thể nâng cấp cấu hình trong tương lai.
- **So sánh an toàn:** dùng API xác minh của thư viện; tránh tự viết so sánh dễ mắc lỗi.
- **Rehash khi cần:** sau khi xác minh password thành công, có thể nâng tham số nếu verifier dùng cấu hình cũ.

Salt không phải bí mật. Nó có thể lưu cùng password hash. Salt phải được tạo bằng CSPRNG và không tái sử dụng tùy tiện giữa các password.

Ví dụ định dạng lưu password verifier:

~~~text
account_id
password_hash = encoded_argon2id_verifier
password_changed_at
password_hash_updated_at
~~~

Định dạng encoded verifier thường bao gồm tên thuật toán, tham số, salt và kết quả. Hãy dùng thư viện có khả năng parse và verify format đó; không tự cắt chuỗi để đoán tham số.

### 4.2. Vì sao không dùng SHA-256 đơn thuần cho password?

SHA-256 là hash mật mã nhanh, phù hợp cho nhiều mục đích toàn vẹn và fingerprint, nhưng quá nhanh khi dùng trực tiếp để lưu password. Kẻ tấn công có bản sao database có thể thử số lượng password lớn với tốc độ cao. Password hashing function chuyên dụng làm mỗi lần thử tốn thời gian và/hoặc bộ nhớ hơn, nâng chi phí dò offline.

Không dùng:
- SHA-256(password) đơn thuần.
- MD5 hoặc SHA-1 để lưu password.
- Password + salt tự ghép rồi hash bằng một vòng nhanh.
- Một salt cố định dùng cho mọi tài khoản.
- Mã hóa reversible password để “có thể gửi lại password cho người dùng”.

Nếu người dùng quên password, dùng quy trình reset/recovery đã xác minh. Không có lý do hợp lệ để support staff đọc lại password gốc.

### 4.3. Pepper

Pepper là secret bổ sung dùng trong quy trình password verification, được giữ tách khỏi password database, ví dụ trong KMS/HSM hoặc secret manager. Nếu triển khai pepper:
- Không lưu pepper trong cùng database với verifier.
- Hạn chế service identity được phép dùng pepper.
- Có kế hoạch versioning và rotation.
- Hiểu cách xử lý password verifier cũ trong thời gian chuyển pepper.
- Không tự thiết kế scheme mật mã; dùng hướng dẫn của thư viện/kiến trúc đã được đánh giá.

Pepper không thay thế salt, password hashing function, rate limiting hay MFA. Nếu pepper bị lộ cùng database, lợi ích bổ sung có thể mất.

### 4.4. Cấu hình cost và nâng cấp

Không có một con số tham số phù hợp cho mọi hệ thống. Hãy benchmark trên production-like hardware, chọn mức cost phù hợp latency và capacity, rồi kiểm tra khả năng chống DoS khi nhiều login request đồng thời. Đặt giới hạn kích thước input và rate limit trước hoặc quanh thao tác hashing để tránh attacker làm cạn CPU/RAM.

Khi cấu hình hash được nâng cấp:
1. Người dùng đăng nhập bằng password.
2. Server verify bằng tham số đã lưu.
3. Nếu tham số cũ yếu hơn policy hiện tại, server hash lại password với cấu hình mới.
4. Cập nhật verifier nguyên tử.
5. Ghi metadata version, không ghi password.

## 5. Lưu bearer token, session ID và API key

Token ngẫu nhiên có entropy cao khác password. Nếu server chỉ cần xác minh token được client gửi, có thể lưu hash/fingerprint thay vì raw token.

### 5.1. Refresh token và session ID

Một thiết kế thường dùng:
- Sinh token bằng CSPRNG với entropy cao.
- Chỉ hiển thị/cấp raw token cho client đúng một lần.
- Lưu hash hoặc keyed fingerprint cùng metadata cần thiết.
- Khi nhận token, tính fingerprint rồi tra record.
- Kiểm tra issuer/client/subject/scope/expiry/revoked state và token family.
- Khi rotate, đánh dấu token cũ đã dùng hoặc revoked; cấp token mới và cập nhật lineage.
- Không ghi raw token vào log, audit hoặc exception.

Nếu hệ thống cần gửi lại token cho một thành phần khác sau khi cấp, hash-only không đủ; hãy đánh giá liệu có thể chuyển token trực tiếp trong transaction hay cần mã hóa secret ở server-side vault.

### 5.2. API key

API key thường có phần prefix/public identifier và phần secret ngẫu nhiên. Prefix giúp tìm record mà không phải thử hash mọi key; secret dùng làm bearer credential.

Ví dụ định dạng minh họa:

~~~text
sh_live_<public-prefix>.<random-secret>
~~~

Database có thể lưu:
- key ID hoặc prefix.
- owner/service account.
- hash của secret.
- scopes/permissions.
- created_at, expires_at, last_used_at, revoked_at.
- allowed environment hoặc metadata ràng buộc nếu có.

Chỉ hiển thị raw API key lúc tạo. Nếu người dùng mất key, tạo key mới và thu hồi key cũ; không cung cấp nút xem lại secret đã lưu hash. Mỗi integration nên có key riêng để thu hồi và audit độc lập. Tránh dùng chung một key cho nhiều service, người dùng hoặc môi trường.

### 5.3. Hash hay HMAC fingerprint?

Với token đủ ngẫu nhiên, hash mật mã chuẩn thường đủ để lưu verifier. HMAC với pepper/key ngoài database có thể giảm khả năng đối chiếu khi database bị lộ, nhưng thêm phụ thuộc key management. Chọn một phương án nhất quán, có version và khả năng rotation. Không dùng hash nhanh cho password; không dùng password hash chậm cho token ngẫu nhiên trừ khi có lý do cụ thể.

## 6. Secret cần dùng lại: mã hóa có xác thực

Một số secret phải được khôi phục để server sử dụng: TOTP seed, OAuth client secret, shared key hoặc private configuration. Với các trường hợp này, lưu hash không đáp ứng được yêu cầu. Cần mã hóa bằng thuật toán authenticated encryption qua thư viện đã được kiểm chứng, và quản lý encryption key tách khỏi database.

### 6.1. Encryption at rest và authenticated encryption

Mã hóa có xác thực cung cấp cả confidentiality và integrity. Nếu ciphertext bị sửa, thao tác giải mã phải thất bại thay vì trả dữ liệu không đáng tin cậy.

Dùng thư viện chuẩn với thuật toán authenticated encryption hiện hành như AES-GCM hoặc ChaCha20-Poly1305 theo môi trường và hướng dẫn triển khai. Không tự chế mode mã hóa, padding, nonce generation hay key derivation. Nonce/IV phải tuân thủ yêu cầu duy nhất theo từng key và giới hạn của thuật toán.

Mỗi encrypted record nên lưu metadata cần để giải mã:
- ciphertext.
- nonce/IV.
- authentication tag nếu format không gộp chung.
- key ID hoặc key version.
- algorithm/version identifier.
- associated data reference nếu có.

Không lưu encryption key cạnh ciphertext trong cùng database hoặc cùng backup. Nếu attacker lấy được cả hai, mã hóa at rest không còn bảo vệ dữ liệu.

### 6.2. Envelope encryption

Envelope encryption dùng một Data Encryption Key (DEK) để mã hóa dữ liệu; DEK được mã hóa/wrap bởi Key Encryption Key (KEK) do KMS/HSM quản lý.

~~~mermaid
flowchart LR
    A[Secret plaintext] --> B[DEK]
    B --> C[Authenticated encryption]
    C --> D[Ciphertext + nonce + tag]
    B --> E[Wrap DEK]
    E --> F[KMS / HSM KEK]
    D --> G[(Credential DB)]
    E --> G
    F -. unwrap only for authorized workload .-> E
~~~

Luồng tổng quát:
1. Workload được cấp quyền yêu cầu KMS tạo hoặc dùng DEK.
2. DEK mã hóa secret bằng authenticated encryption.
3. DEK được wrap bằng KEK.
4. Database lưu ciphertext, nonce/tag, wrapped DEK và key version.
5. Khi cần sử dụng, workload có identity hợp lệ yêu cầu KMS unwrap DEK.
6. Workload giải mã trong memory, dùng secret và loại bỏ plaintext khi không còn cần.

Lợi ích: có thể rotate KEK bằng cách rewrap DEK mà không phải mã hóa lại mọi payload, tùy khả năng KMS. Nhưng plaintext vẫn xuất hiện trong memory của workload trong lúc sử dụng; quyền truy cập runtime phải được bảo vệ.

### 6.3. Associated data

Authenticated encryption có thể gắn associated data (AAD) không được mã hóa nhưng được xác thực, ví dụ credential ID, tenant ID, secret type hoặc schema version. Khi giải mã, AAD phải giống dữ liệu lúc mã hóa; nếu record bị chuyển sang tenant khác hoặc bị thay metadata, authentication sẽ thất bại.

Không đưa secret hoặc PII nhạy cảm vào AAD với kỳ vọng nó được mã hóa. AAD thường có thể nhìn thấy trong storage hoặc protocol.

## 7. KMS, HSM và quản lý khóa

KMS/HSM quản lý key material và thực hiện một số thao tác mật mã theo policy. Chúng không tự động làm hệ thống an toàn nếu mọi service đều có quyền decrypt mọi secret.

### 7.1. Phân biệt

- **KMS:** dịch vụ quản lý khóa, policy, key version, audit và thao tác mã hóa/giải mã/signing.
- **HSM:** phần cứng bảo mật được thiết kế để bảo vệ key material và thực hiện thao tác mật mã trong ranh giới phần cứng.
- **Secret manager:** kho lưu trữ và phân phối secret như database password, API credential, certificate hoặc config nhạy cảm.
- **Secure Enclave/Android Keystore:** cơ chế nền tảng thiết bị bảo vệ key và có thể cung cấp thao tác mật mã gắn với thiết bị.

Một sản phẩm có thể kết hợp nhiều vai trò. Cần đọc mô hình bảo mật và giới hạn của dịch vụ cụ thể, không chỉ dựa tên sản phẩm.

### 7.2. Key hierarchy và tách quyền

Thiết kế key hierarchy rõ:
- Root/master key được bảo vệ trong KMS/HSM.
- KEK dùng wrap DEK.
- DEK dùng mã hóa dữ liệu hoặc nhóm record.
- Key dùng ký token/certificate có purpose và scope riêng.
- Key development, staging và production tách biệt.

Áp dụng separation of duties:
- Database operator không mặc nhiên có quyền decrypt.
- Application runtime chỉ được gọi key operation cần thiết.
- Nhóm quản trị key không cần quyền đọc dữ liệu nghiệp vụ.
- Break-glass access phải có phê duyệt, thời hạn và audit.
- Không chia sẻ một key cho encryption, signing và mọi môi trường nếu có thể tách purpose.

### 7.3. Key lifecycle

Key có vòng đời:
1. Generate hoặc import theo quy trình được kiểm soát.
2. Activate và gắn purpose, owner, environment, algorithm và policy.
3. Distribute qua KMS/identity mechanism; hạn chế export.
4. Use với least privilege và audit.
5. Rotate theo lịch hoặc sự kiện compromise.
6. Disable/deactivate khi không còn cấp mới.
7. Re-encrypt/rewrap dữ liệu cần thiết.
8. Revoke/destroy theo retention và recovery policy.

Không xóa key cũ trước khi biết dữ liệu nào còn cần giải mã. Nếu phá hủy key trước thời hạn, backup có thể trở thành dữ liệu không thể khôi phục. Ngược lại, giữ key vô thời hạn làm tăng hậu quả nếu key bị lộ. Cần quy trình retention, legal hold và destruction được phê duyệt.

## 8. Lưu TOTP seed, recovery code và MFA credential

TOTP verifier cần shared secret để tính mã theo thời gian, vì vậy server phải bảo vệ seed theo cách có thể sử dụng lại. Không lưu seed dạng rõ trong database.

### 8.1. TOTP seed

Khi người dùng enroll TOTP:
1. Server sinh seed bằng CSPRNG.
2. Chỉ hiển thị QR/provisioning URI trong flow enrollment được xác thực.
3. Người dùng quét bằng authenticator app.
4. Server xác minh một mã TOTP hợp lệ trước khi kích hoạt MFA.
5. Server mã hóa seed bằng envelope encryption và lưu key version.
6. Server hạn chế service identity được phép giải mã seed.
7. Khi người dùng thay MFA device hoặc account recovery, áp dụng quy trình revoke/rotate seed.

TOTP seed là shared secret; nếu attacker lấy được seed, họ có thể tự tạo mã trong cửa sổ thời gian hợp lệ. Không ghi QR code, provisioning URI hoặc seed vào log, analytics, support ticket hay screenshot. Không hiển thị seed lại sau khi enrollment hoàn tất trừ khi có quy trình re-enrollment an toàn.

### 8.2. Recovery code

Recovery code nên:
- Có entropy đủ cao, tạo ngẫu nhiên bằng CSPRNG.
- Được hiển thị một lần khi tạo.
- Lưu verifier dạng hash; không cần lưu raw code.
- Dùng một lần và đánh dấu consumed nguyên tử.
- Có khả năng rotate cả bộ khi người dùng yêu cầu hoặc có nghi ngờ lộ.
- Gửi thông báo khi recovery code được sử dụng nếu policy cho phép.

Không dùng recovery code ngắn, tuần tự hoặc dựa trên thông tin cá nhân. Rate limit và giám sát việc thử mã.

### 8.3. WebAuthn/passkey

Trong WebAuthn, server lưu credential ID, public key, sign counter/metadata và liên kết tài khoản theo protocol. Private key được giữ bởi authenticator/platform authenticator; server không nhận và không lưu private key của passkey.

Điều này là ví dụ rõ về nguyên tắc **lưu đúng phía**:
- Server lưu public key để xác minh assertion.
- Authenticator giữ private key để ký.
- Client không tự xuất private key chỉ để server lưu.
- Biometric hoặc PIN mở khóa authenticator theo cơ chế nền tảng; server nhận assertion, không nhận biometric template.

## 9. Private key và certificate

Private key và certificate thường đi cùng nhau nhưng có vai trò khác nhau:
- Private key là bí mật dùng ký hoặc giải mã.
- Public key có thể chia sẻ.
- Certificate là cấu trúc được CA ký để ràng buộc public key với danh tính/thuộc tính theo policy.

### 9.1. Lưu private key

Ưu tiên:
- HSM hoặc cloud KMS signing operation cho server-side key.
- Secure Enclave/Keychain hoặc Android Keystore cho key gắn với thiết bị.
- Non-exportable key khi ứng dụng chỉ cần ký và nền tảng hỗ trợ.
- Key purpose tách riêng, không dùng chung key signing và encryption nếu không có thiết kế rõ.
- Access control, user presence hoặc biometric gating cho thao tác nhạy cảm khi phù hợp.

Nếu private key phải export để backup/migration, cần quy trình mã hóa, kiểm soát người nhận, retention và audit. Không gửi private key qua email/chat hoặc lưu vào source repository.

### 9.2. Certificate storage

Certificate public có thể lưu trong database hoặc filesystem vì bản thân certificate không phải secret. Tuy vậy, cần:
- Kiểm tra chain, issuer, validity, key usage và extended key usage.
- Theo dõi expiry và renewal.
- Liên kết certificate với private key reference đúng.
- Kiểm tra revocation/status theo policy và khả năng hệ thống.
- Không coi certificate còn hạn là đủ để xác minh mọi request; vẫn phải kiểm tra trust chain, purpose, identity mapping và authorization.

Không nhầm certificate với private key file. Một bundle/container có thể chứa cả certificate và private key; cần xác định nội dung trước khi lưu hoặc phân phối.

## 10. Credential storage trên mobile và browser

### 10.1. iOS

Dùng Keychain Services để lưu credential/secret phù hợp. Chọn accessibility class theo yêu cầu khóa thiết bị, background access và UX. Cân nhắc non-synchronizable item cho credential gắn với thiết bị. Với key pair, ưu tiên Secure Enclave nếu loại key và API hỗ trợ.

Không lưu token dạng rõ trong UserDefaults, plist, file log, cache không bảo vệ hoặc pasteboard. Không giả định gỡ app chắc chắn xóa Keychain item; thiết kế account removal và credential cleanup riêng.

### 10.2. Android

Dùng Android Keystore để bảo vệ key material. Ứng dụng có thể tạo key trong Keystore rồi dùng key mã hóa secret lưu trong app-private storage. Ưu tiên hardware-backed/StrongBox khi thiết bị hỗ trợ và policy cần. Cấu hình backup/data extraction để credential không bị sao chép ngoài ý muốn; kiểm tra hành vi restore khi cài lại hoặc đổi thiết bị.

Keystore bảo vệ key, không tự động làm mọi dữ liệu app trở thành hardware-protected. Plaintext token vẫn có thể xuất hiện trong process memory khi app cần sử dụng.

### 10.3. Browser và web application

Với session-based web app:
- Dùng cookie xác thực HttpOnly, Secure và SameSite phù hợp.
- Lưu session state ở server-side store nếu cần revoke tập trung.
- Không đặt long-lived bearer token vào localStorage chỉ vì dễ truy cập từ JavaScript.
- Nếu dùng BFF, browser giữ cookie session; backend giữ OAuth token và quản lý server-side.
- Bảo vệ CSRF, XSS, cookie scope và logout.
- Không gửi credential trong URL query string.

Nếu kiến trúc buộc browser giữ token, cần threat model cụ thể, thời hạn ngắn, kiểm soát XSS, rotation và storage phù hợp. Không có một storage API browser nào biến bearer token thành không thể bị sử dụng bởi script độc hại đang chạy cùng origin.

## 11. Secret manager và runtime configuration

Secret manager giúp tách secret khỏi source code và artifact. Workload nên lấy secret bằng identity ngắn hạn hoặc cơ chế workload identity thay vì dùng một master credential cố định.

### 11.1. Nguyên tắc

- Không hardcode secret trong source, test fixture, Docker image hoặc package.
- Không commit file .env thật vào repository.
- Tách secret theo service, environment, tenant và purpose.
- Dùng workload identity/short-lived credential khi có thể.
- Cấp secret đúng runtime, đúng service và đúng thời gian cần thiết.
- Không cấp quyền list/read toàn bộ secret store cho mọi developer hoặc workload.
- Rotate secret khi nhân sự, service, môi trường hoặc threat model thay đổi.
- Có audit cho read, write, version, disable và delete.
- Tránh truyền secret qua command line argument vì có thể lộ trong process listing/history.
- Không in secret vào build output hoặc deployment logs.

### 11.2. Environment variable có đủ an toàn không?

Environment variable có thể hữu ích trong một số runtime nhưng không phải secret manager. Giá trị có thể bị lộ qua process inspection, crash dump, diagnostics, child process hoặc cấu hình deploy. Nếu dùng:
- Giới hạn ai được xem process/config.
- Tránh dump environment vào log.
- Hạn chế lifetime và scope.
- Ưu tiên file mount có permission chặt hoặc secret retrieval qua workload identity nếu nền tảng hỗ trợ.
- Không để secret tồn tại trong build artifact hoặc image layer.

Không có cách phân phối secret tuyệt đối an toàn cho process cần dùng secret. Mục tiêu là thu hẹp quyền, giảm lifetime, audit và có khả năng rotate/revoke.

### 11.3. CI/CD

Pipeline cần:
- Lấy secret từ secret manager bằng identity được cấp theo job/repository/environment.
- Ưu tiên short-lived federation/OIDC thay cho static cloud access key.
- Không chạy job untrusted pull request với quyền đọc production secret.
- Mask/redact output nhưng không dựa vào masking như biện pháp duy nhất.
- Tách deployment approval và secret access theo môi trường.
- Thu hồi credential của runner/job sau khi hoàn tất.
- Scan repository/history và artifact để phát hiện secret lỡ commit.

Nếu phát hiện secret đã commit, xóa dòng khỏi source không đủ: phải revoke/rotate secret và đánh giá lịch sử Git, fork, cache, artifact và log đã bị lộ.

## 12. Access control, audit và data minimization

Một kho credential an toàn phải kiểm soát cả dữ liệu lẫn thao tác:
- **Least privilege:** service chỉ đọc hoặc sử dụng đúng credential cần thiết.
- **Separation of duties:** người vận hành database không mặc nhiên có quyền giải mã secret.
- **Tenant isolation:** credential của tenant này không thể tra cứu hoặc sử dụng cho tenant khác.
- **Purpose binding:** key dùng signing không được dùng để encrypt tùy tiện.
- **Short-lived access:** workload identity và credential truy cập kho nên có thời hạn ngắn.
- **Audit:** ghi actor/workload, secret reference, operation, thời điểm, kết quả và policy; không ghi raw secret.
- **Alerting:** phát hiện truy cập hàng loạt, bất thường theo service, giờ hoặc vùng.
- **Data minimization:** chỉ lưu credential và metadata thực sự cần thiết.

Audit event nên dùng secret ID/fingerprint không thể đảo ngược thành raw credential. Cần bảo vệ audit log khỏi sửa/xóa trái phép, giới hạn quyền truy vấn và đặt retention phù hợp.

## 13. Backup, replication và disaster recovery

Backup có thể trở thành đường rò rỉ credential bị bỏ quên. Nếu database mã hóa secret nhưng backup chứa snapshot plaintext, mục tiêu bảo mật đã thất bại.

Thiết kế cần:
1. Mã hóa backup bằng key riêng hoặc policy KMS phù hợp.
2. Giới hạn quyền tạo, tải, restore và xóa backup.
3. Tách quyền database và quyền decrypt backup.
4. Mã hóa replica và log shipping nếu chứa dữ liệu credential.
5. Quản lý key version để dữ liệu cũ vẫn giải mã được trong retention period.
6. Kiểm thử restore trong môi trường cách ly.
7. Sau restore, kiểm tra revoked credential không bị hồi sinh.
8. Không dùng dữ liệu production chứa secret thật trong môi trường dev/test nếu không có quy trình masking/rotation.
9. Đặt retention và destruction cho cả backup, replica, export và archive.

Điểm quan trọng: restore một snapshot cũ có thể đưa token đã revoke hoặc recovery code đã dùng trở lại trạng thái active nếu state revocation không được đồng bộ. Cần thiết kế tombstone/revocation ledger hoặc đối soát với nguồn trạng thái hiện hành sau restore.

## 14. Rotation, revocation và destruction

Credential lifecycle nên được mô hình hóa rõ:

~~~mermaid
stateDiagram-v2
    [*] --> Provisioned
    Provisioned --> Active: Bind to owner / activate
    Active --> Rotating: Scheduled or event-based rotation
    Rotating --> Active: New credential verified and committed
    Active --> Revoked: Logout / compromise / owner request
    Rotating --> Revoked: Rotation failure or compromise
    Revoked --> Retained: Audit / recovery retention
    Retained --> Destroyed: Retention expires and approval
    Destroyed --> [*]
~~~

### 14.1. Rotation

Rotation có thể xảy ra:
- Theo lịch dựa trên risk và policy.
- Khi nghi ngờ hoặc xác nhận credential bị lộ.
- Khi nhân sự/service owner rời vai trò.
- Khi thay đổi tenant, client, environment hoặc quyền.
- Khi key algorithm/parameter không còn phù hợp.
- Khi certificate sắp hết hạn.

Rotation an toàn cần overlap có kiểm soát:
1. Tạo credential mới.
2. Phân phối cho workload được phép.
3. Xác minh credential mới hoạt động.
4. Chuyển workload sang credential mới.
5. Theo dõi việc sử dụng credential cũ.
6. Revoke credential cũ.
7. Xóa bản sao cũ theo retention policy.

Không rotate tất cả secret cùng lúc nếu điều đó có thể gây outage; cần rollout theo service/tenant và có rollback an toàn. Tuy nhiên, khi có compromise thực sự, ưu tiên containment và revoke nhanh hơn tính liên tục nếu threat model yêu cầu.

### 14.2. Revocation

Revocation phải được kiểm tra ở điểm sử dụng. Việc đánh dấu credential revoked trong database không đủ nếu service cache trạng thái vô thời hạn. Xác định:
- Thời gian propagation tới mọi verifier/resource server.
- TTL cache tối đa.
- Hành vi khi kho credential hoặc KMS unavailable.
- Cơ chế invalidate cache/event.
- Cách xử lý request đang chạy.
- Cách ngăn refresh/session cũ tái kích hoạt credential.

### 14.3. Destruction

Khi hết retention, xóa ciphertext, wrapped key, replicas, exports và bản backup theo policy. Với envelope encryption, crypto-shredding bằng cách hủy key có thể làm dữ liệu không thể giải mã, nhưng phải chắc chắn không còn bản key/backup hợp lệ và đã xử lý nghĩa vụ retention. Hủy key không thay thế xóa metadata hoặc kiểm tra bản sao ngoài hệ thống.

## 15. Threat model: các kiểu lộ credential thường gặp

| Mối đe dọa | Tác động | Biện pháp chính |
| --- | --- | --- |
| Database dump bị đánh cắp | Password hash, token verifier hoặc encrypted secret bị lộ | Password hashing đúng; hash token entropy cao; envelope encryption; tách KMS và DB permission. |
| Secret commit trong Git | Credential có thể bị sao chép lâu dài | Secret scanning, short-lived credential, revoke/rotate ngay, rà soát history/artifact. |
| Log/crash dump chứa token | Người có quyền đọc log có thể replay token | Redaction ở nguồn, không log header/body, hạn chế dump và truy cập telemetry. |
| Backup không mã hóa | Credential có thể lộ ngoài production | Backup encryption, access separation, restore test và retention. |
| Workload có quyền đọc mọi secret | Lateral movement và blast radius lớn | Workload identity, per-service secret scope, least privilege. |
| Key manager policy quá rộng | Có thể decrypt/sign hàng loạt | Tách key, policy theo operation/resource, approval và audit. |
| Mobile device mất hoặc root | Token/secret trên thiết bị có nguy cơ bị lấy hoặc sử dụng | Keychain/Keystore, non-exportable key, device revoke, short lifetime và risk controls. |
| Insider misuse | Credential bị đọc hoặc sử dụng sai mục đích | Separation of duties, JIT access, audit độc lập và alert. |
| Restore backup cũ | Token revoked hoặc recovery code used có thể sống lại | Revocation ledger, post-restore reconciliation và version/state check. |
| Rotation không đồng bộ | Outage hoặc credential cũ vẫn hoạt động | Staged rollout, overlap có thời hạn, verify và revoke có kiểm soát. |
| Plaintext trong memory | Process compromise có thể lấy credential đang dùng | Giảm lifetime, giảm quyền process, tránh copy thừa, isolate workload. |
| TOTP seed hoặc QR lộ | Attacker tạo được OTP hợp lệ | Encrypt seed, enrollment one-time, không log/hiển thị lại, re-enroll và revoke. |

### 15.1. Credential stuffing và password database theft

Credential stuffing dùng password đã lộ từ dịch vụ khác để thử đăng nhập. Đây là vấn đề xác thực và kiểm soát lạm dụng, nhưng credential storage cũng ảnh hưởng hậu quả nếu database bị lấy:
- Password hashing chậm làm tăng chi phí dò offline.
- MFA và passkey giảm phụ thuộc vào password đơn lẻ.
- Rate limiting và breached-password screening giảm lạm dụng online.
- Không lưu password gốc hoặc password reversible.
- Reset/recovery cần chống takeover và không tiết lộ trạng thái tài khoản.

## 16. Pseudocode và schema minh họa

Các ví dụ sau chỉ mô tả luồng. Dùng thư viện password hashing, crypto provider, KMS SDK và secret manager đã được kiểm chứng; không tự viết primitive mật mã.

### 16.1. Lưu password verifier

~~~text
registerPassword(accountId, password):
    validatePasswordPolicy(password)
    salt = secureRandomSalt()
    verifier = passwordHashingLibrary.hash(
        password,
        algorithm = currentPasswordHashPolicy,
        salt = salt
    )
    storePasswordVerifier(
        accountId,
        encodedVerifier = verifier,
        changedAt = now()
    )
~~~

Khi đăng nhập:

~~~text
verifyPassword(accountId, candidate):
    record = loadPasswordVerifier(accountId)
    if record is missing:
        performEquivalentWorkIfNeeded()
        rejectGenericAuthenticationFailure()

    valid = passwordHashingLibrary.verify(
        encodedVerifier = record.encodedVerifier,
        candidate = candidate
    )

    if not valid:
        rejectGenericAuthenticationFailure()

    if needsRehash(record.encodedVerifier, currentPasswordHashPolicy):
        updated = passwordHashingLibrary.hash(candidate, currentPasswordHashPolicy)
        compareAndSwapVerifier(accountId, expectedVersion=record.version, updated)

    acceptAuthentication
~~~

Không lưu candidate, raw password hoặc encoded verifier vào application log. Generic failure giúp giảm account enumeration; rate limit và risk detection vẫn cần thiết.

### 16.2. Lưu shared secret bằng envelope encryption

~~~text
storeReusableSecret(secretId, plaintext, purpose, tenantId):
    assert callerMayCreateSecret(purpose, tenantId)

    dataKey, wrappedDataKey, keyVersion = kms.generateDataKey(
        keyEncryptionKey = configuredKek,
        encryptionContext = {
            "secretId": secretId,
            "purpose": purpose,
            "tenantId": tenantId
        }
    )

    nonce = cryptoProvider.generateNonce(dataKey)
    aad = encode(secretId, purpose, tenantId, schemaVersion)

    ciphertext, tag = cryptoProvider.authenticatedEncrypt(
        key = dataKey,
        nonce = nonce,
        plaintext = plaintext,
        associatedData = aad
    )

    store(
        secretId,
        ciphertext,
        nonce,
        tag,
        wrappedDataKey,
        keyVersion,
        purpose,
        tenantId,
        schemaVersion
    )

    clearSensitiveMemoryBestEffort(dataKey, plaintext)
~~~

Khi sử dụng:

~~~text
useReusableSecret(secretId, requestedOperation):
    record = loadSecretRecord(secretId)
    authorizeWorkload(currentIdentity, record.purpose, requestedOperation)

    dataKey = kms.unwrapDataKey(
        record.wrappedDataKey,
        keyVersion = record.keyVersion,
        encryptionContext = record.expectedContext
    )

    plaintext = cryptoProvider.authenticatedDecrypt(
        key = dataKey,
        nonce = record.nonce,
        ciphertext = record.ciphertext,
        tag = record.tag,
        associatedData = record.expectedAssociatedData
    )

    result = performOnlyAuthorizedOperation(plaintext)
    clearSensitiveMemoryBestEffort(dataKey, plaintext)
    audit(secretReference=secretId, operation=requestedOperation, result=result)
    return result
~~~

Việc xóa plaintext khỏi memory chỉ là best effort trong managed runtime; garbage collector, copy-on-write, crash dump hoặc runtime internals có thể giữ bản sao. Tốt hơn là giảm số lần copy, giới hạn process access và dùng thao tác KMS/HSM trực tiếp nếu không cần export private key.

### 16.3. Schema metadata gợi ý

| Field | Ý nghĩa | Có phải secret? |
| --- | --- | --- |
| credential_id | ID nội bộ | Không, nhưng cần kiểm soát truy cập. |
| subject_id / owner_id | Chủ sở hữu credential | Dữ liệu định danh, cần bảo vệ. |
| credential_type | password_verifier, refresh_token, totp_seed, api_key... | Không. |
| verifier_hash | Hash token/password verifier | Không phải raw secret; vẫn nhạy cảm. |
| ciphertext | Secret đã mã hóa | Có giá trị nhạy cảm. |
| nonce / tag | Metadata authenticated encryption | Không phải key; cần integrity và format đúng. |
| wrapped_dek | DEK đã được wrap | Nhạy cảm, chỉ dùng cùng KMS policy. |
| key_version | Phiên bản KEK | Không. |
| scopes / purpose | Quyền và mục đích sử dụng | Không, nhưng quan trọng với authorization. |
| created_at / expires_at | Vòng đời | Không. |
| last_used_at | Theo dõi sử dụng | Không. |
| revoked_at / status | Trạng thái | Không. |
| version / generation | Chống ghi đè/race | Không. |

Không tạo một bảng generic cho mọi credential nếu điều đó làm lẫn semantics. Password verifier, encrypted shared secret, public key và token verifier có thể cần schema, index, access policy và lifecycle khác nhau.

## 17. Bài thực hành: thiết kế Credential storage cho StudyHub

**Bối cảnh:** StudyHub có web app, mobile app, Course API và trang quản trị. Người dùng đăng nhập bằng password hoặc passkey; một số tài khoản dùng TOTP MFA. Mobile app dùng refresh token. Một số đối tác tích hợp qua API key. Backend có OAuth client secret và private key dùng ký một số assertion. Dữ liệu credential nằm trong database dùng chung, workload chạy trên nhiều instance và có backup định kỳ.

Hãy thiết kế storage đáp ứng:
1. Password chỉ được lưu dưới dạng password verifier bằng thuật toán chuyên dụng.
2. Refresh token và API key được lưu verifier/hash khi server chỉ cần xác minh.
3. TOTP seed và OAuth client secret được mã hóa bằng envelope encryption.
4. Private key được giữ trong KMS/HSM hoặc vùng bảo vệ phù hợp, không export nếu không cần.
5. Passkey server-side chỉ lưu public key và credential metadata.
6. Mobile refresh token được lưu trong secure storage của hệ điều hành.
7. Mỗi service chỉ có quyền đọc/giải mã credential đúng purpose.
8. Database operator không mặc nhiên có quyền decrypt.
9. Backup, log, CI/CD và telemetry không chứa raw credential.
10. Rotation/revocation có thể lan truyền tới mọi instance và không hồi sinh credential cũ khi restore.
11. Có quy trình xử lý credential bị lộ và audit.
12. Có thể thay đổi password hashing parameters hoặc KEK mà không làm mất khả năng xác minh/giải mã dữ liệu còn hợp lệ.

### 17.1. Quyết định thiết kế cần ghi lại

- Danh mục credential và cách sử dụng của từng loại.
- Cách lưu verifier, hash, ciphertext hoặc key reference.
- Password hashing algorithm, salt, cost và rehash policy.
- Token entropy, hash/HMAC strategy và token family reference.
- TOTP seed encryption, enrollment và recovery flow.
- Key hierarchy, KMS/HSM policy, DEK/KEK version và rotation.
- Workload identity, service-to-secret mapping và least privilege.
- Mobile Keychain/Keystore, backup và device revocation.
- Log redaction, audit schema và retention.
- Backup/restore, revocation ledger và disaster recovery.
- Incident response cho password DB dump, token leak, client secret leak và private key compromise.

### 17.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Đăng ký password | Database chỉ chứa password verifier; không có password gốc. |
| Hai tài khoản dùng cùng password | Salt riêng làm verifier khác nhau. |
| Password hash dùng SHA-256 đơn thuần | Security test từ chối cấu hình. |
| Password verifier cũ dùng cost thấp | Đăng nhập thành công có thể trigger rehash theo policy. |
| Password nhập sai | Không lộ password, verifier hoặc account enumeration qua lỗi chi tiết. |
| Password database dump | Không có raw password; verifier dùng algorithm/parameters đã phê duyệt. |
| Pepper bị thiếu hoặc KMS unavailable | Hệ thống xử lý lỗi an toàn, không fallback sang scheme yếu. |
| Refresh token được lưu | Chỉ verifier/hash hoặc encrypted form theo nhu cầu thực; raw token không xuất hiện trong DB/log ngoài policy. |
| API key tạo mới | Secret chỉ hiển thị một lần; database lưu verifier và metadata. |
| API key đã revoke | Mọi verifier/resource server từ chối trong SLA đã xác định. |
| TOTP enrollment | Seed chỉ hiển thị trong enrollment flow; server lưu ciphertext. |
| TOTP seed ciphertext bị sửa | Authenticated decryption thất bại. |
| TOTP seed bị lộ | Có thể revoke/rotate MFA credential và yêu cầu re-enrollment. |
| Recovery code dùng lần hai | Lần thứ hai bị từ chối; consumed state được commit nguyên tử. |
| Passkey registration | Server lưu public key/credential ID; không nhận private key hoặc biometric template. |
| Private key signing | Workload được phép gọi signing operation; không thể export key nếu policy non-exportable. |
| Certificate hết hạn | Renewal/alert được kích hoạt; certificate không được tin chỉ vì còn trong store. |
| DB operator đọc ciphertext | Không thể tự decrypt nếu không có quyền KMS riêng. |
| Workload service A đọc secret của service B | Authorization bị từ chối và có audit event. |
| Secret xuất hiện trong Git hoặc build log | Secret scanning phát hiện; quy trình revoke/rotate được kích hoạt. |
| Secret xuất hiện trong crash report | Test thất bại; redaction/diagnostics phải loại bỏ. |
| Backup chứa credential | Backup được mã hóa, access tách biệt và restore test thành công. |
| Restore snapshot cũ | Revoked token/recovery code không được hồi sinh. |
| Rotate KEK | DEK được rewrap hoặc dữ liệu được migrate; secret hợp lệ vẫn dùng được. |
| Revoke credential trong cache | Tất cả instance từ chối theo SLA propagation. |
| KMS outage | Hệ thống không fallback sang plaintext hoặc key hardcoded. |
| CI job từ pull request không tin cậy | Không đọc được production secret. |
| Device mất | Session/token/device key được revoke theo đúng phạm vi. |
| Audit event | Có reference, actor, operation và kết quả; không có raw credential. |
| Log redaction | Authorization header, Cookie, token body, password và private key không xuất hiện. |

### 17.3. Câu hỏi tự đánh giá

1. Khi nào nên hash credential và khi nào cần mã hóa?
2. Vì sao password verifier cần salt và password hashing function chuyên dụng?
3. Pepper khác salt như thế nào và nên lưu ở đâu?
4. Vì sao refresh token ngẫu nhiên có thể lưu hash trong khi TOTP seed thường phải mã hóa?
5. Vì sao private key nên được giữ trong HSM/Keystore nếu chỉ cần ký?
6. Certificate và private key khác nhau thế nào?
7. Passkey server-side lưu public key hay private key?
8. Envelope encryption dùng DEK và KEK ra sao?
9. Database encryption at rest có đủ nếu database operator cũng có quyền decrypt không?
10. Vì sao log, backup và CI/CD cần nằm trong threat model?
11. Restore backup cũ có thể làm sống lại credential revoked như thế nào?
12. Rotation khác revocation và destruction ở điểm nào?
13. Vì sao environment variable không phải secret manager?
14. Khi một API key bị lộ, cần làm gì ngoài xóa dòng key khỏi source?
15. Làm sao chứng minh mỗi workload chỉ có thể dùng credential đúng purpose?

**Tiêu chí hoàn thành:** Người học có thể phân loại credential theo nhu cầu xác minh hoặc sử dụng lại, chọn hashing/encryption/secure hardware đúng trường hợp, mô hình hóa key hierarchy và access policy, thiết kế rotation/revocation/backup, và chứng minh bằng test rằng raw secret không rò rỉ qua database, log, CI/CD hoặc thiết bị.

## 18. Giám sát và ứng phó sự cố

Các chỉ số nên theo dõi:
- Số credential active theo loại, owner, service và environment.
- Tỷ lệ credential sắp hết hạn hoặc đã quá hạn.
- Số lần đọc/giải mã secret theo workload, purpose và key version.
- Số lần KMS/HSM operation thất bại hoặc bất thường.
- Số lần password rehash và tỷ lệ verifier dùng cấu hình cũ.
- Số token/API key bị revoke và thời gian propagation.
- Số lần reuse/replay hoặc credential bị từ chối sau revoke.
- Số secret scanning alert trong repository, artifact và CI output.
- Số lần backup restore và kết quả đối soát revocation.
- Số access request bị policy từ chối.

Khi nghi ngờ credential bị lộ:
1. Xác định loại credential, owner, scope, issuer, service và môi trường bị ảnh hưởng.
2. Chặn đường truy cập đang bị lạm dụng; disable hoặc revoke credential theo phạm vi.
3. Rotate secret/key liên quan và cập nhật workload được phép.
4. Revoke token family/session/certificate/device binding nếu phù hợp.
5. Kiểm tra audit, API activity, logs và backup access trong khoảng thời gian liên quan.
6. Xác định nguồn lộ: Git, log, database, backup, endpoint, device, CI/CD hoặc insider.
7. Loại bỏ bản sao secret khỏi nguồn gây lộ nhưng không coi đó là thay thế cho revoke.
8. Thông báo người dùng/đối tác qua kênh đã xác minh khi dữ liệu hoặc tài khoản bị ảnh hưởng.
9. Kiểm tra cache, replica và restore path không còn chấp nhận credential cũ.
10. Ghi nhận timeline, tác động, quyết định và biện pháp phòng ngừa.

Không xóa audit evidence khi xử lý incident. Hạn chế quyền truy cập evidence và tuân thủ retention. Nếu private signing key bị compromise, cần xem xét các token/assertion/certificate đã ký bằng key đó, rotate trust configuration và thông báo cho bên xác minh theo quy trình.

## 19. Các lỗi thiết kế phổ biến

- **Lưu password dạng rõ hoặc reversible encryption:** tạo khả năng đọc lại password người dùng.
- **Hash password bằng hàm nhanh:** làm dò offline rẻ hơn đáng kể.
- **Dùng chung salt:** giảm tác dụng chống precomputation và correlation.
- **Lưu pepper cùng database:** mất lợi ích tách secret.
- **Hash TOTP seed hoặc client secret:** server không thể sử dụng lại shared secret để xác minh.
- **Mã hóa token có entropy cao dù chỉ cần verify:** tăng phức tạp và quyền decrypt không cần thiết.
- **Lưu API key raw để có thể hiển thị lại:** biến database thành kho bearer credential.
- **Đặt ciphertext và encryption key cạnh nhau:** attacker lấy được cả hai.
- **Một key cho mọi purpose/environment:** tăng blast radius và làm rotation khó.
- **Service có quyền đọc mọi secret:** tạo đường lateral movement.
- **Tin rằng KMS tự giải quyết authorization:** workload vẫn cần policy least privilege.
- **Lưu private key exportable khi không cần:** tăng bề mặt trích xuất.
- **Nhầm certificate với private key:** có thể phân phối nhầm secret.
- **Lưu passkey private key hoặc biometric template phía server:** sai mô hình WebAuthn và tăng rủi ro dữ liệu nhạy cảm.
- **Log request/response để debug:** có thể lộ password, token, seed và key.
- **Không bảo vệ backup/replica:** secret bị lộ ngoài production.
- **Không đồng bộ revocation:** credential đã thu hồi vẫn có thể được chấp nhận.
- **Rotate mà không kiểm tra:** có thể outage hoặc để credential cũ hoạt động vô hạn.
- **Chỉ xóa secret khỏi Git:** secret đã commit vẫn có thể tồn tại trong history, fork, artifact và cache.
- **Không kiểm thử restore:** credential revoked có thể sống lại từ snapshot cũ.

## 20. Tài liệu tham khảo và hướng đọc tiếp

- **NIST SP 800-63B — Digital Identity Guidelines: Authentication and Lifecycle Management:** yêu cầu về password, authenticator và lifecycle.
- **OWASP Password Storage Cheat Sheet:** thuật toán password hashing, salt, pepper và work factor.
- **OWASP Secrets Management Cheat Sheet:** lưu trữ, cấp phát, rotation, access control và audit.
- **OWASP Cryptographic Storage Cheat Sheet:** lựa chọn thuật toán, key management và encryption at rest.
- **OWASP MASVS — Storage:** bảo vệ dữ liệu nhạy cảm trên ứng dụng mobile.
- **RFC 9106 — Argon2 Memory-Hard Function for Password Hashing and Proof-of-Work Applications:** đặc tả Argon2.
- **RFC 6749 / RFC 9700:** OAuth token lifecycle và bảo vệ refresh token.
- **WebAuthn specification:** lưu public key credential và xác minh assertion.
- **Apple Keychain Services documentation:** quản lý credential/key trên iOS.
- **Android Keystore documentation:** tạo và sử dụng key được bảo vệ bởi hệ điều hành/phần cứng.
- **Cloud KMS/HSM documentation của nền tảng triển khai:** key hierarchy, access policy, rotation và audit.

Khi triển khai thật, hãy đối chiếu phiên bản tiêu chuẩn, thư viện và tài liệu nền tảng đang sử dụng. Tham số password hashing, key policy, retention và thời gian rotation phải được benchmark và phê duyệt theo threat model; không sao chép một cấu hình minh họa thành policy production mà không kiểm chứng.

**Kết luận:** Credential storage an toàn bắt đầu từ phân loại đúng credential và chỉ lưu thứ hệ thống thực sự cần. Password được lưu dưới dạng verifier bằng password hashing chuyên dụng; token ngẫu nhiên có thể lưu hash khi chỉ cần xác minh; shared secret phải mã hóa và quản lý khóa tách biệt; private key nên ở vùng bảo vệ không export khi có thể; public key/certificate được lưu theo vai trò xác minh. Least privilege, audit, backup, rotation, revocation và incident response hoàn thiện vòng đời. Bảo vệ database đơn lẻ là chưa đủ nếu credential vẫn có thể rò qua runtime, log, CI/CD, thiết bị hoặc bản sao lưu.

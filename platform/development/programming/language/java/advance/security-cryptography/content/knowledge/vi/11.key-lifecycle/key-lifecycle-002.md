# 11.2. Sinh khóa, cấp phát, lưu trữ, sử dụng, luân chuyển và thu hồi

## Mục tiêu học tập

Kết thúc bài, bạn có thể:

1. Mô tả **vòng đời khóa mật mã** từ hoạch định, sinh khóa, cấp phát, kích hoạt, lưu trữ, sử dụng đến luân chuyển, vô hiệu hóa, thu hồi, lưu trữ lịch sử và hủy bỏ.
2. Phân biệt **khóa dữ liệu (DEK)**, **khóa bọc khóa (KEK)**, **khóa đối xứng**, **khóa riêng/khóa công khai**, chứng thư số và bí mật truy cập; xác định đúng mục đích, chủ sở hữu và quyền của từng khóa.
3. Tạo khóa an toàn bằng Java 17+ với `KeyGenerator`, `KeyPairGenerator` và `SecureRandom`; hiểu giới hạn của `KeyStore`, vai trò của KMS/HSM và nguyên tắc không làm lộ raw key.
4. Thiết kế **key version**, **cryptoperiod**, phân quyền decrypt-only đối với khóa cũ, rotation định kỳ và **emergency rotation** khi nghi ngờ lộ khóa.
5. Giải thích vì sao **disable/revoke**, **delete/destroy**, **re-encrypt**, **rewrap** và **certificate revocation** khác nhau; tránh khiến dữ liệu cũ không thể giải mã hoặc tin nhầm chữ ký của khóa đã bị lộ.
6. Chạy ví dụ Java 17+ mô phỏng sinh hai phiên bản AES key, lưu/đọc lại `PKCS12 KeyStore`, mã hóa AES-GCM có key-version, đọc ciphertext cũ sau rotation và từ chối khi phiên bản key bị retire.

**Phạm vi:** Bài thuộc **Java Advance – security-cryptography / 11. Vòng đời khóa**. Trọng tâm là kiểm soát *toàn vòng đời và các ranh giới tin cậy*, không phải chỉ chọn một thuật toán AES/RSA hoặc một đường dẫn keystore.

---

## 1. Vì sao quản lý khóa quan trọng hơn một dòng gọi `Cipher`?

Một ứng dụng có thể mã hóa chính xác bằng `AES/GCM/NoPadding` nhưng vẫn không an toàn nếu:

- khóa AES bị hard-code trong repository hoặc cấu hình được chia sẻ;
- cùng khóa dùng cho mọi tenant mà không có ranh giới truy cập;
- bản sao khóa ở log, cache, backup, crash dump không bị kiểm soát;
- khi khóa cần rotate, hệ thống xóa ngay khóa cũ và **mất khả năng giải mã dữ liệu lịch sử**;
- khóa ký bị lộ nhưng hệ thống tiếp tục coi mọi chữ ký mới như hợp lệ;
- người vận hành bấm **disable** rồi nhầm tưởng ciphertext đã bị mã hóa lại hoặc kẻ tấn công đã mất bản sao khóa.

Các primitive mật mã giải quyết những phép toán như encrypt/decrypt, sign/verify, HMAC; **key management** trả lời ai được tạo, sử dụng, lưu giữ, phân phối, đổi, thu hồi và xóa các khóa mà primitive sử dụng.

Nguyên tắc cơ bản: **độ an toàn của ciphertext không lớn hơn độ an toàn của khóa cùng quá trình sử dụng khóa**. Nếu đối thủ lấy được khóa plaintext hợp lệ, AES mạnh không tự bảo vệ được thông điệp đã mã hóa dưới khóa đó.

### 1.1. Khái niệm cần phân biệt

| Thuật ngữ | Định nghĩa thực hành | Cạm bẫy |
| --- | --- | --- |
| **Secret key** | Khóa đối xứng dùng chung cho thao tác như AES/HMAC | Ai nắm được khóa thường có thể thực hiện thao tác được thuật toán cho phép; policy phải hạn chế |
| **Private key** | Thành phần bí mật của key pair (RSA/ECDSA/Ed25519...) | Public key có thể phát hành, private key phải được bảo vệ |
| **Public key** | Thành phần công khai dùng verify chữ ký hoặc bước mật mã tương ứng | Public key chưa được xác thực danh tính không thể tự chứng minh “đúng chủ sở hữu” |
| **DEK – Data Encryption Key** | Khóa mã hóa payload/file/record | Có thể tạo riêng theo object/tenant và bọc bằng KEK |
| **KEK – Key Encryption Key** | Khóa bọc/giải bọc DEK hoặc key material khác | Compromise KEK có thể ảnh hưởng nhiều wrapped DEK tùy phạm vi |
| **Key ID / version** | Danh tính ổn định của đối tượng khóa và phiên bản key material | Không phải bí mật, nhưng không được tin version do client tùy ý đưa vào mà bỏ qua policy |
| **Cryptoperiod** | Khoảng thời gian khóa được phép sử dụng theo mục đích nhất định | Hết thời gian **encrypt new** không nhất thiết có nghĩa không được **decrypt old** |
| **Rotation** | Chuyển từ khóa/phiên bản cũ sang khóa/phiên bản mới | Rotation metadata chưa làm dữ liệu cũ tự đổi khóa |
| **Rewrap** | Bảo vệ lại DEK bằng KEK mới | Không thay bản mã payload nếu DEK giữ nguyên; không sửa được DEK đã lộ |
| **Re-encrypt** | Giải mã và mã hóa lại payload bằng DEK/key mới | Tốn I/O, cần kiểm integrity, atomic migration và backup |
| **Revoke / disable** | Rút quyền/đánh dấu không cho dùng key trong hệ thống quản lý | Không xóa bản sao raw key mà đối thủ đã lưu |
| **Destroy** | Hủy vật liệu khóa với bảo đảm/quy trình thích hợp | Xóa alias file đơn thuần không chứng minh mọi bản sao, backup, memory đã bị xóa |

### 1.2. Không phải mọi loại khóa có vòng đời giống nhau

**AES data key:** Dùng encrypt/decrypt, cần quản lý nonce riêng dưới cùng key, nhiều khi giải mã dữ liệu lịch sử sau khi ngừng encrypt new. 

**HMAC key:** Dùng tạo/verify MAC; sau rotation có thể cần verify thông điệp cũ trong thời hạn chấp nhận. Quyền tạo MAC mới không giống quyền verify MAC cũ trong mô hình shared-secret; bên có HMAC key vẫn có năng lực tạo MAC nên không thể coi “verify-only” là phân biệt mật mã nếu họ giữ raw key.

**Private signing key:** Dùng ký; public key tương ứng dùng verify. Sau ngừng ký, có thể vẫn cần public key/cert hoặc metadata để verify chữ ký lịch sử, nhưng phải xét **thời điểm ký**, trust chain và chính sách khi private key bị compromise.

**TLS private key/certificate:** Certificate có thời hạn và có thể bị thu hồi qua cơ chế PKI; việc thay certificate không tự xóa private key bị rò ở mọi nơi.

**KEK trong KMS/HSM:** Có thể không export được; rotate KEK liên quan những wrapped DEK, quyền unwrap và chính sách sử dụng của dịch vụ.

**Password-derived key:** Độ mạnh bị giới hạn bởi password, cần KDF có salt/work factor; không đánh đồng với khóa ngẫu nhiên mạnh. Nếu đổi password để bảo vệ DEK, có thể rewrap DEK thay vì re-encrypt toàn bộ dữ liệu.

## 2. Vòng đời khóa: giai đoạn công việc và trạng thái sử dụng

Một mô hình dễ nhớ:

```text
Định nghĩa mục đích / threat model
                 │
                 ▼
              Sinh khóa
                 │
                 ▼
       Đăng ký / cấp phát / phân quyền
                 │
                 ▼
            Kích hoạt (ACTIVE)
                 │
        ┌────────┴──────────┐
        ▼                   ▼
  Sử dụng hợp lệ       Backup / giám sát
        │
        ▼
  Rotation định kỳ / kết thúc originator use
        │
        ▼
  Không tạo dữ liệu mới bằng khóa cũ
  (DECRYPT-ONLY / DEACTIVATED theo policy)
        │
        ▼
  Hết nhu cầu đọc lịch sử + giữ chứng cứ
        │
        ▼
    Destroy / crypto-erase

Bất kỳ thời điểm nào phát hiện nghi lộ khóa:
  COMPROMISED → ngăn sử dụng, thông báo, thay khóa,
  điều tra phạm vi và xử lý dữ liệu/chữ ký bị ảnh hưởng
```

NIST SP 800-57 Part 1 Rev. 5 mô tả các trạng thái như **pre-activation, active, deactivated, compromised, destroyed** và các chuyển đổi, đồng thời phân biệt quyền dùng khóa để *bảo vệ dữ liệu mới* với quyền *xử lý dữ liệu đã bảo vệ*. Sơ đồ ở đây là mô hình ứng dụng học tập, không phải sao chép nguyên state machine của tiêu chuẩn.

| Trạng thái | Cho phép làm gì? | Phải chặn/đặc biệt cẩn trọng |
| --- | --- | --- |
| **PENDING / PRE-ACTIVATION** | Nhập metadata, xác thực key ownership, chuẩn bị và phê duyệt | Chưa dùng để encrypt/sign production |
| **ACTIVE** | Thao tác đúng mục đích, chính sách, cryptoperiod và quota | Không cấp tự do toàn quyền; audit, kiểm nonce, policy |
| **DECRYPT-ONLY / DEACTIVATED** | Chỉ đọc dữ liệu cũ hoặc verify lịch sử nếu chính sách/loại khóa cho phép | Không encrypt/sign dữ liệu mới bằng key cũ |
| **SUSPENDED** | Tạm ngưng hoạt động theo điều tra/chính sách, có thể phục hồi nếu không compromise | Không tiếp tục cấp phép ở lớp ứng dụng chỉ vì key material vẫn tồn tại |
| **REVOKED / COMPROMISED** | Chỉ thao tác điều tra/khôi phục đặc biệt đã được kiểm soát | Không tạo dữ liệu/chữ ký đáng tin mới; xử lý dữ liệu cũ theo incident plan |
| **DESTROYED** | Có thể giữ *metadata chứng cứ* không nhạy cảm | Không còn dùng key để decrypt/sign; không được tuyên bố destroyed nếu còn key copies |

**Cẩn thận ngôn ngữ:** “Đã ngừng encrypt bằng khóa cũ” là **deactivation/rotation** thường quy. “Đã phát hiện khóa bị lấy cắp” là **compromise**, đòi hỏi phản ứng khẩn cấp; không thể xử lý bằng cùng thủ tục đơn giản rồi coi rủi ro chấm dứt.

### 2.1. Cryptoperiod là một quyết định theo rủi ro

Cryptoperiod nên phụ thuộc thuật toán, mục đích khóa, lượng dữ liệu, tác động nếu key lộ, số lần sử dụng/giới hạn nonce, loại dữ liệu và yêu cầu compliance. **Không có một chu kỳ 90 ngày/1 năm phù hợp mọi khóa.** Đặt lịch tự động và sự kiện rotation có căn cứ; không copy một con số từ ví dụ sang tất cả hệ thống.

Một DEK chỉ được dùng để mã hóa trong một ngày có thể vẫn cần để giải mã bản ghi chưa hết thời hạn lưu trữ trong nhiều năm. Đây là lý do quản lý **originator-usage period** (sinh bảo vệ mới) tách khỏi **recipient-usage period** (xử lý dữ liệu cũ) theo NIST.

## 3. Bước 1 – Sinh khóa: đúng thuật toán, kích thước và nguồn entropy

### 3.1. Xác định ý định trước khi tạo key

Trước khi gọi API, cần có ít nhất:

- **Key purpose:** encryption, decryption, signing, verification, HMAC, key wrapping hay handshake;
- **Algorithm / size:** AES-128/256, HMAC-SHA256, RSA hoặc Ed25519 tùy protocol và chính sách;
- **Owner/tenant/service/asset:** khóa thuộc đối tượng nào và ai chịu trách nhiệm;
- **Exportability:** có được export key bytes không, hay phải giữ non-exportable trong HSM/KMS?
- **Allowed operations:** encrypt/decrypt, sign/verify, wrap/unwrap và context cụ thể;
- **Environment:** production/staging/test phải tách key material; không dùng cùng khóa trên cả ba;
- **Lifetime/volume:** thời hạn, quota, rotation trigger, giới hạn số lần mã hóa/nonce;
- **Recovery:** backup/escrow/wrapped form, ứng dụng có cần giải mã dữ liệu cũ hay không.

Một khóa mạnh được dùng sai mục đích, sai tenant hoặc sai algorithm vẫn là lỗi bảo mật. Không chọn RSA chỉ vì “khóa dài hơn”; không tái sử dụng một key để vừa encrypt vừa MAC hoặc nhiều protocol mà không có thiết kế key separation.

### 3.2. Tạo AES secret key với Java 17+

```java
import java.security.SecureRandom;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

SecureRandom rng = new SecureRandom();
KeyGenerator generator = KeyGenerator.getInstance("AES");
generator.init(256, rng);
SecretKey key = generator.generateKey();
```

Đây là **đoạn minh họa cần nằm trong method xử lý checked exception**. Với Java 17 và provider thông dụng, AES-256 được hỗ trợ; với môi trường/provider bị giới hạn, kiểm theo chính sách và khả năng cung cấp thuật toán thực tế. Trong chương trình chạy đầy đủ ở mục 12, dùng AES-128 để ví dụ rộng rãi trên các môi trường Java 17, không ngụ ý AES-128 luôn phù hợp mọi threat model.

Các ý quan trọng:

1. `KeyGenerator` biểu diễn yêu cầu **khóa cho thuật toán AES**, không phải mật khẩu.
2. `SecureRandom` là API tạo bit có chất lượng mật mã; không dùng `Random`, `ThreadLocalRandom`, timestamp, UUID ghép hay seed hard-code.
3. `SecretKey` là một đối tượng tham chiếu khóa. Một provider có thể giữ key ngoài phần mềm và `key.getEncoded()` có thể trả `null` đối với non-exportable key.
4. **Không in raw key** bằng `Base64.getEncoder().encodeToString(key.getEncoded())` rồi ghi vào log/config.
5. Độ dài output 256 bit từ một mật khẩu yếu đã băm không tương đương khóa 256 bit lấy từ CSPRNG; nếu đầu vào là password, cần KDF và chính sách password.

### 3.3. Sinh cặp khóa ký trong Java

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = generator.generateKeyPair();
// pair.getPrivate() phải được bảo vệ.
// pair.getPublic() có thể xuất bản theo cơ chế tin cậy.
```

Đây là đoạn minh họa, cần xử lý checked exception và khả năng hỗ trợ provider. `Ed25519` dành cho **chữ ký số**; không sử dụng key pair Ed25519 để làm khóa mã hóa AES.

`KeyPairGenerator.getInstance("RSA")` cũng có thể dùng trong giao thức/PKI tương thích, nhưng kích thước key và scheme/padding phải theo chính sách. Với TLS, việc tự tạo key pair chưa phát hành một **certificate được CA tin cậy**; quy trình CSR, cấp chứng thư, kiểm chain và chính sách tin cậy là một bước riêng.

### 3.4. Ưu tiên tạo khóa ở đúng ranh giới bảo mật

- **Software-generated/exportable:** Java `KeyGenerator` hoặc `KeyPairGenerator` trả đối tượng key, dễ tích hợp, nhưng RAM/process và backup phải được bảo vệ.
- **Provider-backed:** HSM/PKCS#11 có thể tạo khóa tại token và không cho xuất private/raw key, giúp giảm số bản sao key material.
- **Cloud KMS:** có thể tạo và sử dụng key trong dịch vụ quản lý, hoặc tạo DEK dạng plaintext tạm thời + wrapped key. Cách dùng và export policy khác nhau theo provider/API, **không mặc nhiên mọi khóa KMS đều exportable hay mọi lời gọi KMS trả raw key**.

Nếu chính sách yêu cầu non-exportable, không tạo khóa exportable trong ứng dụng rồi import một bản sao và tuyên bố “khóa chưa bao giờ rời HSM”. Cần kiểm chứng nơi key thực sự được sinh và những chỗ raw key đi qua.

### 3.5. Kiểm thử entropy không đồng nghĩa kiểm thử randomness bằng mắt

Một vòng lặp in 100 khóa khác nhau không chứng minh generator an toàn. Chất lượng `SecureRandom` phụ thuộc triển khai/provider và nguồn entropy; không dùng thời gian hoặc giá trị dễ đoán để thay nguồn seed. Trên hệ thống có yêu cầu cao, xem cấu hình JDK/provider, kiểm soát môi trường container/VM, chuẩn vận hành CSPRNG và chính sách compliance.

## 4. Bước 2 – Cấp phát (provisioning): đưa khóa đến đúng bên có quyền

**Cấp phát khóa** không phải việc gửi raw key qua email/chat hoặc copy file keystore cho mọi service. Nó là quy trình bảo đảm đúng đối tượng **được đăng ký, nhận quyền và có khả năng dùng khóa cho đúng purpose**.

Một workflow thường gồm:

1. **Yêu cầu:** service/owner khai báo mục đích, key type, algorithm, environment, tenant, retention, cần export hay không.
2. **Phê duyệt:** policy/IAM và separation of duties quyết định ai được create/activate/access/delete.
3. **Tạo hoặc import:** key được sinh ở ranh giới an toàn, gắn key ID/metadata. Với import phải xác minh nguồn, algorithm, format và đường truyền an toàn.
4. **Liên kết chủ sở hữu:** key ID ↔ service identity / tenant / dataset / operation / environment. Không tin tên alias tùy ý do request bên ngoài gửi.
5. **Phân quyền:** chỉ cấp `Encrypt`/`Decrypt`/`GenerateDataKey`/`Sign`/`Verify`/`Wrap`/`Unwrap` cần thiết; tránh quyền quản trị/disable/delete cho runtime ứng dụng.
6. **Kích hoạt:** chỉ dùng trong thời gian, quota và trạng thái cho phép; cấu hình monitoring/audit.
7. **Kiểm chứng:** chạy test không dùng dữ liệu thật để biết đúng identity, key version và expected operation.

Ví dụ mô hình phân quyền:

| Role | Quyền nên có | Quyền nên tránh |
| --- | --- | --- |
| Application writer | `Encrypt` hoặc `GenerateDataKey` với key/context được phép | `DeleteKey`, export KEK, quản lý key của tenant khác |
| Application reader | `Decrypt`/`Unwrap` đúng đối tượng và điều kiện | Create/rotate vô hạn, xóa key, key admin |
| Key administrator | Tạo, cấu hình policy, lên lịch rotation theo phê duyệt | Đọc plaintext dữ liệu nếu không có nhu cầu |
| Incident responder | Disable, audit, kích hoạt workflow khẩn cấp theo kiểm soát | Tự ý phá hủy key khi chưa đánh giá recovery/retention |
| Auditor | Read-only metadata, log, trạng thái và rotation history | Raw key material hoặc plaintext |

Một dịch vụ có quyền decrypt tất cả tenant tương đương “chìa khóa vạn năng” dù AES rất mạnh. Cần phối hợp IAM, policy theo resource, key alias/context, business authorization và log. KMS quyền thao tác mật mã không tự thay thế **kiểm tra quyền đối tượng nghiệp vụ**.

### 4.1. Đưa public key và secret key ra ngoài khác nhau

- **Public key:** có thể phân phối, nhưng cần bảo đảm **authenticity/binding** bằng certificate, pinned key, trusted registry hoặc kênh đáng tin; public key không phải bí mật.
- **Private/secret key:** chỉ vận chuyển qua cơ chế key transport/wrapping có bảo mật, quy trình HSM/KMS hoặc keystore được bảo vệ. Nếu raw key được xuất ra RAM, đánh giá cả process, log, crash dump, truyền mạng và bên nhận.
- **Wrapped DEK:** vẫn cần authenticated key wrapping và ràng buộc context (tenant, object, version), không phải “Base64 của key” hoặc XOR password hash.
- **Certificate:** chứa public key và thông tin danh tính/issuer/signature; **không** phải cùng thứ với private key. Certificate đã được CA cấp không đồng nghĩa private key đang được bảo vệ.

**Đường cấp phát cũng là một phần của lifecycle**, vì key rất mạnh vẫn có thể lộ trong một lần copy sai kênh.

## 5. Bước 3 – Lưu trữ: KeyStore, KMS, HSM và backup

| Phương án | Lưu gì? | Khi nào phù hợp? | Giới hạn |
| --- | --- | --- | --- |
| Java `KeyStore` loại `PKCS12` | Private key + certificate chain, `SecretKeyEntry` khi provider hỗ trợ, hoặc certs | App/tool cần lưu key có password/file control | File và password là hai tài sản cần bảo vệ; không có IAM/audit tập trung như KMS |
| Java `KeyStore` loại `PKCS11` | Tham chiếu key/token thông qua provider PKCS#11 | HSM/token và yêu cầu phần cứng | Phụ thuộc thiết bị, provider, session/login và cấu hình token |
| Cloud KMS | KEK/key object, key policy, version, encrypt/decrypt hoặc wrap/unwrap | Nhiều service, quyền tập trung, audit, rotation | Availability, permissions, network/latency, nhà cung cấp |
| HSM | Key operations trong module bảo mật, có thể non-exportable | Compliance, signing authority, KEK/tài sản nhạy cảm | Chi phí/quản trị, quota, backup/recovery theo cơ chế HSM |
| Envelope encryption | Ciphertext data + wrapped DEK; KEK ở KMS/HSM | Lượng dữ liệu lớn, rotation KEK, nhiều tenant | Phải giữ wrapped DEK, key ID/context, xử lý plaintext DEK tạm trong RAM |
| Secret manager | Secret được quản lý qua API và policy | Lưu các secret/phần mềm cần truy xuất | Không tự động thay mọi chức năng KMS/HSM và không bảo đảm non-exportability |

**Chú ý:** Có file `.p12` không tự động có security posture của HSM. `PKCS12` là định dạng/keystore được bảo vệ bằng password; nếu file và password cùng bị lộ, key có thể mất an toàn. Đừng lưu cả `keystore.p12` và password giải khóa trong cùng repository/container image rồi coi đã tách secret.

### 5.1. Phân biệt keystore và truststore

**Keystore cho identity của chính ứng dụng** thường giữ private key cùng certificate chain hoặc secret key. **Truststore** giữ trust anchor/chứng chỉ công khai mà ứng dụng tin cậy cho TLS/PKIX. Lưu certificate trong truststore **không** đồng nghĩa có private key tương ứng; truststore cũng cần bảo vệ tính toàn vẹn để ngăn attacker thay trust anchors.

Với Java:

```java
KeyStore store = KeyStore.getInstance("PKCS12");
store.load(inputStream, password);
Key key = store.getKey("data-v1", password);
```

Đây là đoạn **minh họa chưa độc lập**: cần import `java.security.KeyStore` và `java.security.Key`, `inputStream`, `password`; phải xử lý checked exception. Key có thể không tồn tại, password sai hoặc keystore/provider không hỗ trợ loại entry. `getKey` trả tham chiếu `Key`; không tự giải quyết permission/quota/cryptoperiod cấp ứng dụng.

### 5.2. Nguyên tắc lưu khóa trong production

1. **Hạn chế khả năng export:** nếu không cần raw key, ưu tiên thao tác trong KMS/HSM.
2. **Least privilege:** process runtime chỉ được dùng đúng key/operation; không cấp delete/rotate cho toàn bộ service.
3. **Access controls độc lập:** file permissions, secret distribution, token/service identity, network và IAM.
4. **Encryption + integrity:** wrapped DEK/PKCS12/password phải được bảo vệ, key metadata/alias cũng phải có integrity.
5. **Backup và recovery:** backup của key khác với backup của ciphertext. Mất key mà còn data ≠ khôi phục được data.
6. **Audit:** theo dõi create/import/activate/use/rotate/disable/delete/export, nhưng **không log raw key, password hay plaintext**.
7. **Tách môi trường:** dev/test/prod và tenant/scope; không chuyển file prod keystore sang laptop dev.
8. **Vòng đời bản sao:** cache, disaster-recovery replicas, snapshots, exported keystore, laptop, build pipeline, CI artifacts.
9. **Phê duyệt thao tác nguy hiểm:** delete/destroy cần kiểm retention, legal hold, phụ thuộc các phiên bản dữ liệu cũ và two-person control khi phù hợp.

### 5.3. Backup key không phải tạo nhiều bản sao vô quản lý

Backup key phải có encryption, ownership, access policy, inventory và định kỳ kiểm tra restore. Khả năng recovery phải được **diễn tập**, không chỉ dựa vào checkbox “backup enabled”. Nếu HSM/KMS key không export, phải hiểu khả năng backup/restore của chính sản phẩm và giới hạn về vùng địa lý/account.

Khi muốn **crypto-shredding/cryptographic erasure**, phải xác định mọi bản DEK/KEK cần hủy, wrapped copies, backups và nơi key được cache. Xóa một blob mật mã không có nghĩa data không thể khôi phục nếu key vẫn còn trong bản sao khác.

## 6. Bước 4 – Sử dụng khóa: đúng phạm vi và ràng buộc mật mã

### 6.1. Không dùng cùng khóa cho mọi nhu cầu

**Key usage separation:** Khóa AES mã hóa dữ liệu nên được tách khỏi key HMAC, key-wrapping, signing key, JWT secret và những protocol khác trừ khi thiết kế thuật toán chuẩn quy định cách derive subkeys an toàn. Khóa chứa 256 bit entropy không có nghĩa được tái sử dụng vô hạn giữa các mục đích.

Ví dụ:

- `data-v7`: AES-GCM cho record tenant A;
- `wrap-v3`: KEK bọc DEK của tenant A;
- `sign-v5`: private key ký message;
- `tls-server-v2`: private key cho TLS server identity.

Một key ID phải dẫn tới **một key material + purpose + policy + version** rõ ràng. Nếu một application user đổi `keyId` trong JSON để truy cập khóa tenant khác, backend phải từ chối dù lookup key theo ID có kết quả.

### 6.2. AES-GCM: nonce duy nhất dưới cùng key

Mọi lần `AES/GCM/NoPadding` dùng một **key giống nhau** phải tránh dùng lại **nonce giống nhau**. Nonce reuse phá nghiêm trọng confidentiality và authentication của GCM. Thông thường dùng nonce 12 byte (96 bit), tag 128 bit; cơ chế uniqueness phải tính số lượng encryption, concurrency, restart/snapshot và provider behavior.

```java
byte[] nonce = new byte[12];
secureRandom.nextBytes(nonce);

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
cipher.init(Cipher.ENCRYPT_MODE, aesKey,
        new GCMParameterSpec(128, nonce));
cipher.updateAAD(metadataBytes);
byte[] ciphertextAndTag = cipher.doFinal(plaintextBytes);
```

Đây là **đoạn minh họa chưa độc lập**: cần imports JCA/JCE, các biến `secureRandom`, `aesKey`, `metadataBytes`, `plaintextBytes` và exception handling. Trong production, AAD phải ràng buộc **key version, tenant, object, schema/operation** theo thiết kế, và bên decrypt phải truyền y hệt. Nonce là dữ liệu có thể công khai nhưng phải lưu cùng ciphertext nếu cần decrypt.

**Thêm key version vào AAD không tự ngăn nonce reuse.** Tương tự, rotation không hợp lệ hóa những ciphertext đã bị tạo bằng cặp key–nonce lặp trong quá khứ.

### 6.3. Giới hạn quyền: encrypt-only và decrypt-only

Khi app dừng sử dụng key v1 để **mã hóa mới**, nó vẫn có thể cần v1 để giải mã record cũ. Giao thức nên buộc:

- Encryption luôn lấy **active key version** từ key registry tin cậy, không lấy từ tham số caller.
- Decryption đọc key ID/version từ envelope đã được xác thực/bảo vệ, kiểm rằng version này được phép decrypt record/context tương ứng.
- Key v1 chuyển sang **decrypt-only** hoặc deactivated processing mode theo semantics của KMS/policy; không dùng để mint ciphertext mới.
- Retention và migration biết bao nhiêu dữ liệu v1 còn tồn tại và ở đâu, trước khi retire/destroy.
- Không dùng key version làm dữ liệu quyết định authorization duy nhất: version là metadata, phải có role/owner/tenant binding và integrity.

**Lưu ý HMAC:** Vì cùng secret key thực hiện được cả tạo MAC lẫn kiểm MAC, việc thiết lập “verify-only” ở hệ thống chia sẻ raw HMAC key không thể ngăn người cầm raw key tính MAC mới. Cần enforce ở ranh giới dịch vụ/HSM hoặc thay scheme khi cần tách năng lực.

### 6.4. Quan sát hoạt động mà không làm lộ bí mật

Log nên chứa **key ID/version, service principal, operation name, outcome, timestamp, request ID, policy decision**, các mã lỗi đã chuẩn hóa. Không log `SecretKey.getEncoded()`, password, token bearer, plaintext, IV+key cùng lúc như debug dump. Cần kiểm các đường bất thường: crash dump, heap dump, APM tracing, exception stack, metrics labels và test fixtures.

Không phải mọi quyền truy cập key thất bại đều là attack, nhưng gia tăng nhanh `Decrypt` sai key/tenant, `AccessDenied`, nonce duplication hoặc thay đổi policy không mong muốn phải được giám sát.

## 7. Bước 5 – Luân chuyển (rotation) bình thường

**Rotation** thường có nghĩa bắt đầu dùng **key material mới** hoặc một phiên bản mới cho hoạt động mới, trong khi có lộ trình xử lý dữ liệu cũ. Việc chuyển alias `current=v2` không tự tái mã hóa dữ liệu v1.

### 7.1. Quy trình đối xứng key version v1 → v2

```text
Trước:
  ACTIVE encryption key = v1
  Record cũ: [version=v1, nonce1, ciphertext1, tag1]

Tạo v2:
  Generate(v2) → Policy/QA → ACTIVE for new writes
  Deactivate v1 for new encryption; keep v1 for permitted reads

Trong migration:
  New record: [version=v2, nonce2, ciphertext2, tag2]
  Old record vẫn decrypt bằng v1 khi cần

Nếu mục tiêu là loại bỏ v1:
  Xác thực/giải mã record v1 → encrypt lại bằng v2 + nonce mới
  → kiểm readback + atomic switch → xác nhận không còn dependency
  → hủy v1 theo policy và kiểm backups
```

Bảng quyết định:

| Trạng thái | Encrypt record mới | Decrypt record v1 | Decrypt record v2 |
| --- | --- | --- | --- |
| Chưa rotate, v1 active | v1 | Có | Không có v2 |
| Đã activate v2 | **v2** | **Có** trong read window/policy | Có |
| Đã migrate toàn bộ + xác nhận không còn v1 | **v2** | Không nếu đã hủy key v1 | Có |
| V1 bị compromise | Không v1 | Chỉ xử lý đặc biệt trong incident plan | Có nếu v2 được tạo/giữ an toàn |

Điều kiện **“toàn bộ dữ liệu đã migrate”** gồm backup, replica, archive, delayed messages và bản ghi ít được truy cập; nếu bỏ sót, xóa v1 có thể làm data lịch sử không thể giải mã. Không để một node vẫn encrypt bằng v1 trong khi node khác đã chuẩn bị xóa v1; rotation phải phối hợp với rollout và active-version registry.

### 7.2. Envelope encryption: rewrap khác re-encrypt

Giả sử một file lớn được mã hóa bằng **DEK ngẫu nhiên**:

```text
payloadCiphertext = AES-GCM(DEK, plaintext, nonce)
wrappedDEK_v1    = Wrap(KEK_v1, DEK)
```

Khi chỉ thay **KEK**, ta có thể:

```text
DEK = Unwrap(KEK_v1, wrappedDEK_v1)
wrappedDEK_v2 = Wrap(KEK_v2, DEK)

payloadCiphertext vẫn như cũ vì DEK không đổi.
```

Đây là **rewrap**: thay cơ chế bảo vệ DEK, không cần xử lý lại hàng gigabyte ciphertext. Nhưng nếu **DEK đã lộ**, rewrap không làm payload an toàn trở lại: phải sinh DEK mới và **re-encrypt data**. Nếu KEK v1 đã lộ và attacker đã giữ wrappedDEK_v1, họ có thể đã khôi phục DEK; cần incident investigation thay vì chỉ rewrap rồi coi an toàn.

Một KMS có thể hỗ trợ các thao tác re-encrypt/wrap key chuyên dụng mà không trả plaintext DEK về ứng dụng. Kiểm đặc tả từng provider, policy và loại key; không tự suy ra mọi KMS cung cấp cùng API.

### 7.3. Rotation của signing key khác data encryption key

Với private signing key `sign-v1`:

1. Tạo và kích hoạt `sign-v2`, phát hành public key/certificate tương ứng qua kênh đáng tin.
2. Ngừng phát hành chữ ký **mới** bằng private key v1.
3. Verifier tiếp tục nhận chữ ký **lịch sử hợp lệ** của v1 theo chính sách thời điểm ký, validity và trạng thái compromise.
4. Sau thời gian cần thiết, ngừng chấp nhận v1 hoặc áp dụng quy trình lưu bằng chứng thời gian/chứng thực dài hạn.

Cần phân biệt **public key vẫn có thể được lưu để verify** với **private signing key vẫn được phép sign**. Đừng xóa mọi public key cũ nếu hệ thống còn chữ ký lịch sử cần xác minh. Nếu v1 bị compromise, vấn đề phức tạp hơn: chữ ký mới có thể bị giả mạo, và chữ ký lịch sử cần đánh giá với timestamp/trust evidence phù hợp.

### 7.4. Kịch bản zero-downtime có kiểm soát

Một rotation production tốt thường là:

1. **Prepare:** tạo v2, thiết lập quyền, backup/restore, kiểm compatibility và version-aware parser.
2. **Deploy reader first:** đảm bảo mọi instance có thể giải mã v1 và v2 (theo phân quyền), chưa chuyển writer.
3. **Activate v2 writers:** đổi active version qua registry/cấu hình đáng tin, theo dõi writer có đang còn tạo v1 không.
4. **Observe:** đo tỷ lệ encrypt v2, decrypt v1/v2, latency, error rate, audit logs, replication consistency.
5. **Re-encrypt/rewrap (nếu cần):** chạy migration có checkpoint/idempotency và verify tag, tránh mất data khi rollback.
6. **Retire old:** chỉ sau kiểm inventory/dependencies, backup/DR, retention, approvals và rollback policy.
7. **Document:** ghi actor, thời điểm, lý do, incident/ticket, key IDs và kết quả kiểm chứng.

Với multi-region, stale caches và asynchronous queues, có thể tồn tại cửa sổ cả v1/v2 đồng thời. Protocol phải quy định rõ quyền decrypt và **một nguồn chân lý cho active encryption version**, không sử dụng wall-clock time riêng từng máy để chọn key.

## 8. Bước 6 – Thu hồi (revoke) và phản ứng khi khóa lộ

Thu hồi không chỉ là “rotate nhanh hơn”. **Khi nghi ngờ khóa bị lộ**, phải giả định attacker có thể có bản sao raw key hoặc đã thực hiện các thao tác mật mã không được phép.

### 8.1. Những hành động khác nhau

| Hành động | Tác dụng thực tế | Không bảo đảm điều gì? |
| --- | --- | --- |
| **Disable key** trong KMS/policy | Ngăn thao tác mới qua hệ thống KMS đã áp dụng chính sách | Không xóa raw key đã export/cached hay giải mã được bằng bản sao |
| **Revoke access grant / IAM** | Rút quyền của identity thực hiện encrypt/decrypt/sign | Không hủy secret đã bị người đó sao chép trước đó |
| **Rotate key** | Tạo material mới và chuyển thao tác mới sang v2 | Không đổi ciphertext cũ, không thu hồi bản sao v1 |
| **Rewrap DEK** | Bảo vệ DEK bằng KEK mới | Không cứu dữ liệu nếu DEK đã bị lộ |
| **Re-encrypt payload** | Tạo bản mã mới dưới DEK mới, nonce mới | Không thể “lấy lại” plaintext đã bị attacker đọc trước đó |
| **Revoke certificate** | Thông báo certificate/key identity không còn được tin cho mục đích/từ thời điểm theo chính sách PKI | Không xóa private key hoặc khiến tất cả client kiểm revocation ngay |
| **Delete/destroy key** | Loại bỏ key material theo quy trình, có thể tạo cryptographic erasure | Không chứng minh mọi bản backup/cached copy đều biến mất |
| **Expire credentials/token** | Chặn việc gọi API bằng credential cũ qua hệ thống kiểm soát | Không thay key mã hóa nếu đó là hai bí mật khác nhau |

### 8.2. Incident response khi nghi lộ DEK

Ví dụ khóa AES `data-v1` được ghi vào log:

1. **Cô lập nguồn rò:** chặn xuất log và quyền đọc không cần thiết, bảo quản chứng cứ cho điều tra theo quy trình.
2. **Đánh giá phạm vi:** key version, tenant, data sets, wrapped DEKs, logs/backups, retention và khoảng thời gian lộ.
3. **Ngăn tạo dữ liệu mới:** disable v1 for new encrypt, activate v2 từ nguồn an toàn; cân nhắc chặn decrypt v1 qua API trừ luồng recovery hạn chế.
4. **Xử lý ciphertext cũ:** nếu cần phục hồi confidentiality, giải mã từ bản dữ liệu tin cậy rồi mã hóa lại bằng DEK mới/nonce mới; chú ý đối thủ có thể đã đọc bản mã cũ.
5. **Rút quyền/credential liên quan:** IAM keys, deployment secrets, service accounts, key grants và mọi bản sao v1.
6. **Migrate và xác minh:** kiểm tất cả primary/replica/backup theo phạm vi; giữ lịch sử và bằng chứng.
7. **Retire/destroy** v1 khi pháp lý/khả năng recovery/incident plan cho phép; báo cáo và cập nhật detection.

Không tự động delete v1 ngay khi thấy dấu hiệu compromise nếu hệ thống cần nó để khôi phục/migrate và chưa có bản backup tin cậy. Tuy nhiên cũng không được tiếp tục dùng v1 cho encryption mới chỉ vì “còn cần decrypt”. Đây là bài toán balance giữa containment và recovery, cần runbook đã được phê duyệt.

### 8.3. Thu hồi private signing key/TLS certificate

Nếu private signing key hoặc TLS private key lộ:

- Kích hoạt cặp khóa mới, phân phối public key/certificate mới từ kênh tin cậy.
- Ngừng **ký mới/handshake mới** bằng private key cũ trong hệ thống kiểm soát.
- Nếu là chứng thư X.509, thực hiện revocation tại CA hoặc cơ chế tương ứng (CRL/OCSP hoặc mô hình nhà cung cấp) và kiểm hành vi của relying parties.
- Xem xét **chữ ký đã phát hành**: việc verify signature toán học không trả lời chữ ký đã được tạo *trước hay sau khi compromise*. Signed timestamp hoặc bằng chứng thời gian được tin cậy có thể cần trong hệ thống lưu chữ ký dài hạn.
- Nếu verifier pin public key không qua PKI, phải cập nhật trusted-key registry/pin trực tiếp theo protocol; CRL/OCSP có thể không liên quan.

**Không nhầm:** thu hồi certificate không phải hủy private key trên máy đã bị tấn công. Và public key thường không có bí mật nên không phải mục tiêu xóa để “khóa kẻ tấn công”; cần thay chính sách tin cậy của verifier và rút quyền dùng private key.

### 8.4. Revocation và backup

Một backup hệ thống lưu **old key material** có thể làm key đã “xóa khỏi active store” xuất hiện lại sau disaster recovery. Runbook cần quản lý trạng thái revoked/compromised như metadata đáng tin cậy áp dụng **sau restore**, không chỉ restore raw keystore cũ rồi tự động tái kích hoạt v1.

Nếu một service bị compromise, phải xem cả bản sao secret trong container image, environment, CI logs, crash dumps, snapshots, terminal history và artifacts. Việc xoay key trên dashboard không xóa được các bản sao đó.

## 9. Bước 7 – Hủy bỏ, lưu trữ lịch sử và khả năng chứng minh

**Hủy khóa** có thể là một hành động gây mất dữ liệu không thể đảo ngược. Chỉ nên thực hiện khi:

- key đã hết cryptoperiod và không còn dữ liệu hợp lệ cần decrypt/sign/recover theo policy;
- dữ liệu đã được migrate hoặc được cho phép không khôi phục nữa;
- backup, archive, replicas, các bản sao khôi phục được đánh giá;
- có phê duyệt hoặc retention/legal-hold controls;
- thao tác hủy đáp ứng yêu cầu sản phẩm/môi trường, với audit/bằng chứng.

**Crypto-erasure** là việc làm dữ liệu mã hóa không thể giải mã bằng cách phá hủy vật liệu key cần thiết; hiệu quả phụ thuộc việc key **không còn bản sao khả dụng**, các đường recovery không còn và key thật sự là điểm kiểm soát duy nhất. Không được khẳng định `KeyStore.deleteEntry(alias)` trên file hoặc xóa một row DB là bằng chứng cryptographic erasure hoàn chỉnh.

Sau khi hủy, có thể vẫn cần giữ metadata không nhạy cảm: key ID, version, purpose, created/activated/retired time, owner, algorithm, policy approvals, các sự kiện rotate/revoke/destroy và đối chiếu audit; **không giữ raw secret** chỉ để audit.

### 9.1. Key destruction không phải xóa dữ liệu người dùng

Nếu xóa DEK của một record, ciphertext vẫn có thể tồn tại nhưng không đọc được bằng cơ chế hợp lệ. Đây là một chính sách cần quyết định rõ; nếu người dùng yêu cầu **xóa dữ liệu**, hệ thống còn cần xử lý bản sao plaintext, searchable indexes, caches, logs và các nghĩa vụ retention riêng. Mã hóa và key destruction không thay thế toàn bộ data-governance workflow.

### 9.2. Không kỳ vọng zeroization tuyệt đối từ Java object

`SecretKey` hoặc `PrivateKey` có thể là object nằm trên Java heap, trong provider native memory hoặc trên token. Không phải mọi implementation cho phép xóa ngay tất cả bản copy; GC không cam kết tức thời hay secure wipe. Có thể xóa buffer `byte[]` do ứng dụng kiểm soát bằng `Arrays.fill` khi thích hợp, nhưng việc đó **không** chứng minh mọi copy đã được xóa. Nếu yêu cầu kiểm soát nghiêm, ưu tiên non-exportable KMS/HSM và quy trình vận hành được thẩm định.

## 10. Sổ đăng ký khóa: key inventory và metadata

Một hệ thống trưởng thành cần có **key inventory/registry** thay vì đoán key qua tên file hoặc biến môi trường. Gợi ý schema nghiệp vụ:

| Trường | Ý nghĩa |
| --- | --- |
| `key_id` | Định danh key logic ổn định, không chứa material |
| `version` | Phiên bản key material, ví dụ 1, 2, 3 |
| `algorithm`, `length` | AES-256, Ed25519, RSA..., thông số cần biết |
| `purpose` | Encrypt, Decrypt, Sign, Verify, Wrap, Unwrap |
| `owner`, `tenant`, `environment` | Danh tính/ranh giới trách nhiệm |
| `state` | PRE-ACTIVE, ACTIVE, DECRYPT-ONLY, REVOKED, DESTROYED... |
| `created_at`, `activated_at`, `retired_at` | Mốc lifecycle và cryptoperiod |
| `provider_ref` | KMS key ARN/URI, HSM label, keystore alias... |
| `origin`, `exportable` | Nơi sinh/import; policy xuất raw key |
| `rotation_policy` | Ngày/số lượt/incident trigger; chủ sở hữu việc thay key |
| `dependencies` | Datasets, wrapped DEKs, certificates và backups |
| `approval/audit_ref` | Ticket, identity, action/outcome và evidence |

**Không** đặt raw key, private key bytes, password hoặc master secret vào registry metadata. Một key-version có thể được ghi trong ciphertext header, nhưng backend **không** chỉ dựa vào header đó để cấp quyền truy cập: phải kiểm key/tenant/object binding và integrity.

### 10.1. Envelope record mẫu

```text
version=2
tenant=TENANT-A
key_id=data-tenant-a
key_version=7
nonce=<12 bytes>
ciphertextAndTag=<...>
aad=canonical(version,tenant,key_id,key_version,record_id)
```

Đây là **định dạng khái niệm**, chưa phải parser/schema sản xuất. Trong AES-GCM, AAD được xác thực nhưng không mã hóa. Bên decrypt cần sử dụng cùng encoding/AAD và đúng key version; sau đó vẫn kiểm authorization để tránh tráo record giữa tenant/đối tượng.

Nếu nhiều record cùng encrypt bằng AES-GCM một key, thiết kế nonce phải bảo đảm không trùng cặp key/nonce; không dựa vào việc key version khác nhưng thực tế raw key giống nhau.

## 11. Mối liên hệ với Java `KeyStore`, keytool và TLS

### 11.1. Java `KeyStore` là nơi cất key, không phải key-lifecycle service

`KeyStore` có các entry như `SecretKeyEntry`, `PrivateKeyEntry` và `TrustedCertificateEntry` tùy loại/store/provider. Việc gọi:

```java
KeyStore ks = KeyStore.getInstance("PKCS12");
ks.load(null, password);
ks.setEntry("data-v1",
    new KeyStore.SecretKeyEntry(aesKey),
    new KeyStore.PasswordProtection(password));
```

chỉ mô tả việc tạo và thêm entry. **Không tự có** rotation scheduler, IAM, tenant isolation, revocation log, dữ liệu migration hay remote audit. `KeyStore` API có thao tác `deleteEntry`, nhưng đó chỉ là xóa một entry tại nơi quản lý hiện tại, không phải bằng chứng tất cả các bản sao v1 đều biến mất.

Cần bảo vệ password dùng với `PKCS12` khác với dữ liệu cần mã hóa; hard-code store password vào source chỉ phù hợp minh họa, không production.

### 11.2. `keytool` và chứng thư

Ví dụ tạo cặp RSA + chứng thư tự ký trong file PKCS12 để **thử nghiệm**:

```shell
keytool -genkeypair -alias service-sign-v1 -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -keystore service-sign.p12 -storetype PKCS12 -validity 365
```

Lệnh trên chạy tương tác hỏi password/subject; không có stdout cố định. **Self-signed certificate không tự được các client khác tin cậy**. Production cần cơ chế CA/PKI hoặc trusted-key distribution phù hợp, policy bảo vệ private key và kế hoạch rotate trước expiry.

Xem alias/public certificate trong keystore:

```shell
keytool -list -v -keystore service-sign.p12 -storetype PKCS12
```

**Không** truyền password thực bằng argument command-line nếu có nguy cơ lộ process list/shell history. Không đưa file private key và store password vào cùng repository, Docker image hoặc bộ sao lưu công khai.

### 11.3. TLS certificate rotation

TLS thường cần cập nhật key pair/certificate chain, cấu hình server/client trust, OCSP/CRL hoặc policy PKI và triển khai đồng bộ. Việc có certificate mới trên disk không có nghĩa các kết nối/server instance đã reload. Phải kiểm handshake thật, trust chain, hostname, notBefore/notAfter, private-key possession, rollback và thời hạn overlapping certificates.

**Nhớ:** đổi chứng thư hoặc alias không tự đổi khóa mã hóa dữ liệu trong database. Hai mục đích key khác nhau phải có inventory/lifecycle khác nhau.

## 12. Chương trình Java 17+ độc lập: sinh khóa, lưu trữ, mã hóa, rotate và retire

Tạo file **`KeyLifecycleDemo.java`**. Demo này mô phỏng vòng đời nhỏ của hai **AES data keys**:

1. Tạo v1 bằng `KeyGenerator`, đặt vào `PKCS12 KeyStore`, dùng v1 mã hóa một record.
2. Tạo v2 mới độc lập, lưu v2; serialized bytes của KeyStore được ghi ra buffer và nạp lại để minh họa **store/load** mà không tạo file thật.
3. Bắt đầu encrypt mới bằng v2; vẫn giải mã record v1 bằng v1 được lưu, chứng minh rotation không bắt buộc làm mất dữ liệu cũ.
4. Dùng `AES/GCM/NoPadding` với nonce 12 byte, tag 128 bit và AAD gắn với key version; thử sửa tag hoặc gán sai version.
5. Xóa alias v1 khỏi store *đang dùng*, xác nhận record v1 **không còn giải mã được qua store này**. Đây chỉ là mô phỏng retirement, **không phải quy trình destroy/compromise response production**.

**Giới hạn đã biết:** Password literal và KeyStore in-memory phục vụ demo, **không dùng để bảo vệ dữ liệu thật**. Trong ứng dụng thực tế, keystore password phải được đưa qua cơ chế secret management; runtime policy phải kiểm phép encrypt/decrypt theo state/tenant/authorization; cần persistence an toàn, backup, audit, nonce uniqueness ở quy mô lớn và key migration. JDK 17 với provider PKCS12 thông dụng hỗ trợ `SecretKeyEntry`; provider bên thứ ba có thể có giới hạn riêng.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class KeyLifecycleDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private record Envelope(
            int keyVersion, byte[] nonce, byte[] ciphertextAndTag) {}

    private static SecretKey newAesKey() throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(128, RNG); // Universal baseline for this demo.
        return generator.generateKey();
    }

    private static String alias(int version) {
        return "data-v" + version;
    }

    private static void put(KeyStore store, int version,
            SecretKey key, char[] password) throws Exception {
        store.setEntry(alias(version),
                new KeyStore.SecretKeyEntry(key),
                new KeyStore.PasswordProtection(password));
    }

    private static SecretKey read(KeyStore store, int version,
            char[] password) throws Exception {
        KeyStore.Entry entry = store.getEntry(alias(version),
                new KeyStore.PasswordProtection(password));
        if (!(entry instanceof KeyStore.SecretKeyEntry secret)) {
            throw new GeneralSecurityException(
                    "Key version unavailable");
        }
        return secret.getSecretKey();
    }

    // Domain separation + key version are authenticated as AAD.
    private static byte[] aad(int version) {
        return ("key-lifecycle-demo:v1:version=" + version)
                .getBytes(StandardCharsets.UTF_8);
    }

    private static Envelope seal(int version, SecretKey key,
            byte[] plaintext) throws Exception {
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(version));
        return new Envelope(
                version, nonce, cipher.doFinal(plaintext));
    }

    private static byte[] open(Envelope envelope, KeyStore store,
            char[] password) throws Exception {
        SecretKey key = read(store, envelope.keyVersion(), password);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
                new GCMParameterSpec(TAG_BITS, envelope.nonce()));
        cipher.updateAAD(aad(envelope.keyVersion()));
        return cipher.doFinal(envelope.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        // DEMO ONLY: password literal is NOT safe for production.
        char[] password = "demo-only-store-pass".toCharArray();
        try {
            KeyStore firstStore = KeyStore.getInstance("PKCS12");
            firstStore.load(null, password);

            SecretKey keyV1 = newAesKey();
            put(firstStore, 1, keyV1, password);

            byte[] payload =
                    "encrypted customer record".getBytes(
                            StandardCharsets.UTF_8);
            Envelope oldRecord = seal(1, keyV1, payload);

            // Rotation: new key for new encryption.
            SecretKey keyV2 = newAesKey();
            put(firstStore, 2, keyV2, password);
            Envelope newRecord = seal(2, keyV2, payload);

            // Demonstrate serialization + reload of the key store.
            ByteArrayOutputStream serialized =
                    new ByteArrayOutputStream();
            firstStore.store(serialized, password);
            KeyStore restored = KeyStore.getInstance("PKCS12");
            restored.load(new ByteArrayInputStream(
                    serialized.toByteArray()), password);

            boolean bothPresent =
                    restored.containsAlias(alias(1))
                    && restored.containsAlias(alias(2));
            boolean oldReadable = Arrays.equals(
                    payload, open(oldRecord, restored, password));
            boolean newReadable = Arrays.equals(
                    payload, open(newRecord, restored, password));

            // A different key version must NOT silently work.
            Envelope wrongVersion = new Envelope(
                    2, oldRecord.nonce(),
                    oldRecord.ciphertextAndTag());
            boolean wrongVersionRejected = false;
            try {
                open(wrongVersion, restored, password);
            } catch (AEADBadTagException expected) {
                wrongVersionRejected = true;
            }

            // GCM detects a changed authentication tag.
            byte[] changed = newRecord.ciphertextAndTag().clone();
            changed[changed.length - 1] ^= 1;
            Envelope tampered = new Envelope(
                    2, newRecord.nonce(), changed);
            boolean tamperRejected = false;
            try {
                open(tampered, restored, password);
            } catch (AEADBadTagException expected) {
                tamperRejected = true;
            }

            // Retire the v1 alias from the store used for lookups.
            restored.deleteEntry(alias(1));
            boolean v1RetiredFromStore =
                    !restored.containsAlias(alias(1));
            boolean oldUnavailable = false;
            try {
                open(oldRecord, restored, password);
            } catch (GeneralSecurityException expected) {
                oldUnavailable = true;
            }

            System.out.println("bothVersionsRestored=" + bothPresent);
            System.out.println("oldRecordReadableAfterRotation="
                    + oldReadable);
            System.out.println("newRecordReadable=" + newReadable);
            System.out.println("wrongVersionRejected="
                    + wrongVersionRejected);
            System.out.println("tamperRejected=" + tamperRejected);
            System.out.println("v1AliasRetired=" + v1RetiredFromStore);
            System.out.println("oldUnavailableThroughStore="
                    + oldUnavailable);
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch và chạy tại thư mục chứa file:

```shell
javac KeyLifecycleDemo.java
java KeyLifecycleDemo
```

**Stdout kỳ vọng trên Java 17 thông dụng hỗ trợ PKCS12 `SecretKeyEntry` và AES/GCM:**

```text
bothVersionsRestored=true
oldRecordReadableAfterRotation=true
newRecordReadable=true
wrongVersionRejected=true
tamperRejected=true
v1AliasRetired=true
oldUnavailableThroughStore=true
```

### 12.1. Giải thích kết quả

- `bothVersionsRestored=true`: KeyStore chứa alias v1 và v2 và có thể nạp lại từ định dạng đã serialize. **Không** có nghĩa việc bảo vệ password, backup và quyền truy cập đã đáp ứng production.
- `oldRecordReadableAfterRotation=true`: v2 xuất hiện không tự vô hiệu hóa v1; record cũ vẫn cần v1 cho decrypt. Đây là trạng thái **decrypt-old / encrypt-new** quan trọng khi migrate.
- `newRecordReadable=true`: key v2 encrypt/decrypt thành công với AES-GCM, cùng AAD và nonce.
- `wrongVersionRejected=true`: lấy ciphertext v1 nhưng gán key version 2 khiến decryption dùng key v2/AAD v2, nên GCM tag không khớp. Không được dùng cách “thử mọi key cho đến khi giải mã được” để bỏ qua ownership và policy.
- `tamperRejected=true`: sửa authentication tag khiến `AEADBadTagException`, ứng dụng phải từ chối bản mã.
- `v1AliasRetired=true`: alias v1 bị xóa **trong đối tượng KeyStore `restored`**, không phải trong mọi bản sao.
- `oldUnavailableThroughStore=true`: lookup v1 qua **store đang dùng** thất bại, nên oldRecord không giải mã được qua đường đó. **Không phải bằng chứng crypto-erasure**: biến `keyV1`, `firstStore` và bytes đã serialize vẫn tồn tại trong chương trình demo. Sự khác biệt này rất quan trọng khi định nghĩa “destroy key”.

**Cảnh báo bài học:** Code tạo nonce ngẫu nhiên mới cho mỗi lần encrypt ở quy mô minh họa. Production với lượng ciphertext lớn phải thiết kế uniqueness/usage limits theo key và môi trường, không tin rằng ngẫu nhiên có nghĩa không bao giờ trùng. `Envelope` là record chứa mảng mutable và chưa phải parser/format sản xuất, không có defensive copy, tenant ID, record ID, key registry/IAM hay persistence dữ liệu thật.

### 12.2. Vì sao không “xóa v1 ngay sau khi tạo v2”?

Nếu gọi `deleteEntry("data-v1")` ngay khi active v2, record v1 chưa migrate sẽ không mở được qua store hiện tại. Với hệ thống thực, còn có hàng triệu bản ghi và backup chưa scan. Cần **migration plan, dữ liệu kiểm kê, read compatibility, restore test và retention policy** trước khi retire/destroy.

Nếu v1 **bị compromise**, ta có thể phải khóa quyền mới lập tức, nhưng vẫn cần đường recovery rất hạn chế để re-encrypt. Đó là một luồng khẩn cấp khác với rotation định kỳ.

### 12.3. Những việc demo cố ý không làm

Demo không cấp credential cho người dùng, không lưu key file lên disk, không ghi log audit, không dùng KMS/HSM, không tạo certificate/PKI, không bảo đảm xóa raw key khỏi RAM, không triển khai decrypt-only permissions hay trạng thái compromised thực sự. Nó cho phép bạn nhìn thấy **khác biệt giữa tạo phiên bản mới, đọc dữ liệu cũ và xóa alias khỏi lookup**; sản phẩm thực tế cần ranh giới quyền và quản lý trạng thái trên server.

## 13. Các lỗi phổ biến, hậu quả và cách khắc phục

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Hard-code key/password trong source, image hoặc env chia sẻ | Rò cho nhiều bản deployment, khó rotate | KMS/HSM/secret manager, IAM/ACL, distribution an toàn |
| Sinh AES bằng `Random`, `Math.random()`, timestamp | Key có thể đoán được | `KeyGenerator`/`SecureRandom` hoặc key generation trong HSM/KMS |
| Cất private key và certificate vào public repository | Ai đọc repository có thể giả mạo chủ thể | Public certificate được phép phát, private key phải bí mật |
| Dùng cùng raw key giữa prod và test | Compromise môi trường test ảnh hưởng prod | Tách key material và policy theo môi trường |
| Dùng một key chung mọi tenant | Vượt ranh giới dữ liệu nếu quyền decrypt quá rộng | Key scoping/authorization theo tenant và context |
| Cấp quyền runtime `DeleteKey`/admin | Lỗi app có thể làm mất toàn bộ dữ liệu | Least privilege, separation of duties, approval |
| Mặc định mọi key version đều được encrypt | App ghi record mới bằng key đã retire | Trusted active-version registry, phép encrypt bị ràng buộc state |
| Rotation nhưng quên đưa key version vào envelope | Không biết dùng khóa nào để decrypt lịch sử | Versioned/authenticated metadata, lookup có policy |
| Xóa khóa cũ trước migration | Dữ liệu backup/record v1 không khôi phục | Reader hỗ trợ old versions, checkpoint và kiểm hết dependencies |
| Tưởng rewrap xong sẽ cứu dữ liệu nếu DEK lộ | DEK đã bị lộ vẫn decrypt bản mã cũ | Rotate DEK + re-encrypt + incident response |
| Dùng lại AES-GCM nonce dưới cùng key | Nguy cơ phá confidentiality và authenticity | Nonce uniqueness, giới hạn use, coordination qua restart |
| “Disable” rồi coi attacker không còn key | Bản copy/cached raw key ngoài KMS còn dùng được | Scope compromise, re-encrypt, revoke credentials và điều tra |
| Bấm delete ngay để chặn sự cố | Mất khả năng re-encrypt/recover trong incident | Containment có kiểm soát trước, hủy theo runbook |
| Coi `KeyStore.deleteEntry` là secure wipe | Key vẫn còn ở backup, memory, bản clone | Truy vết tất cả key material, hủy theo assurance mục tiêu |
| Chỉ đổi cert mà không kiểm TLS trust chain/reload | Server/client vẫn chạy cấu hình cũ, lỗi handshake | Test thật, rollout overlapping, revocation theo PKI |
| Log raw key hoặc `getEncoded()` | Mất bí mật và tạo bản sao khó xóa | Chỉ log key ID/version/operation/outcome |
| Dùng key ID client gửi để cho phép decrypt bất kỳ | Cross-tenant data access | Binding key↔tenant↔resource, server-side authorization |
| Không có backup key | Mất key = mất khả năng đọc ciphertext | Backup/restore drill theo chính sách, bảo vệ mọi bản sao |
| Không theo dõi expiration/cryptoperiod | Key sử dụng vượt hạn/không có owner | Inventory + alerts + scheduled/event-driven rotation |
| Mở lại backup keystore có key đã revoke | Vô tình tái kích hoạt key bị lộ | Restore phải áp dụng lại denylist/status từ registry đáng tin |

## 14. Tình huống luyện tập có đáp án

**Tình huống A – ứng dụng v1 → v2 nhưng không đọc được bản ghi cũ.**  
Nguyên nhân có thể là bỏ key version, xóa v1 quá sớm, hoặc parser chỉ hỗ trợ active key. Giải pháp: versioned envelope, v1 decrypt permission cho giai đoạn migration, reader-first rollout, dữ liệu inventory và QA trước retirement.

**Tình huống B – KEK trong KMS được rotate nhưng wrapped DEK cũ chưa rewrap.**  
Nếu policy hỗ trợ các key versions cũ cho unwrap thì dữ liệu có thể vẫn đọc, nhưng còn dependency với key material cũ; cần biết đúng semantic provider và lên kế hoạch rewrap/retire. Không đồng nhất “KMS auto-rotation” với “mọi ciphertext đã thay sang key material mới”.

**Tình huống C – một nhân viên cũ có bản sao raw AES key.**  
Rút IAM/KMS grant sẽ chặn API ở hệ thống hiện tại nhưng **không làm bản sao raw key mất tác dụng**. Cần xác định ciphertext liên quan, key exposure window, re-encrypt bằng key mới, hạn chế bản sao và xem quyền/secret bị lộ khác.

**Tình huống D – khóa ký đã hết hạn nhưng cần xác minh hợp đồng cũ.**  
Ngừng dùng private key ký mới; giữ public key/certificate và bằng chứng thời điểm ký theo policy lưu chữ ký dài hạn. Nếu private key bị lộ, không chỉ nhìn `Signature.verify == true` mà phải xét trạng thái compromise/time evidence/trust.

**Tình huống E – để “xóa dữ liệu” chỉ xóa DEK ở keystore chính.**  
Phải kiểm wrapped copies, backup, replicas, process memory, snapshot và chính sách recovery; còn cần xử lý bản copy plaintext/data indexes. Một thao tác delete alias không chứng minh tất cả bí mật đã biến mất.

**Tình huống F – khi deploy v2, một node cũ vẫn encrypt bằng v1.**  
Cần active-version registry, enforcement của key-management layer, deploy reader-first và quan sát audit số lần encrypt theo version; nếu có writer v1 phải fix trước khi retire.

**Tình huống G – có 10.000 record được mã hóa AES-GCM bằng cùng key, nonce ngẫu nhiên mỗi lần. Có thể mặc định an toàn mãi không?**  
Không. Phải tuân thủ giới hạn nonce/usage của GCM theo độ lớn hệ thống, xác suất trùng, concurrency/restart, threat model và tiêu chuẩn provider. Khi cần, dùng nonce counter được điều phối và rotate key trước giới hạn.

**Tình huống H – tenant A muốn decrypt record tenant B bằng cách thay `keyId` trong request.**  
Backend phải từ chối dựa trên tenant/resource authorization và key binding, dù keyId hợp lệ và key tồn tại trong KMS. Cryptography không tự làm business authorization.

## 15. Checklist vận hành trước khi go-live

- [ ] **Inventory:** mọi key có owner, purpose, algorithm, ID/version, môi trường, trạng thái, cryptoperiod, dependencies?
- [ ] **Generation:** được sinh bằng CSPRNG/HSM/KMS thích hợp, kích thước phù hợp, không seed cố định hoặc export không cần thiết?
- [ ] **Provisioning:** key được cấp tới đúng service/tenant, có IAM least privilege, approval và kênh phân phối bí mật?
- [ ] **Storage:** file keystore/password tách rời, backup được mã hóa, HSM/KMS policy rõ, restore đã được thử?
- [ ] **Usage:** encryption key được chọn bởi active-version registry, AAD/nonce hợp lệ, authentication tag được kiểm, quyền decrypt theo đối tượng?
- [ ] **Rotation:** có reader-first rollout, old decrypt-only, migration/rewrap/re-encrypt khi cần, xác nhận không còn old dependencies?
- [ ] **Revocation:** có incident runbook về suspected compromise, rút quyền, đánh giá bản sao và dữ liệu/chữ ký đã bị ảnh hưởng?
- [ ] **Destruction:** biết điều kiện hủy, retention/legal hold và cách chứng minh key không còn bản sao khả dụng?
- [ ] **Audit:** ghi metadata không nhạy cảm, giám sát use anomalies, truy vết create/activate/rotate/disable/delete?
- [ ] **Recovery:** có kế hoạch mất KMS/HSM, mất keystore password, disaster recovery, key escrow phù hợp và kiểm lại trạng thái revoked sau restore?

**Câu kết luận cần nhớ:** Sinh ra một khóa an toàn chỉ là bước đầu. **Cấp phát đúng đối tượng, lưu giữ đúng nơi, kiểm soát sử dụng, xoay phiên bản an toàn, thu hồi có ngữ nghĩa và hủy khi hết phụ thuộc** mới tạo thành vòng đời khóa đáng tin cậy.

## Tài liệu chính thống

- [NIST SP 800-57 Part 1 Rev. 5 – Recommendation for Key Management: General](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): key types, trạng thái vòng đời, cryptoperiod, tạo/backup/thu hồi/hủy key.
- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html): key inventory, least privilege, storage, key rotation và monitoring.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): key handling, AEAD, key storage, ciphertext và key lifecycle.
- [Java SE 17 – KeyGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html): tạo secret keys theo thuật toán.
- [Java SE 17 – KeyPairGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html): sinh keypairs.
- [Java SE 17 – SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn ngẫu nhiên mật mã cho key material và nonce.
- [Java SE 17 – KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): `SecretKeyEntry`, `PrivateKeyEntry`, `setEntry`, `getEntry`, `store/load` và `deleteEntry`.
- [Java SE 17 – Cipher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html) và [GCMParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html): AES-GCM, tag, nonce, AAD và authentication.
- [JDK 17 keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): tạo, quản lý key pair/certificate và keystore dạng PKCS12.
- [NIST SP 800-38D – Galois/Counter Mode](https://csrc.nist.gov/pubs/sp/800/38/d/final): đặc tính AEAD và yêu cầu về nonce/IV AES-GCM.
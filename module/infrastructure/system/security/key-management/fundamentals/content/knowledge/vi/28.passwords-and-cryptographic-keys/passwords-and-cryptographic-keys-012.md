# Không đưa password vào backup plaintext

**Không đưa password vào backup plaintext** là nguyên tắc yêu cầu mọi bản sao lưu phải được kiểm tra để không chứa mật khẩu, token, private key hoặc bí mật xác thực ở dạng có thể đọc trực tiếp. Một bản backup không mã hóa có thể gom dữ liệu từ nhiều hệ thống vào một file hoặc tập snapshot; nếu file đó bị tải xuống, gửi nhầm, lưu trên object storage công khai hoặc bị ransomware đánh cắp, kẻ tấn công có thể nhận được thông tin đủ để đăng nhập vào database, cloud, máy chủ, ứng dụng và hệ thống quản trị khóa.

Nguyên tắc này không có nghĩa tổ chức phải bỏ mọi dữ liệu bí mật khỏi kế hoạch khôi phục. Một số hệ thống cần khôi phục secret hoặc key để tiếp tục vận hành. Khi đó, bí mật phải được phân loại, mã hóa bằng khóa bảo vệ độc lập, giới hạn người có quyền truy cập và có quy trình restore được kiểm toán. **Bản backup plaintext không được chứa giá trị password hoặc secret có thể sử dụng trực tiếp.**

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Password và cryptographic key**. Nội dung kết nối bảo vệ password với vòng đời khóa mật mã: tạo, cấp phát, lưu trữ, sử dụng, backup, khôi phục, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Vì sao password trong backup plaintext nguy hiểm?

Password thường là thông tin xác thực có thể sử dụng trực tiếp. Khác với dữ liệu nghiệp vụ thông thường, một password bị lộ có thể giúp kẻ tấn công vượt qua bước xác thực và tiếp tục truy cập các tài nguyên khác.

Một file backup có thể tập trung:

- Password tài khoản database và tài khoản quản trị.
- API token, access token, refresh token và client secret.
- Password của keystore, private key container hoặc thiết bị.
- SSH private key, TLS private key và credential của service account.
- Secret trong file cấu hình, biến môi trường, pipeline CI/CD và infrastructure state.
- Password verifier, salt, pepper reference và dữ liệu định danh người dùng.
- Secret dùng để kết nối KMS, HSM, secret manager hoặc hệ thống backup.

Nếu các giá trị này được lưu plaintext, một sự cố ở nơi lưu backup có thể trở thành sự cố trên toàn bộ hệ thống. Kẻ tấn công không cần xâm nhập từng máy chủ; chỉ cần lấy một bản sao lưu có chứa credential dùng chung hoặc quyền cao.

Các hậu quả có thể gồm:

- Đăng nhập trái phép vào database hoặc hệ thống quản trị.
- Truy cập dữ liệu của nhiều tenant bằng một service credential.
- Dùng API token để gọi dịch vụ cloud hoặc tạo tài nguyên mới.
- Giải mã backup khác nếu cùng password hoặc key được tái sử dụng.
- Đăng nhập máy chủ qua SSH hoặc truy cập thiết bị bằng private key.
- Chiếm quyền pipeline để phát hành phần mềm hoặc lấy thêm secret.
- Duy trì quyền truy cập sau khi hệ thống nguồn đã thay password nếu bản sao lưu cũ vẫn còn hiệu lực.

## 2. Backup plaintext là gì?

**Plaintext backup** là bản sao lưu mà nội dung nhạy cảm có thể được đọc trực tiếp mà không cần giải mã bằng một khóa hoặc thông tin bảo vệ độc lập. File dump, archive, snapshot, export hoặc log có thể là plaintext backup nếu chứa dữ liệu đã giải mã.

Không nên chỉ dựa vào phần mở rộng file để phân loại. File có đuôi .zip, .tar, .sql, .json, .yaml, .csv hoặc .bak vẫn có thể chứa dữ liệu plaintext. Base64, gzip và các dạng nén/encoding không phải mã hóa.

| Dạng bản sao | Ví dụ | Rủi ro cần xem xét |
|---|---|---|
| Database dump | SQL dump hoặc export bảng cấu hình | Có thể chứa password verifier, token và dữ liệu nhạy cảm. |
| File archive | TAR/ZIP của thư mục ứng dụng | Có thể gom file .env, config, keystore và private key. |
| VM/container snapshot | Snapshot filesystem hoặc image | Có thể giữ secret trong file, swap, cache và log. |
| Object storage version | Bản cũ của object hoặc manifest | Xóa bản hiện tại không đồng nghĩa xóa mọi version. |
| Log/archive | Log ứng dụng, audit export, support bundle | Có thể chứa Authorization header, URL có token hoặc command argument. |
| CI/CD artifact | Build artifact, cache, pipeline bundle | Có thể vô tình đóng gói credential hoặc file cấu hình môi trường. |
| Offline media | Tape, disk hoặc thiết bị chuyển giao | Có thể thất lạc và nằm ngoài khả năng thu hồi nhanh. |

Mã hóa ổ đĩa hoặc storage volume không tự động chứng minh file export đã được bảo vệ theo đúng chính sách. Khi backup được tạo thành file dump rồi chuyển sang một storage khác, phải xác minh lớp mã hóa áp dụng cho chính bản backup đó.

## 3. Phân biệt password, password verifier và cryptographic key

Ba loại dữ liệu này có yêu cầu lưu trữ khác nhau:

| Loại | Có thể khôi phục giá trị gốc không? | Cách xử lý phù hợp |
|---|---|---|
| Password người dùng | Không nên có khả năng khôi phục từ hệ thống xác thực | Lưu password verifier bằng password hashing có salt riêng; không lưu password plaintext. |
| Service password/API secret | Ứng dụng có thể cần lấy lại để xác thực với hệ thống khác | Lưu trong secret manager hoặc vault; nếu cần backup, mã hóa bằng cơ chế độc lập. |
| Password bảo vệ file/key entry | Có thể cần khi restore keystore hoặc sử dụng entry | Quản lý trong secret manager/recovery vault tách khỏi bản backup được bảo vệ. |
| Private key/secret key | Là vật liệu mật mã, không phải password đăng nhập | Giữ trong KMS/HSM hoặc container được mã hóa; backup theo chính sách key management. |
| Password verifier | Dùng để kiểm tra password người dùng, không phải password gốc | Bảo vệ như dữ liệu nhạy cảm vì có thể bị tấn công đoán password offline. |

Password verifier thường được tạo bằng thuật toán password hashing chậm và có salt riêng, ví dụ Argon2id, scrypt, bcrypt hoặc PBKDF2 theo policy. Không mã hóa password người dùng theo cách có thể giải mã ngược chỉ để thuận tiện cho backup.

Password verifier vẫn là dữ liệu nhạy cảm. Kẻ tấn công có thể lấy bản dump và thử đoán password offline. Nếu hệ thống dùng pepper, pepper phải được giữ riêng trong secret manager/KMS/HSM; không đưa pepper vào cùng database dump hoặc backup chứa verifier.

## 4. Không lưu password người dùng dạng có thể đọc lại

Trong hệ thống xác thực, ứng dụng chỉ cần xác minh password người dùng nhập có khớp hay không. Ứng dụng không cần khôi phục password gốc.

Luồng đúng:

1. Người dùng gửi password qua kênh truyền được bảo vệ.
2. Ứng dụng chạy password hashing với salt và tham số đã cấu hình.
3. Ứng dụng so sánh verifier theo cách phù hợp.
4. Hệ thống lưu verifier, salt/metadata và phiên bản thuật toán.
5. Khi backup database, verifier vẫn được bảo vệ như dữ liệu nhạy cảm.

~~~mermaid
flowchart TD
    A["Người dùng nhập password"] --> B["Password hashing + salt riêng"]
    B --> C["Password verifier"]
    C --> D["Lưu verifier trong database"]
    D --> E["Backup database được mã hóa"]
    F["Password pepper"] --> G["Secret manager / KMS"]
    G --> B
~~~

Ví dụ cấu trúc bản ghi:

~~~sql
CREATE TABLE account_credential (
    account_id       BIGINT PRIMARY KEY,
    password_hash    VARCHAR(512) NOT NULL,
    hash_algorithm   VARCHAR(40) NOT NULL,
    hash_parameters  VARCHAR(512) NOT NULL,
    password_updated_at TIMESTAMP NOT NULL
);
~~~

Ví dụ chỉ minh họa metadata cần quản lý; định dạng hash thực tế thường chứa salt và tham số trong chuỗi verifier. Không lưu cột password_plaintext để tiện debug hoặc phục hồi.

Khi người dùng quên password, dùng quy trình reset có xác minh danh tính, token dùng một lần và thời hạn ngắn. Không gửi lại password cũ từ backup vì hệ thống không nên có khả năng đọc lại nó.

## 5. Những nguồn thường vô tình đưa password vào backup

Secret có thể lọt vào backup từ nhiều nơi ngoài database chính:

- File .env hoặc file properties đặt cạnh ứng dụng.
- YAML/JSON manifest chứa password inline.
- Script triển khai hoặc script backup có credential viết trực tiếp.
- Shell history, process arguments hoặc file log của job.
- File .pgpass, credential helper hoặc cấu hình client database.
- Java keystore, PKCS#12/PFX và file chứa private key.
- SSH directory, cloud CLI profile hoặc credential cache.
- Terraform state, Kubernetes Secret export và pipeline variables.
- Crash dump, heap dump, swap file, temporary directory và support bundle.
- Backup của home directory hoặc thư mục workspace nhà phát triển.

Trước khi bật backup cho một thư mục hoặc máy chủ, cần xác định các file và process có thể chứa secret. Một thư mục tên config hoặc backup không tự động an toàn; phải kiểm tra nội dung và quyền truy cập theo chính sách.

## 6. Không đặt password cạnh bản backup

Một sai lầm phổ biến là mã hóa file backup bằng password rồi lưu password trong cùng archive, cùng thư mục có quyền đọc giống nhau hoặc cùng ticket bàn giao.

Ví dụ thiết kế không an toàn:

~~~text
backup-2026-11-28.tar.enc
backup-password.txt
~~~

Nếu hai file có cùng quyền truy cập hoặc cùng được tải lên một nơi, kẻ tấn công có cả ciphertext và password. Lớp mã hóa khi đó không còn tạo rào cản đáng kể.

Password bảo vệ backup phải được phân phối qua kênh độc lập, chỉ cấp cho người hoặc workload có nhiệm vụ restore. Tốt hơn, dùng KMS/HSM hoặc secret manager để quản lý key-encryption key và policy giải mã. Không ghi password vào tên file, metadata công khai, log hoặc tài liệu vận hành được lưu cạnh backup.

## 7. Mã hóa backup trước khi rời vùng dữ liệu

Backup cần được mã hóa trước khi chuyển đến storage, media hoặc tài khoản quản trị khác. Cách thực hiện phụ thuộc hệ thống, nhưng cần xác định:

- Dữ liệu nào được mã hóa và ở thời điểm nào.
- Thuật toán/mode và tham số được sử dụng.
- Ai sở hữu khóa mã hóa backup.
- Khóa được lưu ở đâu và ai có quyền unwrap.
- Cách xác minh tính toàn vẹn và nguồn gốc bản backup.
- Cách khôi phục khi KMS/HSM hoặc vùng dữ liệu chính gặp sự cố.

Với backup chứa dữ liệu lớn, thường dùng **envelope encryption**: tạo DEK để mã hóa backup, sau đó dùng KEK trong KMS/HSM để bọc DEK. Backup chứa ciphertext, wrapped DEK và metadata cần thiết; KEK được giữ trong miền bảo vệ độc lập.

~~~mermaid
flowchart TD
    A["Dữ liệu nguồn"] --> B["Tạo DEK cho backup"]
    B --> C["Mã hóa backup bằng DEK"]
    B --> D["Yêu cầu KMS/HSM wrap DEK"]
    D --> E["KEK trong KMS/HSM"]
    C --> F["Ciphertext backup"]
    D --> G["Wrapped DEK + key ID/version"]
    F --> H["Backup storage"]
    G --> H
    E --> I["Giữ ngoài backup storage"]
~~~

Wrapped DEK có thể được lưu cùng ciphertext vì nó đã được bọc bằng KEK. Điều kiện quan trọng là KEK và quyền unwrap không nằm trong cùng miền truy cập với bản backup. Nếu kẻ tấn công có thể đọc backup và gọi KMS bằng một identity quá rộng, việc bọc DEK không đủ để bảo vệ dữ liệu.

## 8. Chọn khóa bảo vệ backup độc lập

Không nên dùng chính password của database, tài khoản quản trị hoặc private key nghiệp vụ làm khóa mã hóa backup.

Một thiết kế tốt phân biệt:

| Khóa/credential | Mục đích | Nguyên tắc |
|---|---|---|
| Database credential | Xác thực vào database | Không dùng làm backup encryption key. |
| Application secret | Xác thực service-to-service | Giữ trong secret manager, giới hạn theo workload. |
| DEK backup | Mã hóa một backup hoặc một backup set | Tạo ngẫu nhiên, phạm vi hẹp, version rõ ràng. |
| KEK backup | Bọc DEK backup | Quản lý trong KMS/HSM hoặc miền bảo vệ độc lập. |
| Recovery credential | Mở quy trình khôi phục khẩn cấp | Tách quyền, kiểm soát quorum và audit. |
| Password pepper | Tăng bảo vệ password verifier | Lưu ngoài database backup và không đưa vào cùng backup. |

Khóa bảo vệ backup cần có owner, purpose, thuật toán, version, thời hạn, policy và quy trình backup/restore riêng. Nếu KEK bị compromise, phải có kế hoạch thay thế và rewrap DEK; nếu DEK bị lộ, cần đánh giá backup nào bị ảnh hưởng và tạo bản mới.

## 9. Mã hóa bằng password: khi nào phù hợp?

Một số công cụ backup hỗ trợ password-based encryption. Cách này có thể phù hợp cho bản backup offline hoặc trao đổi có kiểm soát khi không có KMS, nhưng cần quản lý cẩn thận:

- Dùng passphrase dài, ngẫu nhiên và duy nhất cho từng backup scope.
- Dùng KDF phù hợp để dẫn xuất encryption key từ passphrase, với salt riêng và tham số đủ mạnh.
- Dùng chế độ mã hóa có xác thực (AEAD) hoặc cơ chế integrity được chuẩn hóa.
- Không tự thiết kế thuật toán mã hóa hoặc tự ghép hash/cipher.
- Lưu passphrase qua kênh độc lập, không cùng backup.
- Kiểm thử khả năng restore trước khi đưa bản backup vào retention dài hạn.

Salt không phải bí mật; có thể lưu cùng ciphertext. Passphrase thì phải giữ riêng. Nếu công cụ dùng KDF hoặc cipher yếu, chỉ tăng độ dài passphrase không giải quyết hết rủi ro.

Không dùng password người dùng thông thường làm DEK trực tiếp. Nếu phải dùng passphrase để bảo vệ backup, cần KDF được phê duyệt như Argon2id hoặc PBKDF2 theo yêu cầu tương thích/compliance, cùng tham số được ghi nhận trong metadata.

## 10. Secret manager và backup của secret

Secret manager là nơi quản lý credential tập trung, thường hỗ trợ policy, audit, versioning và phân phối secret cho workload. Backup của secret manager cần có mô hình bảo vệ riêng vì nó có thể chứa nhiều credential có quyền cao.

Các nguyên tắc:

- Backup vault bằng cơ chế native được nhà cung cấp hỗ trợ.
- Mã hóa bản backup bằng key thuộc miền quản trị riêng.
- Tách quyền export secret, quản trị vault và restore vault.
- Giữ audit ai tạo, tải, đọc hoặc khôi phục backup.
- Giới hạn quyền của workload; không cấp quyền đọc toàn bộ vault.
- Lưu version và metadata để khôi phục đúng secret.
- Có phương án khôi phục khi chính secret manager không sẵn sàng.

Nếu có thể tái tạo credential sau restore, ưu tiên reissue hoặc rotate secret thay vì giữ nhiều bản sao password dài hạn. Backup secret chỉ nên tồn tại khi yêu cầu khôi phục và threat model chứng minh cần thiết.

## 11. File cấu hình và biến môi trường

File cấu hình thường là nguồn rò rỉ password vì chúng được đưa vào repository, container image, deployment bundle hoặc backup thư mục ứng dụng.

Thay vì lưu giá trị trực tiếp:

~~~yaml
database:
  host: db.internal
  username: orders-service
  passwordRef: secret://production/orders/database-password
~~~

Ứng dụng lấy password tại runtime bằng identity được cấp quyền. File backup cấu hình chỉ cần giữ secret reference, tên service, version hoặc metadata không nhạy cảm.

Biến môi trường có thể xuất hiện trong process inspection, diagnostic dump hoặc crash report tùy nền tảng. Nếu dùng environment injection, phải giới hạn quyền đọc process và tránh dump environment vào log. Với credential nhạy cảm, ưu tiên cơ chế secret file/agent/socket hoặc API của secret manager theo nền tảng.

Không đưa file .env thật vào repository, container image hoặc backup chung. Nếu cần sao lưu template cấu hình, chỉ giữ placeholder và secret reference.

## 12. Database backup và password verifier

Database dump có thể chứa bảng người dùng, password verifier, reset token, API key, session token và thông tin định danh. Dù không có password plaintext, bản dump vẫn có giá trị cao đối với kẻ tấn công.

Đối với tài khoản người dùng:

- Chỉ lưu password verifier từ password hashing phù hợp.
- Dùng salt riêng cho từng verifier.
- Giữ pepper trong secret manager/KMS tách khỏi database.
- Không lưu password reset token lâu hơn thời hạn cần thiết.
- Xóa hoặc vô hiệu hóa token/session đã hết hạn theo chính sách.
- Bảo vệ database backup bằng mã hóa và kiểm soát truy cập.

Đối với service account:

- Ưu tiên credential ngắn hạn hoặc workload identity nếu nền tảng hỗ trợ.
- Không lưu password service trong bảng cấu hình plaintext.
- Nếu ứng dụng cần secret gốc, lưu trong vault và chỉ backup qua quy trình được phê duyệt.
- Có kế hoạch rotate sau khi restore hoặc sau sự cố rò rỉ.

Password verifier có thể bị tấn công offline nếu dump bị lộ. Cần xem nó là dữ liệu xác thực nhạy cảm, áp dụng password hashing đủ mạnh và giám sát dấu hiệu credential stuffing hoặc reset bất thường sau sự cố.

## 13. Keystore, certificate và private key trong backup

File PKCS#12/PFX, JKS hoặc file chứa private key có thể là tài sản chứa bí mật. Một bản backup keystore có thể cần thiết cho disaster recovery, nhưng không được đặt password bảo vệ keystore cạnh file backup.

Các yêu cầu:

- Phân loại keystore theo loại entry và mức độ nhạy cảm.
- Giới hạn ai có thể export, đọc hoặc restore private key.
- Mã hóa file backup bằng cơ chế độc lập với password của keystore.
- Lưu key ID, alias, certificate fingerprint và version trong inventory phù hợp.
- Không lưu password/PIN trong manifest hoặc log.
- Kiểm thử restore trên provider/backend tương thích.
- Với HSM non-exportable key, dùng quy trình backup/clone chính thức của HSM.

Certificate công khai không phải private key, nhưng certificate chain và metadata vẫn có thể tiết lộ cấu trúc hạ tầng. Private key và secret key phải được bảo vệ theo chính sách key management.

## 14. Backup của cloud credential và token

Cloud CLI profile, access key, service account JSON, refresh token và API token có thể cấp quyền rộng. Nếu được đóng gói trong home directory hoặc backup workstation, chúng có thể trở thành đường truy cập vào tài khoản cloud.

Ưu tiên:

- Workload identity hoặc credential ngắn hạn thay cho access key dài hạn.
- Secret manager hoặc vault thay cho file credential tĩnh.
- Phân quyền theo resource và operation cần thiết.
- Tách môi trường development, staging và production.
- Không backup token cache hoặc credential file nếu có thể tái xác thực an toàn.
- Nếu phải lưu credential phục hồi, mã hóa riêng và kiểm soát quorum.
- Sau sự cố, revoke token và phát hành credential mới.

Không giả định token hết hạn là đã vô hiệu hóa mọi bản sao. Refresh token, client secret hoặc access key dài hạn có thể vẫn còn hiệu lực và phải được thu hồi ở hệ thống cấp phát.

## 15. Quyền truy cập vào backup storage

Mã hóa là một lớp bảo vệ; quyền truy cập storage vẫn cần được kiểm soát.

| Biện pháp | Mục đích |
|---|---|
| Least privilege | Chỉ backup service được ghi; chỉ restore operator được đọc/khôi phục theo phê duyệt. |
| Tách account/project | Giảm khả năng một credential production đọc hoặc xóa mọi backup. |
| MFA và strong authentication | Bảo vệ tài khoản quản trị storage và KMS. |
| Dual control/quorum | Yêu cầu nhiều người cho thao tác restore hoặc export nhạy cảm. |
| Immutable retention/Object Lock | Ngăn sửa hoặc xóa backup trong thời hạn bảo vệ. |
| Offline/air-gapped copy | Giảm khả năng ransomware truy cập đồng thời production và backup. |
| Network restriction | Chỉ cho phép backup/restore từ network hoặc workload được phê duyệt. |
| Audit và alert | Phát hiện download bất thường, thay đổi policy hoặc xóa hàng loạt. |

Tài khoản có quyền đọc backup không nên mặc định có quyền đọc KEK trong KMS. Tài khoản có quyền quản trị KMS cũng không nên mặc định có quyền tải toàn bộ backup. Tách hai miền quyền giúp giảm khả năng một danh tính duy nhất lấy được cả ciphertext và khóa giải mã.

## 16. Metadata của backup cần lưu gì?

Metadata giúp khôi phục đúng backup và đúng phiên bản khóa mà không phải ghi password vào manifest.

Ví dụ:

~~~yaml
backupId: orders-prod-2026-11-28T020000Z
dataSet: orders-production
formatVersion: 3
encryption:
  algorithm: AES-256-GCM
  keyId: backup-kek-prod-v4
  keyVersion: 4
  wrappedDekLocation: embedded
createdAt: 2026-11-28T02:00:00Z
integrity:
  manifestSignature: detached
  checksumAlgorithm: SHA-256
~~~

Đây là metadata minh họa; tên trường và thuật toán phải phù hợp hệ thống thực tế. Không ghi passphrase, DEK dạng rõ, KEK bytes, token hoặc private key vào manifest.

Metadata cần được xác thực để kẻ tấn công không thể thay key ID, version hoặc vị trí dữ liệu nhằm chuyển hướng restore. Có thể ký manifest bằng khóa ký riêng được quản lý độc lập hoặc dùng cơ chế integrity của backup platform.

## 17. Kiểm tra trước khi tạo backup

Một quy trình pre-backup có thể thực hiện:

1. Xác định dữ liệu và hệ thống nằm trong scope.
2. Phân loại password, verifier, token, certificate, private key và secret khác.
3. Xác định secret nào không cần đưa vào backup vì có thể tái tạo hoặc reissue.
4. Quét file/config/log/artifact theo chính sách để phát hiện secret có nguy cơ plaintext.
5. Xác minh backup encryption đã được bật và key reference hợp lệ.
6. Xác minh storage destination, quyền, retention và immutable policy.
7. Ghi metadata và audit, không ghi giá trị secret.
8. Chạy kiểm tra integrity sau khi tạo.

Quét secret chỉ là biện pháp hỗ trợ; regex hoặc scanner có thể bỏ sót định dạng lạ và tạo false positive. Cần kết hợp phân loại tài sản, kiểm soát cấu hình và review quy trình backup.

## 18. Kiểm tra bản backup sau khi tạo

Sau khi tạo backup, không chỉ kiểm tra file có tồn tại hoặc kích thước lớn hơn 0. Cần xác minh:

- Backup đã được mã hóa bằng thuật toán và key reference dự kiến.
- Không có password/token/private key plaintext trong archive, manifest, log hoặc temporary file.
- Wrapped DEK và metadata có thể được đọc, nhưng không thể unwrap nếu thiếu quyền KMS/HSM.
- Checksum/chữ ký manifest hợp lệ.
- Bản backup đã đến storage đích và có retention/immutability đúng.
- Các bản tạm, staging copy và upload cache được xử lý theo chính sách.
- Audit ghi nhận job, workload identity, key ID và kết quả.

Việc kiểm tra không được in giá trị secret ra terminal hoặc log. Nếu scanner phát hiện secret, chỉ báo loại phát hiện, vị trí và fingerprint đã che bớt; không hiển thị toàn bộ giá trị.

## 19. Restore an toàn

Restore là thời điểm cần mở dữ liệu và có thể tái tạo secret trong bộ nhớ hoặc filesystem. Quy trình phải giới hạn người, máy và thời gian thực hiện.

~~~mermaid
flowchart TD
    A["Yêu cầu restore"] --> B["Xác minh phê duyệt và phạm vi"]
    B --> C["Lấy backup ciphertext"]
    C --> D["Xác minh manifest/integrity"]
    D --> E["KMS/HSM kiểm tra quyền unwrap"]
    E --> F["Giải mã trong môi trường cô lập"]
    F --> G["Kiểm tra dữ liệu và secret"]
    G --> H["Reissue/rotate credential nếu cần"]
    H --> I["Đưa hệ thống vào vận hành"]
    I --> J["Audit và đóng phiên restore"]
~~~

Quy trình restore nên:

1. Xác minh yêu cầu, owner, người phê duyệt và môi trường đích.
2. Lấy đúng backup ID, version và manifest đã ký.
3. Xác minh checksum/chữ ký trước khi giải mã.
4. Lấy quyền unwrap DEK qua identity tạm thời có phạm vi hẹp.
5. Giải mã trong môi trường cô lập, hạn chế truy cập và log.
6. Kiểm tra dữ liệu, key version và certificate chain.
7. Rotate/reissue credential nếu backup có thể chứa secret đã cũ hoặc đã lộ.
8. Xóa temporary plaintext theo quy trình và xác minh cleanup.
9. Ghi audit, đóng quyền tạm thời và thu hồi session.

Không restore backup production trực tiếp vào môi trường development nếu dữ liệu hoặc credential chưa được làm sạch. Bản sao production có thể mang theo token, password verifier, thông tin cá nhân và secret còn hiệu lực.

## 20. Bảo đảm có thể khôi phục khóa giải mã

Mã hóa backup sẽ vô ích nếu KEK hoặc recovery path bị mất. Trước khi áp dụng, phải có kế hoạch duy trì khả năng unwrap trong suốt thời hạn retention:

- Giữ key ID/version và policy cần thiết.
- Có backup/replication của KMS/HSM theo hướng dẫn nhà cung cấp.
- Tách miền lỗi và tài khoản quản trị.
- Dùng quorum hoặc M-of-N recovery cho khóa quan trọng nếu policy yêu cầu.
- Lưu recovery procedure trong kho tài liệu được kiểm soát, không ghi secret vào cùng backup.
- Kiểm thử restore khi KMS chính không khả dụng.
- Không xóa KEK version cũ khi backup còn phụ thuộc.

Khi rotate KEK, có thể rewrap DEK đã lưu hoặc giữ key version cũ trong trạng thái chỉ cho phép decrypt/unwrap. Chỉ xóa version cũ sau khi mọi backup phụ thuộc đã hết retention hoặc đã được re-encrypt/rewrap và xác minh.

## 21. Password của backup và quy trình bàn giao

Nếu buộc phải dùng passphrase thay cho KMS:

- Tạo passphrase ngẫu nhiên, dài và không tái sử dụng.
- Lưu passphrase trong password manager/vault riêng với quyền truy cập giới hạn.
- Gửi passphrase qua kênh khác với kênh gửi backup.
- Yêu cầu xác minh danh tính người nhận trước khi cấp.
- Đặt thời hạn và thu hồi sau khi hoàn tất restore nếu không cần giữ.
- Ghi audit ai tạo, cấp và sử dụng passphrase.
- Không đưa passphrase vào ticket, chat log hoặc file hướng dẫn restore được lưu cùng backup.

Nếu cần escrow passphrase cho DR, dùng recovery vault có phân quyền, MFA, dual control và quy trình kiểm tra định kỳ. Không gửi một password chung cho nhiều nhóm hoặc lưu bản in không kiểm soát.

## 22. Ransomware và backup immutable

Ransomware thường tìm cách xóa hoặc mã hóa backup để ngăn khôi phục. Nếu credential production có quyền ghi/xóa backup storage, kẻ tấn công chiếm được máy chủ có thể xóa cả bản sao lưu.

Để giảm rủi ro:

- Dùng account/project riêng cho backup storage.
- Tách quyền ghi backup khỏi quyền xóa và thay đổi retention.
- Dùng immutable retention hoặc object lock cho thời hạn đã định.
- Có bản sao offline/air-gapped theo yêu cầu phục hồi.
- Không dùng cùng credential quản trị production và backup.
- Giám sát thay đổi policy, xóa hàng loạt và download bất thường.
- Kiểm thử restore định kỳ để phát hiện backup hỏng hoặc bị mã hóa.

Immutable storage không thay thế mã hóa. Nếu backup immutable nhưng plaintext, kẻ tấn công vẫn có thể đọc dữ liệu nếu lấy được quyền download.

## 23. Xử lý khi phát hiện password trong backup plaintext

Nếu phát hiện password hoặc secret có thể sử dụng trong bản backup không được bảo vệ:

1. Cô lập quyền truy cập vào bản backup và storage liên quan.
2. Xác định bản nào, version nào, replica nào và ai đã truy cập.
3. Phân loại secret: user password, service credential, token, private key, keystore password hay recovery secret.
4. Revoke hoặc rotate credential còn hiệu lực; thu hồi session/token nếu cần.
5. Đánh giá password verifier có nguy cơ bị crack offline và áp dụng reset/rehash phù hợp.
6. Nếu private key bị lộ, revoke certificate liên quan, tạo key mới và xử lý key cũ theo incident response.
7. Kiểm tra log, download history, access policy và dấu hiệu sử dụng trái phép.
8. Xử lý mọi bản sao plaintext theo retention/legal hold và quy trình destruction.
9. Tạo backup mới đã mã hóa và xác minh trước khi tiếp tục chu kỳ.
10. Ghi lại phạm vi, nguyên nhân, hành động và bằng chứng audit.

Chỉ xóa file backup khỏi vị trí hiện tại là chưa đủ nếu object version, replica, snapshot, offline media hoặc bản tải xuống vẫn tồn tại. Cần xác định toàn bộ đường sao chép và nghĩa vụ retention trước khi kết thúc incident.

## 24. Kiểm soát trong script và công cụ backup

Script backup thường chạy với quyền cao và có thể làm lộ secret qua command line, shell history, process listing hoặc log.

Tránh:

- Hardcode password hoặc token trong script.
- Truyền secret trực tiếp bằng command-line argument.
- In toàn bộ environment hoặc config khi debug.
- Bật shell tracing với biến chứa secret.
- Ghi secret vào temporary file không có quyền hạn chế.
- Đưa file credential vào archive theo glob rộng.

Ưu tiên:

- Workload identity hoặc credential ngắn hạn.
- Secret manager API/agent theo quyền tối thiểu.
- Cơ chế prompt hoặc secret file có quyền truy cập chặt nếu nền tảng yêu cầu.
- Tắt tracing hoặc redaction cho bước xử lý secret.
- Temporary directory riêng, cleanup và kiểm tra sau khi job kết thúc.
- Tách log vận hành khỏi payload backup và không ghi nội dung bí mật.

Với PostgreSQL, ví dụ file .pgpass có thể được dùng thay cho password trong command line; file này vẫn là credential và phải có quyền filesystem phù hợp, không được vô tình đưa vào backup thư mục home. Cách lấy credential phải theo tài liệu database và môi trường triển khai.

## 25. Retention và xóa bản sao chứa secret

Backup có thể tồn tại lâu hơn dữ liệu nguồn. Khi secret đã rotate hoặc bị revoke, bản backup cũ vẫn có thể chứa giá trị trước đó.

Retention policy cần xác định:

- Thời hạn giữ backup theo loại dữ liệu.
- Bản nào immutable và khi nào hết thời hạn khóa.
- Cách xử lý legal hold hoặc yêu cầu điều tra.
- Cách xóa bản backup và các version/replica liên quan.
- Cách xử lý media offline và bản sao do bên thứ ba lưu.
- Khi nào cần rotate credential chỉ vì bản backup cũ đã được truy cập.
- Khi nào cần re-encrypt hoặc rewrap backup theo key version mới.

Không xóa KEK chỉ vì credential đã rotate nếu backup hợp lệ vẫn cần nó để restore. Ngược lại, không giữ secret cũ vô thời hạn chỉ vì có một bản backup không còn cần thiết. Retention và key lifecycle phải được quản lý cùng nhau.

## 26. Kiểm toán và bằng chứng

Một quy trình backup an toàn cần lưu dấu vết đủ để trả lời:

- Ai hoặc workload nào tạo backup?
- Backup ID, dataset, môi trường và thời điểm nào?
- Thuật toán, provider, key ID/version nào được sử dụng?
- Ai có quyền đọc ciphertext và ai có quyền unwrap DEK?
- Có lần export/download/restore nào bất thường không?
- Backup đã được kiểm tra integrity và restore drill chưa?
- Temporary plaintext đã được cleanup chưa?
- Credential nào đã được rotate sau sự cố?

Audit log phải được bảo vệ chống sửa đổi và lưu theo chính sách. Không ghi password, token, private key bytes, DEK dạng rõ hoặc nội dung nhạy cảm. Có thể ghi key ID, principal, operation, thời điểm, kết quả và request ID.

## 27. Ví dụ thực tế: backup ứng dụng bán hàng

Một ứng dụng bán hàng có database, API service, TLS certificate và kết nối tới cổng thanh toán. Backup hàng đêm cần khôi phục dữ liệu và cấu hình khi trung tâm dữ liệu gặp sự cố.

Thiết kế:

1. Database lưu password verifier của người dùng, không lưu password plaintext.
2. Service credential và API token được quản lý trong secret manager; backup cấu hình chỉ giữ secret reference.
3. TLS private key nằm trong HSM hoặc keystore được bảo vệ; quy trình DR dùng backup chính thức của backend.
4. Job backup xác thực bằng workload identity có quyền đọc dữ liệu cần thiết.
5. Backup được mã hóa bằng DEK riêng cho backup set; DEK được KMS/HSM wrap bằng KEK backup.
6. Ciphertext và wrapped DEK được lưu trong tài khoản backup tách biệt, có immutable retention.
7. KMS policy chỉ cho phép restore role được phê duyệt unwrap DEK.
8. Restore diễn ra trong môi trường cô lập, kiểm tra integrity rồi reissue/rotate credential cần thiết trước khi mở traffic.
9. Audit ghi backup ID, key version, principal, operation và kết quả.

Nếu một nhân viên tải nhầm file backup, người đó chỉ nhận ciphertext và metadata không chứa password. Nếu kẻ tấn công chiếm storage account, họ vẫn cần quyền unwrap trong miền KMS riêng. Nếu KMS chính gặp sự cố, quy trình DR dùng replica/recovery quorum đã được diễn tập.

## 28. Checklist trước khi đưa backup vào production

Trước khi bật lịch backup, hãy xác nhận:

- [ ] Đã phân loại password, verifier, token, private key, secret key và credential.
- [ ] Không có password hoặc secret sử dụng trực tiếp trong backup plaintext.
- [ ] Password người dùng được lưu dưới dạng verifier bằng password hashing phù hợp.
- [ ] Pepper và secret manager credential được giữ ngoài database backup.
- [ ] File cấu hình chỉ chứa secret reference hoặc placeholder.
- [ ] Log, shell history, environment dump và temporary file không làm lộ secret.
- [ ] Keystore/PFX/private key được phân loại và backup theo policy riêng.
- [ ] Backup được mã hóa trước khi rời vùng dữ liệu nguồn.
- [ ] DEK/KEK được tách biệt; KEK nằm trong KMS/HSM hoặc miền bảo vệ độc lập.
- [ ] Password bảo vệ backup không được lưu cạnh backup.
- [ ] Storage account, IAM, MFA, dual control và immutable retention được cấu hình.
- [ ] Metadata có key ID/version và integrity protection, không chứa secret.
- [ ] Restore đã được kiểm thử cùng key recovery path.
- [ ] Có kế hoạch rotate/revoke khi backup bị lộ.
- [ ] Có retention và destruction cho mọi version, replica và media.
- [ ] Audit ghi đủ principal, operation, key version và kết quả mà không lộ bí mật.

## 29. Checklist khi restore

Trước và sau mỗi lần restore:

- [ ] Yêu cầu restore có owner, lý do, phạm vi và phê duyệt.
- [ ] Backup ID, version, manifest và checksum/chữ ký đã được xác minh.
- [ ] Người thực hiện dùng identity riêng, MFA và quyền tạm thời.
- [ ] KMS/HSM chỉ unwrap đúng key version và backup scope.
- [ ] Dữ liệu được giải mã trong môi trường cô lập.
- [ ] Không ghi password, token hoặc key bytes vào log.
- [ ] Secret được kiểm kê; credential không còn hợp lệ được revoke/rotate.
- [ ] Dữ liệu production không được đưa vào môi trường dev/test khi chưa sanitize.
- [ ] Temporary plaintext và session được cleanup.
- [ ] Quyền tạm thời được thu hồi và audit hoàn tất.

Không đưa password vào backup plaintext là yêu cầu bảo vệ cả dữ liệu lẫn đường truy cập vào hệ thống. Hãy lưu password người dùng dưới dạng verifier, giữ service secret trong vault, mã hóa backup bằng khóa độc lập và bảo đảm quyền restore được kiểm soát. Một bản backup chỉ thực sự hữu ích khi vừa bảo vệ được bí mật trong thời gian lưu giữ, vừa có key recovery path đã được kiểm thử khi cần khôi phục.

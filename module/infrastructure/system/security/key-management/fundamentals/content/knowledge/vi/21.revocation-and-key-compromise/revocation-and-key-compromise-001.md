# Key compromise là gì? — Nhận diện, đánh giá và ứng phó khi khóa mật mã mất an toàn

## 1. Khái niệm Key Compromise

**Key compromise (khóa mật mã bị xâm phạm)** là tình trạng **tính bí mật, tính toàn vẹn, quyền kiểm soát hoặc độ tin cậy đối với một khóa mật mã không còn đáp ứng giả định bảo mật ban đầu**. Trường hợp trực quan nhất là **private key, KEK, DEK hoặc MAC key bị một bên không được phép lấy được**. Tuy nhiên, sự cố liên quan khóa còn có thể xuất hiện dưới dạng **lạm dụng API ký/giải mã**, thay đổi trái phép key policy, đánh tráo public key/trust anchor, hoặc vật liệu khóa được tạo bằng nguồn ngẫu nhiên không an toàn.

Ví dụ: một hệ thống Java dùng **AES-GCM DEK** để mã hóa dữ liệu hóa đơn và dùng KMS để bảo vệ DEK. Nếu DEK dạng rõ bị đưa vào log, những ai có quyền xem bản log có thể có khả năng giải mã ciphertext liên quan. Dù KMS vẫn giữ KEK an toàn, **bản DEK đã xuất hiện ngoài ranh giới được phép** phải được điều tra như một sự cố về khóa.

Ví dụ khác: private signing key **không rời HSM**, nhưng attacker chiếm workload identity có quyền gọi **Sign** và yêu cầu ký một lệnh thanh toán giả. Đây là **lạm dụng khả năng sử dụng khóa**; chưa có bằng chứng raw private key bị trích xuất. Tác động đối với giao dịch có thể nghiêm trọng dù tính non-exportable của key material chưa bị phá.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học thuộc chương **Revocation và compromise**. Chủ đề liên kết toàn bộ vòng đời khóa **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy** với mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Điểm then chốt:** Khi nói “khóa bị compromise”, phải chỉ rõ **khóa nào, vật liệu hay khả năng sử dụng nào bị ảnh hưởng, bằng chứng đến đâu, đối thủ có thể làm gì với khóa đó, và những ciphertext/chữ ký/dịch vụ nào còn phụ thuộc vào nó**. “Đã đổi khóa” không đủ để khẳng định sự cố đã được khắc phục.

### 1.1. Khóa nào có thể bị compromise?

| Loại khóa | Vật liệu cần bảo vệ | Hậu quả nếu mất kiểm soát |
| --- | --- | --- |
| **Symmetric DEK** | AES/AEAD key dùng trực tiếp để mã hóa payload | Ciphertext được mã hóa bằng DEK có thể bị giải mã hoặc thao túng tùy mode, dữ liệu và điều kiện tấn công |
| **KEK / wrapping key** | Key dùng để bọc các DEK | Có thể mở nhiều wrapped DEK phụ thuộc, mở rộng blast radius |
| **HMAC/MAC key** | Secret chia sẻ cho bên phát và kiểm tra tag | Bên có secret có thể tạo tag giả; không phân biệt được hai bên cùng biết secret chỉ từ HMAC |
| **Private signing key** | RSA-PSS/ECDSA/Ed25519 private material | Có thể tạo chữ ký giả và mạo danh chủ thể ký theo trust policy |
| **Private decryption key** | RSA-OAEP/recipient private key | Có thể giải mã wrapped DEK hoặc dữ liệu mã hóa cho public key tương ứng |
| **Key-agreement private key** | ECDH/X25519 long-term hoặc ephemeral secret | Có thể ảnh hưởng phiên/thiết lập khóa tùy giao thức, xác thực và forward secrecy |
| **Root/intermediate CA private key** | Khóa ký chứng chỉ của CA | Có thể cấp chứng chỉ giả được những bên tin CA chấp nhận; phạm vi thường rất lớn |
| **KMS/HSM credentials, grants** | Quyền API sử dụng khóa thay vì raw material | Có thể Sign/Decrypt/Unwrap trái phép trong phạm vi principal được cấp |

**Public key** thường **không phải bí mật**. Việc nhiều người đọc được public key là điều bình thường. Nguy cơ là **thay public key được tin bằng key của attacker**, chiếm quyền phát hành public keys, hoặc lộ **private key tương ứng**.

### 1.2. Tính bí mật của key khác quyền sử dụng key

Hai câu hỏi phải tách riêng:

1. **Attacker đã lấy được raw key material chưa?** Nếu có, attacker có thể dùng khóa ở ngoài KMS/HSM và có thể giữ bản sao ngay cả sau khi tổ chức thu hồi quyền.
2. **Attacker có thể yêu cầu hệ thống đang giữ key thực hiện phép toán không?** Nếu có, attacker có thể tạo chữ ký hoặc giải mã qua API mà không sở hữu raw key bytes.

Một khóa **non-exportable** thường làm khó hoặc ngăn việc trích xuất qua API thông thường, nhưng không tự chứng minh hệ thống không có **signing/decryption oracle**. Ngược lại, thu hồi một IAM grant có thể dừng API abuse nhưng **không thu hồi được raw key đã bị sao chép**.

## 2. Các tình huống cần phân biệt trước khi kết luận

Thuật ngữ “compromise” thường được dùng rộng trong xử lý sự cố. Để tránh suy diễn quá mức, hãy phân loại rõ **đối tượng bị ảnh hưởng** và **mức độ bằng chứng**.

| Tình huống | Điều đã biết | Điều chưa thể tự kết luận |
| --- | --- | --- |
| **Confirmed raw-key exposure** | Raw private/secret key được tìm thấy ở nơi trái policy hoặc bằng chứng bị truy xuất | Chưa chắc attacker đã lấy tất cả ciphertext liên quan |
| **Suspected key compromise** | Có dấu hiệu khả nghi nhưng chưa chứng minh key bytes bị lộ | Không được báo “đã xác nhận raw key bị lộ” |
| **Unauthorized crypto operation** | Sign/Decrypt/Unwrap được gọi ngoài quyền nghiệp vụ | Không tự chứng minh KEK/private key đã xuất HSM |
| **Compromised key-management principal** | IAM credential/token/key-admin role bị chiếm | Phạm vi phụ thuộc grants, logs và thời gian tồn tại |
| **Public-key/trust substitution** | Registry, JWKS, certificate hoặc truststore bị thay | Không đồng nghĩa raw private key gốc đã lộ |
| **Weak key generation** | RNG/entropy/algorithm/provenance có vấn đề | Không chắc từng khóa đã bị đoán, nhưng độ tin cậy có thể không còn |
| **Nonce/IV misuse** | Ví dụ nonce AES-GCM bị lặp dưới cùng DEK | Không nhất thiết raw DEK bị tiết lộ, nhưng dữ liệu/tags có thể bị tổn hại nghiêm trọng |
| **Storage/backup exposure** | File PKCS#12, secret vault export hoặc snapshot chứa key có thể bị đọc trái phép | Cần kiểm tra password/ACL, bản sao và chứng cứ truy cập |

### 2.1. Confirmed, suspected và potentially impacted

Ba mức khẳng định khác nhau:

- **Confirmed:** Có bằng chứng trực tiếp đáng tin rằng vật liệu khóa hoặc operation đã rời phạm vi được phép.
- **Suspected:** Telemetry, quyền truy cập hoặc dấu hiệu bất thường đặt ra khả năng bị xâm phạm; chưa đủ chứng cứ xác nhận.
- **Potentially impacted:** Các khóa hoặc dữ liệu thuộc miền mà attacker **có thể** đã tiếp cận, cần khoanh vùng/điều tra.

Một bản **heap dump chứa plaintext DEK** trong môi trường có người không được quyền truy cập là dấu hiệu phải xử lý nghiêm túc. Nhưng nếu không có chứng cứ ai đã tải dump, cần phân biệt **DEK xuất hiện ngoài phạm vi chuẩn** với **đã có người cụ thể đọc**.

### 2.2. Key compromise khác credential compromise

Một **short-lived workload token** bị chiếm có thể cho phép attacker gọi KMS Sign trong thời gian hiệu lực. Khi revoke token/grant, đường lạm dụng có thể bị chặn. Nếu không có bằng chứng export key, không nên khẳng định raw HSM key đã bị lộ.

Tuy nhiên, những **chữ ký đã được tạo** hoặc **plaintext DEK đã được KMS trả** trong thời gian bị chiếm vẫn có hậu quả. Phạm vi đánh giá phải xem **kết quả operation** chứ không chỉ xem raw key material.

### 2.3. Compromise không phải lúc nào cũng có nghĩa hủy ngay

Với một **private decryption key** bị nghi xâm phạm, hủy ngay key trước khi có đường phục hồi dữ liệu có thể gây mất dữ liệu nghiêm trọng, trong khi attacker đã có bản sao thì việc hủy ở nguồn không xóa bản đó. Cần thực hiện **containment, bảo toàn chứng cứ, migration và destruction approval** theo rủi ro, không dùng một thao tác xóa mù quáng.

## 3. Vì sao key compromise nguy hiểm hơn mất một password thông thường?

Khóa mật mã thường bảo vệ **nhiều dữ liệu, nhiều phiên hoặc nhiều bên nhận**. Một key bị lộ có thể ảnh hưởng **cả dữ liệu đã lưu trong quá khứ** và **những hoạt động tương lai** cho đến khi mọi nơi thực sự chuyển sang key mới.

### 3.1. Tính bí mật, toàn vẹn, xác thực và khả dụng

| Thuộc tính | Ví dụ ảnh hưởng từ key compromise |
| --- | --- |
| **Confidentiality** | Attacker có DEK/recipient private key có thể đọc ciphertext tương ứng đã thu thập |
| **Integrity** | Attacker có AEAD key hoặc MAC key có thể tạo thông điệp/tag hợp lệ trong một số phạm vi |
| **Authenticity** | Attacker có private signer hoặc Sign API có thể tạo chữ ký mạo danh |
| **Authorization boundary** | Workload có quyền Unwrap rộng có thể trở thành “confused deputy” đọc dữ liệu sai tenant |
| **Availability** | Thu hồi/hủy key không đúng trình tự làm mất quyền Decrypt hoặc làm TLS/JWT verification lỗi |
| **Auditability / trust** | Chữ ký giả, token giả hoặc trust anchor bị thay có thể làm mất độ tin cậy của chứng cứ |

Một **chữ ký số hợp lệ về toán học** không tự chứng minh hành động nghiệp vụ đã được phê duyệt. Nếu private signer bị lộ, attacker có thể ký nội dung giả. Một **HMAC hợp lệ** cũng không phân biệt được bên nào tạo tag khi cả hai đều biết MAC key.

### 3.2. Forward secrecy không giải quyết mọi vấn đề

Giao thức như TLS 1.3 có thể dùng **authenticated ephemeral key agreement** để giảm ảnh hưởng của việc lộ một số long-term authentication keys đối với **traffic của các phiên đã hoàn tất**, dưới giả định an ninh và điều kiện triển khai phù hợp.

Nhưng nếu **application DEK dài hạn** được truyền bên trong TLS rồi lưu ở hai endpoints, forward secrecy của TLS **không làm DEK đó biến mất**. Key compromise phải được đánh giá theo **đúng loại key và protocol**, không suy từ “đã dùng TLS” rằng ciphertext at rest không còn rủi ro.

### 3.3. Blast radius của KEK lớn hơn một DEK đơn lẻ

Trong envelope encryption:

~~~text
      KEK-prod-v3
         |
   Wrap nhiều DEK
      /      \
   DEK-A    DEK-B
    |         |
  Tenant A  Tenant B
  ciphertext ciphertext
~~~

Nếu raw **DEK-A** bị lộ, phạm vi chủ yếu là ciphertext phụ thuộc DEK-A. Nếu raw **KEK-prod-v3** bị lộ, attacker có thể giải bọc **nhiều wrapped DEKs** nếu đồng thời có các blobs đó. Vì thế phải kiểm kê cả **quan hệ KEK → wrapped DEK → ciphertext → tenant/backup**.

Không có nghĩa tất cả dữ liệu đã bị đọc: còn phụ thuộc attacker có ciphertext/wrapped blobs, quyền thao tác, thuật toán, các phiên bản và bằng chứng. Nhưng **blast radius tiềm năng** thường lớn hơn.

## 4. Bề mặt tấn công theo vòng đời khóa

Key compromise có thể bắt nguồn từ nhiều giai đoạn, không chỉ lúc một file secret bị đánh cắp.

| Giai đoạn | Lỗi tiêu biểu | Dấu hiệu/bảo vệ cần có |
| --- | --- | --- |
| **Generation** | RNG yếu, seed dự đoán được, dùng thuật toán/key size không đáp ứng policy | CSPRNG/KMS/HSM, self-tests, provenance, key inventory |
| **Provisioning/distribution** | Gửi raw key qua chat/email, gửi cho public key giả | Recipient authentication, wrap/HPKE/TLS, manifest/audit |
| **Storage** | Private key vào Git/container image, backup rộng quyền, PKCS#12 password yếu | ACL, secret manager/HSM, scanning, backup encryption/retention |
| **Usage** | Sign/Unwrap API mở rộng, thiếu tenant authorization | IAM least privilege, per-operation policy, anomaly detection |
| **Rotation** | Alias đổi nhưng key material không đổi, không revoke phiên bản cũ | Actual key version telemetry, cutover/negative tests |
| **Backup/DR** | Snapshot giữ secret cũ ngoài scope, restore hồi sinh grants/trust đã thu hồi | Inventory, controlled recovery, revocation epoch |
| **Revocation** | Disable ở KMS nhưng client tiếp tục tin signing key cũ | Trust propagation, JWKS/cert cache invalidation |
| **Destruction** | Xóa một bản copy nhưng raw key ở dump/partner vẫn tồn tại | Dependency graph, destruction evidence, residual risk |

### 4.1. Trong source code và CI/CD

Key có thể xuất hiện qua:

- Hardcode **AES/HMAC secret**, private key hoặc keystore password.
- Commit **.p12/.jks/.pem** chứa private material; lịch sử Git vẫn giữ bản cũ.
- CI logs, command-line arguments, deployment manifests hoặc environment snapshots.
- Test fixtures sao chép **production keys** sang môi trường không được bảo vệ tương đương.
- Container image layers, artifact registry, cached build outputs và file chia sẻ.

Một secret scanning alert không tự chứng minh attacker đã sử dụng key, nhưng là **tín hiệu kiểm soát phạm vi và quyết định rotate/revoke**. Xóa dòng secret khỏi branch hiện tại **không xóa bản sao trong lịch sử, registry hoặc người đã clone**.

### 4.2. Trong process memory

Khi một API **GenerateDataKey/Unwrap** trả plaintext DEK, bản rõ có thể tồn tại trong **SDK response, SecretKey, heap, native buffers, logs, dumps hoặc cache**. Một attacker có quyền debug/dump process có thể lấy key dù KEK vẫn an toàn trong KMS.

Thao tác **Arrays.fill** chỉ xóa mảng mà chương trình kiểm soát, không chứng minh JVM/provider không giữ bản sao. Quản lý heap dumps, debugger, crash reports và thời gian sống plaintext keys là một phần bảo vệ vòng đời.

### 4.3. Trong HSM/KMS

HSM có thể hạn chế Export raw key, nhưng **KMS/HSM API misuse** vẫn có thể xảy ra qua:

- Credential bị chiếm, IAM role quá rộng hoặc token chưa thu hồi.
- Principal có quyền **Sign/Decrypt/Unwrap** trên key sai purpose/tenant.
- Signing service nhận arbitrary messages không qua business authorization.
- KMS key policy/admin grant bị thay trái phép.
- Backup/replication/import material không tuân theo ranh giới non-exportable.

**Bảo vệ key material và bảo vệ quyền sử dụng key là hai lớp độc lập.** Cả hai phải có audit và bài kiểm thử.

## 5. Dấu hiệu nhận biết và giới hạn của bằng chứng

Việc phát hiện key compromise thường dựa trên **nhiều nguồn chứng cứ**, không phải một log duy nhất.

### 5.1. Tín hiệu kỹ thuật

1. **Secret scanning:** Phát hiện private key/KEK/DEK/HMAC secret trong repository, artifact, log hoặc public storage.
2. **KMS/HSM anomaly:** Đột biến Sign, Decrypt, Unwrap, Export hoặc ChangePolicy; principal/region bất thường.
3. **IAM drift:** Workload được cấp grant mới rộng hơn, break-glass role được dùng ngoài thay đổi đã duyệt.
4. **Certificate/JWKS event:** Public key/trust anchor bị thay không có change ticket hoặc fingerprint lệch.
5. **Application errors:** Tỷ lệ GCM authentication tag thất bại, signature mismatch, message replay hoặc certificate chain errors tăng sau thay đổi.
6. **Storage exposure:** Đối tượng backup/heap dump/keystore đọc được bởi principal không cần thiết.
7. **Cryptographic hygiene:** Reused AES-GCM nonce, RNG bị lỗi, signature nonce ECDSA yếu hoặc parameter downgrade.
8. **Known unauthorized operation:** Đã xác định chữ ký, token hoặc giao dịch được tạo ngoài quy trình phê duyệt.

### 5.2. Tín hiệu không đủ để kết luận riêng lẻ

Một lỗi Verify JWT **không tự chứng minh private signing key bị lộ**: nguyên nhân có thể là cache JWKS cũ, clock skew, algorithm mismatch hoặc cấu hình issuer sai.

Một lần KMS AccessDenied **không tự chứng minh attacker đã lấy DEK**: đó có thể là policy chặn đúng. Ngược lại, không có AccessDenied **không chứng minh không có lạm dụng** nếu attacker dùng chính quyền đã bị chiếm.

Một file key bị đọc thành công bởi service **không chứng minh mọi bản sao đều đã bị lộ**; nhưng nếu policy yêu cầu private material non-exportable mà file đã tồn tại ngoài HSM, **giả định ranh giới bảo vệ đã bị vi phạm** và cần đánh giá.

### 5.3. Phải bảo toàn evidence khi điều tra

Trong phạm vi chính sách IR, cần lưu:

- **Key ID/version, owner, purpose, environment, algorithm, provider**.
- **Principal, operation, thời điểm, request/correlation ID**, KMS/HSM response metadata.
- **Change records, IAM grants, certificate/JWKS fingerprints**, key state theo từng mốc.
- **Storage access logs**, nguồn xuất hiện secret, CI/artifact URLs hoặc references.
- Những **ciphertext/wrapped DEK/signature references** và affected consumers.
- Chuỗi thời gian từ khi có thể bị lộ đến containment/rotation/trust propagation.

**Không chép raw DEK/private key vào ticket hoặc audit để “làm bằng chứng”.** Nếu cần thu thập vật liệu nhạy cảm vì điều tra, phải theo quy trình forensic được phê duyệt, hạn chế người truy cập và bảo vệ chính evidence đó.

## 6. Đánh giá blast radius bằng đồ thị phụ thuộc khóa

Câu hỏi đầu tiên sau khi xác định một key có nguy cơ bị xâm phạm không phải “đổi alias ở đâu?”, mà là **“key này có thể tác động lên những tài sản nào?”**.

### 6.1. Key inventory cần những thông tin gì?

| Thuộc tính | Ví dụ | Dùng để |
| --- | --- | --- |
| **keyId / materialVersion** | billing-kek-prod / v3 | Chỉ ra đúng vật liệu/phiên bản |
| **keyType / algorithm / usage** | AES KEK, Wrap/Unwrap | Xác định capability của attacker |
| **owner / environment / region** | billing-platform / prod / region-a | Phân công phản ứng và tránh lan sang test |
| **tenant / dataDomain / purpose** | tenant-a / invoice-at-rest | Khoanh vùng data access |
| **createdAt / activatedAt / retiredAt** | Mốc theo UTC | Xác định khả năng ảnh hưởng theo thời gian |
| **KMS/HSM reference / key state** | Key resource và grants | Containment ở đúng control plane |
| **wrappedDEK / ciphertext relationships** | KEK-v3 → DEK-17 → object-42 | Xác định tập dữ liệu cần migrate |
| **public-key consumers** | JWKS clients, mTLS peers | Phân phối trust/revocation |
| **backup / replica / DR locations** | Snapshot và vùng lưu trữ | Tránh dữ liệu hoặc key cũ xuất hiện lại |
| **incident / change / approval** | INC-123, CHG-456 | Theo dõi truy vết và quyết định |

Nếu không có bản đồ phụ thuộc, tổ chức có thể **rotate một key** rồi bỏ sót encrypted objects, certificate consumers hoặc tenant dùng phiên bản đó.

### 6.2. Truy vết theo hướng tác động

~~~mermaid
flowchart TD
    INC["Dấu hiệu compromise<br/>key ID / principal / trust source"] --> CLASS{"Phân loại đối tượng?"}
    CLASS -->|"Raw DEK"| DEK["DEK version và usages"]
    CLASS -->|"Raw KEK"| KEK["KEK -> wrapped DEKs -> dữ liệu"]
    CLASS -->|"Signing key / Sign API"| SIGN["Chữ ký, tokens, certificates,<br/>issuers và verifiers"]
    CLASS -->|"MAC key"| MAC["Đối tác, webhook consumers,<br/>message history"]
    CLASS -->|"Key agreement / TLS"| TLS["Phiên, giao thức,<br/>certificate/key schedule"]
    CLASS -->|"Trust registry"| TRUST["Public keys/trust anchors<br/>và người tin chúng"]
    DEK --> ASSET["Asset inventory<br/>tenant, object, backup, retention"]
    KEK --> ASSET
    SIGN --> ASSET
    MAC --> ASSET
    TLS --> ASSET
    TRUST --> ASSET
    ASSET --> RESPONSE["Containment + migration<br/>revocation, audit, residual risk"]
~~~

### 6.3. Thời gian ảnh hưởng phải gắn với dữ liệu/operation

Giả sử raw DEK-v1 được tìm thấy trong một bản dump tạo lúc **T1**, dữ liệu mã hóa bằng DEK-v1 bắt đầu từ **T0** và DEK-v2 được kích hoạt từ **T2**. Phạm vi tiềm năng không chỉ là các ciphertext tạo **sau T1**: nếu attacker có DEK-v1 và ciphertext đã lưu **từ T0**, các bản mã cũ cũng có thể bị giải mã.

Tương tự, nếu private signing key bị sao chép vào lúc T1, một chữ ký mới được kiểm tra hợp lệ về toán học bằng public key v1 **không tự chứng minh nó được tạo trước T1**, trừ khi có chứng cứ thời gian đáng tin cậy phù hợp.

### 6.4. Key ID không phải bản thân secret

Một bản ghi chứa **key reference** bị lộ thường chưa đủ để giải mã dữ liệu nếu key material và quyền unwrap còn an toàn. Nhưng key IDs/tenant references có thể giúp attacker tìm đích. Không xem key ID là bằng chứng raw key exposure; đồng thời không dùng nó như một “mật khẩu bí mật” để cấp quyền KMS.

## 7. Phân loại mức độ khẩn cấp và quyết định containment

Mức độ nghiêm trọng phụ thuộc **quyền tấn công, loại dữ liệu, ảnh hưởng tin cậy, khả năng tiếp tục lạm dụng và phạm vi hệ thống**. Một sự cố suspected raw KEK leak có thể yêu cầu hành động phòng ngừa mạnh dù chưa kết luận cuối.

### 7.1. Bảng quyết định ban đầu

| Dấu hiệu / kết luận | Rủi ro trước mắt | Containment cần cân nhắc |
| --- | --- | --- |
| **Raw private signing key công khai** | Attacker có thể Sign bên ngoài HSM | Ngừng Sign cũ, phát trust/revocation, thay signer, điều tra chữ ký |
| **Raw DEK/KEK trong log** | Bên xem log có thể mở dữ liệu liên quan | Chặn thêm log/export, hạn chế quyền evidence, xác định phạm vi, thay key và dữ liệu khi cần |
| **KMS Sign/Decrypt bị gọi trái phép** | Có chữ ký/DEK/plaintext đã được trả | Revoke principal/grants, cô lập workload, điều tra từng operation và outputs |
| **HMAC partner secret lộ** | Có thể tạo webhook/MAC giả | Chặn v1, phân phối v2, chống replay và đối soát messages |
| **JWKS/truststore bị sửa** | Verifier có thể tin key giả | Khôi phục nguồn trust, ngăn update, invalidation cache, điều tra tokens/handshakes |
| **RNG sinh khóa bị nghi yếu** | Nhiều key materials có thể dự đoán được | Dừng generation path, xác định batch keys, tái tạo bằng nguồn đáng tin |
| **Key deletion request trái phép** | Mất khả năng Decrypt/Sign và rủi ro availability | Chặn admin quyền, bảo vệ recovery, kiểm tra trạng thái pending |
| **Nonce AES-GCM bị trùng dưới DEK** | Rủi ro mất bí mật/toàn vẹn bản mã | Dừng Encrypt dưới DEK, điều tra ciphertext và migrate khi cần |

### 7.2. Ưu tiên ngăn tác hại tiếp diễn

Khi đủ căn cứ cho containment, thứ tự tùy sự cố:

1. **Cắt đường lạm dụng đang hoạt động:** IAM credentials, grants, API endpoints, Sign/Decrypt permissions hoặc outbound secret publication.
2. **Bảo toàn chứng cứ:** Tránh xóa logs, history, trạng thái policy và sự kiện operation cần điều tra.
3. **Giữ dữ liệu hợp lệ phục hồi được:** Không destroy decryption key trước dependency analysis.
4. **Thông báo owners và relying parties** theo mức độ tin cậy bị ảnh hưởng.
5. **Chuyển key mới từ vùng sạch** và kiểm tra quyền trước khi mở traffic.

Nếu một private signing key đã **bị xác nhận lộ**, đừng để nó tiếp tục Sign trong cửa sổ “rotation định kỳ” chỉ vì lịch cutover chưa tới. Tuy nhiên, **không tự xóa public verification key/history**: cần kiểm soát trust và chứng cứ chữ ký cũ theo policy.

### 7.3. Suspension và revocation không giống nhau

- **Suspension:** Hạn chế tạm thời một hoặc nhiều hoạt động trong khi điều tra hoặc chờ khắc phục.
- **Revocation:** Quyết định key/credential/trust **không còn được phép sử dụng hoặc tin** trong phạm vi xác định.
- **Rotation:** Sinh/kích hoạt vật liệu khóa mới và cập nhật consumers.
- **Destruction:** Xóa/hủy vật liệu theo chính sách; có thể không phục hồi được.

Không dùng một cờ **active=false** làm lời giải cho mọi mục tiêu. Với public signing key có thể cần **Verify historical signatures** theo chứng cứ riêng, trong khi không cho **Sign mới**. Với KEK, có thể ngừng **Wrap mới** nhưng vẫn tạm **Unwrap data cũ** trong quy trình migration được giám sát.

## 8. Incident response: từ phát hiện đến phục hồi

Một runbook cần có các bước nhất quán nhưng **không máy móc**: raw key leak, API abuse và trust-source compromise khác nhau.

~~~mermaid
sequenceDiagram
    participant MON as Monitoring / detector
    participant IR as Incident Response
    participant OWNER as App/Data owner
    participant KMS as KMS/HSM + IAM
    participant APP as Applications / verifiers
    participant DR as Backup / DR / partners
    MON->>IR: Dấu hiệu compromise + evidence references
    IR->>OWNER: Xác minh key ID, purpose, asset inventory
    IR->>KMS: Chặn grants/operations cần containment
    IR->>APP: Cô lập workload hoặc trust cũ
    OWNER->>OWNER: Khoanh vùng ciphertext / signatures / tenants
    OWNER->>KMS: Sinh key mới từ ranh giới sạch
    KMS-->>OWNER: New key reference/public material
    OWNER->>APP: Cutover và cập nhật public trust / grants
    OWNER->>DR: Rewrap/re-encrypt và reconcile backups nếu cần
    APP-->>IR: Negative tests / readback / telemetry
    DR-->>IR: Recovery tests / acknowledged updates
    IR->>IR: Đánh giá residual risk và kết thúc theo evidence
~~~

### 8.1. Bước 0 — Kích hoạt Incident Response

Thông báo đúng **security on-call, application owner, KMS/PKI owner, data owner và vận hành/DR** theo chính sách. Gắn **incident ID**, xác định người chịu trách nhiệm quyết định containment và log timeline.

Không gửi raw secrets trong channel điều phối. Một sự cố có thể liên quan dữ liệu cá nhân hoặc nghĩa vụ thông báo; cần phối hợp bộ phận pháp lý/compliance theo quy trình và luật áp dụng, **không suy đoán rằng mọi lần rotate đều đòi thông báo giống nhau**.

### 8.2. Bước 1 — Xác định điều bị xâm phạm

Câu hỏi:

- Vật liệu raw key đã bị xuất hay chỉ **quyền sử dụng** bị lạm dụng?
- Thuộc **DEK, KEK, MAC, signing, decrypt, CA root, trust anchor hay credential KMS**?
- Có bằng chứng **tenant, region, environment, key version và mốc thời gian** không?
- Những **API calls/output** nào đã được tạo? Nếu là Sign, chữ ký nào? Nếu là Unwrap, raw DEK nào có thể đã được trả?
- Có trường hợp **alg/nonce/RNG weakness** làm suy yếu dữ liệu mà không lộ raw key?

### 8.3. Bước 2 — Contain và giữ đường đọc hợp pháp

Những hành động có thể gồm:

- **Revoke/suspend IAM grants và credentials**, khóa workload bị chiếm.
- **Disable Sign/Wrap/Encrypt mới** bằng key nghi lộ theo policy.
- **Cắt đường export** hoặc sửa quyền truy cập vào files, backups, secret versions.
- **Cập nhật trust/revocation** tại relying parties khi private signing/CA key bị lộ.
- **Phân tách đường đọc lịch sử**: Decrypt/Unwrap chỉ qua workflow có approval nếu dữ liệu vẫn cần migration.

**Không destroy một KEK còn giữ hàng triệu wrapped DEK trước khi xác minh recovery path.** Containment và destruction là hai quyết định khác nhau.

### 8.4. Bước 3 — Thay khóa và loại bỏ nguồn lộ

Sinh vật liệu khóa mới từ **CSPRNG/KMS/HSM an toàn**, với key usage/permission đúng. Nếu nguồn RNG hoặc HSM instance bị nghi xâm phạm, không sinh key mới qua chính nguồn đó khi chưa được làm sạch/đánh giá.

Đồng thời xử lý **root cause**: IAM quá rộng, secret logging, CI pipeline, certificate trust registry hoặc bug nonce allocator. Nếu chỉ thay key nhưng vẫn log DEK mới, sự cố sẽ lặp lại.

### 8.5. Bước 4 — Di chuyển dữ liệu và hệ thống phụ thuộc

- **DEK exposure:** Đánh giá re-encrypt ciphertext còn cần dưới DEK mới.
- **KEK exposure:** Đánh giá wrapped DEKs/ciphertexts attacker có thể có; rewrap với KEK mới và có thể phải thay DEKs tùy mức độ lộ.
- **Signing key exposure:** Phát signer mới, cập nhật public trust và policy với chữ ký cũ.
- **MAC key exposure:** Phân phối secret mới cho các bên dùng chung, chặn key cũ và kiểm tra replay.
- **Trust substitution:** Khôi phục registry/CA trust và rà soát token/chứng chỉ đã chấp nhận.

### 8.6. Bước 5 — Xác minh và đóng sự cố

Không kết luận “đã hoàn tất” chỉ vì API **CreateKey/Rotate** trả thành công. Cần test:

1. Old key **không còn tạo protection mới** nơi policy yêu cầu.
2. Principal bị thu hồi **không còn Sign/Unwrap/Decrypt**.
3. Verifiers thực sự **đã cập nhật trust**; cache và các bên offline được theo dõi.
4. Data migration/rewrap có **readback**, không mất ciphertext còn cần.
5. Backup/DR restore **không hồi sinh key/grants/trust bị thu hồi**.
6. Root cause đã xử lý, audit đủ và residual risk được ghi nhận.

## 9. Revocation, rotation, rewrap, re-encrypt và destruction

Đây là năm nhóm hành động rất dễ bị dùng lẫn nhau trong sự cố.

| Hành động | Đối tượng thay đổi | Giải quyết | Không tự giải quyết |
| --- | --- | --- | --- |
| **Revoke grant/credential** | IAM principal hoặc quyền API | Chặn một đường gọi KMS/HSM | Raw key attacker đã copy, outputs đã trả |
| **Revoke certificate/public trust** | Quyết định verifier tin key/identity | Chặn chấp nhận chữ ký/chứng chỉ theo cập nhật trust | Private key bytes attacker đang giữ, verifiers chưa cập nhật |
| **Rotate key** | Vật liệu khóa dùng cho operation mới | Giới hạn phụ thuộc vào key cũ trong tương lai | Ciphertext/chữ ký cũ, bản raw key bị lấy |
| **Rewrap DEK** | KEK/wrapped key blob | Chuyển lớp bảo vệ DEK | DEK cũ bị lộ hoặc payload encryption dưới DEK cũ |
| **Re-encrypt payload** | DEK và ciphertext | Tạo bản mã mới dưới key mới | Bản ciphertext + DEK mà attacker đã lấy trước đó |
| **Destroy key** | Material tại nơi được quản lý | Chặn dùng material trong boundary đó, hỗ trợ crypto-erasure có điều kiện | Bản sao bên ngoài, plaintext đã sao chép, record history |

### 9.1. Khi nào rewrap là đủ?

Ví dụ một tổ chức thay **KEK vì thay chính sách/nhà cung cấp**, không có bằng chứng lộ raw KEK/DEK và DEK hiện hành vẫn đáp ứng cryptoperiod. Khi đó **rewrap cùng DEK** bằng KEK mới có thể là phương án phù hợp.

Ngược lại, khi **raw KEK đã bị lộ** và attacker có thể đã lấy wrapped DEKs, việc rewrap hiện tại **không thu hồi được bản cũ của DEK đã có thể được giải ra**. Cần phân tích dữ liệu cũ và cân nhắc **tạo DEKs mới/re-encrypt**.

### 9.2. Khi nào phải thay DEK?

Nếu có bằng chứng **raw DEK** bị lộ cho đối tượng không được phép, cần coi những ciphertext phụ thuộc có nguy cơ. Tạo DEK mới cho Encrypt tương lai là quan trọng; để giảm phụ thuộc của dữ liệu còn giữ, cần xem xét **re-encrypt**. Các bản mã attacker đã lấy với DEK cũ có thể không cứu vãn được bằng thao tác ở hệ thống hiện tại.

### 9.3. Disable khác Destroy

KMS/HSM thường có các trạng thái như **Enabled, Disabled, PendingDeletion** hoặc tương đương, nhưng semantics phụ thuộc nhà cung cấp. Disable có thể chặn operation qua API; nó **không xóa ciphertext, bản sao raw key hoặc audit history**. Delete có thể có thời gian chờ hoặc yêu cầu quorum/approval; **pending deletion không phải destroyed**.

### 9.4. Rotation định kỳ khác emergency rotation

Trong **planned rotation**, có thể có **overlap hữu hạn** cho verifiers và clients, vì key cũ vẫn được tin trong khoảng cho phép. Trong **compromise**, cho phép sử dụng key cũ thêm vì tiện tương thích có thể tạo cơ hội tiếp tục giả mạo/giải mã.

Phải chọn theo **loại incident, tình trạng trust và policy**, không dùng cùng cron-job cutover để xử lý mọi sự cố.

## 10. Key compromise trong envelope encryption: DEK và KEK

Envelope encryption cho phép tách **khóa mã hóa dữ liệu (DEK)** khỏi **khóa bảo vệ DEK (KEK)**. Đây là lợi ích bảo mật quan trọng, nhưng cũng tạo quan hệ phụ thuộc phải được hiểu rõ khi có sự cố.

### 10.1. Một bản ghi envelope điển hình

~~~text
recordId: invoice-42
tenantId: tenant-a
payloadAlgorithm: AES-256-GCM
kekReference: billing-kek-v3
encryptedDataKey: wrapped-DEK-42
payloadNonce: nonce-42
payloadCiphertextAndTag: encrypted-invoice-42
context: tenant-a / invoice-42 / invoice-at-rest
~~~

Ứng dụng dùng DEK để **AES-GCM Encrypt/Decrypt** và sử dụng KMS/HSM để **Wrap/Unwrap** DEK dưới KEK. Có những KMS cung cấp API tương tự **GenerateDataKey** trả cả plaintext DEK tạm và encrypted data key; khi đó chính **Java process** vẫn cần bảo vệ plaintext DEK trong bộ nhớ.

**Không coi opaque wrapped DEK là secret dạng rõ.** Nhưng cũng không cho phép attacker tùy ý thay key reference, tenant hoặc encryption context; cần bảo vệ toàn vẹn, authorization và khả năng diễn giải của envelope.

### 10.2. Nếu raw DEK bị lộ

1. Xác định **key ID/version hoặc encrypted data key instance** bị ảnh hưởng.
2. Liệt kê records, tenants, backups và ciphertext đã mã hóa dưới DEK đó.
3. Chặn **Encrypt mới** bằng DEK cũ; dừng đường rò như logging/heap exports.
4. Sinh DEK mới từ nguồn an toàn, cập nhật envelope cho dữ liệu mới.
5. Với dữ liệu còn cần, đánh giá **giải mã và mã hóa lại** dưới DEK mới.
6. Kiểm tra **AEAD tag/AAD** khi đọc bản cũ; ghi atomically bản mới.
7. Xem xét việc attacker có thể đã lấy **DEK + ciphertext cũ**; công bố rủi ro tồn dư theo quy trình.

**Chỉ thay KEK bọc lại cùng DEK bị lộ không khôi phục tính bí mật của dữ liệu đó.**

### 10.3. Nếu raw KEK bị lộ

1. Xác định KEK resource, material version, algorithm, state và nơi raw KEK có thể bị xuất.
2. Liệt kê **mọi wrapped DEK** được tạo dưới material đó, kể cả backups/regions/archives.
3. Xác định attacker có thể đã sở hữu **wrapped DEKs/ciphertexts** nào.
4. Chặn Wrap/Unwrap không được phép và thu hồi IAM/export paths.
5. Sinh KEK mới và rewrap các DEK được phép giữ.
6. Khi rủi ro cho thấy DEKs cũ cũng có thể bị giải bọc, đánh giá **DEK replacement và payload re-encryption**.
7. Kiểm tra backup/DR trước khi destroy KEK cũ; không để recovery bất khả thi.

Một số managed KMS **không xuất raw KEK** qua API thông thường. Nếu sự cố là **quyền Decrypt/Unwrap bị lạm dụng** mà không có chứng cứ raw KEK, phạm vi và cách khắc phục cần dựa trên **operation outputs**, không tự mô tả là “KEK bytes đã bị đánh cắp”.

### 10.4. Nếu attacker chỉ có ciphertext + wrapped DEK

Nếu primitives được dùng đúng, KEK và quyền Unwrap còn được bảo vệ, việc lấy database **không đồng nghĩa lấy plaintext DEK**. Tuy nhiên:

- Attacker có thể tìm lỗi **nonce reuse, AAD thiếu, algorithm downgrade hoặc key version confusion**.
- Attacker có thể thử **sửa/tráo toàn bộ envelope** để kích hoạt ứng dụng xử lý sai context.
- Nếu họ chiếm workload được KMS cho phép Unwrap, ranh giới giữa storage và KEK có thể bị vượt.

Do đó **bảo vệ context và data authorization** vẫn cần thiết, ngay cả khi wrapped DEK là blob được mã hóa hợp lệ.

### 10.5. Re-encrypt phải có khả năng kiểm chứng

Khi thực hiện migration sau compromise:

- Không phát plaintext ra message bus hoặc log.
- Dùng DEK mới và nonce mới với AEAD.
- Ràng buộc AAD với **record/tenant/purpose từ nguồn tin cậy**.
- Dùng transaction/CAS để tránh race giữa rotation worker và writer.
- Đối chiếu số records đã migrate, failures và backups.
- Chỉ retire/decommission đường cũ khi **readback + retention + recovery** đạt.

Nếu attacker đã lấy bản ciphertext cũ và raw key, việc re-encrypt bản production không thể **xóa bản đã mất kiểm soát**. Sự cố còn có thể cần đánh giá tác động dữ liệu, không chỉ báo “migration 100%”.

## 11. Private signing key compromise và niềm tin vào chữ ký

**Private signing key** thuộc mô hình bất đối xứng: bên ký giữ private material, bên xác minh dùng public key được tin qua **PKI, certificate, JWKS hoặc trusted registry**. Nếu attacker có private key, họ có thể tạo chữ ký đúng về toán học cho dữ liệu giả.

### 11.1. Hai loại sự cố khác nhau

| Tình huống | Bằng chứng | Biện pháp |
| --- | --- | --- |
| **Raw private signer bị lộ** | Secret material đã xuất khỏi vùng được phép | Rotate key pair, revoke trust, điều tra signatures và consumers |
| **KMS/HSM Sign API abuse** | Operation Sign bị gọi bởi principal bị chiếm | Revoke credentials/grants, điều tra signed payloads; đánh giá có cần thay key tùy phạm vi |

Một HSM **non-exportable** có thể giảm nguy cơ raw private key bị lấy qua API, nhưng không chặn ký giả nếu application cho phép ký **arbitrary bytes** mà không kiểm tra user, tenant, document và purpose.

### 11.2. Public key vẫn Verify được chữ ký giả

Giả sử attacker đã lấy **private key-v1**, tạo một JWT giả với **kid=v1** rồi ký. Verifier dùng public-v1 có thể **Verify=true**, bởi chữ ký đúng về toán học.

Đó là lý do **Verify=true không đủ để tin message**. Cần:

- Public key từ **issuer/trust registry đã xác thực**.
- **Allowed algorithms** cố định và key type đúng.
- **Revocation/key state** theo issuer và thời điểm được chấp nhận.
- JWT claims như **iss, aud, exp, nbf** và policy người dùng.
- Token/session revocation khi cần; không chỉ kiểm tra một chữ ký.

Không để JWT header tự chỉ định bất kỳ URL/JWKS source nào rồi tin khóa trả về. Không dùng key của issuer khác chỉ vì **kid** trùng.

### 11.3. Thu hồi X.509 certificate

Đối với chứng chỉ X.509, một hệ thống PKI có thể phát hành thông tin thu hồi qua **CRL, OCSP hoặc cơ chế status/trust cập nhật phù hợp**. Việc bên xác minh áp dụng đến đâu phụ thuộc **profile giao thức, cấu hình revocation checking, thời gian cache, connectivity và chính sách fail-open/fail-closed**.

**Không khẳng định phát hành CRL/OCSP mới là tất cả clients ngay lập tức từ chối certificate**. Cần đo **revocation propagation**, kiểm thử các bên dựa vào certificate và xử lý clients offline.

### 11.4. Chữ ký lịch sử có phải đều vô hiệu?

Không thể kết luận máy móc rằng “mọi chữ ký từng tạo bằng key bị lộ đều giả” hoặc “mọi chữ ký cũ vẫn hợp lệ”. Việc đánh giá phụ thuộc:

- Thời điểm key có thể đã bị xâm phạm, với **bằng chứng thời gian đáng tin**.
- Chứng chỉ, chain, usage, revocation info và policy ở thời điểm ký.
- Signed message bytes, signature và issuer/recipient context.
- Yêu cầu pháp lý, lưu trữ, đối chiếu giao dịch và trust framework.

Một trường **signedAt** nằm trong payload do chính attacker tạo **không phải trusted timestamp độc lập**. Nếu hệ thống cần chứng minh chữ ký đã tồn tại trước compromise, cần cơ chế chứng cứ thời gian phù hợp.

### 11.5. Root CA compromise có thể có blast radius rộng

Nếu private key của một CA được nhiều hệ thống tin bị lộ, attacker có thể phát hành các chứng chỉ giả trong phạm vi key usage và trust của CA. Khắc phục có thể cần:

- Ngừng/thu hồi CA key và quy trình cấp phát liên quan.
- Phát hành trust anchor/intermediate mới theo kế hoạch được review.
- Cập nhật client/server truststores, certificate chains và pinning.
- Điều tra certificates đã cấp và những handshakes/identities có thể bị giả.
- Phối hợp rộng rãi với relying parties, không chỉ restart một service.

**Không có một thao tác rotate leaf certificate duy nhất đủ để giải quyết mọi CA compromise.**

## 12. MAC key, HMAC và secret chia sẻ bị lộ

Với **HMAC**, bên tạo và bên Verify thường cùng biết secret. Nếu một bên bị xâm phạm và secret bị sao chép, bên đó hoặc attacker có thể tạo message authentication tags hợp lệ.

### 12.1. Vì sao HMAC không cho non-repudiation?

Nếu hai tổ chức A và B cùng biết một HMAC key, một tag hợp lệ **không chứng minh riêng A** đã tạo nó; B cũng có khả năng tạo tag. Điều này khác chữ ký số với **private key riêng cho signer và public key cho verifier**.

Khi điều tra webhook giả, cần kết hợp **request IDs, application logs, bên gửi, thời gian, network evidence và business state**, không dựa hoàn toàn vào HMAC tag để quy trách nhiệm.

### 12.2. Rotation khẩn cấp shared secret

Quy trình minh họa:

1. Tạm dừng hoặc giới hạn webhook nhạy cảm nếu còn nguy cơ giả mạo.
2. Sinh **HMAC-v2** bằng nguồn bí mật phù hợp và tách riêng các đối tác/tenant nếu cần.
3. Phân phối v2 cho recipients qua kênh/manifest được xác thực.
4. Cập nhật bên phát và bên nhận, gắn **key version** với thông điệp.
5. Chặn v1 theo mức rủi ro; **không để planned overlap kéo dài** khi v1 đã lộ.
6. Bổ sung anti-replay: timestamp, request ID, expiry/nonce và idempotency theo định dạng đã được MAC.
7. Đối soát thông điệp/giao dịch trong thời gian key-v1 có thể bị lạm dụng.

Một secret v1 đã bị sao chép **không biến mất** khi secret manager gắn nhãn v1 là disabled. Phải ngăn hệ thống tiếp tục **tin hoặc sử dụng** secret đó.

### 12.3. “Giữ cả v1 và v2 để không mất traffic” là quyết định rủi ro

Với rotation định kỳ khi v1 còn an toàn, một cửa sổ nhận song song có thể hợp lý. Nhưng khi v1 compromised, **chấp nhận HMAC-v1 đồng nghĩa vẫn có thể nhận tag giả do attacker tạo**. Nếu cần duy trì hệ thống, phải có **ngoại lệ được phê duyệt, scope, deadline và biện pháp bù trừ**, không mặc nhiên giữ v1 mãi.

## 13. KMS/HSM compromised: vật liệu và operation phải điều tra riêng

Một sự cố liên quan KMS/HSM có thể tác động ở nhiều mức:

### 13.1. IAM principal bị chiếm

Attacker có thể gọi những operation principal được cấp. Bước đầu:

1. Revoke credentials/grants/role sessions và chặn nguồn gọi.
2. Đối chiếu **KMS/HSM audit logs** theo key ID, principal, operation, result và thời gian.
3. Xác định có **Sign/Decrypt/Unwrap/GenerateDataKey/Export** nào thành công.
4. Liên kết với application logs để biết **payloads/datasets** nào thực sự bị ảnh hưởng.
5. Rà soát output đã được trả, caches/dumps và dữ liệu attacker có thể đã sao chép.
6. Sửa IAM conditions, key/resource policy và authorization ở ứng dụng.

**AccessDenied event** có thể cho thấy policy đã chặn đúng, nhưng không phủ nhận những operation khác đã thành công.

### 13.2. HSM key attributes hoặc policy bị sửa

Nếu admin role bị chiếm và attacker thay quyền **Sign, Decrypt, Derive, Export**, phải kiểm tra:

- Key material có từng được **exportable** hay nhập từ ngoài không?
- Những thay đổi policy/attributes đã thực sự có hiệu lực từ khi nào?
- Session nào có quyền admin hoặc sử dụng key sau thay đổi?
- Có thay alias, key version hoặc certificate/trust source không?
- Backup/replication có duy trì trạng thái sai đó không?

**Không chỉ khôi phục policy rồi tuyên bố raw key chưa lộ.** Cần dựa vào khả năng export, chứng cứ operation và phạm vi thực sự.

### 13.3. KMS outage không phải key compromise

Một dịch vụ KMS bị gián đoạn có thể khiến application Decrypt/Sign thất bại dù key material vẫn an toàn. Không dùng outage làm lý do:

- Export raw KEK ra file tạm.
- Hardcode một fallback AES/HMAC key.
- Bỏ chữ ký số hoặc tắt kiểm tra certificate.
- Dùng lại key cũ đã revoked.

Cần **HA/DR, bounded retry, circuit breaker và fail-closed behavior** theo chính sách. Chỉ tuyên bố compromise khi có căn cứ phù hợp, không đánh đồng availability incident với confidentiality incident.

## 14. Public key, JWKS, certificate và truststore bị đánh tráo

Đây là nhóm sự cố thường bị gọi nhầm “private key leak”. Thực tế, đối thủ có thể **mạo danh bằng cách thay nguồn mà verifier tin**, không cần có private key của chủ thể thật.

### 14.1. Ví dụ JWKS substitution

Một JWT verifier được cấu hình lấy public keys từ issuer đã xác thực. Nếu attacker điều khiển được endpoint JWKS hoặc đường phân phối khóa, họ có thể:

1. Đăng một public key do chính mình sở hữu.
2. Ký token bằng private key tương ứng.
3. Khi verifier tin JWKS giả, nó có thể chấp nhận token do attacker ký.

Khắc phục phải bao gồm **khôi phục trusted JWKS source, thay đổi quyền, invalidation caches và điều tra tokens**, không chỉ rotate private key thật của issuer.

### 14.2. Ví dụ truststore bị thay CA root

Một Java service dùng truststore để xác thực certificate đối tác. Nếu attacker thêm **CA root của mình** vào truststore, service có thể tin certificate giả phát hành từ root đó, tùy endpoint identity checking và certificate profile.

Đáp ứng:

- Khôi phục truststore từ nguồn được duyệt.
- Kiểm tra **filesystem ACL, CI/deployment pipeline, integrity và audit**.
- Xác minh hostname/SAN/EKU và CA path.
- Đánh giá các kết nối/giao dịch được thực hiện trong khoảng truststore bị sửa.
- Kiểm thử âm tính: certificate do root không được phê duyệt phải bị từ chối.

### 14.3. Key fingerprint giúp gì và không giúp gì?

Fingerprint của public key/certificate có thể giúp phát hiện thay khóa, nhưng **nguồn fingerprint phải đáng tin**. Gửi public key và fingerprint trên cùng một kênh đã bị MITM điều khiển không tự chứng minh danh tính người nhận.

Đối với public-key enrollment, cần **PKI, signed registry, out-of-band verification hoặc cơ chế xác thực được thẩm định**. Rotation phải cập nhật nguồn trust theo approval, không để client tự chấp nhận bất kỳ fingerprint mới nào chỉ vì khóa cũ lỗi.

### 14.4. Key compromise và trust compromise có thể xảy ra cùng lúc

Nếu attacker chiếm **KMS admin role** và **JWKS registry**, họ có thể vừa thay quyền Sign vừa đưa public key giả đến verifier. Incident scope phải xem **quyền theo chuỗi điều khiển**, không giới hạn điều tra ở một resource chỉ vì alert đầu tiên nhắc đến nó.

## 15. Key compromise và cryptoperiod: không chờ đến lịch rotation

**Cryptoperiod** mô tả khoảng thời gian sử dụng khóa theo operation và policy. Rotation định kỳ giúp giới hạn thời gian material tạo protection mới, nhưng **một sự cố compromise phải có đường phản ứng theo sự kiện**.

### 15.1. Planned rotation khác emergency response

| Khía cạnh | Planned rotation | Compromise response |
| --- | --- | --- |
| **Nguyên nhân** | Đến hạn, usage limit hoặc chuyển policy | Mất bí mật, lạm dụng key API, trust giả hoặc nghi ngờ nghiêm trọng |
| **Chuẩn bị** | Có thể pre-publish public key, chạy canary | Containment có thể cần làm ngay trước khi chuẩn bị hoàn tất |
| **Old-key overlap** | Có thể hữu hạn khi key còn an toàn | Phải đánh giá khả năng attacker tiếp tục lợi dụng; thường rút ngắn/chặn |
| **Dữ liệu lịch sử** | Thường giữ đường Decrypt/Verify theo retention | Có thể phải re-encrypt hoặc đánh giá chữ ký lịch sử |
| **Trust change** | Phân phối public key v2 theo lịch | Thu hồi/invalidate v1 khi không còn đáng tin |
| **Bằng chứng hoàn tất** | Writer/Signer đã chuyển và đọc lịch sử vẫn tốt | Ngoài cutover còn có incident scope, forensic evidence và residual risk |

### 15.2. State machine theo chính sách

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Tạo và kích hoạt key
    ACTIVE --> RETIRED: Hết period tạo mới
    ACTIVE --> SUSPENDED: Nghi compromise
    RETIRED --> SUSPENDED: Phát hiện bất thường
    SUSPENDED --> REVOKED: Xác nhận mất tin cậy
    SUSPENDED --> ACTIVE: Điều tra xác nhận false alarm, được phê duyệt
    REVOKED --> DESTROY_PENDING: Đã kiểm tra phụ thuộc và retention
    RETIRED --> DESTROY_PENDING: Hết nhu cầu, được phê duyệt
    DESTROY_PENDING --> DESTROYED: Hủy và xác minh
    DESTROYED --> [*]
~~~

**State machine là mô hình nghiệp vụ, không phải trạng thái mặc định của KMS nào.** Các provider có thể có key states khác; phải ánh xạ đúng **Sign/Encrypt/Wrap/Decrypt/Verify/Unwrap permissions** và điều kiện trust.

### 15.3. Tách quyền tạo mới khỏi quyền sử dụng lịch sử

Một **DEK-v1** bị retire theo lịch có thể vẫn được phép **Decrypt** dữ liệu cũ; nó không nên tiếp tục **Encrypt** dữ liệu mới. Nếu **raw DEK-v1 đã bị lộ**, việc duy trì Decrypt nội bộ cho migration phải đi kèm quyền giới hạn, trong khi dữ liệu bên ngoài có thể đã bị ảnh hưởng.

Một private signer-v1 đã bị retire có thể **không còn Sign**, nhưng public-v1 vẫn Verify chữ ký lịch sử theo chính sách. Nếu signer-v1 bị compromised, **trust decision của relying party** có thể thay đổi mạnh; không lấy phép Verify=true thay cho trust evaluation.

### 15.4. Điều kiện trước khi destroy

**Destruction** là điểm có thể không đảo ngược. Phải kiểm tra:

- Các ciphertext/wrapped DEKs còn cần được giải mã hoặc migrate.
- Backups, snapshots, replicas, long-term archives và DR.
- Public-key/certificate evidence cần giữ để Verify tài liệu lịch sử.
- Legal hold, retention và dữ liệu dùng chung key domain.
- Bản sao raw key ngoài HSM đã được kiểm kê trong phạm vi có thể.
- Phê duyệt độc lập, KMS/HSM deletion state và audit.

Trong một incident, có thể cần **disable/suspend** để containment trước khi đạt điều kiện destroy. **Tạm ngừng dùng key không đồng nghĩa tin rằng key đã bị xóa khỏi mọi nơi.**

## 16. Chuẩn bị trước để giảm thời gian xử lý compromise

Ứng phó hiệu quả phụ thuộc những quyết định **đã được thiết kế trước khi sự cố xảy ra**.

### 16.1. Sở hữu và phân quyền

- **Application owner:** Biết workflows và những places sử dụng key.
- **Data owner:** Xác định dữ liệu nhạy cảm, retention và yêu cầu phục hồi.
- **Security/IR:** Quyết định mức rủi ro, containment, trust/revocation và truyền thông.
- **KMS/HSM/PKI admin:** Thực hiện key policy, grants, tạo/disable/rotate theo thẩm quyền.
- **SRE/DR:** Điều phối rollout, cache invalidation, backup/restore và monitoring.
- **Audit/compliance:** Đánh giá chứng cứ, yêu cầu lưu hồ sơ và ngoại lệ.

**Không giao tất cả quyền CreateKey/Export/Sign/Decrypt/DeleteKey** cho một workload chỉ vì muốn xử lý incident nhanh. Nên chuẩn bị **break-glass workflow** có dual approval, expiry và audit.

### 16.2. Key inventory và dependency index

Để tra key ID trong vài bước thay vì tìm bằng tay khắp repository, inventory nên ghi:

~~~yaml
# Mẫu metadata minh họa, không chứa raw key.
keyId: billing-data-kek-prod
keyMaterialVersion: v3
owner: billing-platform
environment: production
type: symmetric-key-encryption
purpose: wrap-invoice-deks
provider: managed-kms
operations: [Wrap, Unwrap]
state: ACTIVE
dependents:
  dataDomains: [tenant-a-invoices, tenant-b-invoices]
  wrappedDekIndex: envelope-store-index
  backupPolicy: billing-prod-backups
controls:
  exportAllowed: false
  requireScopedKmsGrants: true
  requireTenantAuthorization: true
  auditKeyUse: true
  incidentRunbook: key-compromise-v2
~~~

**Đây là policy/inventory giả định**, không phải cú pháp tiêu chuẩn của một SDK. Trường **exportAllowed: false** chỉ là một yêu cầu quản trị cho đến khi được thực thi bằng khả năng KMS/HSM thực tế.

### 16.3. Gắn phiên bản khóa vào dữ liệu

Một bản mã cần chứa hoặc tham chiếu **algorithm, nonce/tag, wrapped DEK, KEK key resource/material version và dữ liệu ngữ cảnh cần thiết** theo format đã phê duyệt. Một chữ ký cần **key ID/version, issuer/purpose và signed bytes**.

Nếu chỉ giữ alias **current-key**, sau rotation sẽ khó biết ciphertext cũ dùng key nào. Và khi có compromise sẽ khó xác định dữ liệu/bên nhận bị ảnh hưởng.

### 16.4. Định nghĩa quy trình sẵn sàng

Tổ chức nên chuẩn bị và thực hành:

1. Cách **revoke IAM/KMS grants** và không bỏ sót active sessions.
2. Cách **rotate key pairs** hoặc DEK/KEK mà không phá backup.
3. Cách **phát hành thông tin revocation và public verification key** đến recipients.
4. Cách **re-encrypt/rewrap** với versioned metadata, idempotency và kiểm thử.
5. Cách **đối soát DR restore** với key state/trust epoch mới nhất.
6. Cách **ghi audit** và đánh giá residual risk.

Nên thực hiện **tabletop exercise** để xem “nếu root CA/private signing key/KEK bị lộ vào ngoài giờ, người trực có đủ quyền và thông tin để containment không?”.

## 17. Java 17: mô hình phân loại sự cố và chọn hướng xử lý

Đoạn mã sau minh họa cách **tách bản chất bằng chứng và loại key** trước khi quyết định quy trình. Nó **không tự gọi KMS, không xóa key và không làm incident response tự động**. Mục tiêu là ngăn tư duy “mọi compromise đều chỉ cần Rotate”.

~~~java
import java.util.Objects;

public final class KeyCompromiseTriageDemo {
    private KeyCompromiseTriageDemo() {}

    enum KeyKind { DEK, KEK, SIGNING_PRIVATE, HMAC, TRUST_SOURCE }

    enum Evidence {
        CONFIRMED_RAW_KEY_EXPOSURE,
        CONFIRMED_UNAUTHORIZED_KEY_USE,
        CONFIRMED_TRUST_SUBSTITUTION,
        SUSPICIOUS_ACTIVITY_ONLY
    }

    record Incident(
            String incidentId,
            String keyId,
            KeyKind keyKind,
            Evidence evidence
    ) {}

    record Plan(
            boolean containImmediately,
            boolean investigateRawMaterialExposure,
            boolean evaluateDataReEncryption,
            boolean propagateVerificationTrustChange,
            String initialPriority
    ) {}

    static Plan assess(Incident incident) {
        Objects.requireNonNull(incident);
        Objects.requireNonNull(incident.incidentId());
        Objects.requireNonNull(incident.keyId());
        Objects.requireNonNull(incident.keyKind());
        Objects.requireNonNull(incident.evidence());

        boolean knownRaw =
                incident.evidence() == Evidence.CONFIRMED_RAW_KEY_EXPOSURE;
        boolean knownAbuse =
                incident.evidence() == Evidence.CONFIRMED_UNAUTHORIZED_KEY_USE;
        boolean trustTampered =
                incident.evidence() == Evidence.CONFIRMED_TRUST_SUBSTITUTION;

        // Đây chỉ là định hướng triage: đánh giá tác động phải dựa
        // thêm vào inventory, mức độ nhạy cảm và chứng cứ thực tế.
        boolean dataRisk = (incident.keyKind() == KeyKind.DEK ||
                incident.keyKind() == KeyKind.KEK) &&
                (knownRaw || knownAbuse);
        boolean trustRisk =
                incident.keyKind() == KeyKind.TRUST_SOURCE ||
                (incident.keyKind() == KeyKind.SIGNING_PRIVATE &&
                        (knownRaw || knownAbuse));

        boolean contain = knownRaw || knownAbuse || trustTampered;
        String priority = contain
                ? "Contain active abuse and preserve evidence"
                : "Investigate and apply precautionary policy";

        return new Plan(
                contain,
                !trustTampered, // Điều tra raw exposure khi phù hợp;
                                // đây KHÔNG phải kết luận key đã lộ.
                dataRisk,
                trustRisk || trustTampered,
                priority);
    }

    public static void main(String[] args) {
        Incident leakedDek = new Incident(
                "INC-100", "invoice-dek-v7", KeyKind.DEK,
                Evidence.CONFIRMED_RAW_KEY_EXPOSURE);
        Incident signerAbuse = new Incident(
                "INC-101", "billing-signer-v2", KeyKind.SIGNING_PRIVATE,
                Evidence.CONFIRMED_UNAUTHORIZED_KEY_USE);
        Incident jwksTamper = new Incident(
                "INC-102", "issuer-jwks", KeyKind.TRUST_SOURCE,
                Evidence.CONFIRMED_TRUST_SUBSTITUTION);

        Plan p1 = assess(leakedDek);
        Plan p2 = assess(signerAbuse);
        Plan p3 = assess(jwksTamper);

        System.out.println("DEK data-review: " +
                p1.evaluateDataReEncryption());
        System.out.println("Signer trust-review: " +
                p2.propagateVerificationTrustChange());
        System.out.println("JWKS trust-review: " +
                p3.propagateVerificationTrustChange());
        System.out.println("JWKS raw-key confirmed: " +
                (jwksTamper.evidence() ==
                        Evidence.CONFIRMED_RAW_KEY_EXPOSURE));
    }
}
~~~

Kết quả minh họa:

~~~text
DEK data-review: true
Signer trust-review: true
JWKS trust-review: true
JWKS raw-key confirmed: false
~~~

### 17.1. Những điều mã không được phép tự quyết

- **Severity thực tế:** Một KEK của dữ liệu cực kỳ nhạy cảm có blast radius khác với DEK một record test.
- **Ngưỡng containment cho suspected compromise:** Một cảnh báo nghiêm trọng cũng có thể đòi suspend ngay dù chưa confirmed; mã demo chỉ minh họa chứ không thay IR policy.
- **Có cần re-encrypt toàn bộ hay không:** Cần điều tra attacker có ciphertext, wrapped DEKs hay plaintext nào, và những bản sao còn tồn tại.
- **Public trust có phải revoke ngay không:** Với Sign API abuse và private key chưa lộ, tổ chức cần quyết định phạm vi token/chữ ký, không kết luận tất cả key phải bị thu hồi như raw-key leak.
- **Key có được destroy không:** Phải đánh giá dữ liệu còn cần, backup/DR và approval.

**Plan ở trên là một bản ghi định hướng**, không phải một bộ lệnh để chạy trên production KMS. Việc tự động xóa/rotate mọi key theo nhãn “suspicious” có thể vừa phá khả dụng vừa xóa chứng cứ.

### 17.2. Triển khai policy thực tế

Nếu ứng dụng có incident workflow, nên dùng:

- **Immutable incident ID**, key ID/version và timestamps UTC.
- **Approved policy version** để giải thích quyết định.
- **Role-based approval** cho revoke, rewrap, re-encrypt và destroy.
- **KMS/HSM operation logs** đối chiếu với workflow.
- **Readback/negative tests** trước khi đóng ticket.

Một engine chỉ đọc metadata không thay thế **KMS IAM enforce**, **business authorization** hoặc **cryptographic provider validation**.

## 18. Java 17: minh họa re-encrypt dữ liệu sau khi DEK bị lộ

Khi **raw DEK** đã bị compromise, **bọc lại cùng DEK bằng KEK mới** không thay đổi khả năng giải mã ciphertext cũ của attacker. Một biện pháp xử lý dữ liệu còn thuộc quyền kiểm soát là **mã hóa lại dưới DEK mới**.

Ví dụ dưới đây minh họa:

1. Tạo **DEK-v1 và DEK-v2 độc lập** bằng CSPRNG/provider Java.
2. Tạo ciphertext-v1 dưới AES-GCM với **nonce-v1**.
3. Kiểm tra quyền migration, giải mã bản v1 bằng **expected AAD**.
4. Mã hóa lại cùng plaintext bằng DEK-v2 và **nonce-v2 mới**.
5. Chỉ đọc bản mới bằng đúng key version và AAD.

**Giới hạn:** Keys trong ví dụ nằm ở JVM để giải thích phép toán. Production nên dùng **KMS/HSM cho KEK và quản lý encrypted DEKs**, có persistence, IAM, concurrency control và audit riêng. Mã không tự giải quyết bản ciphertext/DEK mà attacker đã lấy.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class DekCompromiseMigrationDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private DekCompromiseMigrationDemo() {}

    record Envelope(
            String dekVersion,
            byte[] nonce,
            byte[] ciphertextAndTag
    ) {}

    static SecretKey freshDek() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static byte[] trustedAad(String tenant, String recordId) {
        // Caller phải xác thực tenant/record từ nguồn được tin cậy.
        byte[] t = tenant.getBytes(StandardCharsets.UTF_8);
        byte[] r = recordId.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(12 + t.length + r.length)
                .putInt(0x44454B31) // DEK1: domain/format version
                .putInt(t.length).put(t)
                .putInt(r.length).put(r)
                .array();
    }

    static Envelope encrypt(
            String keyVersion,
            SecretKey dek,
            byte[] plaintext,
            byte[] aad
    ) throws Exception {
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);
        return new Envelope(keyVersion, nonce, cipher.doFinal(plaintext));
    }

    static byte[] decrypt(
            Envelope record,
            String expectedKeyVersion,
            SecretKey dek,
            byte[] expectedAad
    ) throws Exception {
        if (!expectedKeyVersion.equals(record.dekVersion()) ||
                record.nonce().length != NONCE_BYTES) {
            throw new SecurityException("Key version/format mismatch");
        }
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, record.nonce()));
        cipher.updateAAD(expectedAad);
        return cipher.doFinal(record.ciphertextAndTag());
    }

    static Envelope migrateAfterExposure(
            Envelope existing,
            SecretKey oldDek,
            SecretKey newDek,
            byte[] trustedAad,
            boolean approvedMigration
    ) throws Exception {
        if (!approvedMigration ||
                !"dek-v1".equals(existing.dekVersion())) {
            throw new SecurityException("Migration not authorized");
        }

        byte[] plaintext = decrypt(
                existing, "dek-v1", oldDek, trustedAad);
        try {
            return encrypt("dek-v2", newDek, plaintext, trustedAad);
        } finally {
            Arrays.fill(plaintext, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        SecretKey oldDek = freshDek();
        SecretKey newDek = freshDek();
        byte[] plaintext = "Hoa don tenant A so 42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = trustedAad("tenant-a", "invoice-42");

        Envelope oldRecord = encrypt(
                "dek-v1", oldDek, plaintext, aad);
        Envelope newRecord = migrateAfterExposure(
                oldRecord, oldDek, newDek, aad, true);

        byte[] reopened = decrypt(
                newRecord, "dek-v2", newDek,
                trustedAad("tenant-a", "invoice-42"));
        try {
            System.out.println("Migration OK: " +
                    Arrays.equals(plaintext, reopened));
            System.out.println("New key version: " +
                    newRecord.dekVersion());
        } finally {
            Arrays.fill(reopened, (byte) 0);
        }

        try {
            decrypt(newRecord, "dek-v2", newDek,
                    trustedAad("tenant-b", "invoice-42"));
            System.out.println("Unexpected success");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong AAD rejected: true");
        }
    }
}
~~~

Kết quả minh họa:

~~~text
Migration OK: true
New key version: dek-v2
Wrong AAD rejected: true
~~~

### 18.1. Vì sao re-encrypt khác rewrap?

Trong ví dụ **ciphertext-v2 được tạo bằng key material khác**, và bản ghi lưu **version mới**. Rewrap chỉ thay encrypted blob bảo vệ **cùng một DEK**, không tạo key mới cho payload.

Nếu **raw DEK-v1 đã bị attacker sao chép**, họ vẫn có thể dùng nó với **ciphertext-v1** đã sao chép; việc tạo ciphertext-v2 trong database không thay đổi sự thật này.

### 18.2. Vì sao authentication tag và AAD quan trọng?

AES-GCM kiểm tra **tính xác thực của ciphertext đối với key/nonce/AAD**. Khi tenant đổi từ A sang B trong expected AAD, Decrypt thất bại thay vì âm thầm mở bản mã sai miền.

Tuy nhiên, **expected AAD phải do ứng dụng tạo từ tenant/record đã xác thực**. Nếu client được tự chọn tenant rồi ứng dụng dùng giá trị đó để tạo AAD và cho phép Unwrap, AAD không thay thế được record-level authorization.

### 18.3. Những giới hạn phải xử lý trong production

- **Không lưu raw KEK/DEK trong một Map hoặc singleton lâu dài** chỉ để tiện migration. Dùng KMS/HSM và encrypted DEKs theo thiết kế được duyệt.
- **Không xem array fields của record là immutable sâu**; parser cần defensive copies, bounds checks và schema validation.
- **Không coi Arrays.fill đảm bảo zeroization hoàn toàn**: SecretKey, provider, JVM heap và native memory có thể giữ bản sao.
- **Không dùng code demo làm công cụ bulk migration**: cần transaction, optimistic concurrency, idempotency, backpressure, progress checkpoints và readback.
- **Không xóa key cũ ngay sau một unit test**: phải kiểm kê backup/DR và legal retention.
- **Không chấp nhận AEADBadTagException rồi thử plaintext fallback hoặc bỏ AAD**. Khi tag lỗi phải fail closed và điều tra.
- **Không tiếp tục Encrypt dưới DEK đã bị lộ** trong khi migration chạy.
- **Không kết luận đã thu hồi dữ liệu khỏi attacker** chỉ vì production record đã được thay.

## 19. Backup, DR và forensic evidence sau compromise

Trong sự cố, key material và encrypted records có thể tồn tại trong **snapshots, object versions, VM backups, KMS/HSM replication, filesystem copies, partner exports, trace logs và heap dumps**.

### 19.1. Backup là nơi giữ phiên bản cũ của key/ciphertext

Giả sử:

~~~text
T0: Backup có wrappedDEK-v1 dưới KEK-v1
T1: Phát hiện KEK-v1 có nguy cơ lộ
T2: Production rewrap sang KEK-v2 hoặc re-encrypt dữ liệu
T3: Hủy KEK-v1 khi chưa kiểm kê backup
T4: DR restore dữ liệu T0
~~~

Nếu dữ liệu T0 còn nghĩa vụ lưu trữ và không có đường giải bọc hợp lệ, tại T4 **không thể phục hồi plaintext** dù backup vẫn còn. Vì vậy, một incident runbook cần có **data owner và DR owner** để cân bằng containment với availability và retention.

### 19.2. Restore không được hồi sinh quyền/trust đã thu hồi

Một snapshot trước incident có thể khôi phục:

- IAM grant cho principal bị chiếm.
- Alias trỏ về private signer cũ.
- JWKS/truststore vẫn tin public key đã revoked.
- Secret manager version chứa MAC key cũ.
- Application config cho phép API Sign/Unwrap quá rộng.

Phải có một **control plane/trust registry có thẩm quyền** để reconcile state sau restore. Dùng **revocation epoch/tombstone** hoặc cơ chế tương đương theo kiến trúc, không đơn thuần khôi phục toàn bộ file cấu hình cũ và mở traffic.

### 19.3. Evidence retention khác secret retention

Có thể cần giữ **incident reports, key references, operation logs, chữ ký, certificate chain và timestamps** theo chính sách. Điều đó **không có nghĩa cần giữ raw private key hoặc DEK** trong audit.

Forensic evidence có thể chứa secrets do sự cố; phải áp dụng quyền truy cập riêng, encryption, thời hạn và chain-of-custody. Nếu pháp lý/compliance yêu cầu bảo quản một đối tượng gốc, xử lý theo quy trình chuyên biệt thay vì tái phân phối key trong ticket.

### 19.4. Crypto-shredding cần giới hạn phát biểu

Hủy key có thể góp phần khiến dữ liệu không còn được giải mã **trong phạm vi các bản sao tổ chức kiểm soát**, nếu không còn đường giải mã khác.

Nhưng:

1. Nếu attacker đã có raw key/ciphertext, destroy trong KMS **không xóa bản đó**.
2. Nếu backup vẫn có key hoặc wrapped DEK còn unwrap được, erasure chưa hoàn tất theo mục tiêu.
3. Nếu plaintext copy tồn tại, hủy key không hủy plaintext.
4. Nếu nhiều tenants dùng chung key, hủy có thể ảnh hưởng dữ liệu hợp lệ của tenant khác.
5. Nếu có legal hold hoặc retention, hủy quá sớm có thể vi phạm nghĩa vụ và gây mất dữ liệu.

**Trạng thái destruction phải là kết quả của một dependency/evidence review, không phải hành động mặc định ngay khi có compromise alert.**

## 20. Multi-tenant và multi-region: khoanh vùng thay vì rotate toàn hệ thống một cách mù quáng

### 20.1. Tenant isolation

Một DEK riêng cho tenant A thường cho blast radius nhỏ hơn một DEK dùng chung A/B, nhưng thực tế còn phụ thuộc **data classification, số bản mã, nơi key lưu và IAM**. Một KMS KEK chung có thể bảo vệ nhiều tenants; nếu grants không ràng buộc context, một workload bị chiếm có thể xin Unwrap rộng.

Khi điều tra:

1. Key/version này bảo vệ **tenants/data domains** nào?
2. Principal có quyền **Wrap/Unwrap/Sign** trong scope nào?
3. KMS encryption context có tenant/purpose không? Nó có được tạo từ **nguồn tin cậy**?
4. Application có **record-level authorization** trước KMS calls không?
5. Attacker có thể đọc ciphertext/wrapped DEK của tenant nào?

**Một encryption context có trường tenant do client tự gửi không tự chứng minh caller được phép dùng tenant đó.**

### 20.2. Production và staging

Không tự kết luận keys đã an toàn chỉ vì chúng “được KMS mã hóa” nếu staging/test có quyền Unwrap production KEK. Một bản database production được copy sang staging có thể chứa **wrapped DEKs và ciphertext**, và staging IAM role quá rộng có thể khiến chúng bị giải mã.

Tách **KMS key resources, grants, workload identities và secret versions** theo environment; những ngoại lệ data migration/DR phải có approval và giới hạn cụ thể.

### 20.3. Multi-region key replication

Một KMS có thể cung cấp multi-region keys, vùng sao chép hoặc material riêng theo provider. Key ID/alias giống nhau trên hai regions **không tự chứng minh là cùng vật liệu hoặc cùng permissions**.

Incident response cần:

- Xác định nơi key material/grants/replicas tồn tại.
- Kiểm tra **Revoke/Disable/Delete** có hiệu lực ở vùng nào và khi nào.
- Đối soát wrapped DEKs/ciphertexts, backups và DR access.
- Giám sát instances đang dùng alias/key version cũ do cache hoặc region chưa cập nhật.
- Không báo đã cắt Sign/Unwrap toàn cục khi chỉ một region xác nhận.

### 20.4. Không gây thundering herd trong migration

Khi phải re-encrypt hàng triệu records, một job chạy đồng thời trên tất cả regions có thể gây KMS throttling, memory pressure hoặc outage. Đặt **batch sizes, concurrency limits, idempotency, retry/backoff, transaction CAS và progress metrics**.

Không hy sinh integrity vì tốc độ: mỗi record cần được đọc lại hoặc đối soát với AEAD tag/AAD và key-version metadata thích hợp.

## 21. Case study: Key compromise tại một nền tảng thanh toán Java

Một doanh nghiệp có kiến trúc:

- **Payments API:** Xác thực yêu cầu giao dịch của người dùng và đối tác.
- **Billing Service:** Mã hóa hóa đơn bằng **AES-GCM DEKs**.
- **KMS production:** Giữ **KEK** và cung cấp các API tạo/giải bọc data keys.
- **Receipt Signer:** Ký biên nhận bằng **Ed25519 private key trong HSM**.
- **Partner Gateway:** Xác thực webhook bằng **HMAC key** chia sẻ theo đối tác.
- **JWKS/PKI service:** Phân phối public verification keys và certificate trust.
- **Security/IR, Application owner, SRE và Data owner:** Quản lý incident, quyền, dữ liệu lịch sử và DR.

### 21.1. Sự cố A — Plaintext DEK xuất hiện trong application log

**Phát hiện:** Secret scanner tìm thấy chuỗi có định dạng DEK trong log của Billing Service.

**Những điều phải kiểm tra:**

- Đó là **raw DEK thật**, một encrypted data key blob hay chỉ test fixture/chuỗi giả?
- Nó thuộc key version, tenant/data domain và thời gian nào?
- Ai có quyền xem logs, log có được export sang SIEM/vendor không, có bản lưu retention không?
- Ciphertexts/wrapped DEKs nào được bảo vệ bởi DEK đó?
- Ứng dụng còn tiếp tục log raw DEK sau mỗi lần Unwrap không?

**Hành động minh họa:**

1. Ngừng log plaintext key và hạn chế quyền truy cập đến log, theo quy trình giữ chứng cứ.
2. Xác nhận DEK/version/ownership từ nguồn tin cậy, không copy raw key vào incident ticket.
3. Chặn Encrypt mới bằng DEK bị lộ và sinh DEK mới cho dữ liệu mới.
4. Khoanh vùng ciphertext còn cần để **re-encrypt**; đối soát backup/DR.
5. Kiểm tra audit KMS xem có API abuse đi kèm không.
6. Đánh giá khả năng dữ liệu cũ đã bị đọc ngoài ý muốn và ghi residual risk.

**Điểm học:** KEK ở KMS có thể chưa bị lộ; hành động cần tập trung vào **DEK exposure** và dữ liệu phụ thuộc. Chỉ rewrap DEK dưới KEK khác **không đủ**.

### 21.2. Sự cố B — Đột biến KMS Unwrap từ Analytics Service

**Phát hiện:** KMS audit ghi hàng nghìn thao tác Decrypt/Unwrap từ principal của Analytics Service, ngoài khối lượng dự kiến.

**Chưa thể khẳng định:** Raw KEK đã rời KMS. Các operation có thể trả **plaintext DEKs** cho workload.

**Hành động minh họa:**

1. Cô lập workload và thu hồi principal/grants trong scope cần thiết.
2. Đối chiếu KMS logs với data access logs để xác định **wrapped DEKs, records, tenants và outputs**.
3. Kiểm tra có lỗ hổng **tenant authorization** hoặc data access API không.
4. Đánh giá DEKs đã được giải bọc và plaintext đã được đọc hoặc xuất ra ngoài.
5. Thay/điều chỉnh IAM và application authorization; cân nhắc re-encrypt những data domains bị ảnh hưởng.
6. Kiểm thử principal cũ không còn Unwrap và các workloads hợp lệ vẫn có quyền đúng.

**Điểm học:** Đây có thể là **API abuse và data exposure**, không nhất thiết là **raw KEK compromise**. Mô tả đúng giúp chọn remediation đúng.

### 21.3. Sự cố C — Receipt signing workload bị chiếm

**Phát hiện:** Sign API từ principal Receipt Signer xuất hiện ngoài giờ, với document IDs không tồn tại trong giao dịch đã duyệt.

**Hành động minh họa:**

1. Chặn principal và quyền Sign; bảo toàn signature operation logs.
2. Kiểm kê biên nhận đã ký trong khoảng bất thường.
3. Kiểm tra **business authorization** trước Sign: có cho ký arbitrary bytes hoặc tự chọn tenant/keyId không?
4. Đánh giá private signing material có được export hoặc import từ file ngoài HSM không.
5. Nếu cần, sinh signing pair mới, phát trusted public key và thông báo relying parties.
6. Kiểm tra revocation/cache, danh sách signatures đáng ngờ và evidence thời gian.
7. Hạn chế API Sign theo key purpose, document state và rate limits.

**Điểm học:** HSM non-exportable không làm mất hiệu lực các chữ ký **đã được HSM tạo theo yêu cầu trái phép**. Cần xử lý **trust vào nội dung và signer authorization**, không chỉ raw key bytes.

### 21.4. Sự cố D — Webhook HMAC key bị gửi nhầm đối tác

**Phát hiện:** Một secret-v1 vốn dành cho đối tác A được cấp qua portal cho đối tác B.

**Hành động minh họa:**

1. Xác nhận đối tác B đã tải/nhìn thấy secret-v1 chưa.
2. Coi key-v1 là **compromised về phạm vi chia sẻ** nếu recipient không được phép có nó.
3. Sinh HMAC-v2 độc lập cho A, phân phối qua kênh được xác thực.
4. Chặn verifier chấp nhận v1 theo lịch khẩn cấp; kiểm tra anti-replay.
5. Đối soát webhook và giao dịch có thể bị giả trong khoảng ảnh hưởng.
6. Sửa partner mapping/authorization của secret distribution service.

**Điểm học:** Khóa shared secret không thể thu hồi bản sao đã cấp nhầm chỉ bằng việc đổi password portal.

### 21.5. Ma trận trách nhiệm

| Quyết định | Vai trò chịu trách nhiệm chính | Bằng chứng cần |
| --- | --- | --- |
| Xác nhận raw-key exposure hay API abuse | IR/Security phối hợp KMS/app owner | Logs, artifacts, key provenance |
| Tạm khóa quyền/operation | KMS/IAM admin theo IR runbook | Policy change, response và thời gian |
| Khoanh vùng dữ liệu phụ thuộc | Application + Data owner | Dependency inventory, record counts |
| Rewrap/re-encrypt migration | Application/DB/SRE theo approval | CAS/readback, failed records, audit |
| Trust revocation/JWKS/certificate rollout | PKI/Identity owner | Consumer acknowledgement, negative tests |
| DR/backup reconciliation | SRE/DR + Security | Restore results, revocation state |
| Đóng incident | Incident commander theo governance | Evidence, residual risk, remediation hoàn tất |

Không phải mọi sự cố đều cần **rotate toàn bộ keys của doanh nghiệp**. Cần khoanh vùng bằng key purpose, quyền, nơi material tồn tại và dữ liệu thực sự phụ thuộc.

## 22. Giám sát, kiểm toán và kiểm thử sau key compromise

### 22.1. Những dữ liệu audit nên có

| Trường audit | Mục đích |
| --- | --- |
| **incidentId / correlationId / changeId** | Nối sự kiện với quyết định phản ứng |
| **keyId, materialVersion, algorithm, purpose** | Xác định khóa nào đã tham gia |
| **owner, environment, tenant/data domain** | Phạm vi và trách nhiệm |
| **principal / operation / result** | Ai dùng Sign/Decrypt/Unwrap/Export |
| **key state trước/sau** | Đối soát hiệu lực containment |
| **trust source / certificate/JWKS fingerprint** | Đối chiếu tin cậy của public key |
| **revocation/activation timestamps** | Đo thời gian lan truyền và điểm bắt đầu tin khóa mới |
| **consumer acknowledgement** | Bên nhận nào đã cập nhật và bên nào chưa |
| **migration counts** | Số encrypted objects/wrapped DEKs đã xử lý, còn lỗi |
| **backup/DR tests** | Chứng minh không mất dữ liệu hoặc hồi sinh key cũ |
| **residualRisk / exceptions** | Không đóng sự cố quá mức chứng cứ |

Không lưu raw private key, DEK, KEK, HMAC secret, PIN HSM hoặc plaintext PII chỉ để audit. Nếu context hoặc document hash có thể tiết lộ dữ liệu, áp dụng **data classification và retention** phù hợp.

### 22.2. Các cảnh báo cần gắn với hành động

| Tín hiệu | Hành động điển hình |
| --- | --- |
| Secret scan thấy private key/DEK trong artifact | Khoanh vùng bản sao, hạn chế truy cập, đánh giá rotate |
| KMS Sign/Unwrap tăng bất thường | Kiểm tra principal, key scopes, data accesses, containment |
| Key policy/Export permission bị thay | Đối chiếu change ticket, revert/chặn theo IR, kiểm tra material |
| JWT verifier dùng public key không thuộc trusted issuer | Chặn token, điều tra trust/JWKS source |
| Signing key đã revoked vẫn có Sign calls | Chặn/điều tra đường API khác hoặc state propagation |
| Old KEK bị dùng cho Wrap mới sau cutover | Tìm writer cache/grants, chặn operation |
| GCM tag failures tăng | Kiểm tra tamper, wrong AAD/key version, dữ liệu bị lỗi |
| DR restore reactivates old grants | Chặn traffic, reconcile control plane state |
| Unacknowledged partner sau emergency revoke | Escalate; lưu residual risk và biện pháp bù trừ |

### 22.3. Ma trận negative tests

| Bài kiểm thử | Kết quả mong đợi |
| --- | --- |
| Principal đã revoke gọi KMS Sign | Bị từ chối; audit ghi operation và result |
| Principal đã revoke gọi KMS Unwrap | Bị từ chối; không trả plaintext DEK |
| Raw DEK cũ không còn được writer dùng Encrypt | Dữ liệu mới dùng version an toàn |
| Old KEK vẫn tồn tại để migration | Không dùng Wrap mới; Unwrap lịch sử chỉ theo approval |
| New DEK decrypt payload đã re-encrypt | Thành công với đúng nonce/AAD và key version |
| Sai AAD/tenant trên ciphertext | AEAD tag validation thất bại |
| Migrate record bị thay giữa chừng | CAS/transaction ngăn overwrite sai |
| Public signer key đã revoked được gửi qua JWKS cache cũ | Verifier áp dụng trust/revocation policy, không chấp nhận trái phép |
| JWT token dùng algorithm khác issuer policy | Từ chối algorithm confusion |
| Truststore bị thêm root không được phê duyệt | Integrity/deployment policy chặn |
| HMAC-v1 bị lộ tiếp tục được gửi | Bị từ chối theo emergency cutoff |
| Webhook cũ hợp lệ được replay | Chống replay/idempotency từ chối |
| KMS outage | Không fallback plaintext/hardcoded secret |
| Staging workload thử Unwrap production KEK | IAM/key policy từ chối |
| DR restore snapshot trước revocation | Không hồi sinh grants/trust/old signer |
| Hủy KEK còn wrapped DEKs cần đọc | Dependency review chặn destruction |
| Secret được đưa vào error log hoặc trace | Security tests/scans phát hiện |
| Public-key trust được lấy từ user input chưa xác thực | Registry/PKI allowlist từ chối |

### 22.4. Bằng chứng nào đủ để báo hoàn tất?

Một incident có thể được coi **khắc phục kỹ thuật** theo các tiêu chí được duyệt khi:

1. **Đường tấn công đang hoạt động** đã bị containment.
2. **Vật liệu mới** được sinh và cấp đúng nơi, không lặp lại nguồn lộ.
3. **Ứng dụng thực sự dùng key mới** cho operation mới; có telemetry key ID/version.
4. **Dữ liệu còn cần** được re-encrypt/rewrap khi đánh giá yêu cầu, có readback.
5. **Relying parties** đã nhận revocation/trust update hoặc rủi ro chưa cập nhật được ghi nhận.
6. **Backup/DR** đã đối soát, không hồi sinh key/grants cũ.
7. **Root cause** được sửa và policy được test.
8. **Residual risk** (dữ liệu đã có thể bị đọc, chữ ký giả, bản sao bên ngoài) được mô tả trung thực.

Không cần chờ có bằng chứng attacker đã đọc từng byte dữ liệu mới công nhận một **key-exposure incident** là nghiêm trọng. Ngược lại, không thể khẳng định đã “xóa toàn bộ dữ liệu bị lộ” chỉ bằng rotate khi attacker có thể đã sao chép trước đó.

## 23. Các hiểu nhầm và anti-pattern phổ biến

| Hiểu nhầm/sai lầm | Vì sao nguy hiểm | Cách hiểu hoặc xử lý đúng |
| --- | --- | --- |
| **“KMS có HSM thì không thể bị compromise.”** | IAM/admin/API abuse vẫn có thể gây ký hoặc giải mã trái phép | Bảo vệ đồng thời key material, quyền sử dụng, content authorization và logs |
| **“Không thấy raw key trong log thì key an toàn.”** | Có thể bị lộ qua dumps, CI, snapshots, backups hoặc API outputs | Đánh giá toàn bộ vòng đời và ranh giới |
| **“KMS Decrypt bị lạm dụng tức là raw KEK đã lộ.”** | Có thể chỉ là quyền API bị chiếm và plaintext DEK được trả | Phân biệt raw material exposure với key-use abuse |
| **“Private signing key không export nên không có giả mạo.”** | Attacker chiếm workload có quyền Sign vẫn tạo chữ ký | Kiểm soát signer principal, document authorization, audit |
| **“Public key được đọc công khai là key compromise.”** | Public key vốn được phép công bố | Vấn đề là private key lộ hoặc public trust bị đánh tráo |
| **“Verify chữ ký đúng nghĩa là giao dịch hợp lệ.”** | Chữ ký không kiểm tra quyền, nội dung nghiệp vụ và revocation | Verify đúng key + issuer/purpose/trust + authorization |
| **“Đổi alias là rotate key.”** | Alias có thể trỏ tới cùng raw material | Xác minh key ID/material version và cutover thực |
| **“Đổi keystore password sẽ sửa private key đã lộ.”** | Attacker đã có key bytes vẫn dùng được | Sinh key pair mới, thu hồi trust và đánh giá chữ ký |
| **“Rewrap DEK sau khi raw DEK lộ là đủ.”** | Chính DEK không đổi, ciphertext cũ vẫn phụ thuộc | Đánh giá DEK mới và payload re-encryption |
| **“Rewrap dưới KEK mới thu hồi bản KEK cũ đã bị lấy.”** | Attacker có KEK cũ và wrapped blob cũ vẫn có thể unwrap | Đánh giá bản sao cũ, DEK/data remediation và residual risk |
| **“Hủy KEK ngay khi phát hiện lộ.”** | Có thể làm mất khả năng phục hồi dữ liệu hợp lệ | Containment trước, dependency/migration/backup review rồi destruction |
| **“CRL/OCSP được cập nhật là mọi client đã từ chối.”** | Clients có cache/offline/revocation config khác nhau | Kiểm tra trust propagation và relying-party negative tests |
| **“Xóa JWT key khỏi JWKS làm mọi token cũ vô hiệu ngay.”** | Caches, verifier offline và cấu hình issuer có thể chấp nhận v1 | Revocation/issuer policy và cache invalidation thực tế |
| **“Một lần rotate định kỳ xử lý mọi lộ khóa.”** | Compromise có thể xảy ra trước hạn và cần hành động ngay | Event-driven emergency response |
| **“TLS forward secrecy bảo vệ mọi DEK at rest.”** | Forward secrecy của transport không xóa raw DEK đã cấp/giữ | Đánh giá đúng loại key và nơi sống của bí mật |
| **“Chỉ cần revoke IAM thì attacker không còn key.”** | Raw secret đã sao chép không phụ thuộc IAM | Thay material và đánh giá dữ liệu/trust liên quan |
| **“KMS AccessDenied chứng minh không có xâm nhập.”** | Có thể tồn tại những operation thành công trước đó | Kiểm tra đầy đủ key/operation logs và timeline |
| **“AES-GCM tag lỗi chắc chắn là raw DEK leak.”** | Có thể do data corruption, sai AAD/nonce/version | Điều tra đúng nguyên nhân; tag failure vẫn là tín hiệu toàn vẹn |
| **“Có nonce ngẫu nhiên nên không bao giờ trùng.”** | Nonce collision có thể xảy ra theo usage/thiết kế | Quản lý uniqueness/limits, rotate DEK theo usage khi cần |
| **“HMAC tag hợp lệ chứng minh đối tác A gửi.”** | Bên Verify cũng biết MAC secret có thể tạo tag | Kết hợp identity/network/audit, dùng chữ ký số nếu cần public verification |
| **“Mọi chữ ký lịch sử với key lộ chắc chắn giả.”** | Thiếu phân biệt thời điểm và trusted evidence | Đánh giá trust và timestamp theo chính sách |
| **“Mọi chữ ký lịch sử vẫn tốt vì Verify=true.”** | Attacker có key có thể tạo chữ ký giả | Xác minh provenance, revocation và thời điểm đáng tin |
| **“Đã xóa secret khỏi Git hiện tại nên hết rủi ro.”** | Git history, forks, caches, artifact vẫn có bản sao | Rotate/contain và rà soát phạm vi bản sao |
| **“Có audit thì cứ log plaintext DEK để điều tra.”** | Log trở thành vị trí lộ key mới | Chỉ log IDs, operations, hashes/reference an toàn và approvals |
| **“Backup an toàn nếu cứ giữ mọi raw key vĩnh viễn.”** | Tăng blast radius và phá crypto-erasure | Retention và key recovery được phê duyệt, không hidden exports |
| **“Restore thành công thì trust cũng đúng.”** | Snapshot có thể hồi sinh key/grant đã revoked | Đối soát control plane/revocation epoch sau restore |
| **“KMS outage là key compromise.”** | Nhầm availability với confidentiality/integrity | Phân loại evidence trước, xử lý HA/DR đúng |
| **“Đã re-encrypt production thì attacker quên dữ liệu cũ.”** | Bản DEK+ciphertext đã mất vẫn đọc được ngoài hệ thống | Ghi nhận residual risk và data impact |

## 24. Checklist đánh giá và ứng phó khi key compromise

Khi chuẩn bị triển khai hệ thống hoặc xử lý một sự cố thật, dùng checklist sau để tránh bỏ sót:

1. **Key identity:** Đã xác định key ID, material version, type, algorithm, purpose và owner chưa?
2. **Evidence class:** Đây là confirmed raw-key exposure, suspected compromise, API abuse, trust substitution hay lỗi sử dụng primitive?
3. **Data classification:** Key bảo vệ dữ liệu cá nhân, tài chính, chứng từ, hệ thống quan trọng hay dữ liệu thử nghiệm?
4. **Threat capability:** Attacker có raw key, quyền gọi API, ciphertext, wrapped DEK, public trust hoặc nhiều thứ cùng lúc?
5. **Timeline:** Key được tạo/kích hoạt khi nào, dấu hiệu xâm phạm bắt đầu/được phát hiện/chặn lúc nào?
6. **Inventory:** Có quan hệ KEK → DEK → ciphertext và signer → public verifiers/signed artifacts không?
7. **Tenant scope:** Đã liệt kê tenants/records/data domains có thể bị ảnh hưởng và kiểm tra record authorization?
8. **Environment:** Dev/test/staging/prod/DR có thực sự tách keys, grants và public trust không?
9. **Immediate containment:** Đã ngừng đường Sign/Decrypt/Unwrap/Export bị lạm dụng theo policy?
10. **Credentials:** IAM grants, workload tokens, sessions, admin roles và break-glass access đã được xử lý?
11. **Key material:** Có khả năng raw key đã được export/import ngoài KMS/HSM hoặc xuất hiện trong memory/artifacts?
12. **Secret locations:** Đã rà logs, CI artifacts, images, Git history, dumps, files, backups và partner distributions?
13. **Evidence protection:** Đã giữ logs/chứng cứ với quyền hạn chế mà không nhân bản raw secrets trong ticket?
14. **Data exposure:** Có bằng chứng attacker đã giải mã/đọc dữ liệu hoặc chỉ khả năng tiềm năng?
15. **Signing scope:** Nếu là private signer, đã xác định signatures/JWT/certificates/issuers/relying parties bị ảnh hưởng?
16. **MAC scope:** Nếu là shared HMAC secret, có bên nhận nào giữ bản sao và cửa sổ replay/overlap ra sao?
17. **Trusted public keys:** PKI/JWKS/truststore có bị thay và clients/verifiers có cache key cũ?
18. **Containment vs destroy:** Có giữ đường phục hồi dữ liệu hợp lệ trong khi chặn key cũ được dùng tạo mới?
19. **Replacement generation:** Key mới có được sinh từ CSPRNG/KMS/HSM đáng tin cậy và đúng key purpose/algorithm?
20. **New grants:** Các IAM policies mới có least privilege, không phát sinh wildcard access tạm rồi quên thu hồi?
21. **Rewrap vs re-encrypt:** Đã xác định trường hợp nào chỉ chuyển KEK và trường hợp nào raw DEK/data cần re-encrypt?
22. **AEAD integrity:** Migration có kiểm tra tag/AAD, nonce mới, key versions và record authorization?
23. **Concurrency:** Bulk migration có transaction/CAS, retry idempotent, progress checkpoint và quota controls?
24. **Trust propagation:** Revocation/certificate/JWKS/partner updates có bằng chứng được nhận và áp dụng?
25. **Historical signatures:** Có chính sách về Verify lịch sử, trusted timestamp và retained certificate/revocation evidence?
26. **Replay prevention:** JWT/webhook/command signed có request ID, time window, audience và idempotency khi cần?
27. **KMS/HSM semantics:** Đã phân biệt Disabled, Revoked, PendingDeletion và Destroyed theo backend thực?
28. **Backup/DR:** Đã kiểm tra snapshots, key recovery và restore không hồi sinh revoked grants/trust?
29. **Destruction approval:** Owner/Security/Data owner đã xác nhận dependency, retention, legal hold và recovery trước khi hủy?
30. **Negative tests:** Principal cũ không Sign/Unwrap được; tamper/wrong AAD/key/version bị từ chối; verifiers không tin key giả?
31. **Telemetry:** Có actual key version, old-key-use alerts, KMS anomaly metrics và consumer readiness?
32. **Residual risk:** Đã mô tả trung thực bản dữ liệu/chữ ký có thể đã bị sao chép và không thể thu hồi?
33. **Communications:** Có quy trình phối hợp chủ sở hữu, đối tác, compliance/pháp lý khi cần?
34. **Root cause:** Đã sửa đường rò, IAM policy, code logs, trust registry hay nonce/RNG bug gây sự cố?
35. **Closure:** Có bằng chứng cutover, remediation, DR, audit và phê duyệt kết thúc incident, không chỉ một trạng thái “ROTATED”?

### 24.1. Năm câu hỏi nên hỏi ngay trong một cuộc triage

**Câu hỏi 1 — Chúng ta đang nói về raw key bị lấy hay quyền sử dụng key bị lạm dụng?** Hai điều kiện này có những biện pháp containment khác nhau.

**Câu hỏi 2 — Key nào, phiên bản nào, thuộc tenant/data domain nào?** Không dựa chỉ vào alias hay tên tệp.

**Câu hỏi 3 — Những ciphertext, chữ ký và hệ thống nào thực sự dựa vào key đó?** Cần dependency graph và timeline.

**Câu hỏi 4 — Chúng ta có thể chặn hại tiếp diễn mà vẫn giữ đường khôi phục dữ liệu hợp lệ không?** Đừng xóa mù quáng KEK/private decryption key.

**Câu hỏi 5 — Chúng ta sẽ chứng minh phục hồi thành công và báo cáo rủi ro tồn dư bằng gì?** Cần logs, negative tests, readback và DR evidence.

## 25. Ghi nhớ

- **Key compromise** là khi vật liệu khóa, quyền sử dụng hoặc độ tin cậy của khóa không còn phù hợp giả định bảo mật. Có thể là **raw key exposure, API abuse, trust-source substitution hoặc lỗi sinh/sử dụng primitive**.
- **Không đánh đồng raw key bị lộ với IAM/KMS principal bị chiếm.** Cả hai có thể gây hậu quả nghiêm trọng nhưng cần điều tra và khắc phục khác nhau.
- **DEK bị lộ** có thể ảnh hưởng dữ liệu mã hóa dưới DEK đó; **KEK bị lộ** có thể ảnh hưởng nhiều wrapped DEKs. Rewrap không sửa việc raw DEK đã lộ; khi cần phải thay DEK và **re-encrypt**.
- **Private signing key bị lộ** có thể tạo chữ ký giả; **non-exportable HSM** giảm rủi ro trích xuất raw material nhưng không loại bỏ **signing oracle** nếu người gọi có quyền Sign sai.
- **Public key thường không bí mật**, nhưng public-key registry, certificate trust và JWKS phải được xác thực; một nguồn tin cậy bị tráo có thể khiến verifier nhận chữ ký giả.
- **HMAC secret bị lộ** cho phép tạo MAC giả, và HMAC không chứng minh riêng bên gửi nào đã tạo tag khi secret được chia sẻ.
- **Revocation, rotation, rewrap, re-encrypt và destruction là các thao tác khác nhau**; không dùng một thao tác để thay toàn bộ quy trình IR.
- **Rotation định kỳ không đủ cho compromise**. Phải có đường containment khẩn cấp, key versioning, IAM, trust propagation, audit và khả năng xử lý dữ liệu lịch sử.
- **Hủy key không thu hồi bản sao raw key hoặc ciphertext đã bị attacker lấy**. Đồng thời hủy quá sớm có thể làm mất dữ liệu còn nghĩa vụ lưu.
- **Backup/DR và kiểm thử âm tính** là điều kiện thiết yếu: old key/grants/trust không được hồi sinh sau restore, dữ liệu còn cần phải đọc được theo quyền.
- **Kết luận về incident phải dựa trên evidence và residual risk**, không chỉ dashboard ghi “ROTATED”, “DISABLED” hoặc “RESOLVED”.

Khi gặp một dấu hiệu **key compromise**, hãy bắt đầu bằng ba câu hỏi: **“Đối thủ có vật liệu khóa, quyền sử dụng hay chỉ kiểm soát nguồn tin cậy nào?”, “Những ciphertext, chữ ký, người dùng và hệ thống nào có thể bị ảnh hưởng?”, “Chúng ta phải chặn, thay khóa, khôi phục niềm tin và xử lý dữ liệu lịch sử như thế nào để không tạo thêm rủi ro?”** Một quy trình trả lời được các câu hỏi ấy bằng **key inventory, KMS/HSM policies, application authorization, audit, kiểm thử và bằng chứng phục hồi** mới có thể quản lý sự cố khóa mật mã một cách an toàn và có trách nhiệm.

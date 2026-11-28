# Cryptographic policy: chính sách mật mã cho toàn bộ vòng đời khóa

## 1. Vì sao cần cryptographic policy?

Một hệ thống Java có thể triển khai AES-256-GCM, Ed25519 và TLS 1.3 đúng thuật toán nhưng vẫn gặp những rủi ro nghiêm trọng:

- Một microservice dùng **khóa chung của mọi tenant** để giải mã dữ liệu không thuộc quyền của mình.
- Một lập trình viên chuyển sang **AES/ECB** vì ví dụ trên mạng ngắn hơn.
- Nhóm tích hợp bỏ **hostname validation** của TLS khi gặp lỗi chứng chỉ.
- Khóa mã hóa đã bị thu hồi vẫn được dùng tạo dữ liệu mới vì ứng dụng cache key quá lâu.
- Private signing key được giữ trong HSM, nhưng bất kỳ service account nào cũng gọi được **Sign**.
- Backup giữ ciphertext nhiều năm trong khi **KEK cần để mở DEK** đã bị hủy.
- Tên thuật toán và các tham số được phép thay đổi trực tiếp từ dữ liệu do client gửi.

Những lỗi đó không chỉ là lỗi lập trình. Chúng phản ánh sự thiếu thống nhất trong việc tổ chức quyết định: **mật mã nào được phép dùng, ai có quyền dùng khóa, mục đích và thời hạn nào hợp lệ, khi nào phải đổi khóa và bằng chứng kiểm soát được lưu ở đâu**.

**Cryptographic policy (chính sách mật mã)** là tập hợp yêu cầu có thẩm quyền của tổ chức đối với việc lựa chọn và sử dụng **thuật toán, giao thức, khóa, tham số, cơ chế tin cậy, phân quyền, lưu trữ, kiểm toán và vòng đời mật mã**. Chính sách cần đủ rõ để triển khai, kiểm thử và phát hiện vi phạm, nhưng phải có cơ chế phiên bản hóa để thích nghi khi tiêu chuẩn, mô hình đe dọa và môi trường thay đổi.

> **Chính sách mật mã không phải một danh sách tên thuật toán.** Một chính sách có hiệu lực phải kết nối thuật toán với **loại dữ liệu, mục đích khóa, phạm vi tenant, key lifecycle, IAM, KMS/HSM, backup, audit và quy trình ứng phó sự cố**.

Trong module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài này thuộc chương **Key policy** và tập trung trả lời: *Làm thế nào chuyển những nguyên tắc mật mã và quản lý khóa thành yêu cầu có thể thực thi trong hệ thống Java?*

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **cryptographic policy**, **cryptographic standard**, **procedure/runbook** và **configuration**.
2. Xác định phạm vi chính sách theo **dữ liệu, hệ thống, tenant, môi trường, thuật toán và cấp độ rủi ro**.
3. Thiết kế một **algorithm allowlist** và các yêu cầu về AEAD, TLS, chữ ký số, HMAC, hash, KDF và mật khẩu.
4. Đặt chính sách cho **key generation, distribution, storage, use, rotation, revocation, destruction và recovery**.
5. Gắn chính sách với **key inventory, owner, custodian, key usage, cryptoperiod, KMS/HSM và IAM least privilege**.
6. Giải thích **policy enforcement** ở nhiều lớp: ứng dụng Java, TLS provider, KMS/HSM, IAM, CI/CD và kiểm toán.
7. Đọc ví dụ Java 17 triển khai **policy gate trước khi AES-GCM Encrypt/Decrypt** và biết ranh giới của code minh họa.
8. Quản lý **exception, legacy migration, crypto-agility, audit và incident response** mà không tự hạ cấp bảo mật.
9. Viết checklist và test case giúp chứng minh chính sách được thực thi chứ không chỉ tồn tại dưới dạng văn bản.

## 2. Cryptographic policy là gì và khác những tài liệu liên quan ra sao?

Một tổ chức thường có nhiều cấp độ tài liệu cùng đề cập mật mã. Cần tránh gộp chúng thành một tập cấu hình không rõ ai được phép sửa.

| Cấp độ | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| **Cryptographic policy** | Tổ chức **bắt buộc** bảo vệ loại dữ liệu và khóa như thế nào? | Dữ liệu nhạy cảm lưu trữ phải được mã hóa có xác thực, key use có phân quyền và audit |
| **Cryptographic standard/profile** | Thuật toán, phiên bản, kích cỡ và tham số nào được phép cho use case? | Profile dữ liệu dùng AES-GCM; profile chữ ký dùng lược đồ được phê duyệt |
| **Procedure/runbook** | Ai làm, thao tác theo thứ tự nào, phê duyệt và kiểm tra ra sao? | Runbook rotation KEK, khôi phục HSM, thu hồi signing certificate |
| **Architecture/design** | Hệ thống thực hiện yêu cầu bằng các thành phần nào? | KMS giữ KEK, ứng dụng nhận DEK ngắn hạn, database lưu wrapped DEK |
| **Configuration/policy-as-code** | Quy tắc nào được diễn đạt để máy thực thi hoặc kiểm tra? | IAM grants, TLS policy, key state, thuật toán được cấu hình cố định |
| **Evidence/audit** | Làm sao chứng minh các quy tắc đã được áp dụng? | KMS audit, change approval, CI test, inventory reconciliation |

### 2.1. Một câu chính sách phải kiểm chứng được

Yêu cầu mơ hồ:

> Ứng dụng phải sử dụng thuật toán mã hóa mạnh.

Yêu cầu có thể kiểm tra hơn:

> Với **dữ liệu nhạy cảm lưu tại production**, dịch vụ phải dùng cơ chế **authenticated encryption** thuộc danh sách được phê duyệt. Mọi bản mã phải có **key reference/version, nonce, authentication tag và metadata cần thiết**. Khóa phải được cấp phát qua cơ chế đã duyệt, chỉ principal có quyền mới được Encrypt/Decrypt; mỗi lần dùng khóa phải tuân thủ policy về tenant, trạng thái khóa và giới hạn sử dụng.

Câu sau cho phép tạo **test case, control và audit evidence**. Không nhất thiết mọi chi tiết thuật toán phải nằm trong một câu; chính sách có thể dẫn tới **cryptographic profile** được phiên bản hóa.

### 2.2. Các mức độ yêu cầu

Một tài liệu tốt nên dùng thuật ngữ nhất quán:

- **MUST / BẮT BUỘC:** điều kiện không đạt thì phải từ chối hoặc được xử lý bằng cơ chế ngoại lệ chính thức.
- **MUST NOT / CẤM:** hành vi không được triển khai, ví dụ tắt certificate validation trong production.
- **SHOULD / NÊN:** mặc định tuân thủ, chỉ khác khi có lý do, đánh giá rủi ro và chấp thuận phù hợp.
- **MAY / CÓ THỂ:** lựa chọn được phép trong phạm vi đã xác định.

Không tự coi các từ này là bản sao chính thức của một quy định bên ngoài. Tổ chức phải **phê duyệt ngữ nghĩa và thẩm quyền** của tài liệu chính sách.

### 2.3. Policy không phải thư viện mật mã

Java cung cấp những primitive như **Cipher, Signature, Mac, KeyAgreement và SecureRandom**. Chúng có thể thực hiện phép toán nhưng không biết toàn bộ chính sách doanh nghiệp:

- Ai sở hữu dữ liệu?
- Service account thuộc tenant nào?
- Khóa có hết cryptoperiod chưa?
- Chữ ký được phép phát hành loại tài liệu nào?
- Có một ngoại lệ legacy còn hiệu lực không?
- Đã có approval khi đổi KEK chưa?

Vì vậy **JCA/JCE là lớp công cụ**, còn cryptographic policy là tập **quyết định và điều kiện** được thực thi thông qua ứng dụng, KMS/HSM, IAM, hạ tầng và quy trình.

## 3. Phạm vi chính sách: bảo vệ đúng tài sản và ranh giới

Không nên viết chính sách theo kiểu “mọi hệ thống phải có một khóa AES-256” mà không phân loại tài sản. Chính sách cần bắt đầu bằng câu hỏi **đang bảo vệ điều gì, trước ai, trong bao lâu**.

### 3.1. Các loại tài sản thường cần bao phủ

- **Data in transit:** HTTP/TLS, message broker, RPC, kết nối nội bộ và đối tác.
- **Data at rest:** file, database, object storage, bản ghi lâu dài và backup.
- **Credentials:** mật khẩu đăng nhập, API secret, PSK và signing credentials.
- **Digital signatures:** chữ ký trên artifact, webhook, token, chứng từ và manifest.
- **Key material:** DEK, KEK, root/master secret, private keys, MAC keys, derived/session keys.
- **Trust material:** CA/trust anchors, chứng chỉ, public verification keys và JWKS.
- **Recovery material:** encrypted backups, recovery shares, HSM quorum credentials.
- **Metadata mật mã:** key ID, key version, salt, nonce, tag, AAD format, algorithm/profile version.

Một số metadata không cần bí mật nhưng **tính toàn vẹn** của chúng phải được bảo vệ. Ví dụ, việc sửa public verification key trong trust store có thể khiến hệ thống chấp nhận chữ ký giả dù private signing key thật chưa bị lộ.

### 3.2. Phân loại dữ liệu và mô hình đe dọa

Chính sách cần liên kết với mức độ nhạy cảm và thời hạn bảo vệ. Một ma trận minh họa:

| Dữ liệu/tài sản | Mục tiêu | Kiểm soát chính cần thiết |
| --- | --- | --- |
| Thông tin thanh toán production | Bí mật, toàn vẹn, đúng tenant | AEAD, DEK/KEK, IAM, AAD, audit, rotation và recovery |
| API giữa các dịch vụ | Bí mật và xác thực peer | TLS chuẩn, kiểm tra certificate/identity, authorization |
| Webhook có chữ ký | Xác thực nguồn và tính toàn vẹn | Trusted verification key, signature, timestamp/idempotency |
| Password verifier | Hạn chế offline guessing | Password-based KDF, salt, cost, không lưu password |
| Artifact release | Xác thực nhà phát hành | Signing key được bảo vệ, manifest, trust và audit |
| Backup mã hóa dài hạn | Bí mật + khả năng khôi phục | DEK/KEK retention, key version, restore test |
| Root/KEK cấp cao | Ngăn lộ hàng loạt khóa con | KMS/HSM, non-exportability khi phù hợp, quorum, SoD |

**Không có một cấu hình tối ưu cho mọi tài sản.** Ví dụ, session key ngắn hạn không nên giữ backup như KEK dùng cho dữ liệu lưu trữ nhiều năm.

### 3.3. Trust boundary

Chính sách phải chỉ rõ các ranh giới:

~~~mermaid
flowchart TD
    U["Người dùng / đối tác"] --> API["Java API / TLS boundary"]
    API --> AUTH["Authentication + business authorization"]
    AUTH --> APP["Ứng dụng xử lý dữ liệu"]
    APP -->|"KMS SDK theo IAM / key policy"| KMS["KMS/HSM key boundary"]
    APP -->|"AES-GCM và wrapped DEK"| DB["Database / storage"]
    KMS --> LOG["Audit về thao tác và policy"]
    APP --> LOG
    OWNER["Key owner + security policy"] --> APPROVAL["Approved policy / exceptions"]
    APPROVAL --> APP
    APPROVAL --> KMS
~~~

Trong sơ đồ này:

- **TLS** bảo vệ kết nối; không thay kiểm tra quyền của user/tenant.
- **KMS/HSM** có thể giữ KEK/private key non-exportable; không biết mọi điều kiện nghiệp vụ của bản ghi.
- **Ứng dụng** có thể nhận plaintext DEK nếu API GenerateDataKey hỗ trợ, nên RAM/log của ứng dụng vẫn là một ranh giới cần bảo vệ.
- **Key owner/security** quyết định policy, nhưng key custodian/administrator chỉ triển khai với quyền được cấp và bằng chứng phù hợp.
- **Audit** phải được bảo vệ khỏi sửa/xóa trái phép, không chỉ bật logging.

## 4. Các nguyên tắc nền tảng của cryptographic policy

Một chính sách hữu ích thường bắt đầu bằng các nguyên tắc không phụ thuộc tên nhà cung cấp cụ thể.

### 4.1. Approved cryptography only

Ứng dụng chỉ được dùng thuật toán, chế độ, thông số và giao thức thuộc **approved profiles** cho use case cụ thể.

- Không dùng primitive tự thiết kế thay thuật toán chuẩn.
- Không để client tự gửi tên thuật toán rồi bắt server dùng nếu không khớp policy.
- Không dùng thuật toán cho mục đích mà nó không được thiết kế, ví dụ **Ed25519** làm key agreement hoặc **SHA-256 thường** làm MAC.
- Không dùng thuật toán đã bị cấm trong production chỉ vì phải hỗ trợ một file legacy, trừ khi có **ngoại lệ migration giới hạn**.

### 4.2. Key purpose separation

Một khóa phải có **key type, purpose và allowed operations** rõ ràng. Ví dụ:

- **DEK:** AES-GCM Encrypt/Decrypt dữ liệu thuộc phạm vi được cấp quyền.
- **KEK:** Wrap/Unwrap DEK; không dùng thay private signing key.
- **Private signing key:** Sign nội dung được phép; public counterpart Verify theo trust policy.
- **HMAC key:** GenerateMac/VerifyMac theo giao thức.
- **Root/IKM:** Derive khóa con qua KDF có domain separation.
- **ECDH private key:** KeyAgreement trong giao thức có xác thực.
- **TLS traffic key:** chỉ dùng trong phiên/hướng/giai đoạn giao thức quy định.

Một khóa có độ dài phù hợp với hai thuật toán **không phải lý do** để dùng lại cùng key material.

### 4.3. Least privilege và separation of duties

- Workload chỉ được dùng **đúng key ID/usage** cần thiết.
- Người quản trị khóa không mặc nhiên có quyền giải mã dữ liệu.
- Người phê duyệt key policy không nên tự thực thi rồi tự xóa log.
- Auditor phải có đường xem evidence nhưng không cần Sign/Decrypt.
- Quyền khẩn cấp (*break-glass*) phải có điều kiện kích hoạt, thời hạn, ghi log và thu hồi.

### 4.4. Fail closed và secure defaults

Khi thiếu key, sai thuật toán, tag không hợp lệ, certificate không xác thực được hoặc trạng thái khóa bị thu hồi, hệ thống **từ chối thao tác** thay vì tự hạ cấp.

Ví dụ, **AES-GCM tag failure** không được trở thành “cứ chuyển sang AES-CBC” hoặc “thử bỏ AAD”. **TLS certificate error** không được xử lý bằng TrustManager chấp nhận mọi chứng chỉ.

### 4.5. Crypto-agility nhưng không algorithm confusion

**Crypto-agility** là khả năng thay thuật toán, tham số và phiên bản giao thức có kiểm soát khi rủi ro thay đổi.

Nó **không** có nghĩa là nhận bất kỳ chuỗi thuật toán nào từ request rồi tạo Cipher tương ứng. Phiên bản và thuật toán phải được chọn từ **allowlist do server quản lý**, với migration path và deadline, chống downgrade.

### 4.6. Visibility và accountability

Mỗi khóa quan trọng cần biết **owner, custodian, storage reference, key state, phiên bản, mục đích, phụ thuộc dữ liệu, thời hạn review/rotate và audit trail**. Không có inventory đáng tin, chính sách thường không thể triển khai nhất quán.

## 5. Chính sách thuật toán: cho phép đúng tổ hợp

Một **algorithm allowlist** không chỉ là danh sách AES, RSA, SHA-256. Phải mô tả **algorithm + mode + parameters + use case + key source + version**.

### 5.1. Profile mã hóa đối xứng

Ví dụ cho **dữ liệu mới** lưu tại production:

| Thành phần | Chính sách minh họa | Vì sao |
| --- | --- | --- |
| **Cipher** | AES-GCM với khóa đúng độ dài đã duyệt | Có authenticated encryption |
| **Key source** | DEK ngẫu nhiên đủ mạnh từ CSPRNG/KMS | Không lấy raw password làm key |
| **Nonce/IV** | 96-bit nonce theo chiến lược duy nhất dưới cùng DEK | Tránh GCM nonce reuse |
| **Authentication tag** | Tag đủ độ dài theo profile, kiểm tra trước dùng plaintext | Chống sửa bản mã/AAD |
| **AAD** | Bản mã gắn resource, tenant, purpose theo schema byte xác định | Giảm rủi ro di chuyển sai ngữ cảnh |
| **Encryption at rest** | DEK được bọc dưới KEK/KMS theo phân loại dữ liệu | Tách vòng đời key và data |
| **Key ID/version** | Lưu đủ metadata để giải mã bản ghi cũ | Hỗ trợ rotation/restore |

**AES-128 và AES-256** đều là biến thể AES được sử dụng trong nhiều hệ thống chuẩn; lựa chọn phải dựa vào profile/rủi ro/khả năng tương thích. Việc dùng chữ **256** không tự cứu thiết kế khi nonce trùng, khóa lộ hoặc ứng dụng bỏ tag check.

Các cơ chế như **ChaCha20-Poly1305** có thể phù hợp khi giao thức/thư viện và chính sách cho phép. Không thêm thuật toán vào allowlist chỉ vì provider đã hỗ trợ nó.

### 5.2. Các lựa chọn cần cấm hoặc giới hạn

- **AES-ECB:** không phù hợp cho mã hóa dữ liệu tổng quát vì làm lộ cấu trúc và không có xác thực.
- **DES/3DES** cho mã hóa dữ liệu mới: không nên là lựa chọn mặc định của hệ thống mới; xử lý legacy theo chương trình migration được phê duyệt.
- **RC4** và các cơ chế lỗi thời: không dùng cho kết nối/dữ liệu mới.
- **CBC không có kiểm tra toàn vẹn**: không thể thay AEAD bằng CBC trần mà giữ cùng mức bảo vệ.
- **Tự băm password một lần bằng SHA-256** để tạo encryption key.
- **Thuật toán hoặc mode do client không tin cậy chỉ định** ngoài allowlist.

Nếu còn ciphertext legacy, chính sách có thể cho phép **giải mã có kiểm soát** để migration nhưng **không cho mã hóa mới** theo cơ chế cũ. Chỉ định **deadline, owner, inventory, dữ liệu phụ thuộc và hướng chuyển đổi**.

### 5.3. Quy tắc nonce của AES-GCM phải vận hành được

~~~text
Trong phạm vi MỘT khóa AES-GCM:
   Encrypt(K, nonce1, ...)   OK nếu nonce1 mới
   Encrypt(K, nonce2, ...)   OK nếu nonce2 khác nonce1
   Encrypt(K, nonce1, ...)   KHÔNG ĐƯỢC lặp dưới cùng K
~~~

Một hệ thống phân tán phải xét:

- Nhiều thread/process/instance cùng dùng DEK.
- Restart, snapshot, failover và rollback counter.
- Số lượng bản ghi được mã hóa dưới một DEK.
- Random nonce và xác suất va chạm khi số lần dùng key tăng.
- Key rotation khi đến giới hạn thuật toán hoặc policy.

**Chính sách “dùng 12 byte random nonce” chưa đầy đủ** nếu không giới hạn số bản mã, cách cấp nonce và vận hành ở quy mô lớn. Với môi trường cần bảo đảm chặt, có thể dùng chiến lược cấp phát nonce duy nhất phù hợp, được thiết kế và kiểm chứng.

### 5.4. AEAD không tự chống replay hoặc rollback

Ciphertext, AAD và tag hợp lệ có thể bị phát lại nguyên vẹn. Chính sách ứng dụng phải bổ sung **event ID, sequence, timestamp được xác thực, version/counter hoặc idempotency state** khi cần tính mới.

Đừng coi một tag đúng là bằng chứng “giao dịch chưa được xử lý”.

## 6. Chính sách hash, HMAC, chữ ký số và KDF

### 6.1. Hash dùng để kiểm tra integrity, không tự xác thực nguồn

**SHA-256** hoặc họ SHA-2 có thể dùng tạo digest. Nhưng:

~~~text
digest = SHA-256(message)
~~~

Nếu attacker sửa được cả message và digest đi kèm, họ có thể tính digest mới. Để chống giả mạo, cần **digest tham chiếu từ nguồn đáng tin**, HMAC hoặc chữ ký số theo threat model.

Chính sách nên quy định:

- Hash nào được phép cho use case mới.
- Hash nào chỉ được đọc để tương thích legacy.
- Có yêu cầu chống sửa đổi có chủ đích hay chỉ phát hiện lỗi lưu trữ/truyền tải.
- Nguồn tin cậy của digest/manifest và các bằng chứng xác minh.

### 6.2. HMAC

**HMAC-SHA256** có thể dùng tạo/xác minh MAC với khóa bí mật phù hợp:

~~~text
MAC = HMAC(macKey, canonicalMessageBytes)
VerifyMAC = ConstantTimeCompare(
    HMAC(macKey, receivedMessageBytes), receivedMAC
)
~~~

Một phía có raw HMAC key về mặt toán học có thể **tạo MAC**, không chỉ verify. Nếu yêu cầu **VerifyMac-only**, cần cơ chế KMS/HSM hoặc dịch vụ kiểm soát không cung cấp raw key cho verifier. Không xuất shared HMAC key cho mọi client rồi tuyên bố client chỉ được xác minh.

Chính sách phải quy định **key rotation, tag length nếu có rút ngắn, message format, anti-replay và allowed principals**. Không xây MAC tùy tiện bằng **SHA256(secret || message)**.

### 6.3. Chữ ký số và trust policy

Một profile chữ ký có thể cho phép **Ed25519, ECDSA với curve/hash phù hợp, hoặc RSA-PSS** theo yêu cầu và nền tảng.

Cần kiểm soát đồng thời:

1. Private signing key được tạo/giữ ở ranh giới phù hợp.
2. Quyền **Sign** chỉ cấp cho workload cần và với **purpose** được phê duyệt.
3. Payload được ký có **định dạng byte xác định**; tenant/issuer/audience/amount quan trọng phải nằm trong phần được bảo vệ.
4. Public verification key được lấy từ **trusted registry/certificate/JWKS** gắn đúng issuer.
5. Thuật toán, key type, key ID/version và key usage được ràng buộc.
6. Phép Verify thành công còn phải đi kèm **authorization, thời hạn, chống replay** khi cần.
7. Key rotation/revocation phải cập nhật verifier và lưu evidence cho xác minh lịch sử.

Không cho client tự cung cấp bất kỳ public key nào rồi coi kết quả **Verify=true** là đã chứng minh danh tính.

**RSA-OAEP** là cơ chế mã hóa bất đối xứng thích hợp trong một số use case, không phải tên một lược đồ chữ ký. **RSA-PSS** dành cho chữ ký; không thay hai chức năng chỉ vì cùng dùng RSA.

### 6.4. KDF và domain separation

Với **input key material mạnh**, **HKDF** hoặc key schedule chuẩn có thể dẫn xuất nhiều khóa con:

~~~text
Root / ECDH shared secret
       |
       +-- KDF(info = "billing/v1|tenant-A|encrypt") -> encryption key
       +-- KDF(info = "billing/v1|tenant-A|mac")     -> MAC key
       +-- KDF(info = "billing/v1|tenant-A|wrap")    -> wrapping key
~~~

Các nhãn trên chỉ minh họa; không phải protocol production. Chính sách phải quy định **kdf algorithm, salt, info encoding, output length, purpose và phạm vi root/IKM**. Đặc biệt, context phải được tạo từ **giá trị đã xác thực** khi dùng để tách tenant.

**HKDF nhanh không thay password-based KDF** khi nguồn là password dễ đoán. Trong password hashing hoặc mã hóa từ passphrase, dùng **Argon2id, scrypt, PBKDF2-HMAC-SHA256** theo chính sách và tính năng môi trường; có **salt riêng, cost parameters, version và kế hoạch migration**.

Không dùng password verifier của database làm key mã hóa dữ liệu. Nếu verifier bị lộ, attacker có thể có chính key material đang được sử dụng.

### 6.5. Key agreement và xác thực danh tính

Đối với **ECDH/X25519**, chính sách cần yêu cầu:

- Chỉ dùng nhóm/đường cong và provider được phê duyệt.
- Kiểm tra public input/shared secret theo giao thức.
- **Authenticated key establishment** thay vì ECDH không xác thực.
- Không dùng raw shared secret làm AES key trực tiếp ngoài một key schedule đã được thiết kế.
- Tách traffic keys theo vai trò/hướng và giới hạn phiên.
- Hủy ephemeral keys/session secrets khi không cần.
- Tuân thủ khả năng **forward secrecy** mà giao thức thực sự cung cấp.

**ECDH không tự chống MITM**; công thức toán học có thể đúng với kẻ mạo danh. Với dịch vụ Java thông thường, dùng **TLS 1.3/JSSE** là lựa chọn phù hợp hơn tự viết protocol.

## 7. Chính sách TLS, certificate và key establishment

### 7.1. Mục đích chính sách truyền thông

Một profile TLS cần bảo đảm:

- Kênh bảo mật dùng **phiên bản và cipher suites được phép**.
- Danh tính máy chủ được kiểm tra bằng chứng chỉ/chuỗi tin cậy phù hợp.
- **Hostname/service identity validation** không bị tắt.
- Khi cần mTLS, danh tính client cũng được kiểm tra và ánh xạ sang principal.
- Giao thức/key exchange phù hợp với yêu cầu **forward secrecy**.
- Chính sách **PSK, session resumption và 0-RTT** rõ ràng.
- Key logging/debug secrets bị giới hạn trong production.
- Khóa và certificate có lifecycle, renewal, revocation/incident process.

### 7.2. TLS 1.3 và ngoại lệ

Nhiều hệ thống ưu tiên **TLS 1.3** vì key schedule và tập lựa chọn hiện đại hơn, nhưng cần tránh câu khẳng định quá rộng “TLS 1.3 có FS trong mọi chế độ”.

| Trường hợp | Điểm chính sách cần kiểm tra |
| --- | --- |
| Full handshake có ephemeral (EC)DHE | Xác thực peer và session secret lifecycle để đạt bảo đảm FS phù hợp |
| PSK-only key establishment | Không mặc nhiên có FS trước việc PSK bị lộ về sau |
| PSK kết hợp DHE | Có thể có bảo đảm FS cho traffic theo giao thức/điều kiện |
| 0-RTT early data | Có nguy cơ replay và không có cùng tính chất FS như dữ liệu sau DHE mới |
| TLS 1.2 legacy | Chỉ cho phép cấu hình đã được duyệt nếu cần; kiểm soát key exchange/cipher suite |

Hệ thống thanh toán nên có chính sách rõ cho **0-RTT**, đặc biệt không dùng nó cho thao tác không idempotent khi thiếu cơ chế chống replay.

### 7.3. Certificate và trust governance

Một chứng chỉ X.509 chứa public key và thông tin danh tính, nhưng **parse được certificate không đồng nghĩa tin certificate**. Chính sách verifier phải định nghĩa:

- Trust anchors/CA nào được phê duyệt.
- Danh tính nào được chấp nhận cho hostname/service/issuer.
- Kiểm tra thời hạn, chain, key usage/extended key usage.
- Phương án kiểm tra thu hồi theo rủi ro và cách xử lý khi không lấy được trạng thái thu hồi.
- Thời hạn certificate, chủ sở hữu, rotation/renewal và phản ứng khi private key bị lộ.
- Quy trình thay trust anchors và public keys được bảo vệ chống sửa.

Một thay đổi **JWKS URL/trust store/certificate pin** cần được coi như **thay đổi bảo mật**, không phải sửa chuỗi cấu hình thông thường.

### 7.4. TLS không thay IAM

Một client có thể kết nối mTLS thành công nhưng **không có quyền đọc dữ liệu của tenant B**. Chính sách mật mã phải yêu cầu đồng thời:

~~~text
TLS authenticated channel
        +
Workload/user authentication
        +
Business authorization per tenant/resource
        =
Yêu cầu có thể được xử lý, nếu các điều kiện khác đều đúng
~~~

Không dùng chứng chỉ hoặc shared key như giấy phép truy cập không giới hạn.

## 8. Chính sách sinh khóa và bảo vệ vật liệu khóa

### 8.1. Key generation

Mỗi key type cần quy tắc sinh cụ thể:

- **DEK/KEK đối xứng:** dùng CSPRNG hoặc cơ chế sinh của KMS/HSM phù hợp.
- **Signing key pair:** KeyPairGenerator/provider/HSM thích hợp, đúng thuật toán.
- **ECDH ephemeral keys:** sinh theo giao thức để tạo key material cho từng phiên/nhóm phiên phù hợp.
- **HMAC key:** bí mật có entropy phù hợp, không dùng password chưa qua cơ chế xử lý tương ứng.
- **Password-derived material:** KDF dành cho password với salt/cost đúng policy.
- **Root/master secret:** ranh giới bảo vệ cao và quy trình tạo/khôi phục riêng.

Không lấy **timestamp, tenant ID, UUID có thể đoán, tên máy hoặc chuỗi cấu hình** làm khóa bí mật.

### 8.2. Non-exportability và key locality

Với khóa giá trị cao, một policy có thể yêu cầu **non-exportable private signing key hoặc KEK** nếu nhà cung cấp hỗ trợ. Nhưng phải xác định:

- Có thể **Sign/Decrypt/Unwrap** mà key material không xuất khỏi ranh giới bảo vệ không?
- Có cần xuất **plaintext DEK** về ứng dụng để mã hóa dữ liệu không?
- Chính sách có ngăn được tài khoản vận hành **gọi API nhạy cảm** một cách quá rộng không?
- HSM/KMS thực sự hỗ trợ **algorithm/key type/operation** cần thiết không?
- Backup và recovery có giữ nguyên thuộc tính non-exportable trong mô hình provider không?

**Non-exportable không đồng nghĩa không thể bị lạm dụng.** Workload có quyền KMS Decrypt có thể lấy plaintext hoặc DEK qua API trong nhiều kiến trúc; phải kiểm soát **quyền sử dụng**, không chỉ quyền xuất byte.

### 8.3. Không ghi secret vào vùng không kiểm soát

Chính sách phải cấm hoặc giới hạn việc đưa:

- Private keys, root keys, HMAC keys, plaintext DEKs/KEKs.
- Shared secrets/HKDF PRKs, TLS traffic secrets.
- Passwords, pepper, recovery shares.
- Access tokens hoặc decrypted sensitive payload.

vào **log, metrics, trace, crash dump, source code, repository, build artifact, chat, email hoặc ticket** không đủ ranh giới an toàn.

Với JVM, **Arrays.fill** giúp giảm thời gian tồn tại của một số mảng byte/char, nhưng không bảo đảm xóa mọi bản sao trong provider/heap/native memory. Ưu tiên **không xuất bí mật**, giới hạn tuổi thọ object và bảo vệ runtime/dumps.

## 9. Chính sách vòng đời khóa: tạo, sử dụng, rotation, thu hồi, hủy

Một cryptographic policy có hiệu lực phải đưa ra yêu cầu cho **toàn bộ vòng đời**, không chỉ bước Encrypt đầu tiên.

~~~mermaid
flowchart LR
    CREATE["Generate / Import"] --> REG["Register inventory + owner/custodian"]
    REG --> ACT["Activate + grant minimal rights"]
    ACT --> USE["Use for approved purpose"]
    USE --> REVIEW{"Cryptoperiod / risk review"}
    REVIEW -->|"Còn phù hợp"| USE
    REVIEW -->|"Thay khóa"| ROT["Rotate / rekey / migrate"]
    ROT --> LEG["Retire old key for new operations"]
    LEG --> ARCH["Legacy verify/decrypt nếu được phép"]
    ARCH --> DEST["Destroy after dependency check"]
    REVIEW -->|"Compromise"| REVOKE["Suspend / revoke + incident response"]
    REVOKE --> ROT
~~~

### 9.1. Key inventory là một phần chính sách

Với khóa quan trọng, inventory tối thiểu nên ghi:

| Field | Ý nghĩa |
| --- | --- |
| **keyId / version** | Xác định chính xác key material hoặc phiên bản |
| **keyType / algorithm / usage** | DEK, KEK, signing, HMAC, root; các operations được phép |
| **service / environment / tenantScope** | Phạm vi nghiệp vụ và ranh giới |
| **owner / custodian** | Ai phê duyệt chính sách, ai chịu trách nhiệm giám hộ |
| **kmsReference / storageMode** | Nơi giữ khóa, yêu cầu non-exportability |
| **state / cryptoperiod** | Khóa đang active, read-only, suspended, revoked hay pending deletion |
| **createdAt / rotateDue / reviewDue** | Mốc theo dõi vòng đời |
| **recoveryPolicy / dependencies** | Wrapped DEKs, backup, certs hoặc dữ liệu phụ thuộc |
| **policyVersion / approvals** | Cấu hình đã duyệt và bằng chứng thay đổi |
| **auditRef** | Liên kết nhật ký thao tác và lịch sử quản trị |

Inventory **không nên lưu raw key, private key, recovery shares hoặc secrets**. Nó là công cụ quản trị, không phải kho bí mật.

### 9.2. Cryptoperiod và key state

Một khóa có thể hết thời hạn dùng cho **Encrypt hoặc Sign mới**, nhưng vẫn cần cho **Decrypt hoặc Verify dữ liệu cũ**. Chính sách nên phân biệt các quyền theo giai đoạn:

| Trạng thái chính sách minh họa | Encrypt/Sign mới | Decrypt/Verify cũ |
| --- | --- | --- |
| **ACTIVE** | Có theo IAM và purpose | Có theo IAM và purpose |
| **LEGACY_READ_ONLY** | Không | Có giới hạn nếu policy cho phép |
| **SUSPENDED** | Không | Từ chối hoặc xử lý riêng theo incident policy |
| **REVOKED** | Không | Không cho use case đã bị thu hồi; lịch sử xử lý theo chính sách riêng |
| **DESTROYED** | Không | Không thể dựa vào khóa đã mất |

Tên trạng thái trên là **mô hình ứng dụng minh họa**. Nhà cung cấp KMS có thể chỉ hỗ trợ **Enabled/Disabled/PendingDeletion** hoặc mô hình khác; cần triển khai một lớp policy đúng với khả năng thực tế, không tự giả định mọi provider hỗ trợ decrypt-only như nhau.

### 9.3. Rotation, rewrap và re-encrypt

~~~text
Ban đầu:
  DEK-v1 --AES-GCM--> Ciphertext-v1
  KEK-v1 --Wrap(DEK-v1)--> WrappedDEK-v1

Rewrap:
  KEK-v2 --Wrap(DEK-v1)--> WrappedDEK-v2
  Ciphertext-v1 có thể giữ nguyên.

Re-encrypt:
  DEK-v2 --AES-GCM, nonce mới--> Ciphertext-v2
  KEK được phép --Wrap(DEK-v2)--> WrappedDEK-v2
~~~

**Rewrap** thay cách bảo vệ DEK, không nhất thiết thay dữ liệu mã hóa. **Re-encrypt** đổi khóa dữ liệu thực tế và thường yêu cầu tạo ciphertext/tag/nonce mới.

Nếu DEK đã lộ, **chỉ rewrap cùng DEK không đủ**. Nếu KEK cũ bị lộ cùng các bản wrapped DEK cũ, cần đánh giá dữ liệu/khóa con và các bản sao đã bị attacker lấy.

### 9.4. Revocation không giống deletion

- **Disable/revoke:** chặn hoặc thay đổi quyền dùng khóa theo policy; có thể còn giữ key material phục vụ pháp lý/điều tra/phục hồi có kiểm soát.
- **Rotate:** chuyển sang key material mới, có thể cần overlap/migration.
- **Destroy:** xóa key material hoặc điều kiện khôi phục của nó; có thể làm dữ liệu không đọc được.

Trước khi destroy KEK/root hoặc private key có phụ thuộc dài hạn, cần **owner approval, dependency inventory, backup/restore test, retention review và audit evidence**.

### 9.5. Policy về sao lưu và khả năng khôi phục

Một chính sách có thể yêu cầu:

1. Xác định loại khóa nào **cần backup**, loại nào phải ephemeral và **không lưu lại**.
2. Không xuất raw key khỏi HSM nếu không có lược đồ được phê duyệt.
3. Lưu **wrapped DEK, key IDs/versions, nonce/tag/AAD/KDF metadata** phù hợp với ciphertext.
4. Giữ KEK/đường unwrap hợp lệ cho dữ liệu cũ theo retention.
5. Thử restore định kỳ **gồm cả khả năng giải mã**, không chỉ kiểm tra hash backup.
6. Quản lý **recovery shares/quorum** và quyền break-glass theo sự phân tách nhiệm vụ.
7. Đảm bảo thao tác phục hồi có approval, audit và thu hồi quyền tạm thời.

**Backup ciphertext thành công không có ý nghĩa nếu KEK đã bị hủy và không có đường khôi phục DEK.**

## 10. Chính sách cho KMS/HSM, IAM và key custodian

### 10.1. Trách nhiệm không chỉ thuộc security team

| Vai trò | Trách nhiệm trong cryptographic policy | Điều không mặc nhiên được quyền |
| --- | --- | --- |
| **Policy owner / security governance** | Ban hành profile, đánh giá rủi ro, phê duyệt ngoại lệ | Đọc mọi raw key hoặc dữ liệu |
| **Key owner** | Xác định mục đích, dữ liệu, cryptoperiod và yêu cầu recovery | Tự xuất KEK/private key |
| **Key custodian** | Giám hộ khóa, thực thi custody/backup/rotation theo quy trình | Decrypt hoặc Sign mọi nội dung |
| **Key administrator** | Quản lý KMS key state/grants dưới approval | Tự phê duyệt quyền nhạy cảm của mình |
| **Application owner** | Mapping key usage với business authorization | Bỏ policy chỉ để đạt latency |
| **Workload identity** | Gọi Encrypt/Decrypt/Sign/Unwrap trong phạm vi | Thay key policy, xóa audit |
| **Security auditor** | Đối soát inventory, KMS logs, policy và evidence | Tạo chữ ký hoặc giải mã dữ liệu vì tiện kiểm thử |

### 10.2. IAM và authorization hai tầng

Một KMS có thể cho phép workload gọi **Decrypt** trên key ID. Nó không nhất thiết biết request này có quyền đọc **invoice ID** của tenant B.

Cần cả hai:

~~~text
KMS authorization:
  Caller được phép dùng key X để Unwrap/Decrypt?

Business authorization:
  Caller có được đọc bản ghi R của tenant T?

Chỉ tiếp tục nếu cả hai điều kiện cùng hợp lệ.
~~~

Không lấy tenant ID chỉ từ header client để chọn key. Dùng nguồn danh tính đã xác thực và kiểm tra quyền trên resource ở tầng ứng dụng.

### 10.3. Encryption context/AAD

Một số KMS hỗ trợ **encryption context** để ràng buộc wrapped key với metadata. Ví dụ:

~~~json
{
  "service": "billing",
  "purpose": "invoice-data-key",
  "environment": "production",
  "tenant": "tenant-A"
}
~~~

- Context thường **không bí mật** và có thể xuất hiện trong audit.
- Không chứa password, token hoặc dữ liệu nhạy cảm không cần thiết.
- Context khi unwrap phải nhất quán theo API/provider và policy.
- **KMS context của wrapped DEK không thay AAD của AES-GCM trên bản mã dữ liệu** do ứng dụng tạo.
- IAM/key policy phải giới hạn ai được dùng key, không chỉ tin context do request tự khai.

### 10.4. Phân tách nhiệm vụ và phê duyệt

Với KEK/root/signing key rủi ro cao, có thể yêu cầu:

- **Dual approval** khi thay grant/exportability, khôi phục HSM hoặc hủy khóa.
- **Separate owner, custodian, executor, auditor** khi khả thi.
- **Time-bound grants** cho bảo trì/break-glass.
- **Key ceremony** khi tạo/import/recovery root keys theo chính sách.
- **Quorum hoặc split knowledge** cho recovery materials nếu được thiết kế và hỗ trợ.

Không nhầm **dual control** với **secret sharing m-of-n**: một bên là kiểm soát phê duyệt, bên kia là cơ chế phân chia bí mật/khả năng khôi phục. Không tự chia raw key bằng kỹ thuật thủ công rồi gọi đó là threshold scheme chuẩn.

## 11. Mẫu cryptographic policy cho một dịch vụ Java

Một policy có thể được diễn đạt thành **tài liệu phê duyệt**, rồi chuyển một phần sang **cấu hình máy có thể kiểm tra**. Dưới đây là **mô hình YAML minh họa**, không phải định dạng bắt buộc hoặc cấu hình trực tiếp của một nhà cung cấp.

~~~yaml
policyId: billing-crypto-policy
policyVersion: 3
environment: production
ownerTeam: security-governance
approvedBy: change-approval-reference
reviewDue: "2027-02-01"

profiles:
  invoiceAtRest:
    purpose: billing-invoice-content
    dataClass: confidential
    newEncryptions:
      algorithm: AES-256-GCM
      keySource: CSPRNG-or-approved-KMS
      nonceLengthBytes: 12
      authenticationTagBits: 128
      requireContextAAD: true
      requireKeyIdAndVersion: true
      requireWrappedDEK: true
    decryption:
      requireAuthorizedTenantAndObject: true
      requireAuthenticatedTag: true
      allowOnlyApprovedKeyVersions: true

  releaseSignatures:
    purpose: signed-release-manifest
    algorithms:
      - Ed25519
    privateKeyStorage: approved-KMS-or-HSM
    requireApprovedSignerIdentity: true
    requireTrustedVerificationKey: true

  serviceTransport:
    minPreferredProtocol: TLSv1.3
    requirePeerAuthentication: true
    requireHostnameOrServiceIdentityValidation: true
    allowZeroRttForFinancialMutations: false

keyGovernance:
  requireOwnerAndCustodian: true
  requireLeastPrivilege: true
  requireAuditOfKeyUseAndPolicyChange: true
  requireDocumentedRotation: true
  requireRecoveryDependencyInventory: true
  requireApprovalBeforeDestroy: true

exceptions:
  requireRiskAcceptance: true
  requireOwnerAndExpiry: true
  requireCompensatingControls: true
~~~

**Giới hạn quan trọng của ví dụ:**

- Các giá trị như thuật toán, độ dài nonce/tag và tên profile thể hiện **một baseline minh họa**, không phải quy định pháp luật hay cấu hình bắt buộc cho mọi hệ thống.
- Tham số KDF password hoặc cipher suites phải được điều chỉnh theo **chuẩn/chính sách hiện hành, threat model, khả năng provider và interoperability**, không đoán từ YAML.
- **approvedBy** là tham chiếu, không phải bằng chứng chỉ cần ghi một chuỗi là hợp lệ; approval phải được xác minh qua workflow đáng tin.
- Một file YAML tự nó **không thực thi KMS grants, nonce uniqueness, certificate validation hoặc chống replay**.
- Không nhận file policy hoặc tên thuật toán trực tiếp từ client chưa tin cậy để thay cấu hình server.
- Không lưu **raw key, DEK, KEK, private signing key, password hoặc recovery share** trong policy file.

### 11.1. Tách baseline và exception

Bản policy nên xác định:

~~~text
Baseline profile đã phê duyệt
        |
        +-- production: bắt buộc
        |
        +-- legacy profile:
              owner, use case, phạm vi dữ liệu,
              risk acceptance, compensating controls,
              hiệu lực từ ngày nào đến ngày nào,
              migration deadline, người giám sát
~~~

Không làm một cấu hình “allowLegacy=true” toàn hệ thống mà không có **scope, expiry và monitoring**.

### 11.2. Tránh policy drift

**Policy drift** xảy ra khi tài liệu nói một điều nhưng cấu hình thực tế khác:

- Policy yêu cầu AES-GCM, code mới lại sử dụng ECB.
- KMS policy cấp quyền Decrypt cho một principal không có trong inventory.
- Certificate của một service bị bỏ kiểm tra hostname để khắc phục lỗi kết nối.
- Key owner đã đổi nhưng inventory vẫn ghi người cũ.
- Cipher suite legacy được mở lại sau khi migration hoàn tất.

Cần tự động đối soát **configuration → approved policy version → evidence**. Nếu không thể tự động, phải có kỳ review, owner và checklist rõ ràng.

## 12. Từ policy tới enforcement: ai thực sự chặn thao tác sai?

Một **policy document** là nguồn yêu cầu; một **policy enforcement point (PEP)** mới là nơi chặn hành động. Không nên đặt toàn bộ niềm tin vào một hàm kiểm tra tự viết trong ứng dụng.

### 12.1. Lớp triển khai

~~~mermaid
flowchart TD
    GOV["Approved crypto policy + profiles"] --> REG["Key inventory / policy registry"]
    GOV --> CI["CI/CD security tests + configuration review"]
    GOV --> INF["TLS / platform configuration"]
    GOV --> IAM["KMS/HSM/IAM policy & grants"]
    REG --> APP["Java application policy gate"]
    INF --> APP
    IAM --> APP
    APP --> DEC{"Identity + resource + key usage + state + algorithm"}
    DEC -->|"Reject"| NO["Fail closed + audit"]
    DEC -->|"Allow"| OP["JCA/JCE or KMS operation"]
    OP --> DATA["Authenticated result only"]
    OP --> AUD["Audit operation + key ID/version"]
    NO --> AUD
    CI --> AUD
    IAM --> AUD
~~~

Một bản thiết kế thường có:

1. **Policy authority:** nhóm/role phê duyệt policy.
2. **Policy registry:** nguồn cấu hình/phạm vi tin cậy và version.
3. **Policy decision:** quyết định request có đáp ứng yêu cầu không.
4. **Policy enforcement:** KMS/IAM, API gateway, service code, TLS provider.
5. **Observation/audit:** bằng chứng thao tác, cấu hình và thay đổi.
6. **Review/exception:** cơ chế kiểm soát và sửa sai khi yêu cầu biến đổi.

### 12.2. Enforcement phải gần tài nguyên cần bảo vệ

Một ví dụ sai:

~~~text
Java API kiểm tra "canDecrypt=true"
        |
        v
Workload có credential KMS Decrypt mọi key/tenant
        |
Attacker chiếm workload và gọi KMS trực tiếp,
bỏ qua toàn bộ hàm Java.
~~~

Ví dụ đúng hơn:

- Java kiểm tra **principal, tenant, resource ownership**.
- KMS key policy/role giới hạn **key ID và action**, dùng encryption context khi hỗ trợ.
- Không phát raw root/private key cho workload.
- Workload identity bị giới hạn môi trường và thời gian.
- Audit KMS giúp phát hiện request bỏ qua API nghiệp vụ.

**Không một lớp nào tự giải quyết hết**: KMS không biết mọi quyền của invoice, Java application không bảo đảm account KMS của nó không bị lạm dụng nếu grants quá rộng.

## 13. Ví dụ Java 17: policy gate trước khi dùng AES-GCM

Đoạn mã sau minh họa một **lớp kiểm tra policy của ứng dụng** trước Encrypt/Decrypt. Nó kết nối ba yêu cầu:

1. **Đúng identity/tenant/resource và quyền thao tác**.
2. **Đúng key purpose, algorithm, key state và operation**.
3. **Đúng cơ chế AES-GCM** với nonce, AAD và tag.

Chương trình tạo một **DEK ngẫu nhiên trong JVM để minh họa**. Trong production, dùng **GenerateDataKey/KMS envelope encryption** và xử lý plaintext DEK theo chính sách. Đây **không phải** một KMS client, một policy engine đầy đủ hoặc lớp bảo mật thay thế IAM thực.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Objects;
import java.util.Set;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class CryptographicPolicyDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;
    private static final String PURPOSE = "billing-invoice-content";
    private static final String ALGORITHM = "AES-256-GCM";

    enum Role {
        BILLING_WRITER, BILLING_READER, AUDITOR, KEY_ADMIN
    }

    enum Operation {
        ENCRYPT, DECRYPT
    }

    enum KeyState {
        ACTIVE, LEGACY_READ_ONLY, SUSPENDED, DESTROYED
    }

    // Giả định actor đã được xác thực bởi hệ thống identity thật.
    record Actor(
            String principalId, String tenantId,
            Role role, boolean authenticated) {}

    // Metadata từ registry tin cậy, không chứa raw key.
    record KeyDescriptor(
            String keyId, String tenantScope,
            String purpose, String algorithm,
            KeyState state, Set<Operation> allowed) {

        KeyDescriptor {
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(tenantScope);
            Objects.requireNonNull(purpose);
            Objects.requireNonNull(algorithm);
            Objects.requireNonNull(state);
            allowed = Set.copyOf(allowed);
        }
    }

    record CiphertextRecord(
            String keyId, byte[] nonce, byte[] ciphertextAndTag) {}

    static void requireAllowed(
            Actor actor, KeyDescriptor key,
            Operation operation, String authoritativeTenant) {

        if (actor == null || !actor.authenticated()
                || actor.principalId() == null
                || actor.principalId().isBlank()
                || authoritativeTenant == null
                || !authoritativeTenant.equals(actor.tenantId())
                || !authoritativeTenant.equals(key.tenantScope())) {
            throw new SecurityException("Crypto use denied");
        }

        if (!PURPOSE.equals(key.purpose())
                || !ALGORITHM.equals(key.algorithm())
                || !key.allowed().contains(operation)) {
            throw new SecurityException("Crypto use denied");
        }

        if (operation == Operation.ENCRYPT) {
            if (actor.role() != Role.BILLING_WRITER
                    || key.state() != KeyState.ACTIVE) {
                throw new SecurityException("Crypto use denied");
            }
        } else if (operation == Operation.DECRYPT) {
            if (actor.role() != Role.BILLING_READER
                    || (key.state() != KeyState.ACTIVE
                        && key.state() != KeyState.LEGACY_READ_ONLY)) {
                throw new SecurityException("Crypto use denied");
            }
        } else {
            throw new SecurityException("Crypto use denied");
        }
    }

    // AAD là chuỗi field có length-prefix, không nối tùy tiện.
    static byte[] aad(String tenant, String invoiceId)
            throws IOException {

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            putField(out, "billing-policy/v1");
            putField(out, PURPOSE);
            putField(out, tenant);
            putField(out, invoiceId);
        }
        return buffer.toByteArray();
    }

    private static void putField(DataOutputStream out, String field)
            throws IOException {

        byte[] bytes = field.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static CiphertextRecord encrypt(
            Actor actor, KeyDescriptor descriptor, SecretKey dek,
            String authoritativeTenant, String invoiceId,
            byte[] plaintext) throws Exception {

        requireAllowed(
            actor, descriptor, Operation.ENCRYPT, authoritativeTenant);

        // Demo đơn giản: random nonce mới cho mỗi lần Encrypt.
        // Production phải có chiến lược bảo đảm không lặp
        // dưới cùng DEK, kể cả khi có nhiều instance/failover.
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, dek,
            new GCMParameterSpec(GCM_TAG_BITS, nonce));
        cipher.updateAAD(aad(authoritativeTenant, invoiceId));

        byte[] ciphertextAndTag = cipher.doFinal(plaintext);
        return new CiphertextRecord(
            descriptor.keyId(), nonce, ciphertextAndTag);
    }

    static byte[] decrypt(
            Actor actor, KeyDescriptor descriptor, SecretKey dek,
            String authoritativeTenant, String invoiceId,
            CiphertextRecord stored) throws Exception {

        requireAllowed(
            actor, descriptor, Operation.DECRYPT, authoritativeTenant);

        // Không để dữ liệu chưa tin cậy tự chọn key ID khác.
        if (!descriptor.keyId().equals(stored.keyId())
                || stored.nonce() == null
                || stored.nonce().length != NONCE_BYTES) {
            throw new SecurityException("Invalid encrypted record");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, dek,
            new GCMParameterSpec(GCM_TAG_BITS, stored.nonce()));
        cipher.updateAAD(aad(authoritativeTenant, invoiceId));

        // doFinal trả plaintext chỉ khi xác thực tag thành công.
        return cipher.doFinal(stored.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey demoDek = generator.generateKey();

        KeyDescriptor key = new KeyDescriptor(
            "billing-dek-v3", "tenant-A", PURPOSE, ALGORITHM,
            KeyState.ACTIVE,
            Set.of(Operation.ENCRYPT, Operation.DECRYPT));

        Actor writerA = new Actor(
            "writer-A", "tenant-A", Role.BILLING_WRITER, true);
        Actor readerA = new Actor(
            "reader-A", "tenant-A", Role.BILLING_READER, true);
        Actor readerB = new Actor(
            "reader-B", "tenant-B", Role.BILLING_READER, true);
        Actor auditorA = new Actor(
            "auditor-A", "tenant-A", Role.AUDITOR, true);

        byte[] plaintext = "invoice=154;amount=250000"
            .getBytes(StandardCharsets.UTF_8);

        CiphertextRecord stored = encrypt(
            writerA, key, demoDek, "tenant-A", "invoice-154",
            plaintext);

        byte[] restored = decrypt(
            readerA, key, demoDek, "tenant-A", "invoice-154",
            stored);

        System.out.println("Authorized read: "
            + Arrays.equals(plaintext, restored));

        try {
            decrypt(readerB, key, demoDek,
                "tenant-A", "invoice-154", stored);
            throw new AssertionError("Expected deny");
        } catch (SecurityException expected) {
            System.out.println("Foreign tenant denied: true");
        }

        try {
            decrypt(auditorA, key, demoDek,
                "tenant-A", "invoice-154", stored);
            throw new AssertionError("Expected deny");
        } catch (SecurityException expected) {
            System.out.println("Auditor decrypt denied: true");
        }

        try {
            decrypt(readerA, key, demoDek,
                "tenant-A", "invoice-999", stored);
            throw new AssertionError("Expected tag failure");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong record AAD rejected: true");
        }

        KeyDescriptor retired = new KeyDescriptor(
            "billing-dek-v3", "tenant-A", PURPOSE, ALGORITHM,
            KeyState.LEGACY_READ_ONLY,
            Set.of(Operation.ENCRYPT, Operation.DECRYPT));

        try {
            encrypt(writerA, retired, demoDek,
                "tenant-A", "invoice-155", plaintext);
            throw new AssertionError("Expected deny");
        } catch (SecurityException expected) {
            System.out.println("Retired key encrypt denied: true");
        }

        // Không in DEK hoặc plaintext nhạy cảm vào production log.
    }
}
~~~

Kết quả dự kiến:

~~~text
Authorized read: true
Foreign tenant denied: true
Auditor decrypt denied: true
Wrong record AAD rejected: true
Retired key encrypt denied: true
~~~

### 13.1. Điều code minh họa

- **Fail closed** khi sai principal, tenant, role, purpose, algorithm, key usage hoặc state.
- **Encrypt** chỉ với key state ACTIVE và writer đúng tenant.
- **Decrypt** có thể dùng key LEGACY_READ_ONLY theo chính sách, nhưng chỉ cho reader được phép.
- **AAD** ràng buộc bản mã với tenant và invoice ID bằng byte encoding xác định.
- **Authentication tag** chặn decrypt nếu ngữ cảnh dữ liệu khác hoặc bản mã bị sửa.
- **Key ID** không được lấy tùy ý từ record để chọn key ngoài registry đáng tin.
- **Role auditor** không tự có quyền đọc plaintext.
- **Nonce** được tạo cho từng bản mã trong ví dụ; việc bảo đảm duy nhất ở quy mô production cần thiết kế riêng.

### 13.2. Điều code chưa giải quyết

**Đây là mô hình dạy học, không phải production security library.**

1. **Actor.authenticated** là một cờ giả định đã được xác thực; client không được tự đặt cờ này thành true.
2. **KeyDescriptor** phải đến từ registry/config đáng tin, không từ payload người gọi.
3. Code chưa có KMS thật: **KeyGenerator sinh DEK trong JVM**, chưa có KEK, wrapped DEK hoặc IAM grants.
4. Code không ghi audit KMS, không cấp phát key version/migration thực.
5. **CiphertextRecord** chứa mảng byte mutable; production cần defensive copy và serialization an toàn.
6. Random 96-bit nonce không tự bảo đảm không trùng khi lượng dùng khóa cao hoặc có nhiều instance; phải có strategy và usage limit.
7. Thiếu resource authorization chi tiết cho **invoice ID**. Actor được phân quyền theo tenant chưa chắc có quyền với mọi invoice; tầng ứng dụng phải kiểm tra.
8. Dữ liệu demo không có bảo vệ chống replay/rollback của một ciphertext hợp lệ cũ.
9. Không có xử lý logging, quota, persistence, backup/restore, KMS context, break-glass và approval.
10. Một tài khoản ứng dụng có IAM Decrypt quá rộng vẫn có thể **gọi thẳng KMS**, bỏ qua hàm kiểm tra Java. KMS/IAM phải thực thi ranh giới riêng.

**Giá trị của ví dụ là biến yêu cầu chính sách thành điều kiện có thể test, không khẳng định một hàm requireAllowed có thể thay toàn bộ hệ thống key management.**

## 14. Trường hợp thực tế: chính sách cho PaymentService nhiều tenant

### 14.1. Yêu cầu nghiệp vụ

PaymentService lưu dữ liệu hóa đơn, gọi đối tác thanh toán qua HTTPS và phát webhook có chữ ký số. Các tenant phải được tách quyền, có backup lâu dài, audit và khả năng ứng phó sự cố.

Chính sách cần bao phủ **ba nhóm khóa**:

| Mục đích | Key và primitive | Điều kiện policy |
| --- | --- | --- |
| **Invoice at rest** | DEK + AES-GCM; KEK trong KMS | Tenant/resource authorization, nonce/AAD, key ID/version, wrapped DEK |
| **Service transport** | TLS authenticated key establishment | Peer identity, certificate validation, protocol/group policy, anti-replay nghiệp vụ |
| **Webhook signing** | Private signing key; trusted public verification key | Sign theo purpose, key rotation, issuer/claims, timestamp/event ID |

### 14.2. Luồng xử lý

~~~mermaid
sequenceDiagram
    participant U as Authorized client
    participant P as PaymentService
    participant K as KMS/HSM
    participant D as Database
    participant A as Audit system

    U->>P: Request qua TLS đã xác thực
    P->>P: Verify principal + tenant/resource authorization
    P->>P: Chọn approved cryptographic profile + key reference
    P->>K: GenerateDataKey / Wrap theo IAM + context
    K-->>P: Plaintext DEK tạm thời + wrapped DEK
    P->>P: AES-GCM Encrypt, nonce, expected AAD
    P->>D: Ciphertext + tag + nonce + wrapped DEK + version
    P->>P: Giảm thời gian giữ plaintext DEK
    K->>A: Audit key use/policy
    P->>A: Audit request/key ID/version (không log secret)
    P-->>U: Kết quả đã qua kiểm soát
~~~

### 14.3. Các kiểm tra bắt buộc

- **Nếu tenant B yêu cầu hóa đơn A:** từ chối **trước khi** dùng DEK, ngay cả khi KMS Unwrap về mặt kỹ thuật có thể chạy.
- **Nếu key state là LEGACY_READ_ONLY:** không cho Encrypt dữ liệu mới nhưng có thể hỗ trợ Decrypt cũ theo policy.
- **Nếu AES-GCM tag không hợp lệ:** không dùng bất kỳ plaintext nào.
- **Nếu certificate của đối tác không tin cậy:** không bỏ kiểm tra hostname/trust để tiếp tục gửi dữ liệu.
- **Nếu signing key bị thu hồi:** không phát webhook mới bằng key đó; xử lý verifier/trust và hồ sơ lịch sử.
- **Nếu KEK cũ chuẩn bị hủy:** kiểm kê dữ liệu/backups còn wrapped DEK dưới KEK cũ, thử restore và có approval.
- **Nếu KMS Decrypt bị lạm dụng:** coi đây là **key usage compromise**, dù không có bằng chứng raw KEK export.

### 14.4. Một chính sách không thể chỉ nằm trong team security

Để các yêu cầu trở thành thực tế cần phối hợp:

- **Security governance:** phê duyệt thuật toán, risk acceptance, cryptoperiod và ngoại lệ.
- **Platform/KMS team:** key references, grants, HSM controls, rotation, audit và khả năng phục hồi.
- **Java application team:** business authorization, đúng AAD, fail closed, replay protection.
- **SRE/operations:** certificate renewal, secrets hygiene, backup, disaster recovery, monitoring.
- **Auditor:** đối soát evidence giữa các nguồn, phát hiện drift và quyền quá rộng.

## 15. Ngoại lệ, legacy migration và crypto-agility

Không phải doanh nghiệp nào cũng có thể thay toàn bộ hệ thống trong một đợt deploy. Vì vậy **cryptographic policy phải có cơ chế exception nhưng không được biến exception thành đường tắt vĩnh viễn**.

### 15.1. Một ngoại lệ hợp lệ cần những gì?

Tối thiểu:

1. **Use case và tài sản:** hệ thống, tenant, loại dữ liệu và thuật toán/profile chưa đạt.
2. **Risk owner:** ai có thẩm quyền chấp nhận rủi ro.
3. **Lý do kỹ thuật/nghiệp vụ:** vì sao không thể tuân thủ ngay.
4. **Đánh giá rủi ro:** khả năng bị tấn công, dữ liệu và blast radius.
5. **Compensating controls:** phân đoạn mạng, giới hạn quyền, bảo vệ phụ trợ, giám sát, rate limit hoặc giảm phạm vi.
6. **Expiration/deadline:** ngày kết thúc rõ ràng và kế hoạch migration.
7. **Approval evidence:** quy trình phê duyệt không thể giả mạo từ request.
8. **Monitoring:** ai theo dõi sử dụng ngoại lệ và cảnh báo vượt phạm vi.
9. **Rollback/kill switch:** cách chặn use case khi rủi ro tăng.

### 15.2. Không cho phép fallback nguy hiểm

Anti-pattern:

~~~text
try AES-GCM with current policy
    if tag fails:
        try CBC legacy without authentication
    if still fails:
        use raw plaintext from request
~~~

Cách tiếp cận như vậy làm **lỗi xác thực** biến thành một cơ chế hạ cấp.

Với migration hợp lệ:

- Dữ liệu legacy có **format/version đáng tin**.
- Đường đọc legacy có **scope và expiry**, không quyết định từ giá trị attacker tùy ý.
- Khi đọc thành công, có thể **re-encrypt sang profile mới** theo kế hoạch.
- **Không tạo ciphertext mới** bằng thuật toán bị ngừng sử dụng.
- Audit số lượng record legacy còn lại và tiến độ loại bỏ.
- Không bỏ authentication/authorization dù đang xử lý format cũ.

### 15.3. Crypto-agility và phiên bản hóa

Một thiết kế dễ thay thuật toán cần:

- **Key ID/version và algorithm profile** được ghi nhận rõ.
- Byte serialization của AAD, signature, KDF info có **phiên bản**.
- Không hard-code một thuật toán rồi phải sửa khắp dự án khi thay đổi.
- Không chấp nhận arbitrary algorithm string từ client.
- Có **positive tests và negative tests** cho thuật toán cũ/mới.
- Có khả năng chuyển luồng ghi mới rồi xử lý dữ liệu lịch sử.
- Có phương án **roll-forward/rollback** an toàn với key dependencies.
- Có theo dõi các tiêu chuẩn mới, khả năng thư viện/provider và yêu cầu tương thích.

### 15.4. Chuyển đổi hậu lượng tử

Hệ thống cần bảo mật thông tin lâu dài nên theo dõi **chuẩn key establishment/chữ ký hậu lượng tử** và các lựa chọn hybrid khi nền tảng hỗ trợ, đặc biệt với rủi ro **thu thập ciphertext hôm nay để giải mã trong tương lai**.

Tuy nhiên, cryptographic policy không nên yêu cầu lập trình viên tự nối **ECDH shared secret + KEM secret** theo một công thức tự chế hoặc tự sửa TLS handshake. Cần áp dụng **profile, protocol và implementation được chuẩn hóa/đánh giá**, có phiên bản, threat model, interoperability tests và kế hoạch xử lý khóa cũ.

**Forward secrecy của ECDHE cổ điển trước việc lộ signing key** không tự đồng nghĩa bảo vệ trước mọi năng lực tính toán tương lai. Đây là một lý do để cryptographic policy phải **được review định kỳ**, không đóng băng tên thuật toán mãi mãi.

## 16. Audit, compliance evidence và phát hiện vi phạm

### 16.1. Cần ghi những sự kiện nào?

| Sự kiện | Evidence hữu ích |
| --- | --- |
| **Key creation/import** | Key ID/version, owner/custodian, algorithm, policy/approval reference |
| **Grant/policy change** | Principal, action, before/after, change ticket, approver |
| **Crypto use** | Key ID/version, workload, operation, timestamp, result, request ID |
| **Rotation/rekey** | Khóa cũ/mới, state transition, migration/rewrap progress |
| **Certificate/trust change** | Issuer, certificate/public key metadata, approval, validity, trust source |
| **Backup/restore** | Recovery plan, restore test results, key dependencies |
| **Suspension/revocation** | Nguyên nhân, thời điểm, cập nhật client/cache |
| **Destruction** | Approval, dependency validation, KMS evidence |
| **Exception** | Risk owner, scope, duration, compensating controls và review |
| **Incident** | Điều tra quyền/key material, kết quả audit, hành động khắc phục |

**Không log** raw key, private keys, DEK/KEK rõ, HMAC secret, TLS traffic secret, password, pepper, recovery share hoặc plaintext nhạy cảm.

### 16.2. Audit phải bảo vệ tính toàn vẹn

Nếu một tài khoản vừa có quyền dùng KEK vừa có thể xóa audit log, việc điều tra sau khi bị xâm phạm rất khó. Cần tách quyền ghi/đọc/xóa, retention, kho lưu có bảo vệ, correlation ID và đối soát với **KMS logs, IAM history, change tickets và inventory**.

Không coi “có log” là tương đương “đã ngăn hành vi sai”. **Enforcement phải chặn từ trước**; audit dùng để phát hiện và truy vết.

### 16.3. Các chỉ số cần theo dõi

- Số/tỷ lệ key **không có owner/custodian**.
- Số key quá hạn cryptoperiod, review hoặc rotation.
- Số grants cho phép Decrypt/Sign/Unwrap rộng hơn scope.
- Tỷ lệ Encrypt/Decrypt thất bại do key state, algorithm mismatch hoặc AEAD tag.
- Số trường hợp certificate validation bị tắt trong cấu hình.
- Tỷ lệ dịch vụ chưa dùng approved TLS profile.
- Số legacy ciphertext/connection còn dùng exception quá hạn.
- Tỷ lệ restore test thành công gồm cả khả năng unwrap.
- Số trường hợp manual key export hoặc key logging xuất hiện ở production.
- Số policy drift và thời gian khắc phục.
- Số hành động break-glass và thời gian thu hồi quyền.
- Số lần cập nhật trust store/JWKS/key policies thiếu approval.

Mỗi metric cần **owner và hành động** khi vượt ngưỡng; dashboard đẹp không thay quyết định vận hành.

## 17. Testing: chứng minh chính sách được thực thi

### 17.1. Positive tests và negative tests

Một lớp policy gate nên có test cả điều được phép và điều bị cấm:

| Test | Kỳ vọng |
| --- | --- |
| Writer tenant A Encrypt bằng DEK ACTIVE của tenant A | **ALLOW** |
| Reader tenant A Decrypt record hợp lệ của tenant A | **ALLOW** |
| Reader tenant B xin Decrypt record tenant A | **DENY** |
| Key LEGACY_READ_ONLY dùng Encrypt mới | **DENY** |
| Key LEGACY_READ_ONLY dùng Decrypt cũ theo policy | **ALLOW có điều kiện** |
| Ciphertext hoặc AAD bị sửa | **AUTHENTICATION FAILURE** |
| Key ID không nằm trong trusted registry | **DENY** |
| Algorithm do client chọn ngoài allowlist | **DENY** |
| Chữ ký hợp lệ với public key do attacker cung cấp | **DENY trust**, dù phép Verify có thể true |
| KMS grant không phù hợp purpose/tenant | **DENY** |
| TLS certificate sai hostname hoặc chain không tin | **DENY connection** |
| Legacy algorithm hết exception | **DENY new operation** |
| KMS key bị disable/revoked | **DENY use** theo policy |
| Backup thiếu KEK/DEK cần thiết | **RESTORE TEST FAILURE** để sửa trước sự cố |

### 17.2. Kiểm thử cấu hình và CI/CD

Nên có:

- Static checks tìm các API/mode không được phép như **AES/ECB**, insecure TrustManager, hard-coded secrets.
- Unit tests cho policy mapping **role–tenant–resource–key–operation**.
- Integration tests với **KMS IAM/key policy** thực hoặc môi trường thử có tương đương.
- TLS tests cho certificate validation, hostname, protocol/profile policy.
- Test AES-GCM tag/AAD/nonce strategy, kích thước input và error handling.
- Secret scanning đối với repository, build artifacts và cấu hình.
- Migration tests đọc format cũ nhưng chỉ ghi format mới.
- Restore tests khôi phục dữ liệu đã mã hóa và đúng key dependencies.

Không chạy thử bằng production private keys hoặc lưu session secrets để tiện debug. Test data và keys nên được **cô lập khỏi production**.

### 17.3. Runtime drift detection

Sau deploy, cần kiểm tra:

- Có KMS grants mới ngoài approved inventory không?
- Certificate đã đổi nhưng trust store client chưa cập nhật?
- Một workload bị cấp role rộng do refactor infrastructure-as-code?
- Key đã bị deactivated nhưng plaintext DEK còn ở cache?
- Service mới dùng provider/cipher mặc định khác profile đã duyệt?
- Có endpoints bật legacy/0-RTT ngoài exception không?

Thời điểm CI PASS không bảo đảm runtime luôn đúng; policy enforcement cần **theo dõi thay đổi thực tế**.

## 18. Incident response theo cryptographic policy

### 18.1. Các loại sự cố phải phân biệt

| Loại sự cố | Hậu quả điển hình | Hướng phản ứng |
| --- | --- | --- |
| **Raw DEK lộ** | Ciphertext thuộc DEK có nguy cơ bị giải | Thu hồi quyền, tạo DEK mới và re-encrypt khi cần |
| **Raw KEK/root lộ** | Nhiều DEK/derived keys có thể bị ảnh hưởng | Đánh giá blast radius, rotate/rekey/migrate |
| **KMS grant bị lạm dụng** | Có thể Decrypt/Sign qua API dù key non-exportable | Thu hồi principal/grant, kiểm tra thao tác đã xảy ra |
| **Private signing key lộ** | Attacker tạo chữ ký giả/giả mạo danh tính | Revoke/rotate, cập nhật trust/verifiers |
| **Trust anchor/JWKS bị tráo** | Verify chấp nhận khóa giả | Khôi phục trust, điều tra các message đã chấp nhận |
| **AES-GCM nonce reuse** | Có thể mất bí mật và integrity | Ngừng dùng DEK, điều tra dữ liệu, thay khóa |
| **TLS certificate validation bị tắt** | MITM có thể diễn ra | Khôi phục cấu hình, điều tra traffic/credentials |
| **Password verifier bị lộ** | Offline password guessing | Đánh giá KDF/cost, thông báo/reset theo chính sách |
| **Backup mất KEK** | Không thể phục hồi dữ liệu | Kiểm tra recovery path; có thể là mất dữ liệu không đảo ngược |
| **Policy/approval bị sửa** | Attacker cấp quyền hoặc cho thuật toán yếu | Khôi phục baseline, đối soát IAM/KMS/audit |

### 18.2. Runbook phản ứng tối thiểu

1. **Xác định loại key hoặc control** bị ảnh hưởng, không chỉ tên thuật toán.
2. **Cô lập principal/workload** hoặc chặn key operation gây nguy cơ.
3. **Bảo vệ bằng chứng** KMS/HSM, IAM, key inventory, audit logs và change history.
4. **Xác định phạm vi** key IDs/versions, tenants, ciphertext, signatures, backups và dữ liệu đã xử lý.
5. **Đánh giá lộ key material hay lộ key usage**: hai loại cần hành động khác nhau.
6. **Thu hồi quyền hoặc khóa** theo rủi ro, tránh hủy ngay những key còn cần phục hồi dữ liệu chưa bị ảnh hưởng.
7. **Tạo khóa/certificate mới**, cập nhật trust và policy.
8. **Rewrap/re-encrypt/re-sign** theo mô hình và dữ liệu bị ảnh hưởng; không giả định một thao tác giải quyết tất cả.
9. **Kiểm thử hoạt động và backup/restore** sau khắc phục.
10. **Hậu kiểm policy drift**: vì sao kiểm soát không chặn được lỗi, phải sửa tài liệu, CI, IAM, KMS hay runbook nào?

**Thay key ID không khiến attacker quên raw key hoặc plaintext đã sao chép.** Chính sách phải ưu tiên đánh giá phạm vi thực tế, không chỉ “đã rotate xong”.

## 19. Các sai lầm thường gặp khi xây cryptographic policy

| Sai lầm | Hậu quả | Điều chỉnh |
| --- | --- | --- |
| **Policy chỉ liệt kê tên thuật toán** | Không kiểm soát purpose, mode, nonce, trust, lifecycle | Có profile theo use case và key type |
| **Không phân loại dữ liệu** | Một baseline cứng cho cả ephemeral key và backup lâu dài | Gắn yêu cầu với data class/retention |
| **Tin KMS non-exportable giải quyết mọi thứ** | Workload có thể lạm dụng Decrypt/Sign API | IAM least privilege + audit + business authorization |
| **Chỉ có key owner, không có custodian** | Thiếu người vận hành rotation/recovery | Inventory owner/custodian và succession |
| **Cho client chọn thuật toán/key ID tùy ý** | Downgrade, key confusion, cross-tenant access | Trusted profile và mapping theo identity |
| **Dùng AES-256-GCM nhưng tái dùng nonce** | Mất bí mật/toàn vẹn | Nonce management và usage limit |
| **Bỏ tag/AAD khi lỗi** | Chấp nhận dữ liệu bị sửa | Fail closed |
| **Dùng raw password hoặc SHA-256(password)** | Offline guessing hiệu quả | Password-based KDF hoặc random DEK/KMS |
| **Verify chữ ký với khóa do request gửi** | Attacker tự ký và tự cung cấp khóa | PKI/trusted registry/JWKS policy |
| **Tắt TLS hostname validation** | MITM | Không bypass; sửa chain/trust đúng |
| **Không chống replay** | Xử lý lại event/transaction hợp lệ | State, event ID, sequence và expiry |
| **Không lưu key version/metadatas** | Migration/restore thất bại | Versioned envelope và registry |
| **Giữ KEK cũ vô hạn** | Tăng thời gian rủi ro | Cryptoperiod và destroy sau dependency check |
| **Hủy KEK quá sớm** | Mất khả năng mở ciphertext/backup | Restore test + inventory phụ thuộc |
| **Exception không có expiry** | Legacy thuật toán tồn tại vĩnh viễn | Risk owner, deadline, metrics |
| **Policy-as-code do client cung cấp** | Attacker hạ cấp policy | Chỉ cấu hình đã ký/phê duyệt từ nguồn tin cậy |
| **Chỉ check ở Java, KMS grants quá rộng** | Bypass application check bằng gọi API trực tiếp | Enforcement ở KMS/IAM và app |
| **Audit log chứa raw secrets** | Rò mật mã qua observability | Log metadata tối thiểu, redaction |
| **Rotation xem như đã xóa dữ liệu cũ bị lộ** | Sai đánh giá sự cố | Phân biệt rewrap, re-encrypt và exfiltration |
| **Không review khi chuẩn/threat model đổi** | Tích lũy thuật toán/nhánh lỗi thời | Crypto-agility, periodic review |

## 20. Checklist xây dựng chính sách mật mã

### Governance và scope

1. **Chủ sở hữu:** tài liệu có policy owner và thẩm quyền phê duyệt rõ?
2. **Phạm vi:** bao gồm application, environment, data classification, tenant và partners cần thiết?
3. **Thời hạn:** có reviewDue/version, changelog và cơ chế emergency change?
4. **Trách nhiệm:** owner, custodian, key user, admin, auditor có phân định?
5. **Ngoại lệ:** có risk acceptance, scope, expiry, compensating controls và migration plan?

### Thuật toán và triển khai

6. **Allowlist:** thuật toán, mode, params, key size, provider và use case có được mô tả đầy đủ?
7. **AEAD:** dữ liệu nhạy cảm có dùng authenticated encryption và fail-closed?
8. **Nonce/AAD:** chiến lược duy nhất theo key, byte encoding/context từ nguồn tin cậy đã định nghĩa?
9. **Hash/MAC:** có phân biệt SHA-256 thường với HMAC/Signature?
10. **Chữ ký:** signing key đúng purpose, verification key lấy từ nguồn tin cậy?
11. **KDF:** dùng HKDF cho IKM mạnh, password-based KDF cho password?
12. **Key agreement:** có authenticated handshake, key schedule và peer identity validation?
13. **TLS:** certificate/hostname/mTLS/PSK/0-RTT/resumption có chính sách?
14. **Provider/JDK:** library và security provider có được cập nhật/kiểm thử, không tự viết cryptographic primitive?

### Key lifecycle và phân quyền

15. **Generation:** khóa sinh bằng CSPRNG/KMS/HSM đúng thuật toán?
16. **Inventory:** có key ID/version, owner, custodian, purpose, state, dependency?
17. **Usage:** Encrypt/Decrypt, Sign/Verify, Wrap/Unwrap, Derive có giới hạn theo principal?
18. **IAM:** KMS grants và business authorization đều được kiểm tra?
19. **Non-exportable:** khóa cấp cao có giữ ở ranh giới phù hợp; plaintext DEK được xử lý an toàn?
20. **Cryptoperiod:** có thời hạn tạo dữ liệu mới và chính sách đọc dữ liệu cũ?
21. **Rotation:** phân biệt KEK rewrap và DEK re-encrypt?
22. **Backup/recovery:** đã thử restore gồm key dependencies và context?
23. **Revocation/destruction:** có approval, thu hồi quyền nhanh, dependency check trước hủy?
24. **Secret hygiene:** không raw key/private key/password trong log/CI/repository?

### Vận hành và chứng minh tuân thủ

25. **Enforcement:** có policy gates thực tại Java, IAM/KMS, TLS và CI/CD?
26. **Fail closed:** cấu hình/key/certificate/tag/algorithm sai đều bị từ chối đúng?
27. **Negative testing:** test sai tenant, key state, thuật toán, tag, cert và replay?
28. **Audit:** thao tác key và policy change có evidence, log được bảo vệ?
29. **Monitoring:** có phát hiện drift, exception quá hạn, grants quá rộng, key quá cryptoperiod?
30. **Incident response:** có playbook riêng cho raw key compromise, key usage compromise, trust compromise?
31. **Crypto-agility:** có roadmap migration/protocol version và đánh giá yêu cầu dài hạn?
32. **Khôi phục vận hành:** khi security incident hoặc KMS outage, có cơ chế fail-safe phù hợp thay vì bypass crypto?

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Cryptographic policy và algorithm allowlist có phải một không?

**Đáp án:** Không. Allowlist là một phần của policy. Chính sách còn phải quy định **mục đích khóa, phân quyền, vòng đời, bảo vệ vật liệu khóa, cryptoperiod, audit, recovery, ngoại lệ và quản trị thay đổi**.

**Câu 2.** Một dịch vụ dùng AES-256-GCM, nhưng cùng DEK và nonce xuất hiện ở hai bản ghi. Có đáp ứng chính sách mã hóa an toàn không?

**Đáp án:** Không. Việc tái sử dụng nonce dưới cùng GCM key có thể làm mất tính bí mật và toàn vẹn. Key size 256 bit không khắc phục lỗi nonce.

**Câu 3.** Nếu KMS giữ KEK non-exportable, có thể cấp quyền Decrypt mọi tenant cho một workload bị phân quyền kém không?

**Đáp án:** Không. Attacker chiếm workload có thể lạm dụng KMS API để unwrap/giải plaintext dù KEK không xuất được. Cần **IAM least privilege** và kiểm tra quyền tenant/resource.

**Câu 4.** Vì sao chỉ lưu ciphertext và wrapped DEK là chưa đủ để giải mã về sau?

**Đáp án:** Có thể cần **key ID/version, KMS context, nonce, tag, AAD/format và quyền truy cập KEK**. Thiếu key dependencies có thể khiến restore thất bại dù ciphertext nguyên vẹn.

**Câu 5.** Có nên cho token JWT tự chỉ định một URL JWKS bất kỳ rồi dùng khóa trả về để Verify không?

**Đáp án:** Không. Endpoint và issuer phải được **cấu hình tin cậy**; key ID chỉ chọn trong tập khóa cho phép. Nếu không, attacker có thể tự tạo token, chữ ký và public key.

**Câu 6.** TLS 1.3 có tự cho phép một service đọc mọi hóa đơn của mọi tenant không?

**Đáp án:** Không. TLS bảo vệ kênh và xác thực peer theo cấu hình. Quyền đọc bản ghi vẫn cần **business authorization** theo principal và tenant.

**Câu 7.** Vì sao một key có thể không còn được Encrypt mới nhưng vẫn được Decrypt bản ghi cũ?

**Đáp án:** Chính sách có thể tách **cryptoperiod bảo vệ dữ liệu mới** khỏi giai đoạn cần xử lý dữ liệu cũ. Một key sau rotation có thể được giữ theo state **legacy read-only** nếu platform/policy cho phép.

**Câu 8.** Rotation KEK có bắt buộc thay DEK và ciphertext không?

**Đáp án:** Không. Có thể **rewrap cùng DEK** dưới KEK mới, giữ ciphertext cũ. Nhưng nếu DEK hoặc raw KEK/bản wrapped DEK đã bị lộ, phải đánh giá thay DEK/re-encrypt riêng.

**Câu 9.** Tại sao một file YAML cryptographic policy chưa tự bảo đảm hệ thống tuân thủ?

**Đáp án:** Nó chỉ biểu diễn yêu cầu/cấu hình. Cần **enforcement** tại Java, KMS/HSM IAM, TLS/provider, CI/CD và kiểm toán thực tế. Nếu grants cho phép bypass Java gate thì policy chưa được bảo vệ đầy đủ.

**Câu 10.** Một ngoại lệ cho thuật toán legacy có thể giữ mãi vì khách hàng chưa nâng cấp không?

**Đáp án:** Không nên. Phải có **risk owner, phạm vi, compensating controls, expiry, migration deadline và review**. Nếu rủi ro không thể chấp nhận, phải từ chối thao tác thay vì kéo dài ngoại lệ vô thời hạn.

**Câu 11.** Vì sao Argon2id/PBKDF2 khác HKDF trong policy?

**Đáp án:** Password-based KDF tăng chi phí thử đoán mật khẩu; HKDF dùng cho **vật liệu khóa mạnh** và domain separation. HKDF nhanh không thay thế việc chống offline guessing của password yếu.

**Câu 12.** Nếu private signing key đã được bảo vệ trong HSM, việc app được phép Sign mọi payload có an toàn không?

**Đáp án:** Không. Một workload có quyền Sign có thể bị lạm dụng để tạo chữ ký giả trên nội dung trái phép. Phải giới hạn **purpose, principal, payload schema, approval và audit**.

**Câu 13.** Đã có AEAD tag hợp lệ cho giao dịch, vì sao vẫn cần idempotency?

**Đáp án:** Một ciphertext/message có tag hợp lệ vẫn có thể bị phát lại. AEAD bảo vệ integrity/authenticity theo khóa; nghiệp vụ cần **freshness và state** để tránh xử lý trùng.

**Câu 14.** Tại sao cryptographic policy cần key owner và key custodian?

**Đáp án:** Owner quyết định **mục đích và rủi ro**, custodian chịu trách nhiệm **giám hộ và thực thi vòng đời khóa**. Không có trách nhiệm rõ ràng sẽ thiếu người cập nhật grants, rotation, backup và thu hồi khi thay nhân sự.

**Câu 15.** Nếu root key đã bị lộ, chỉ thay nhãn HKDF có tạo lại tính bí mật cho dữ liệu cũ không?

**Đáp án:** Không. Attacker có root và context công khai có thể dẫn xuất khóa con cũ. Cần đánh giá phạm vi root, khóa con/dữ liệu liên quan và kế hoạch rekey/re-encrypt phù hợp.

**Câu 16.** Có thể tắt certificate validation nếu service đích đang bị lỗi certificate và API cần hoạt động ngay không?

**Đáp án:** Không nên. Làm vậy loại bỏ xác thực peer và có thể cho phép MITM. Cần sửa chain/trust/certificate theo quy trình, hoặc áp dụng phương án contingency đã được phân tích rủi ro mà không tự bỏ cơ chế bảo vệ cốt lõi.

**Câu 17.** Key usage compromise khác raw key compromise như thế nào?

**Đáp án:** Với key usage compromise, attacker có **quyền gọi Sign/Decrypt/Unwrap** qua API mà không cần thấy raw key. Với raw key compromise, attacker có byte bí mật và có thể thao tác ngoài hệ thống kiểm soát. Hai trường hợp đều cần ứng phó, nhưng **phạm vi và biện pháp** có thể khác.

**Câu 18.** Vì sao chính sách phải có crypto-agility nhưng không nhận thuật toán do client tự chọn?

**Đáp án:** Crypto-agility là khả năng thay profile/version **có phê duyệt và migration**, không phải cho attacker điều khiển thuật toán. Hệ thống phải chọn thuật toán từ **allowlist/trusted configuration** và chống downgrade.

## Kết luận

**Cryptographic policy** biến các nguyên tắc mật mã thành những yêu cầu **có chủ sở hữu, phạm vi, kiểm soát và bằng chứng thực thi**. Một chính sách hiệu quả xác định **thuật toán được phép, mục đích và quyền dùng khóa, nguồn sinh khóa, cách lưu trữ, cryptoperiod, rotation, thu hồi, hủy, recovery và audit**; đồng thời tách rõ trách nhiệm **key owner, custodian, administrator, workload và auditor**.

Trong hệ thống Java, cần thực hiện chính sách xuyên suốt **JCA/JCE, TLS/JSSE, KMS/HSM, IAM, DEK/KEK và envelope encryption**, không chỉ ở một file cấu hình. **AEAD nonce/AAD/tag, trust của chữ ký số, password KDF, authenticated key establishment, key usage limits, fail-closed và business authorization** phải được kiểm thử theo use case thật.

**Một thuật toán mạnh được sử dụng ngoài chính sách vẫn có thể bảo vệ sai đối tượng hoặc sai cách. Chính sách mật mã chỉ thực sự có giá trị khi mỗi quyết định về khóa và thuật toán đều có nơi thực thi, người chịu trách nhiệm và bằng chứng để kiểm chứng.**

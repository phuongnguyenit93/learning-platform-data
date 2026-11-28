# Encryption Assurance: Đánh giá có bằng chứng về hiệu lực mã hóa và quản lý khóa

## 1. Vì sao “đã bật mã hóa” chưa đủ để kết luận an toàn?

Một công ty cung cấp ứng dụng hóa đơn SaaS lưu dữ liệu khách hàng trong database, file PDF trên object storage và các bản backup. Bảng điều khiển cloud hiển thị **Encryption: Enabled**. Đội sản phẩm vì thế tuyên bố: “Toàn bộ dữ liệu khách hàng đã được bảo vệ bằng mã hóa”.

Tuy nhiên, một số câu hỏi vẫn chưa được trả lời:

- Database có mã hóa ổ đĩa, nhưng **worker export** có trả file cho sai tenant không?
- API dùng HTTPS với client, nhưng **CDN hoặc load balancer** có giải mã TLS trước khi chuyển dữ liệu qua một đoạn kết nối khác không?
- Khóa mã hóa nằm trong KMS, nhưng tài khoản dịch vụ nào có quyền **Decrypt** và có bị cấp quá rộng không?
- File backup mã hóa thành công nhưng khi cần restore, khóa đã bị vô hiệu hóa; hệ thống có còn phục hồi được không?
- Một trường dữ liệu được mã hóa nhưng **IV/nonce bị tái sử dụng**, dẫn tới nguy cơ mất tính bí mật hoặc toàn vẹn tùy thuật toán?
- Log của ứng dụng có ghi nội dung plaintext sau khi giải mã không?

Đây là vấn đề của **encryption assurance (bảo đảm mã hóa)**: đánh giá có phương pháp và bằng chứng rằng **cơ chế mật mã, quản lý khóa, ranh giới bảo vệ và hoạt động vận hành thực tế** đáp ứng các mục tiêu bảo mật đã xác định trong phạm vi và thời kỳ đánh giá.

Trong chương **Mã hóa và khóa** thuộc module **SECURITY_SECURITY_ASSURANCE**, mục tiêu không dừng ở lý thuyết thuật toán. Người học cần chuyển **risk scenario → security requirement → cryptographic control → verification → evidence → finding/remediation → residual risk** để xây dựng chương trình assurance liên tục trong phát triển và vận hành.

> **Encryption enabled** là một trạng thái cấu hình. **Encryption effective for a stated threat and data flow** là một kết luận cần chứng minh. Mã hóa có thể hoạt động đúng nhưng không chặn được một ứng dụng có quyền giải mã rồi trả dữ liệu cho sai người.

## 2. Encryption assurance kiểm chứng những tuyên bố nào?

Một tuyên bố bảo mật muốn kiểm tra được phải nêu **dữ liệu, kẻ tấn công hoặc tình huống sai, ranh giới, trạng thái mong muốn và giới hạn**.

**Tuyên bố yếu:**

> “Hệ thống dùng AES-256 và TLS nên dữ liệu an toàn.”

**Tuyên bố kiểm chứng được:**

> “Trong các môi trường production thuộc phạm vi, mọi object chứa hóa đơn Confidential được mã hóa at rest bằng cấu hình storage được phê duyệt; các identities không có nhiệm vụ không được phép đọc object hoặc dùng khóa giải mã; các kết nối từ client đến endpoint đã đăng ký có xác minh TLS; quyền và hiệu lực của các controls đã được kiểm tra trên tài sản và phiên bản được liệt kê.”

Một chương trình nên phân tách các nhóm claim:

| Nhóm claim | Câu hỏi kiểm chứng | Ví dụ |
| --- | --- | --- |
| **Confidentiality** | Dữ liệu có bị lộ trước một attacker được mô tả không? | Người có bản sao volume nhưng không có khóa không đọc được nội dung qua cơ chế dự kiến. |
| **Integrity/authenticity của dữ liệu mã hóa** | Có phát hiện dữ liệu mã hóa hoặc metadata bị sửa trái phép không? | Thay ciphertext hoặc tag khiến AEAD decryption thất bại, không trả plaintext. |
| **Cryptographic design** | Thuật toán, mode, tham số và protocol có phù hợp use case? | AEAD với nonce management, TLS hiện hành theo baseline. |
| **Key security** | Khóa được tạo, cấp quyền, dùng, xoay, thu hồi và hủy an toàn? | Chỉ workload đủ quyền được gọi KMS Decrypt trong scope. |
| **End-to-end flow** | Dữ liệu có đi qua đoạn/bản sao không được bảo vệ? | Client → gateway → service → queue → backup có inventory và controls riêng. |
| **Availability/recovery** | Khi khóa bị lỗi, bị mất hoặc cần rotate, dữ liệu còn khôi phục theo mục tiêu? | Restore drill thành công trong RTO/RPO cùng quyền KMS phù hợp. |
| **Operational assurance** | Controls có hoạt động ở production, trong thời kỳ cần đánh giá? | Config readback, audit KMS, negative tests, deployment và rotation records. |

### Claim phải có phạm vi

Một báo cáo “tất cả bucket đều mã hóa” có thể chỉ kiểm tra bucket **trong inventory của một cloud account**. Nó không chứng minh file gửi qua email vendor, local developer copy hoặc object ở account khác cũng được bảo vệ. **Không mở rộng kết luận vượt phạm vi evidence**.

## 3. Mật mã cung cấp thuộc tính gì và không cung cấp thuộc tính gì?

### Encryption, hashing, MAC và digital signature

| Cơ chế | Mục tiêu chính | Điểm cần nhớ khi assurance |
| --- | --- | --- |
| **Encryption (mã hóa)** | Bảo vệ bí mật nội dung với các giả định về khóa, thuật toán và hệ thống. | Không tự xác minh người gọi ứng dụng được quyền lấy plaintext. |
| **Authenticated encryption / AEAD** | Bảo vệ bí mật và phát hiện sửa đổi ciphertext hoặc associated data được xác thực. | Phải quản lý nonce, tag và AAD đúng; không bỏ qua lỗi xác thực. |
| **Cryptographic hash** | Tạo digest cho nội dung, hỗ trợ kiểm tra thay đổi trong thiết kế phù hợp. | Hash **không phải mã hóa**, không có cơ chế giải mã; hash đơn thuần không chứng minh nguồn gốc đáng tin. |
| **HMAC/MAC** | Xác thực thông điệp và toàn vẹn bằng khóa bí mật chia sẻ. | Bên giữ khóa đều có khả năng tạo MAC; cần quản lý khóa và miền sử dụng. |
| **Digital signature** | Xác minh chữ ký bằng public key, hỗ trợ kiểm tra nguồn ký và toàn vẹn trong mô hình tin cậy. | Cần xác thực public key/certificate và quy trình quản lý khóa; chữ ký không giữ bí mật nội dung. |
| **KDF/password hashing chuyên dụng** | Dẫn xuất khóa hoặc lưu password verifier theo thiết kế. | Không lưu mật khẩu bằng hàm hash nhanh đơn giản; dùng cơ chế chuyên dụng và tham số đã duyệt. |

### Confidentiality khác access control

Một database mã hóa toàn bộ ổ đĩa. Khi ứng dụng đang chạy, nó có thể đọc dữ liệu vì tầng storage giải mã cho workload hợp lệ. Nếu API thiếu object-level authorization, user tenant A có thể nhận dữ liệu tenant B. **Disk encryption vẫn có thể hoạt động đúng trong threat model mất ổ đĩa**, nhưng không ngăn lỗi logic ở ứng dụng.

### Encryption không tự giải quyết Availability

Mất khóa hoặc mất khả năng gọi KMS có thể khiến dữ liệu không thể giải mã, gây gián đoạn. Mã hóa không thay thế backup, DR, phân quyền, kiểm tra dữ liệu, chống xóa và khả năng phục hồi.

**Điều cần xác định trước:** cụ thể muốn chống ai — người lấy bản backup, nhân viên có quyền đọc storage, attacker ở mạng trung gian, operator ở đích, malware trong process hay người dùng đăng nhập hợp lệ nhưng đọc sai tenant?

## 4. Ba trạng thái dữ liệu và ranh giới bảo vệ

| Trạng thái | Dữ liệu đang ở đâu | Control thường dùng | Điều chưa được bảo đảm |
| --- | --- | --- | --- |
| **At rest** | Database files, object storage, snapshot, disks, backup, archive. | Storage/database encryption, envelope encryption, KMS/HSM, key access policies. | Không chặn người đã được ứng dụng giải mã hoặc IAM cho phép đọc. |
| **In transit** | Giữa client, gateway, services, broker, database và vendor. | TLS, mTLS khi phù hợp, certificate validation, endpoint authentication. | Không bảo vệ plaintext sau khi được giải mã tại endpoint/terminator. |
| **In use** | Process memory, CPU, cache, ETL worker, analytics job và các logic nghiệp vụ. | Authorization, process isolation, secure coding, giới hạn quyền; công nghệ chuyên biệt khi có yêu cầu. | Mã hóa at rest và TLS không làm dữ liệu luôn ở dạng mã hóa khi ứng dụng cần xử lý. |

### Mô tả theo ranh giới, không chỉ tên sản phẩm

Một request từ người dùng tới Invoice SaaS có thể đi qua:

**Browser → CDN/TLS terminator → API gateway → application → DB → broker → worker → object storage → download client.**

Mỗi chặng có thể có **giao thức, danh tính, mức quyền và điều kiện tin cậy khác nhau**. Chứng chỉ hợp lệ tại CDN không chứng minh đoạn CDN→backend dùng TLS; database at-rest encryption không chứng minh export file được bảo vệ; broker encryption không chứng minh message không chứa secret bị lộ cho consumer.

### Chọn độ chi tiết theo rủi ro

Không cần yêu cầu một sơ đồ hệ thống chứa mọi byte, nhưng phải có **data flow register** cho những tài sản nhạy cảm và các bản sao trọng yếu, để đối chiếu từng ranh giới với mục tiêu và bằng chứng.

## 5. Mô hình hóa đe dọa trước khi chọn biện pháp mã hóa

| Threat scenario | Attacker/điều kiện | Encryption giúp gì? | Control khác vẫn cần |
| --- | --- | --- | --- |
| Mất ổ đĩa/snapshot | Attacker có bản sao phương tiện, không có khóa thích hợp. | At-rest encryption có thể giảm khả năng đọc dữ liệu. | Quản lý khóa tách biệt, kiểm soát snapshot, logging. |
| Nghe lén đường truyền | Attacker quan sát/sửa gói tin giữa hai bên. | TLS được xác minh đúng có thể bảo vệ nội dung và kênh. | Xác minh endpoint, tránh downgrade/cleartext fallback. |
| User A đọc invoice B | Người dùng hợp lệ khai thác authorization thiếu. | Mã hóa DB không tự chặn API trả plaintext sai tenant. | Object-level authz, tenant scoping, tests. |
| KMS principal quá rộng | Workload bị chiếm có quyền Decrypt nhiều tài sản. | Key trong KMS vẫn có thể bị lạm dụng qua API. | Least privilege, encryption context, monitoring, isolation. |
| Sửa ciphertext trong storage | Attacker sửa nội dung trước giải mã. | AEAD có thể phát hiện tampering trong điều kiện triển khai đúng. | Xử lý fail closed, rollback/version checks nếu cần. |
| Nonce bị tái sử dụng | Cùng khóa và nonce dùng cho nhiều thông điệp ở mode không cho phép. | Encryption bị suy yếu nghiêm trọng. | Nonce uniqueness, limits, tests, rekey strategy. |
| Backup bị mất khóa | Cấu hình KMS/khóa không còn truy cập được khi restore. | Encryption có thể làm dữ liệu không khôi phục được. | Key backup/recovery policy, DR test, access continuity. |
| Debug log chứa plaintext | Ứng dụng ghi dữ liệu sau giải mã. | Encryption ở storage không giúp với log plaintext. | Data minimization, redaction, log IAM, retention. |
| Nhà cung cấp nhận plaintext | Vendor được phép nhận một dataset nhưng dùng sai mục đích. | TLS chỉ bảo vệ trên đường, không kiểm soát bên nhận. | Contract, purpose/recipient review, vendor assurance. |

### Threat model là cơ sở chọn độ mạnh và phạm vi

Mã hóa có chi phí CPU, vận hành, key management, logging và recovery. Không thể suy ra **“mã hóa mọi field”** luôn là phương án tốt nhất. Tổ chức cần chọn controls bảo vệ **đúng tài sản, trạng thái, ranh giới và attacker**, đồng thời quản lý phần rủi ro không thể giải quyết chỉ bằng cryptography.

## 6. Từ security objective thành yêu cầu mã hóa có thể kiểm tra

Một encryption standard hiệu quả nên mô tả cả **khi nào mã hóa, dùng gì, ai được giải mã và kiểm chứng ra sao**.

| Requirement ID | Yêu cầu minh họa | Kết quả phải quan sát được |
| --- | --- | --- |
| **ENC-REST-01** | Dữ liệu Confidential trong object storage thuộc scope phải có at-rest encryption theo baseline đã duyệt. | Config/effective policy và thử nghiệm cho các bucket/objects trong inventory. |
| **ENC-TRAN-02** | Kết nối nhạy cảm giữa các endpoint thuộc scope phải dùng phiên TLS với chính sách xác minh peer phù hợp. | Handshake tests, TLS config, logs và negative cases. |
| **ENC-ALG-03** | Ứng dụng mã hóa nội dung bằng thuật toán/mode/parameters được duyệt, có kiểm soát toàn vẹn khi cần. | Code/config review và tamper tests. |
| **ENC-NONCE-04** | Với AEAD cần nonce duy nhất theo điều kiện của mode cho mỗi lần mã hóa dưới cùng key. | Design, test trùng, giới hạn lưu lượng/rotation và telemetry. |
| **ENC-KEY-05** | Khóa được tạo, lưu, sử dụng, xoay và hủy theo lifecycle có owner. | Key registry, KMS policy, usage audit và runbook. |
| **ENC-IAM-06** | Quyền sử dụng Decrypt/Unwrap chỉ cấp cho identities và ngữ cảnh được duyệt. | Effective policy và negative permission tests. |
| **ENC-ROT-07** | Có phương án rotation/compromise response không làm mất truy cập dữ liệu hợp lệ. | Rewrap/re-encrypt design, test phiên bản khóa, restore drill. |
| **ENC-BKP-08** | Backup mã hóa vẫn restore được theo recovery objectives đã phê duyệt. | Restore test, KMS permissions và đối soát dữ liệu. |
| **ENC-LOG-09** | Plaintext, khóa và token bí mật không bị ghi không cần thiết ở logs/traces. | Canary tests, redaction review, quyền/retention log. |
| **ENC-OBS-10** | Lỗi key, cert, decrypt và bất thường về quyền được giám sát. | Test alert và audit events nối với incident/finding. |

Các mã ENC-* chỉ là ví dụ nội bộ. **Không tự biến một bảng minh họa thành chuẩn pháp lý**; các phiên bản thuật toán, độ dài khóa, TLS và yêu cầu FIPS/tiêu chuẩn cụ thể phải được xác định theo baseline và nghĩa vụ thật sự áp dụng.

## 7. Chọn thuật toán và mode: bảo mật nằm trong cách sử dụng

### Symmetric vs asymmetric cryptography

**Symmetric encryption** dùng khóa bí mật cho mã hóa và giải mã, phù hợp dữ liệu lớn. Ví dụ AES là block cipher thường được triển khai trong mode có tính chất cụ thể.

**Asymmetric cryptography** dùng cặp public/private key, thường hỗ trợ trao đổi/đóng gói khóa hoặc các mục đích khác. Không nên tự mã hóa lượng dữ liệu lớn bằng một phép RSA đơn giản, hoặc tự viết protocol kết hợp RSA/AES. Hãy dùng thư viện/protocol và dịch vụ quản lý khóa đã được kiểm chứng.

### AEAD vì sao quan trọng?

Với **Authenticated Encryption with Associated Data (AEAD)**, một phép mã hóa có thể cung cấp bí mật và kiểm tra tính toàn vẹn của ciphertext cùng associated data được xác thực. Các mode như **AES-GCM** được dùng rộng rãi khi cấu hình đúng.

Ví dụ record ciphertext có các thành phần:

| Thành phần | Tác dụng | Cách quản lý |
| --- | --- | --- |
| **Algorithm/version** | Cho biết cách giải mã đã được chuẩn hóa. | Versioning và allowlist, không nhận arbitrary algorithm từ input không tin cậy. |
| **Key reference / key ID** | Xác định key/version thích hợp. | Registry tin cậy, KMS policy; tránh tùy ý đổi key source. |
| **Nonce/IV** | Tham số đầu vào cho mode; có yêu cầu đặc biệt về uniqueness. | Tạo và lưu đúng cách, không tái sử dụng sai mode. |
| **Ciphertext** | Nội dung đã biến đổi bằng thuật toán. | Có thể lưu cùng metadata nhưng phải giới hạn truy cập. |
| **Authentication tag** | Hỗ trợ kiểm tra ciphertext/AAD không bị sửa. | Xác minh trong decryption, không bỏ qua lỗi tag. |
| **AAD** | Metadata có liên quan cần xác thực nhưng không nhất thiết giấu. | Ràng buộc record/tenant/version qua biểu diễn chuẩn và nguồn tin cậy. |

### Không dùng encryption không có integrity sai mục tiêu

Một số mode chỉ mã hóa bí mật mà không phát hiện sửa đổi theo nghĩa cần thiết. Nếu ứng dụng cần chống sửa ciphertext hoặc metadata, chọn **authenticated encryption hoặc thiết kế encrypt-then-MAC đã được kiểm chứng** theo yêu cầu và thư viện tin cậy. Đừng ghép các primitive tự phát hoặc mặc định CBC với padding đã đủ cho mọi yêu cầu.

## 8. Nonce/IV, AAD và chống thay thế ciphertext

### Nonce uniqueness không phải chi tiết tùy ý

Với AES-GCM, **tái sử dụng cùng nonce với cùng key** cho các nội dung khác nhau có thể làm suy yếu nghiêm trọng confidentiality và authenticity. Một thiết kế an toàn cần bảo đảm uniqueness theo giới hạn của mode, ví dụ sử dụng bộ tạo nonce có quản trị hoặc giá trị ngẫu nhiên phù hợp với **ngân sách số lần mã hóa và xác suất va chạm**.

Đối với GCM, nonce 96 bit là lựa chọn chuẩn phổ biến; dùng nonce ngẫu nhiên 96 bit không có nghĩa **có thể mã hóa vô hạn** dưới cùng một key. Tổ chức cần xác định giới hạn traffic/cryptoperiod và rekey strategy theo hướng dẫn thuật toán và hệ thống triển khai.

### AAD giúp ràng buộc ngữ cảnh, nhưng không phải authorization

Một record hóa đơn mã hóa với AAD:

~~~text
tenant_id = "tenant-a"
record_type = "invoice"
record_id = "invoice-008"
schema_version = "v2"
~~~

Khi giải mã, ứng dụng tạo AAD từ **ngữ cảnh đã được xác minh** và metadata có định nghĩa chuẩn. Nếu attacker chuyển ciphertext sang record khác nhưng không có AAD tương ứng, phép xác thực tag có thể thất bại.

Tuy nhiên, **AAD không tự quyết định tenant A có được đọc invoice đó hay không**. Nếu API giải mã với đúng AAD rồi trả cho user B vì thiếu authorization, cryptography vẫn làm đúng nhiệm vụ nhưng hệ thống vẫn lộ dữ liệu.

### Cần xử lý lỗi fail closed

Nếu tag sai, key sai, nonce sai hoặc AAD khác, decryption phải **không trả plaintext**, không thực hiện fallback sang mode yếu, không bỏ qua integrity check và không ghi khóa/secret vào log. Error response nên an toàn, đồng thời có tín hiệu cho đội vận hành điều tra đúng phạm vi.

## 9. Key management là một control độc lập với thuật toán

**Khóa là một tài sản bảo mật**; tính an toàn của AES hay TLS phụ thuộc lớn vào ai có khả năng lấy hoặc sử dụng khóa, trong thời gian nào và theo ngữ cảnh nào.

### Vòng đời khóa

~~~mermaid
flowchart TD
    A["Risk, algorithm và key-use requirements"] --> B["Generate từ nguồn ngẫu nhiên phù hợp"]
    B --> C["Register: owner, purpose, key scope và version"]
    C --> D["Protect: KMS/HSM, access policies, backup"]
    D --> E["Use: Encrypt/Decrypt/Wrap/Unwrap đúng quyền"]
    E --> F["Monitor: usage, anomalies, failures"]
    F --> G{"Rotate / revoke / retire?"}
    G -- "Rotate" --> H["Tạo key version mới, rewrap/re-encrypt theo plan"]
    H --> E
    G -- "Revoke" --> I["Hạn chế quyền + incident / recovery decision"]
    G -- "Retire" --> J["Giữ decrypt cũ có kiểm soát hoặc hủy theo retention"]
    I --> J
    J --> K["Destroy khi được phép, ghi evidence + impact"]
~~~

### Các thuộc tính nên có trong key inventory

| Thuộc tính | Mục đích |
| --- | --- |
| **key_id / version** | Định danh ổn định và lịch sử phiên bản. |
| **owner / custodian** | Ai chịu trách nhiệm nghiệp vụ và vận hành. |
| **algorithm / parameters** | Kiểu và mục đích sử dụng khóa; không chỉ độ dài. |
| **data scope / classification** | Loại dữ liệu hoặc tenant/service mà key bảo vệ. |
| **state / cryptoperiod** | Active, retiring, disabled, scheduled destruction; giới hạn sử dụng. |
| **generate/import origin** | Khóa được tạo/quản lý ở đâu và qua quy trình nào. |
| **allowed operations** | Encrypt, Decrypt, GenerateDataKey, WrapKey hoặc Verify theo nhu cầu. |
| **principals / trust conditions** | Danh tính được dùng khóa, theo resource, environment, context và chính sách. |
| **backup/recovery dependencies** | Dữ liệu cũ cần key nào để restore hoặc decrypt. |
| **rotation/incident runbook** | Quy trình thay đổi, ứng cứu và rollback có kiểm soát. |
| **audit/evidence reference** | Chính sách, test, key events và kết quả review. |

### Không lưu raw key trong repository

Hardcode khóa vào source code, image, file cấu hình chung hoặc CI output tạo khả năng rò rỉ và khiến việc thu hồi rất khó. Tùy thiết kế, ứng dụng nên dùng **KMS/HSM/secret management và workload identity**. Sử dụng dịch vụ managed **không tự bảo đảm quyền được giới hạn đúng**; phải review IAM và cách ứng dụng gọi API.

## 10. KMS, HSM và envelope encryption

### Khái niệm chính

**Key Management Service (KMS)** hỗ trợ quản lý khóa, chính sách quyền, cryptographic operations và audit tùy nhà cung cấp. **Hardware Security Module (HSM)** là một loại thiết bị/mô-đun cung cấp một số biện pháp bảo vệ khóa và hoạt động mật mã; mức bảo vệ phụ thuộc cấu hình, tiêu chuẩn và phạm vi hệ thống.

**Envelope encryption** thường phân biệt:

- **Data Encryption Key (DEK):** khóa được dùng để mã hóa nội dung dữ liệu.
- **Key Encryption Key (KEK):** khóa dùng để wrap/protect DEK; có thể được quản lý qua KMS/HSM.
- **Encrypted DEK (wrapped DEK):** bản DEK đã được bảo vệ, có thể lưu cùng encrypted data theo thiết kế.

Một cấu trúc điển hình:

~~~mermaid
sequenceDiagram
    participant App as Invoice Service
    participant KMS as Trusted KMS
    participant Store as Object Storage
    App->>KMS: Request data key / wrapping operation theo policy
    KMS-->>App: Plaintext DEK theo kênh bảo vệ + wrapped DEK
    App->>App: AES-GCM encrypt với fresh nonce + AAD
    App->>Store: Ciphertext + nonce + tag + wrapped DEK + key ref
    Note over App: Plaintext DEK trong memory cần hạn chế tuổi thọ/phạm vi
    App->>Store: Read encrypted object và metadata
    Store-->>App: Ciphertext + wrapped DEK + metadata
    App->>KMS: Unwrap/Decrypt DEK với principal và context hợp lệ
    KMS-->>App: DEK nếu policy cho phép
    App->>App: Verify tag/AAD, chỉ trả plaintext sau authz
~~~

Đây là sơ đồ **khái niệm**, không phải API bắt buộc của một cloud. Một số nền tảng thực hiện envelope encryption **trong tầng storage** và ứng dụng không trực tiếp nhìn thấy DEK. Mô hình này khác với **application-layer encryption**, nên threat model và evidence phải theo triển khai thực tế.

### Vì sao không dùng một khóa lâu dài cho mọi record?

Một key dùng vô thời hạn cho tất cả dữ liệu tạo **blast radius** lớn nếu bị lộ và làm rotation khó. Envelope encryption hỗ trợ giảm phạm vi của DEK và phân tách quyền, nhưng thiết kế cụ thể vẫn cần xét số lần mã hóa, nonce management, tốc độ, giới hạn KMS, chi phí, backup và phục hồi.

### KMS key không đồng nghĩa plaintext không bao giờ xuất hiện

Nếu ứng dụng được KMS trả DEK dạng plaintext để mã hóa tại application layer, khóa có thể tồn tại trong RAM. KMS làm giảm một số nguy cơ quản lý khóa, **không loại bỏ rủi ro process compromise, memory disclosure hoặc ứng dụng bị cấp quyền Decrypt quá rộng**.

## 11. Key access policies và tách nhiệm vụ

Một hệ thống không nên mặc định mọi admin đều có quyền đọc dữ liệu bằng cách gọi KMS Decrypt. Cần thiết kế **least privilege**, theo vai trò nghiệp vụ và môi trường.

| Principal | Quyền có thể cần | Quyền nên xem xét giới hạn |
| --- | --- | --- |
| **Invoice API runtime** | Encrypt/Decrypt những key/data context cần phục vụ API. | Không được dùng khóa backup hoặc tenant khác nếu không có nhu cầu. |
| **Export Worker** | Giải mã dữ liệu trong phạm vi job/tenant đã xác minh. | Không tự được quyền thay key policy hoặc decrypt mọi nguồn. |
| **Backup service** | Encrypt/wrap và thao tác backup phù hợp. | Không mặc định có quyền đọc plaintext nghiệp vụ. |
| **Recovery operator** | Quyền kích hoạt khôi phục theo runbook và approval. | Hạn chế Decrypt trong môi trường thường; audit việc nâng quyền. |
| **KMS/key administrator** | Thay cấu hình/lifecycle theo thẩm quyền. | Tránh đồng thời có quyền xem dữ liệu ứng dụng nếu không cần. |
| **Security assessor** | Xem policy/config/evidence, thực hiện phép thử được phép. | Không cần quyền giải mã dữ liệu thật chỉ để xem chứng cứ. |

### Separation of Duties (SoD)

Một nguyên tắc có thể áp dụng là người có quyền **thay key policy** không mặc định có quyền **đọc mọi dữ liệu khách hàng**. Tuy nhiên, SoD cần đánh giá cả quyền kế thừa, break-glass, cloud owner và identity federation; tên role đẹp trên giấy chưa chứng minh effective permissions đúng.

### Encryption context có ích nhưng phải dùng đúng

Một số KMS hỗ trợ **encryption context/AAD** để ràng buộc hoạt động vào service, dataset hoặc tenant trong policy. Điều đó có thể giảm misuse, nhưng phải kiểm tra **context do ai quyết định**. Nếu attacker kiểm soát context trong request còn principal có quyền dùng key rộng, policy có thể không hạn chế như mong đợi.

### Các phép thử âm tính

- Service A không được dùng key của Service B.
- Workload tenant A không được dùng key hoặc context của tenant B theo mô hình tách khóa đã chọn.
- Developer account không thể tự gán quyền Decrypt production.
- KMS administration và data access không bị kết hợp ngoài thẩm quyền.
- Exception/break-glass có hạn, approval, audit và hậu kiểm.

**Cẩn thận:** một KMS key chung phục vụ nhiều tenant không nhất thiết là lỗi nếu kiến trúc có authorization và controls phù hợp; vấn đề là **risk scenario và boundary thực tế**, không phải cứ mỗi tenant phải có một key.

## 12. Mã hóa in transit: kiểm chứng toàn bộ tuyến kết nối

TLS giúp bảo vệ tính bí mật/toàn vẹn của kênh trong điều kiện triển khai đúng. Tuy nhiên, hệ thống hiện đại thường có **nhiều TLS sessions và điểm giải mã**.

### Flow thực tế

~~~text
Browser --[TLS-1]--> CDN / WAF
CDN     --[TLS-2]--> Load balancer
LB      --[TLS-3]--> Application service
App     --[TLS-4]--> Database / Message broker
Worker  --[TLS-5]--> External vendor API
~~~

Không nên xem TLS-1 thành công là bằng chứng TLS-2 đến TLS-5 cũng đúng. Nếu có đoạn truyền trong plaintext, phải ghi nó trong data flow, đánh giá rủi ro, ranh giới và chính sách áp dụng; không mặc định một mạng “nội bộ” luôn tin cậy.

### Những điều cần kiểm tra

| Khía cạnh | Câu hỏi |
| --- | --- |
| **Protocol/cipher policy** | Có cho phép phiên bản/gói mã đã lỗi thời hoặc bị baseline cấm không? |
| **Certificate/hostname validation** | Client thực sự kiểm tra danh tính endpoint, chuỗi chứng chỉ và tên máy? |
| **Mutual TLS** | Nếu yêu cầu xác thực cả hai bên, server có kiểm tra client cert đúng trust/scope không? |
| **Termination/re-encryption** | Có giải mã ở proxy/gateway; chặng tới backend có được bảo vệ riêng? |
| **Redirect/downgrade** | Có đường HTTP không bắt buộc nâng lên TLS, open redirect hoặc fallback yếu? |
| **Certificate lifecycle** | Cấp phát, gia hạn, revoke/rotate và cảnh báo hết hạn có chủ sở hữu? |
| **API/vendor traffic** | Outbound requests có được xác thực endpoint, không tắt certificate verification? |
| **Logging** | Header chứa Authorization/cookie có bị ghi tại điểm termination không? |

### TLS không bảo vệ dữ liệu sau termination

CDN có thể nhận dữ liệu plaintext sau khi giải mã hợp lệ theo thiết kế. Khi đó vendor CDN hoặc người vận hành có quyền phù hợp có thể xử lý dữ liệu tại điểm termination. Cần đưa **vị trí xử lý và shared responsibility** vào mục tiêu bảo vệ và hợp đồng; không dùng từ “end-to-end encrypted” khi endpoint mã hóa thực tế dừng trước đích người dùng nghĩ tới.

## 13. Mã hóa at rest: volume, database, object và application layer

| Lớp mã hóa | Thường bảo vệ trước điều gì | Điểm giới hạn assurance |
| --- | --- | --- |
| **Volume/disk encryption** | Lộ nội dung từ phương tiện hoặc snapshot trong threat model phù hợp. | Workload có quyền đọc volume thường vẫn nhận plaintext. |
| **Managed database/storage encryption** | Dữ liệu lưu trên hạ tầng và bản sao thuộc phạm vi provider. | DB users, queries, cache, exports và ứng dụng không tự được bảo vệ. |
| **Object-level encryption** | Từng object hoặc nhóm object theo policy, có thể quản lý KMS key. | Metadata, access control, CDN, signed URL và download path phải xét riêng. |
| **Application/field-level encryption** | Có thể giới hạn plaintext khỏi một số tầng lưu trữ/operator khi ứng dụng giữ key riêng. | Mở rộng trách nhiệm app: nonce/key lifecycle, index/search, migration, access và debugging. |
| **Backup/archive encryption** | Bảo vệ bản sao dài hạn khi bị mất hoặc truy cập sai. | Khóa có còn dùng được ở môi trường khôi phục và sau rotation? |

### Điểm cần lưu ý với TDE

**Transparent Data Encryption (TDE)** có thể mã hóa database files at rest, nhưng người dùng được phép truy vấn qua database engine vẫn có thể nhận plaintext. Đánh giá TDE cần gắn với **kẻ tấn công là ai** và phân biệt database account compromise với việc lấy cắp media.

### Field-level encryption làm thay đổi dữ liệu sử dụng được

Nếu application mã hóa email, khả năng tìm kiếm, sắp xếp và chỉ mục có thể bị ảnh hưởng. **Deterministic encryption** hoặc tokenization để cho phép tra cứu có thể tiết lộ mẫu trùng lặp và có giả định riêng; không tự biến nó thành phương án an toàn chung. Cần review bởi người hiểu cryptography, dữ liệu, nghiệp vụ và privacy.

### Dữ liệu sao chép cũng là tài sản độc lập

Một database có encryption đúng không chứng minh **CSV export, search index, cache spill, event DLQ, log, BI dataset hoặc môi trường test** cũng đúng. Data inventory và lineage phải đủ để đối chiếu các bản sao có giá trị.

## 14. In-use exposure: mã hóa không phải “lá chắn” với ứng dụng bị chiếm

Một ứng dụng cần giải mã để hiển thị hóa đơn. Trong process có thể có plaintext, khóa tạm hoặc kết quả truy vấn. Nếu attacker chiếm quyền process hoặc dùng API hợp lệ sai mục đích, encryption at rest không tự ngăn lộ.

Các controls bổ trợ:

- Object-level/tenant authorization ở mọi đường đọc, sửa, export và batch.
- Workload identity có quyền tối thiểu tới KMS, database, storage và event broker.
- Giới hạn dữ liệu được giải mã, thời gian tồn tại plaintext và các bản sao trong RAM/cache.
- Không gửi plaintext sang logs, crash dumps, tracing hoặc công cụ debug ngoài phạm vi.
- Secrets handling và hardening, quản lý dependency và isolation phù hợp.
- Monitoring số lượng Decrypt bất thường, export mass data và access patterns.
- Với use case phù hợp, đánh giá kỹ thuật specialized confidential computing/TEE và trust assumptions thực tế.

### Không nhầm confidential computing với bảo đảm tuyệt đối

Các cơ chế xử lý trong vùng bảo vệ phần cứng có thể giảm một số attacker capabilities nhưng không tự loại bỏ bugs, key management, side channels, access logic hoặc lỗi vận hành. Assurance phải dựa vào **threat model, attestation/trust chain khi áp dụng và phép kiểm thử đúng ranh giới**.

## 15. Phân biệt key rotation, rewrap, re-encryption và crypto-erasure

Những hoạt động này có mục tiêu khác nhau:

| Hành động | Điều xảy ra | Điều chưa chắc đã xảy ra |
| --- | --- | --- |
| **Rotate KEK/KMS key version** | Thay phiên bản key bảo vệ DEK mới hoặc thay chính sách tạo key mới. | Dữ liệu đã mã hóa cũ được mã hóa lại tự động. |
| **Rewrap DEK** | Giải bọc và bọc lại DEK bằng KEK mới theo cơ chế cho phép. | Ciphertext nội dung đổi hay DEK bị lộ trước đó được thay mới. |
| **Re-encrypt data với DEK mới** | Nội dung được giải mã và mã hóa lại bằng khóa mới theo quy trình an toàn. | Mọi bản sao offline/backup/đối tác đã được xử lý. |
| **Disable key** | Hạn chế khả năng dùng key theo nền tảng và trạng thái. | Key hoặc các DEK/plaintext đã cache được xóa ở mọi nơi. |
| **Destroy key / crypto-erasure** | Có thể làm ciphertext không thể giải mã nếu tất cả bản khóa/khả năng giải mã thật sự không còn. | Dữ liệu đã được xóa khỏi mọi bản sao hoặc không có plaintext đã từng được xuất. |

### Khi một KEK bị nghi compromise

Rewrap wrapped DEKs dưới KEK mới **không nhất thiết đủ** nếu attacker đã lấy được plaintext DEKs hoặc dữ liệu mã hóa cũ cùng khả năng giải mã. Phải điều tra khả năng đã bị lộ gì, khoảng thời gian, bản sao và quyền sử dụng; kế hoạch có thể cần **re-encrypt với DEK mới**, thu hồi sessions/quyền và đánh giá hậu quả lịch sử.

### Key destruction là thay đổi phá hủy cần kiểm soát

Hủy key trong khi backup hoặc records còn yêu cầu sử dụng có thể làm dữ liệu mất vĩnh viễn. Quy trình phải xét retention, legal hold, dependency, phê duyệt và khả năng khôi phục; cần test trên phạm vi an toàn trước khi dùng các hành động không thể đảo ngược.

## 16. Case study kiến trúc: hóa đơn SaaS đa tenant

Hệ thống cung cấp:

- Invoice API nhận requests từ người dùng nhiều tenant.
- Database giữ hóa đơn và thông tin liên hệ.
- Worker tạo bản PDF/CSV trên object storage.
- Broker và analytics warehouse giữ sự kiện giao dịch.
- Backup lưu snapshots phục vụ khôi phục.
- Một email vendor gửi chứng từ tới người nhận.

~~~mermaid
flowchart LR
    U["User / Browser"] -->|"TLS + AuthN/AuthZ"| GW["CDN / Gateway"]
    GW -->|"TLS theo scope"| APP["Invoice API"]
    APP -->|"DB auth + TLS"| DB[("Encrypted Database")]
    APP -->|"Job metadata"| Q[("Protected Queue")]
    Q --> WRK["Export Worker"]
    WRK -->|"Encrypted object + ACL"| OBJ[("Export Storage")]
    WRK -->|"Approved fields"| WH[("Analytics Warehouse")]
    DB --> BK[("Encrypted Backups")]
    APP -->|"Allowed payload / TLS"| V["Email Vendor"]
    KMS[("KMS / Key policies")] -. "Key use & audit" .-> DB
    KMS -. "Wrap/unwrap if design requires" .-> WRK
    KMS -. "Restore key dependencies" .-> BK
    APP --> LOG[("Security Logs / SIEM")]
~~~

### Vấn đề 1: cấu hình tốt ở database nhưng export yếu

Database có encryption at rest, nhưng Export Worker tạo file trong bucket có đường tải public. **Mã hóa storage vẫn có thể tồn tại**, song user không có quyền có thể tải file qua API/storage được cấp quyền giải mã tại tầng phục vụ. Cần kiểm tra **download authorization, bucket policies, signed URL scope/expiry và audit**.

### Vấn đề 2: KMS shared key và cross-tenant risk

Worker dùng một KMS key chung và có quyền decrypt dữ liệu của nhiều tenant. Đó không tự động là vi phạm nếu thiết kế yêu cầu multi-tenant service identity, nhưng làm tăng hậu quả khi worker bị lạm dụng. Cần test **tenant binding, job integrity, resource scoping, encryption context nếu có và monitoring**, không suy rằng key chung tương đương lỗi mà không đánh giá risk scenario.

### Vấn đề 3: mã hóa backup nhưng không restore được

Backup service tạo bản sao mã hóa mỗi ngày, nhưng recovery environment thiếu quyền KMS và các wrapped DEKs cũ phụ thuộc key đã bị hủy. Backup job báo success không chứng minh **RTO/RPO, integrity và khả năng giải mã**. Cần diễn tập restore với key history và quyền trong môi trường DR.

### Vấn đề 4: TLS chỉ đến gateway

Endpoint người dùng có HTTPS hợp lệ nhưng gateway gửi plaintext qua một network segment khác ngoài trust assumptions. Phải ghi flow thực tế, đánh giá điều kiện nội bộ, baseline và nguy cơ; không được viết “encrypted end-to-end” từ một phép quét domain bên ngoài.

## 17. Java: ví dụ AEAD AES-GCM có AAD

Ví dụ dưới đây minh họa **API và các invariants** cho encryption/decryption ở application layer. Nó **không phải module production có thể sao chép nguyên bản**: ứng dụng thực cần KMS/DEK management, key versioning, safe serialization, concurrency/nonce limits, input limits, error handling, secrets lifecycle, test vectors và security review.

~~~java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AeadExample {
    private static final int NONCE_BYTES = 12; // 96-bit nonce
    private static final int TAG_BITS = 128;   // authentication tag
    private final SecureRandom random = new SecureRandom();

    public record Envelope(byte[] nonce, byte[] ciphertextWithTag) {}

    public Envelope encrypt(
            SecretKey dataKey, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {

        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce); // fresh for every encryption

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                dataKey,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad);

        return new Envelope(nonce, cipher.doFinal(plaintext));
    }

    public byte[] decrypt(
            SecretKey dataKey, Envelope envelope, byte[] trustedAad)
            throws GeneralSecurityException {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                dataKey,
                new GCMParameterSpec(TAG_BITS, envelope.nonce()));
        cipher.updateAAD(trustedAad);

        // Fails on authentication/tag mismatch; do not return partial plaintext.
        return cipher.doFinal(envelope.ciphertextWithTag());
    }
}
~~~

### Những điều phải review ở ví dụ

1. **Nguồn DEK:** SecretKey không được hardcode, dùng lại tùy tiện hoặc chuyển sang client; phải được quản lý theo kiến trúc đã duyệt.
2. **Uniqueness:** nonce ngẫu nhiên 96 bit chỉ phù hợp trong giới hạn sử dụng đã đánh giá; **không bảo đảm uniqueness tuyệt đối** khi số lượng encrypt rất lớn. Cần ngân sách, key segmentation/rekey và test thiết kế.
3. **AAD:** cần cấu trúc chuẩn có version, lấy từ ngữ cảnh tin cậy, ví dụ tenant/record; không chỉ nhận nguyên chuỗi do client đưa.
4. **Serialization:** Envelope phải lưu thuật toán/phiên bản, key reference và nonce/ciphertext theo format đã duyệt; không tự giải mã theo lựa chọn tùy ý từ người gọi.
5. **Integrity:** nếu tag/AAD sai, cipher.doFinal ném lỗi; caller phải **fail closed**, không gửi plaintext chưa được xác thực và không fallback sang mode không an toàn.
6. **Input validation:** kiểm tra định dạng, độ dài và giới hạn request trước các phép toán để hạn chế DoS; không để exception chứa secret.
7. **Mutable arrays:** ví dụ record chứa byte[] có thể bị caller chỉnh sửa; code production cần defensive copying hoặc loại biểu diễn phù hợp, quản lý dữ liệu nhạy cảm trong memory.
8. **Authorization:** caller được phép giải mã đối tượng hay không là một security control khác cần được thực thi trước khi trả plaintext.

### Những unit/integration tests cần có

| Test | Dự kiến |
| --- | --- |
| Encrypt→Decrypt cùng key, nonce, AAD. | Trả đúng plaintext. |
| Thay một byte ciphertext/tag. | Decrypt thất bại, không rò plaintext. |
| AAD bị thay tenant/record ID. | Decrypt thất bại. |
| Key không đúng. | Decrypt thất bại. |
| Nonce/ciphertext bị hỏng định dạng hoặc thiếu. | Bị từ chối an toàn, không crash/DoS vượt giới hạn. |
| Encrypt nhiều lần cùng dữ liệu. | Nonce được quản lý theo policy; không mặc định ciphertext giống nhau. |
| Quyền service không đủ dùng DEK/KMS key. | Request từ chối và có audit trong scope. |

### Không tự viết cryptographic protocol

Khi cần production, ưu tiên **thư viện được duy trì và các giải pháp chuẩn**, đi cùng kiểm tra version/dependency và cryptographic review. Một unit test round-trip đạt không đủ phát hiện mọi sai sót nonce collision, side channel hoặc protocol design.

## 18. Mẫu key/evidence register dạng YAML

Ví dụ học tập sau giúp liên kết requirements và hồ sơ kiểm chứng, **không phải file cấu hình KMS có thể triển khai trực tiếp**:

~~~yaml
control_id: ENC-INVOICE-REST-001
control_name: "Protect confidential invoice storage"
owner_role: "Data Encryption Control Owner"
risk_owner_role: "Customer Data Risk Owner"
environment: production
data_scope:
  asset: invoice-objects
  classification: Confidential
  tenant_boundaries: application_authorization_required
security_claim: >
  In-scope objects are encrypted at rest and only approved
  workloads may use required cryptographic keys.
implementation:
  encryption_layer: object_storage_with_managed_kms
  algorithm_policy: approved_current_cryptography_baseline
  key_reference: example-key-alias-not-a-secret
  operations:
    - Encrypt
    - Decrypt
  principals:
    - invoice-service-workload
  key_rotation_policy: approved_key_lifecycle_standard
  backup_dependency: recovery_runbook_with_key_history
verification:
  - inventory_vs_encryption_policy
  - positive_authorized_decrypt
  - negative_unauthorized_decrypt
  - audit_key_usage_and_policy_changes
  - restore_with_required_key_versions
  - key_rotation_and_failure_simulation
evidence:
  - "restricted://assurance/encryption/storage-config-example"
  - "restricted://assurance/encryption/iam-negatives-example"
  - "restricted://assurance/encryption/recovery-drill-example"
known_limitations:
  - "Application authorization and export flows assessed separately"
  - "Legacy archive inventory requires reconciliation"
reassessment_triggers:
  - new_storage_account_or_region
  - key_policy_or_iam_change
  - algorithm_or_sdk_change
  - failed_decrypt_or_restore
  - suspected_key_compromise
~~~

Mọi ID, aliases, đường dẫn và kết quả trong mẫu là **giả định**, không là evidence có thật. Khi sử dụng cho audit, phải gắn **environment, source, timestamp, policy version, asset population, expected/observed, reviewer và findings** thực tế.

## 19. Chứng chỉ, PKI, signing keys và certificate lifecycle

Encryption assurance phải phân biệt **khóa mã hóa dữ liệu**, **khóa ký**, **khóa chứng chỉ TLS** và **khóa dùng để wrap**. Không nên dùng một key vô định cho nhiều mục đích trái thiết kế/chuẩn.

### Trong TLS, việc tin cậy chứng chỉ gồm nhiều lớp

- Chứng chỉ gắn public key với danh tính endpoint theo mô hình PKI/trust đã chọn.
- Client kiểm tra tên máy/danh tính dịch vụ, chuỗi tin cậy và các điều kiện xác minh liên quan.
- TLS handshake thiết lập bảo vệ kênh; phần thực thi phụ thuộc phiên bản và cấu hình.
- Server certificate hợp lệ không chứng minh **backend nghiệp vụ** đã authorization đúng.
- Private key bị lộ hoặc certificate bị cấp sai có thể làm suy yếu danh tính kênh; cần incident/rotation runbook.

### Khi kiểm tra certificate lifecycle

| Sự kiện | Điều phải làm rõ |
| --- | --- |
| **Issuance** | Ai được yêu cầu/cấp, xác minh danh tính và phê duyệt? |
| **Deployment** | Certificate đến đúng service/endpoint? Private key được bảo vệ ra sao? |
| **Renewal** | Có tránh outage do hết hạn, có test khi cert mới được triển khai? |
| **Revocation/compromise** | Có khả năng hạn chế tin cậy, rotate và cập nhật clients trong thời gian cần? |
| **Inventory** | Bao gồm internal, outbound, vendor connections, mTLS clients, intermediate CAs? |
| **Evidence** | Config, handshake test, alerts, record change, kiểm tra đúng thời kỳ. |

Không tự kết luận “PKI đạt” chỉ vì website có biểu tượng ổ khóa. Đối với mTLS, phải kiểm tra **client identity authorization**, không chỉ client có bất kỳ chứng chỉ hợp lệ từ một CA rộng.

## 20. Cryptographic agility: thay thuật toán/khóa mà không mất dữ liệu

**Cryptographic agility** là khả năng điều chỉnh thuật toán, key sizes, protocols hoặc provider khi có yêu cầu/rủi ro mới mà vẫn quản trị an toàn dữ liệu hiện có.

Các thành phần kiến trúc:

1. **Versioned encryption envelope:** có algorithm ID/key reference được allowlist, định nghĩa format và AAD.
2. **Algorithm policy tập trung:** không để từng service tự dùng thuật toán hoặc thông số yếu.
3. **Data/key inventory:** biết ciphertext nào phụ thuộc key/version/algorithm nào.
4. **Rotation/migration orchestration:** có phương án rewrap/re-encrypt, song song cũ/mới và cutover an toàn.
5. **Backward decryption có kiểm soát:** nếu cần giải mã dữ liệu cũ, quyền và thời hạn phải được quản trị; không tạo fallback bất kỳ.
6. **Test vectors và regression tests:** đảm bảo format, compatibility, integrity, performance và recovery.
7. **Metrics/alerts:** theo dõi thuật toán cũ, key quá hạn, migration chưa hoàn tất và lỗi decrypt.

### Tác động của việc dùng thuật toán lỗi thời

Khi chuẩn hoặc threat model thay đổi, có thể cần migration. **Không chỉ sửa dependency mà bỏ ciphertext cũ**, cũng không để “legacy mode” mở vĩnh viễn không owner/expiry. Phải đo những bản dữ liệu còn dùng mode cũ, cách đọc, kế hoạch chuyển và rủi ro chấp nhận tạm.

### Post-quantum readiness ở mức assurance

Nếu thời hạn bí mật của dữ liệu kéo dài và tổ chức có đánh giá rủi ro liên quan công nghệ lượng tử, có thể cần inventory **các public-key dependencies** và kế hoạch migration theo tiêu chuẩn được phê duyệt. Không suy “AES phải thay ngay” hoặc “mọi ứng dụng cần một thuật toán hậu lượng tử duy nhất”; cần tách threat model, lifespan, interoperability, maturity và yêu cầu áp dụng.

## 21. Kiểm chứng Design Effectiveness và Operating Effectiveness

### Design effectiveness

Hỏi **nếu thiết kế hoạt động đúng như mô tả**, các controls có thể xử lý rủi ro đã xác định không?

- Thuật toán/protocol có được phê duyệt và hợp mục đích?
- Có quản lý nonce/AAD/tag, key lifecycle, key scope và quyền?
- Có thiết kế mã hóa ở **đúng các bản sao và đoạn truyền** cần thiết?
- Có phương án lỗi KMS, cert expiry, rotation, DR, key loss và incident response?
- Có quản lý audit, data minimization của plaintext và key material?
- Có owner, điều kiện ngoại lệ, review trigger và phương pháp kiểm tra?

### Operating effectiveness

Hỏi **thiết kế có thực sự hoạt động trong thời kỳ/phạm vi đã đánh giá không?**

- Asset inventory có đối chiếu cloud, DB, queue, storage, backup và môi trường?
- Cấu hình thực tế có đúng encryption/key policy không?
- KMS/TLS logs, policy history và positive/negative tests có khớp claim?
- Có failed decrypt, denied access, expired certificate, key disabled hoặc rotation errors được xử lý?
- Restore drills có thành công đúng điều kiện dữ liệu và recovery target?
- Các thay đổi role, key, algorithm, storage mới có được review và kiểm tra lại?

**Design PASS, Operating NOT TESTED** không được gộp thành control PASS toàn diện. Một lần thành công của deployment cũng không tự chứng minh cả quý key policies đúng.

### Ma trận chứng cứ

| Claim | Evidence về thiết kế | Evidence về vận hành | Khoảng trống có thể còn |
| --- | --- | --- | --- |
| Data at rest encrypted. | Standard, storage/IaC policy, key design. | Live config readback trên population, object sampling. | Backup, developer copy, exports ngoài inventory. |
| Chỉ service được duyệt dùng key. | IAM/KMS policy và SoD design. | Effective permissions, negative decrypt tests, audit usage. | Hidden roles, cross-account trust, cached DEKs. |
| TLS đến mọi endpoint trong scope. | Architecture, transport standard, certificate policy. | Handshake/config tests trên từng chặng, error paths. | Vendor/internal hop ngoài phạm vi đo. |
| AEAD bảo vệ integrity. | Mode/nonce/AAD design và SDK review. | Tamper/AAD mismatch tests, failure outcomes. | Nonce collision ở quy mô lớn nếu chỉ test một vài mẫu. |
| Rotation không mất dữ liệu. | Migration/runbook, key history và retention analysis. | Canaries, key rotation drill, old data read/restore. | Bản sao offline, dịch vụ chưa cập nhật. |
| Backup mã hóa có thể phục hồi. | Backup policy, keys/DR design. | Restore drill, dữ liệu đối soát, RTO/RPO thực đo. | Một bài test giới hạn không bao phủ mọi loại failure. |

## 22. Claim – Argument – Evidence (CAE) cho Encryption assurance

### Claim mẫu

“Trong bản phát hành và môi trường production được đánh giá, các objects hóa đơn thuộc inventory được mã hóa at rest theo baseline; quyền truy cập khóa được giới hạn theo service/operation đã duyệt; file export và backup có controls riêng; quy trình restore được kiểm chứng.”

### Argument

1. Inventory và data flow xác định dữ liệu, nơi lưu, bản sao và ranh giới.
2. Baseline chỉ ra thuật toán, storage control, key lifecycle và owner.
3. IaC/KMS policies cùng service identities giới hạn operations và tài sản.
4. Runtime configuration và negative tests chứng minh người ngoài scope không dùng key hoặc đọc object.
5. Backup/rotation/recovery tests chứng minh tính khả dụng theo mục tiêu.
6. Findings/limitations được quản lý, retest khi thay đổi hoặc khắc phục.

### Evidence

Inventory có timestamp và sources, policy export/version, cấu hình KMS/storage production, test reports với commit/release, audit KMS (đã hạn chế dữ liệu), signed/managed config history khi có, restore logs, key lifecycle events, exception/risk approvals và kết quả retest.

### Evidence có thể bác bỏ claim

- Một bucket Confidential ngoài inventory không có mã hóa phù hợp.
- Một principal không được phê duyệt vẫn dùng KMS Decrypt thành công.
- Decryption trả plaintext khi tag hoặc AAD sai.
- Restore DR không đọc được dữ liệu vì khóa bị hủy.
- TLS termination tạo đường plaintext ngoài phạm vi được phép.

Khi có bằng chứng không đạt, không được chỉ chọn những screenshot xanh để tạo câu chuyện “all encrypted”. **Kết luận phải thể hiện failure và giới hạn**, xử lý rủi ro rồi kiểm chứng lại.

## 23. Point-in-time, period-of-time và population

Một snapshot bucket ngày kiểm toán có thể chứng minh **cấu hình tại thời điểm đó**; nó không tự chứng minh không có lúc bucket chuyển sang trạng thái khác trong ba tháng trước.

### Population cho encryption assurance có thể gồm

- Data assets: DB instances, tables/fields có bảo vệ riêng, object buckets, backup sets, snapshots, archives.
- Network flows: ingress, proxy, internal east-west, database, broker, third-party.
- Keys và certificates: owner, key versions, algorithms, trust stores, cryptoperiods.
- Principals và grants: workloads, admins, backup/recovery identities, service accounts.
- Cryptographic operations: KMS Encrypt/Decrypt/GenerateDataKey, rotation events, failures.
- Ciphertext samples/records: format, nonce/AAD/tag/version trong các nhóm đã chọn.

### Sampling cần có phương pháp

Nếu có 500 bucket, kiểm tra 50 bucket có thể hỗ trợ claim **trong mẫu 50** theo phương pháp đã nêu; không tự chứng minh 500/500 đạt. Với thuộc tính cloud có thể tự kiểm tra tất cả, ưu tiên giải pháp full inventory/readback phù hợp nhưng vẫn phải kiểm tra **completeness của nguồn inventory và độ tin cậy collector**.

Một đánh giá nên ghi:

1. Population source, kỳ và cách đối chiếu.
2. Sample selection (risk-based/random/canary), quy mô và lý do.
3. Expected/observed, environment, key version và result.
4. Ngoại lệ, failures, quyền chưa quan sát và phần ngoài scope.
5. Cách mở rộng kiểm tra khi phát hiện drift/failure.

## 24. Kế hoạch kiểm thử Encryption controls

Các bài test phải chứng minh **cả điều đúng và điều bị từ chối**, cùng hành vi khi hệ thống lỗi. Ưu tiên **sandbox/canary và dữ liệu giả** để tránh gây gián đoạn hoặc lộ dữ liệu thật.

| Test ID | Kịch bản | Tiêu chí cần quan sát |
| --- | --- | --- |
| **ENC-T01** | Mã hóa/giải mã dữ liệu với key và AAD đúng. | Round trip đúng nội dung, format/version hợp lệ. |
| **ENC-T02** | Sửa một byte ciphertext hoặc tag. | AEAD xác thực thất bại, không lộ plaintext. |
| **ENC-T03** | Sửa AAD từ tenant A sang tenant B. | Decrypt từ chối; không bypass authorization. |
| **ENC-T04** | Dùng key sai hoặc key version không có quyền. | Không trả plaintext, lỗi được ghi an toàn. |
| **ENC-T05** | Nonce management dưới tải/retry. | Thiết kế uniqueness được kiểm chứng theo giới hạn; không reuse ngoài policy. |
| **ENC-T06** | Principal không được phép gọi KMS Decrypt. | Bị từ chối tại KMS, có audit/alert phù hợp. |
| **ENC-T07** | Một service cố dùng key của service khác/tenant khác ngoài scope. | Không dùng được theo policy/condition đã chọn. |
| **ENC-T08** | Một bucket hoặc snapshot thiếu encryption config. | Gate/monitor phát hiện, không ghi PASS nhầm. |
| **ENC-T09** | Kết nối TLS tới endpoint có cert hostname sai. | Client từ chối handshake. |
| **ENC-T10** | Một hop nội bộ không đáp ứng transport baseline. | Scan/config/test phát hiện đúng hop, tạo finding. |
| **ENC-T11** | Provider/IdP/KMS connection lỗi hoặc timeout. | Hệ thống xử lý fail closed phù hợp; không bỏ verification. |
| **ENC-T12** | Key rotation với dữ liệu và DEK cũ. | Ghi mới dùng policy mới; đọc dữ liệu cũ hợp lệ theo kế hoạch. |
| **ENC-T13** | Key bị disable hoặc revoked trong diễn tập. | Không giải mã trái phép; có alert và recovery/escalation. |
| **ENC-T14** | Restore backup mã hóa vào môi trường DR. | Khóa/permissions khả dụng, dữ liệu đối soát đúng, đo RTO/RPO. |
| **ENC-T15** | Log/debug với secret/plaintext canary. | Không chứa nội dung cấm trong log/traces/cảnh báo trong scope. |
| **ENC-T16** | File export object được tải bởi user sai tenant. | Bị từ chối dù storage encryption vẫn bật. |
| **ENC-T17** | Key administrator tự nâng quyền giải mã ngoài quy trình. | Policy/SoD ngăn hoặc ghi nhận và escalation theo kiểm soát. |
| **ENC-T18** | Collector/monitoring KMS im lặng. | Health check tạo evidence gap; không báo compliant giả. |
| **ENC-T19** | Mã hóa/decrypt lượng lớn, dữ liệu/metadata sai format. | Giới hạn tài nguyên, validate input, lỗi an toàn, tránh DoS. |
| **ENC-T20** | Thu hồi quyền/khóa sau sự cố. | Quyền dùng key, phiên/caches/bản sao liên quan được đánh giá; không tuyên bố thu hồi hoàn toàn nếu thiếu chứng cứ. |

**Kết quả test phải giữ trạng thái** PASS/FAIL/PARTIAL/NOT TESTED/NOT APPLICABLE/EXCEPTION đúng định nghĩa. Thất bại thu evidence không được tự chuyển thành PASS vì không thấy cảnh báo. Với tests liên quan hủy key hoặc disable production, không thực hiện thao tác phá hủy ở môi trường thực nếu chưa được phê duyệt.

### Một test “encrypt rồi decrypt đúng” chứng minh được gì?

Nó có thể kiểm tra implementation với input đã chọn. Nó **không chứng minh** key không lộ, nonce không bị trùng ở quy mô lớn, TLS đúng, IAM đúng, các bản sao được mã hóa hay backup có thể restore. Security assurance phải dùng **nhiều loại evidence độc lập** phù hợp claim.

## 25. Case study: KMS permissions quá rộng trong Invoice SaaS

### Bối cảnh

Invoice SaaS mã hóa file PDF bằng object storage kết hợp KMS-managed key. Khóa và storage đều hiển thị trạng thái bật mã hóa. Một automation worker cần quyền GenerateDataKey/Decrypt cho luồng export, nhưng do cấu hình IAM, vai trò support admin có thể sử dụng Decrypt với key đó dù nhiệm vụ không cần.

**Threat scenario:** nhân viên hoặc tài khoản support bị xâm nhập có thể dùng key hoặc kết hợp các quyền lưu trữ để tiếp cận dữ liệu ngoài nhiệm vụ. **Key vẫn được quản lý trong KMS**; lỗi nằm ở phạm vi sử dụng.

### Bước 1 — Xác định claim và nhận diện failure

**Claim ban đầu:** “Chỉ workload invoice/export có quyền dùng key mã hóa dữ liệu khách hàng.”

**Evidence không đạt:** KMS effective access policy cho thấy support admin cũng có quyền sử dụng, hoặc negative permission test bằng identity được phép trong sandbox cho kết quả Decrypt thành công ngoài scope.

### Bước 2 — Điều tra đường quyền

Xác định policy gốc, inherited roles, grants, cross-account trust, break-glass, condition context, các service accounts, KMS usage logs và khả năng storage access. Cần phân biệt:

- **Có quyền Decrypt** là một điều kiện rủi ro.
- **Đã gọi Decrypt** là hành động có thể có evidence nếu audit đủ.
- **Đã đọc plaintext khách hàng** là kết luận cần thêm bằng chứng về data access/response và phạm vi.

Không suy diễn một trong ba thành cái còn lại.

### Bước 3 — Containment và remediation

Theo quy trình được duyệt, giới hạn grants/policies vượt thẩm quyền, xem xét thay vai trò support hoặc dùng JIT với approval, kiểm tra service dependencies để tránh outage. Đánh giá log, dấu hiệu lạm dụng và data exposure theo khả năng quan sát.

Nguyên nhân gốc có thể do **IAM policy template quá rộng**, thiếu review principal-to-key mapping hoặc dùng common admin role cho cả key operation và support. Biện pháp lâu dài gồm sửa IaC/policy, negative policy test, access review và cảnh báo thay đổi grants.

### Bước 4 — Retest và evidence

| Retest | Kỳ vọng |
| --- | --- |
| Runtime invoice/export gọi KMS đúng nhu cầu. | Thành công trong scope, không làm hỏng nghiệp vụ. |
| Support admin thử Decrypt ngoài quyền. | Bị từ chối và tạo audit event phù hợp. |
| Cross-account/tenant test theo policy. | Không vượt boundary nếu control yêu cầu. |
| Xem policy diff và effective grants. | Không còn quyền không được phê duyệt. |
| Khôi phục file cũ và backup. | Giải mã hợp lệ vẫn hoạt động theo runbook/role được phép. |
| Review lần cấp quyền tiếp theo. | Pipeline/approval phát hiện thay đổi role/condition ngoài baseline. |

### Bước 5 — Kết luận

Có thể khẳng định quyền key đã thu hẹp **trong scope và phiên bản được kiểm chứng**. Nhưng không thể kết luận không có exfiltration trong quá khứ chỉ từ kết quả policy đã sửa; lịch sử usage logs và thời gian retention có giới hạn riêng.

## 26. Sự cố lộ khóa: phản ứng và rủi ro còn lại

Một sự kiện có thể gồm key bị đưa vào Git, signing private key nằm trong log, KMS key policy bị lạm dụng hoặc dữ liệu ciphertext được tải cùng với khóa giải mã.

### Quy trình cần phối hợp

1. **Xác nhận loại khóa, mục đích và scope:** key mã hóa nội dung, KEK, token signing key, TLS key hoặc secret khác.
2. **Bảo toàn dấu vết:** thời gian, nguồn, quyền, các bản sao của key và dữ liệu đã được bảo vệ.
3. **Hạn chế khả năng tiếp tục dùng:** revoke/disable grants hoặc credential theo phương án có thẩm quyền và tác động được đánh giá.
4. **Đánh giá exposure:** dữ liệu nào phụ thuộc, có ai đã dùng key, nguồn log nào đủ hay không.
5. **Thay thế/rotation:** chọn rewrap hoặc re-encryption theo loại key, mức lộ và khả năng plaintext DEK bị ảnh hưởng.
6. **Sửa nguyên nhân:** secret scanning, IaC policy, tách quyền, logging và kênh phân phối.
7. **Retest và restore:** kiểm tra dịch vụ vẫn đọc dữ liệu hợp lệ, khóa cũ bị từ chối trong scope và DR không hỏng.
8. **Residual risk:** ghi giới hạn lịch sử, hậu quả dữ liệu đã lộ và các nghĩa vụ xử lý/thông báo nếu áp dụng.

### Xóa secret khỏi Git không phải thu hồi khóa

Secret có thể còn trong history, clone, logs, CI cache hoặc bản copy. Ưu tiên **thu hồi khả năng sử dụng tại nguồn, đánh giá impact và thay thế đúng cách**; dọn history nếu cần là một phần khác của quy trình, không thay thế revoke/rotate.

### Incident response không được tự phá recovery

Vô hiệu hóa tất cả keys ngay có thể làm hệ thống quan trọng và dữ liệu backup không thể dùng. Quyết định containment phải cân bằng mức nguy hiểm hiện tại, khả năng ứng cứu, khả năng chuyển khóa và thẩm quyền; ghi rõ trạng thái còn rủi ro.

## 27. Backup, Disaster Recovery và khả năng giải mã sau thảm họa

Một backup chỉ đáng tin nếu có thể được **khôi phục và sử dụng an toàn** trong kịch bản thật:

| Thành phần | Cần kiểm tra |
| --- | --- |
| **Backup ciphertext** | Bản sao có tồn tại, integrity và encryption trong scope? |
| **Key availability** | Key versions, KEKs/DEKs, chính sách KMS và dependencies còn khả dụng khi restore? |
| **Identity/permissions** | Recovery workload có quyền hợp lệ, có approval/audit và điều kiện giới hạn? |
| **Region/account failure** | Khi account/region chính gặp sự cố, key/trust dependency có còn? |
| **Restore procedure** | Trình tự, phiên bản schema, certificate/secret dependencies và rollback? |
| **Business validation** | Dữ liệu hóa đơn, tổng tiền, trạng thái giao dịch có đối soát? |
| **RTO/RPO** | Thời gian và mức mất dữ liệu thực đo có đáp ứng mục tiêu nghiệp vụ? |
| **Past deletion decisions** | Dữ liệu đã phải xóa có bị xuất hiện lại trái quy tắc sau restore không? |

### Phép thử bắt buộc theo threat scenario

“Backup job SUCCESS” chỉ hỗ trợ claim job chạy xong; nó không tự chứng minh key còn sẵn hoặc trạng thái sau restore đúng. Đợt drill nên giả lập các tình huống như **key version cũ**, **IAM khác môi trường**, **khôi phục không cùng region** và **mất một dịch vụ phụ thuộc**, theo kịch bản được phép và không làm ảnh hưởng production.

## 28. Bằng chứng phải có provenance và được bảo vệ

Encryption assurance evidence thường chứa **KMS key IDs, policy, kiến trúc, principal, configuration, log lỗi và dữ liệu thử**. Đây là thông tin có thể hỗ trợ attacker, nên cần quyền xem, redaction và retention.

### Evidence record nên chứa

| Trường | Ý nghĩa |
| --- | --- |
| **evidence_id / control_id** | Gắn hiện vật với claim, requirement và control. |
| **asset/population reference** | Những data stores, keys, endpoints và identities được kiểm tra. |
| **environment/region/time** | Production/staging, region và thời kỳ/mốc thu thập. |
| **source/collector version** | API/cloud account, test harness, SDK/algorithm/collector version. |
| **expected/observed/result** | Tiêu chí, kết quả thực tế và trạng thái PASS/FAIL/PARTIAL. |
| **key/cert reference** | ID/version được phép ghi, không chứa raw key material. |
| **artifact location/integrity** | Kho evidence được phân quyền, versioning và cách kiểm tra toàn vẹn. |
| **reviewer/owner** | Ai tạo, ai phê duyệt, ai đánh giá. |
| **limitations/findings** | Những phần chưa kiểm tra, thất bại, ngoại lệ, risk decision. |

### Chain of custody và log an toàn

Với incident nghi lộ khóa, cần bảo vệ bản gốc, ghi người thu, thời điểm, chuyển giao và phạm vi sửa/redaction nếu có. Nhưng không đưa **raw plaintext DEK, private key, session token hay nội dung hóa đơn** vào evidence pack khi không thật sự cần.

**Hash của artifact** có thể hỗ trợ phát hiện thay đổi nếu hash tham chiếu được bảo vệ; hash đơn thuần **không chứng minh dữ liệu gốc đáng tin, phương pháp đủ hoặc population đầy đủ**.

## 29. Vai trò và RACI trong Encryption assurance

| Vai trò | Trách nhiệm |
| --- | --- |
| **Data owner** | Xác định classification, dữ liệu cần bảo vệ, impact và nhu cầu nghiệp vụ. |
| **Cryptographic/control owner** | Duy trì baseline/algorithm/key scope, thiết kế control và bằng chứng. |
| **KMS/HSM/platform operator** | Vận hành key lifecycle, IAM, rotation, audit và availability theo quy trình. |
| **Application/service owner** | Triển khai encryption/authorization, key use, mã hóa dữ liệu và regression tests. |
| **Network/PKI owner** | Quản lý TLS, certificate, mTLS và transport trust. |
| **Backup/recovery owner** | Đảm bảo backup và key dependencies có thể restore. |
| **Security assurance/assessor** | Đánh giá thiết kế/vận hành, population, evidence, test và findings. |
| **Risk owner** | Quyết định residual risk trong thẩm quyền được giao. |
| **Incident response** | Điều phối key compromise, containment và điều tra dữ liệu. |
| **Privacy/legal/compliance** | Xác định nghĩa vụ dữ liệu, algorithm/standards và giới hạn xử lý khi áp dụng. |

### RACI minh họa

**R** = thực hiện; **A** = chịu trách nhiệm cuối cùng; **C** = tham vấn; **I** = thông báo.

| Công việc | Crypto control owner | Platform operator | Application owner | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Định nghĩa baseline, key purpose và ranh giới | **A/R** | C | C | C | I |
| Triển khai KMS policies và vận hành keys | C | **A/R** | C | C | I |
| Kiểm soát encryption/AAD/authorization trong ứng dụng | C | C | **A/R** | C | I |
| Kiểm tra độc lập, điều tra evidence gaps | C | C | C | **A/R** | I |
| Diễn tập khôi phục liên quan keys | C | **A** | **R** | C | I |
| Chấp nhận residual risk theo thẩm quyền | C | I | C | C | **A/R** |

RACI thực tế phải được điều chỉnh theo governance và shared responsibility. **KMS administrator không tự động có quyền chấp nhận rủi ro về dữ liệu khách hàng**, và assessor không thay cho người sở hữu nghiệp vụ.

## 30. Continuous Encryption Assurance trong SDLC và vận hành

Mã hóa dễ bị suy giảm bởi **key policy drift, provider configuration change, SDK upgrade, certificate expiration, cryptoperiod và data flow mới**. Cần chương trình theo dõi liên tục.

### Chu trình

~~~mermaid
flowchart TD
    A["Data inventory, threat model, crypto baseline"] --> B["Requirements + control design"]
    B --> C["CI tests + policy as code + reviews"]
    C --> D["Deploy + runtime config verification"]
    D --> E["Key usage, TLS, failures, recovery evidence"]
    E --> F{"Claim đạt trong scope?"}
    F -- "Không / thiếu chứng cứ" --> G["Finding + triage + remediation"]
    G --> H["Retest + residual risk decision"]
    H --> C
    F -- "Có" --> I["Assurance conclusion có giới hạn và thời kỳ"]
    I --> J["New data / key / SDK / endpoint / provider change"]
    J --> A
~~~

### Trigger bắt buộc cân nhắc

- Thêm database, bucket, backup, export hoặc dataset có phân loại cao.
- Thay key policies, KMS grants, IAM role hierarchy hoặc trust giữa accounts.
- Thay thuật toán, mode, SDK, cryptographic provider hoặc cấu trúc encrypted envelope.
- Certificate/TLS policy thay đổi, outbound vendor mới, thêm proxy/termination.
- Key/certificate rotation, revoke, nghi compromise, quá hạn.
- Giới hạn nonce/key usage hoặc sự kiện high-volume encryption.
- Khôi phục dữ liệu, thay vùng/DR account, thay retention và key destruction.
- Test fail, audit finding, logging gap hoặc incidents liên quan plaintext/secret.

### Gắn vào CI/CD

Một pull request thêm object storage mới cần tạo câu hỏi: data classification gì, storage policy/key reference nào, IAM cho ai, backup/retention ra sao và những tests nào sẽ chứng minh đáp ứng baseline? Pipeline có thể dùng **policy-as-code** để chặn cấu hình rõ ràng sai, nhưng **production drift và quyền hiệu lực** vẫn cần được kiểm chứng ở runtime.

## 31. Chỉ số chương trình Encryption assurance

| Chỉ số | Ý nghĩa | Bẫy diễn giải |
| --- | --- | --- |
| **In-scope encrypted asset coverage** | Tỷ lệ tài sản trong population có config đúng. | Population thiếu thì 100% là giả. |
| **Key inventory ownership coverage** | Tỷ lệ keys/certs có owner, purpose, review lifecycle. | Có owner không chứng minh IAM hiệu quả. |
| **Unauthorized key use denied tests** | Khả năng ngăn principals ngoài scope. | Chỉ test vài role không bao phủ effective grants. |
| **Deprecated algorithms/versions** | Tài sản còn dùng baseline cũ hoặc mode bị cấm. | Mẫu số/format cũ có thể khó quan sát. |
| **Key/certificate rotation health** | Rotation diễn ra đúng và không làm outage vượt mục tiêu. | Rotation hoàn thành không tự re-encrypt dữ liệu cũ. |
| **TLS hop coverage** | Những chặng kết nối đã kiểm tra theo requirements. | Scan domain ngoài chỉ thấy hop đầu. |
| **Tamper/AAD test coverage** | Những đường AEAD có negative tests. | Test 100 records không chứng minh nonce uniqueness ở quy mô lớn. |
| **KMS denied/error anomalies** | Sự kiện bất thường, quyền drift hoặc mất dependency. | Nhiều failures có thể do config; cần triage. |
| **Restore drill success & RTO/RPO** | Khả năng đọc lại dữ liệu có mã hóa khi gặp sự cố. | Backup success khác restore. |
| **Evidence freshness/gaps** | Có đủ chứng cứ đúng release/kỳ/asset không. | Collector im lặng không đồng nghĩa không có lỗi. |
| **Open crypto findings and residual risk** | Rủi ro còn tồn tại quá hạn và kết quả remediation. | Đóng ticket chưa chứng minh đã sửa đúng. |

### Không dùng “Encryption coverage 100%” thay cho risk decision

Một hệ thống có mọi disk mã hóa nhưng KMS Decrypt quyền rộng vẫn có rủi ro lớn; một chặng có TLS chuẩn nhưng API lộ dữ liệu sai tenant vẫn thất bại confidentiality. Scorecard phải **liên kết từng số với claim, threat scenario và giới hạn**.

## 32. Ngoại lệ và residual risk

Một hệ thống legacy có thể chưa hỗ trợ cơ chế mã hóa theo baseline, hoặc quá trình thay khóa cần migration kéo dài. Khi đó:

1. Ghi rõ **data asset, flow, key, environment và requirement** chưa đáp ứng.
2. Phân tích **threat scenario, likelihood, impact, thời gian phơi lộ** theo phương pháp tổ chức.
3. Nêu **existing controls có bằng chứng**, không tính kế hoạch chưa triển khai là đã giảm rủi ro.
4. Đánh giá biện pháp bù (segment, IAM, monitoring, hạn chế dữ liệu, kiểm soát truy cập vật lý) và khả năng kiểm chứng.
5. Chỉ rõ owner, deadline, plan, rollback, retest và điều kiện hết hạn.
6. Yêu cầu **risk owner có thẩm quyền** quyết định, có thể cần privacy/legal/compliance tham vấn theo nghĩa vụ.
7. Định nghĩa trigger đánh giá lại khi có incident, dữ liệu mới, key compromise hoặc biện pháp bù thất bại.

**Current residual risk** phản ánh tình trạng thực tế trước khi sửa và controls đã có. **Target residual risk** là mức dự kiến sau triển khai + retest. Một PR mã hóa đang chờ merge không làm dữ liệu hiện tại được bảo vệ nhiều hơn.

Không phải yêu cầu pháp luật, hợp đồng hay chuẩn bắt buộc nào cũng có thể bỏ qua bằng ngoại lệ nội bộ. Khi yêu cầu riêng như validated cryptographic module hoặc chứng chỉ được đòi hỏi, phải xác định đúng phạm vi và bằng chứng theo tài liệu/tiêu chuẩn đang áp dụng.

## 33. Những ngộ nhận thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Storage hiển thị encrypted nghĩa là data flow an toàn.” | Cần kiểm tra access, copies, plaintext tại application và transport. |
| “AES-256 tự bảo đảm security.” | Mode, nonce, AAD, key lifecycle, implementation và threat model quyết định. |
| “Hash dữ liệu giống encryption.” | Hash không phục hồi nội dung bằng giải mã; mục đích khác. |
| “Mã hóa cung cấp integrity ở mọi mode.” | Cần AEAD hoặc cơ chế xác thực phù hợp; kiểm chứng tag và xử lý lỗi. |
| “Nonce có thể sử dụng lại nếu plaintext khác.” | Reuse nonce với cùng GCM key có thể làm suy yếu bảo mật nghiêm trọng. |
| “KMS bảo đảm không ai ngoài đúng người được giải mã.” | IAM/grants, app runtime, context và principal có thể được cấp quá rộng. |
| “Dùng cùng key cho tất cả tenants luôn là lỗi.” | Đánh giá theo risk/boundaries; key riêng có thể giảm blast radius nhưng không thay authz. |
| “Đổi KEK tức toàn bộ dữ liệu được re-encrypt.” | Rewrap và re-encryption khác nhau; cần inventory key/data versions. |
| “Destroy key luôn tương đương xóa toàn bộ dữ liệu.” | Các bản key/plaintext, backups, exports và dependencies cần xem riêng. |
| “HTTPS ở website nghĩa là TLS tới database/vendor.” | Mỗi hop/termination có cấu hình và evidence riêng. |
| “TLS đúng nghĩa bên nhận có mục đích hợp lệ.” | TLS bảo vệ kênh, không quyết định mục đích/quyền của recipient. |
| “Backup encrypted và job xanh là DR PASS.” | Phải restore được với key/dependencies, đo RTO/RPO và data integrity. |
| “AEAD unit test round-trip đủ chứng minh implementation an toàn.” | Cần negative tests, nonce limits, key authorization, input validation và threat review. |
| “Không có KMS error nghĩa là không có misuse.” | Có thể thiếu logging hoặc misuse không phát lỗi; cần coverage và monitoring. |
| “Mã hóa cho phép bỏ object-level authorization.” | App có quyền giải mã vẫn phải kiểm tra user/tenant/action. |
| “Chỉ khi key raw rời KMS mới có key compromise.” | Quyền gọi decrypt sai có thể là con đường khai thác tương đương theo threat. |
| “Ngoại lệ được ký đồng nghĩa control hiệu quả.” | Risk acceptance là quyết định có phạm vi/hạn, không chứng minh control đạt. |

## 34. Checklist đánh giá Encryption assurance trước release/audit

1. **Scope:** data assets, classifications, flow, backup, exports, regions và bên nhận được xác định?
2. **Threat model:** encryption giải quyết attacker nào; các rủi ro ngoài crypto có được nêu?
3. **Requirements:** baseline về algorithm, mode, TLS, key policy và recovery phù hợp use case?
4. **At rest:** mọi asset/bản sao cần thiết có encryption và key references được xác minh ở runtime?
5. **In transit:** mọi TLS hop được kiểm tra certificate/peer identity/termination phù hợp?
6. **In use:** plaintext, secrets, caches, logs, crash dumps và application permissions được quản trị?
7. **Crypto design:** AEAD/tag/nonce/AAD, versioning, input validation, provider/SDK có review?
8. **Key generation/storage:** nguồn tạo, nơi lưu, ownership, lifecycle và hạn dùng đã rõ?
9. **Key IAM:** Encrypt/Decrypt/Wrap/Unwrap grants giới hạn theo service/environment/context?
10. **SoD/PAM:** key administration, read data, recovery và break-glass được phân quyền/giám sát?
11. **Rotation/migration:** rewrap/re-encrypt, key history, compatibility và rollback có test?
12. **Backup/recovery:** key dependencies, restore drills, integrity, RTO/RPO đã chứng minh?
13. **Negative tests:** wrong key/AAD/tag/issuer/cert/principal và retry/failure behavior có kiểm tra?
14. **Evidence:** configuration, tests, key usage logs, time period, scope, version, provenance có đầy đủ?
15. **Incidents/exception:** unauthorized decrypt, key leak, expired cert, drift, risk decision có owner?
16. **Change triggers:** thêm storage/vendor, sửa key policy/SDK/TLS hoặc schema có reassessment?

## 35. Bài tập tình huống và gợi ý giải

### Bài tập A — Mã hóa ổ đĩa nhưng API lộ dữ liệu

DB sử dụng encryption at rest. User tenant A có thể đọc hóa đơn tenant B nếu đoán ID. Đội platform cho rằng không có lỗ hổng vì dữ liệu “đã mã hóa”.

**Gợi ý:** Encryption bảo vệ theo threat model storage, không thay authorization. Cần negative object/tenant tests, kiểm tra queries và export, đánh giá tác động dữ liệu đã tiếp cận và khắc phục tại service.

### Bài tập B — Nonce GCM bị trùng

Worker dùng AES-GCM với nonce luôn bằng giá trị mặc định cố định cho mọi file export dưới một DEK chung.

**Gợi ý:** Đây là lỗi cryptographic design nghiêm trọng. Cần dừng sử dụng sai, đánh giá ciphertext/key exposure, thiết kế nonce uniqueness/rekey đúng, test retry/concurrency và re-encrypt khi rủi ro yêu cầu. Không chỉ thay một dòng code mà mặc định file cũ vẫn an toàn.

### Bài tập C — Một role support gọi được Decrypt

KMS key lưu tốt, nhưng support engineer có quyền Decrypt production và đọc object nếu biết đường dẫn.

**Gợi ý:** Xem effective IAM/grants, tách nhiệm vụ và thu hẹp key/data access; kiểm tra denied use cho principal ngoài scope, audit quá khứ và residual risk. “Key không export được” không có nghĩa plaintext không thể lấy qua API.

### Bài tập D — TLS chỉ ở hop đầu

Khách hàng thấy HTTPS trên domain Invoice SaaS. Nhưng gateway gửi HTTP tới ứng dụng trong segment dùng chung với workload khác.

**Gợi ý:** Phải mô hình hóa cả hai hop, trust boundary và attacker capabilities; so với transport baseline, bổ sung TLS/mTLS hoặc phương án được phê duyệt và test thực tế. Không tuyên bố end-to-end encrypted.

### Bài tập E — Rotate KEK nhưng không re-encrypt DEKs

Một key wrapping key bị nghi lộ. Đội vận hành rewrap DEKs dưới KEK mới rồi tuyên bố mọi dữ liệu cũ tuyệt đối an toàn.

**Gợi ý:** Cần phân biệt khả năng attacker lấy KEK, wrapped DEKs, plaintext DEKs hoặc ciphertext. Rewrap chỉ bảo vệ vòng bọc mới, không loại bỏ mọi bản key lộ trước đó. Threat analysis quyết định có cần DEK/data re-encryption, thu hồi quyền và đánh giá dữ liệu lịch sử.

### Bài tập F — Backup không giải mã được khi restore

Backup báo SUCCESS và encrypted, nhưng key cũ đã bị xóa trong cleanup; quy trình DR thất bại.

**Gợi ý:** Design/operating effectiveness của recovery chưa đạt. Cần key dependency inventory, lifecycle/retention policy, restore drill với dữ liệu kiểm tra, thay đổi quy trình destroy và đánh giá RTO/RPO, impact.

### Bài tập G — Unit tests PASS, nonce collision vẫn có thể xảy ra

Team chạy một nghìn phép encrypt/decrypt với nonce ngẫu nhiên và không phát hiện trùng. Họ kết luận nonce uniqueness đã được chứng minh cho hàng tỷ thao tác mỗi ngày dưới một key.

**Gợi ý:** Một mẫu nhỏ không chứng minh an toàn ở quy mô lớn. Cần phân tích thống kê nguy cơ va chạm, giới hạn của mode, số lần mã hóa dưới mỗi key và thiết kế nonce/key rotation, không chỉ unit tests.

### Bài tập H — Log chứa plaintext sau giải mã

Ứng dụng dùng AEAD đúng, nhưng exception handler ghi nguyên hóa đơn và key reference vào log gửi tới vendor ngoài.

**Gợi ý:** Encryption không bảo vệ log plaintext. Cần tối thiểu hóa/redact log, kiểm tra error paths, quyền và retention nhà cung cấp, điều tra bản sao đã gửi và dùng canary tests để ngăn tái diễn.

### Bài tập I — Certificate rotation gây outage

Một mTLS certificate hết hạn vào ngày cuối quý; người vận hành thay cert nhưng ứng dụng nhận vẫn chỉ tin cert cũ.

**Gợi ý:** Kiểm tra inventory/cert chain/truststore, quy trình overlap/rollover theo thiết kế, test handshake hai bên và cảnh báo hết hạn; không tắt peer verification để khôi phục nhanh.

### Bài tập J — Dashboard báo 100% encrypted

Cloud scanner xác nhận 200/200 production buckets được mã hóa, nhưng phát hiện ba file export được lưu trong kho analytics vendor chưa đăng ký.

**Gợi ý:** Population không đầy đủ, claim phải giới hạn vào 200 buckets. Bổ sung data flow/inventory và shared responsibility, kiểm tra đường truyền, encryption, IAM, retention/vendor controls. Tỷ lệ 100% không có giá trị trên tập chưa được kiểm kê.

## Kết luận

**Encryption assurance** không phải bài kiểm tra xem hệ thống có dùng tên thuật toán mạnh hay có bật cờ mã hóa hay không. Nó là quá trình **đánh giá có bằng chứng** rằng dữ liệu trong phạm vi được bảo vệ theo **threat scenario, trạng thái và ranh giới thực tế**, với thuật toán/mode đúng, nonce/AAD/integrity phù hợp, quản lý khóa an toàn, TLS được kiểm chứng qua các chặng, IAM và vòng đời khóa được kiểm soát, backup có thể phục hồi và các bản sao downstream được xét đầy đủ. Trong **SECURITY_SECURITY_ASSURANCE**, encryption controls phải liên kết với requirements, testing, audit, findings, remediation, retest và residual risk. **Kết luận chỉ đáng tin khi dựa trên data flow và effective configurations, negative tests, key usage/recovery evidence, scope và thời kỳ được nêu rõ**; cryptography không thay thế authorization, mục đích xử lý dữ liệu hoặc việc quản trị rủi ro liên tục.

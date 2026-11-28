# Use key: sử dụng khóa mật mã an toàn trong vòng đời key management

## 1. Vì sao giai đoạn “Use key” quyết định an toàn của cả hệ thống?

Một dịch vụ Java lưu dữ liệu thanh toán bằng **AES-256-GCM**. Khóa được sinh từ nguồn ngẫu nhiên đủ mạnh, bọc trong **KMS**, có lịch rotation và chỉ nhân viên quản trị được thay đổi chính sách. Thoạt nhìn, hệ thống đã quản lý khóa tốt. Tuy nhiên, trong code xử lý nghiệp vụ, một tài khoản dịch vụ có quyền **Decrypt mọi dữ liệu của mọi tenant**, dùng lại **nonce AES-GCM** hoặc ghi plaintext DEK vào log để debug.

Trong các trường hợp đó, thuật toán AES và khóa có thể vẫn mạnh, nhưng hệ thống đã dùng khóa **sai phạm vi, sai cách hoặc sai mục đích**. Chỉ một lỗi ở giai đoạn **Use key** cũng đủ làm mất tính bí mật, tính toàn vẹn hoặc khả năng kiểm toán của dữ liệu.

**Use key (sử dụng khóa)** là giai đoạn trong **key lifecycle** khi một khóa đã được tạo, cấp phát và đặt dưới chính sách kiểm soát được dùng để thực hiện những thao tác mật mã **được cho phép**, trong **ngữ cảnh** và **thời gian** phù hợp.

Ví dụ các thao tác sử dụng khóa:

- Dùng **DEK** (*Data Encryption Key*) để mã hóa hoặc giải mã dữ liệu bằng AES-GCM.
- Dùng **KEK** (*Key Encryption Key*) để **wrap/unwrap** một DEK thay vì mã hóa trực tiếp mọi bản ghi.
- Dùng **private signing key** để tạo chữ ký số, **public verification key** đáng tin để kiểm tra.
- Dùng **HMAC key** để tạo hoặc xác minh MAC.
- Dùng **private key thỏa thuận khóa** cùng public key đã xác thực của đối tác để tính shared secret.
- Dùng **root/IKM** với KDF chuẩn để dẫn xuất các khóa con có nhãn mục đích.
- Dùng **KMS/HSM** để thực hiện thao tác mật mã mà không cần xuất private key/KEK khi nền tảng hỗ trợ.

**Thông điệp cốt lõi:** một khóa chỉ nên được dùng **đúng thuật toán, đúng mục đích, đúng chủ thể, đúng ngữ cảnh, đúng trạng thái vòng đời** và với đủ kiểm soát trước, trong, sau thao tác.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định vị trí **Use key** trong vòng đời từ sinh khóa đến thu hồi/hủy.
2. Phân biệt **key material**, **key reference**, **key usage**, **key state**, **cryptoperiod** và **key operation**.
3. Thiết kế quyền **Encrypt/Decrypt, Sign/Verify, GenerateMac/VerifyMac, DeriveKey, Wrap/Unwrap** theo nguyên tắc *least privilege*.
4. Vận dụng **AES-GCM, nonce, AAD, authentication tag** đúng cách khi dùng DEK.
5. Hiểu cách sử dụng private signing key, HMAC key, ECDH private key và derived key mà không đánh đồng các vai trò.
6. Triển khai ví dụ Java 17 với **JCA/JCE** cho AES-GCM và chữ ký Ed25519; nhận biết phần phải thay bằng KMS/HSM trong production.
7. Phân tích các rủi ro lúc dùng khóa: sai tenant, lạm dụng KMS API, nonce reuse, key confusion, replay, log bí mật, cache khóa và dùng key đã bị thu hồi.
8. Thiết lập kiểm toán, xử lý lỗi, rotation, cryptoperiod và phương án ứng phó khi key material hoặc quyền sử dụng khóa bị lộ.

## 2. Use key nằm ở đâu trong key lifecycle?

Vòng đời khóa thường gồm những hoạt động liên hệ chặt chẽ:

~~~mermaid
flowchart LR
    A["Tạo / sinh khóa"] --> B["Đăng ký, cấp phát, bảo vệ"]
    B --> C["Kích hoạt và cấp quyền"]
    C --> D["USE KEY: thao tác mật mã được phép"]
    D --> E["Giám sát, đánh giá cryptoperiod"]
    E --> F{"Còn phù hợp?"}
    F -->|"Có"| D
    F -->|"Cần thay"| G["Rotate / rekey / chuyển trạng thái"]
    G --> H["Dùng khóa mới; xử lý dữ liệu cũ"]
    H --> I["Thu hồi, deactive, archive hoặc hủy"]
    F -->|"Không được dùng"| I
~~~

Sơ đồ là mô hình học tập, không quy định tất cả hệ thống đều có tên trạng thái giống nhau. Ví dụ, các nhà cung cấp KMS có thể dùng các trạng thái **Enabled, Disabled, PendingDeletion**; chuẩn quản lý khóa có thể phân biệt các giai đoạn phục vụ mã hóa mới, xử lý dữ liệu cũ và lưu hồ sơ.

### 2.1. “Có khóa” khác “được phép dùng khóa”

Một ứng dụng sở hữu **key ID** hoặc **public key** chưa có nghĩa nó được sử dụng mọi thao tác.

Một yêu cầu sử dụng khóa đúng thường phải thỏa:

~~~text
ALLOW USE =
    Key tồn tại và đúng thuật toán/loại khóa
    AND Key ở trạng thái cho phép thao tác
    AND Principal/workload được xác thực
    AND Principal được cấp đúng action
    AND Key được phép dùng cho purpose/environment/tenant
    AND Tài nguyên nghiệp vụ đã được phân quyền
    AND Tham số mật mã (nonce, AAD, context...) hợp lệ
    AND Quy tắc cryptoperiod/rotation được tuân thủ
~~~

**Key ID chỉ là định danh**, không phải quyền. Nếu attacker sửa trường key ID thành khóa của tenant khác mà ứng dụng vẫn dùng, lỗi nằm ở **policy chọn khóa và cấp quyền**, dù KMS thực hiện phép toán đúng.

### 2.2. Vật liệu khóa và key reference

| Khái niệm | Ý nghĩa | Điểm cần kiểm soát |
| --- | --- | --- |
| **Key material** | Byte bí mật hoặc vật liệu mật mã dùng thật sự | Giữ bí mật, bảo vệ trong bộ nhớ, tránh log và xuất khẩu ngoài ý định |
| **Key reference / key ID** | Tên/ID dùng chọn khóa trong KMS/HSM/keystore | Không tin ID do client đưa vào nếu chưa đối chiếu policy |
| **Key usage** | Loại tác vụ được phép với khóa | Encrypt không tự có quyền Decrypt; Sign không đồng nghĩa DeriveKey |
| **Key state** | Trạng thái hoạt động/thu hồi/đang xóa của khóa | Không dùng key đang Disabled hay PendingDeletion cho tác vụ mới nếu policy cấm |
| **Cryptoperiod** | Khoảng thời gian khóa được phép dùng cho loại chức năng xác định | Có thể phân biệt thời hạn bảo vệ mới với thời hạn xử lý dữ liệu cũ |
| **Key version** | Phiên bản vật liệu khóa hoặc bản định danh khi rotate | Dữ liệu cũ có thể còn cần phiên bản cũ |
| **Key policy / grant** | Quyền và điều kiện gọi thao tác khóa | Cần nguyên tắc cấp quyền tối thiểu, audit, thời hạn và môi trường |

Khái niệm **key usage** còn xuất hiện trong chứng chỉ **X.509 Key Usage/Extended Key Usage**. Trường chứng chỉ là một lớp ràng buộc theo chính sách PKI; nó **không thay thế IAM của KMS hay phân quyền nghiệp vụ**.

### 2.3. Use key là một tập thao tác, không phải một hàm duy nhất

Không có một phương thức Java tổng quát tên “useKey” phù hợp với mọi loại khóa. Tùy use case:

- **Cipher** mã hóa/giải mã.
- **Mac** tạo MAC và ứng dụng kiểm tra MAC theo quy tắc giao thức.
- **Signature** ký hoặc xác minh chữ ký.
- **KeyAgreement** thực hiện một phần thỏa thuận khóa.
- **SecretKeyFactory** hoặc **Mac** theo KDF dẫn xuất khóa.
- **KMS/HSM SDK** thực hiện các API tương ứng mà nền tảng hỗ trợ.

Một thiết kế tốt phải **chọn primitive và key usage trước khi chọn API**.

## 3. Tách các vai trò khóa trước khi sử dụng

Để quản lý an toàn, hệ thống cần biết mỗi khóa có **mục đích** gì. Không nên dùng một key chỉ vì “cũng dài 32 byte”.

| Vai trò khóa | Thao tác phù hợp | Không nên làm |
| --- | --- | --- |
| **DEK đối xứng** | Encrypt/Decrypt nội dung bằng AEAD phù hợp | Dùng chung như signing key, HMAC root hoặc KEK nếu chưa có thiết kế |
| **KEK** | Wrap/Unwrap DEK; bảo vệ khóa khác | Xuất KEK và dùng trực tiếp mã hóa mọi bản ghi một cách tùy tiện |
| **HMAC key** | GenerateMac/VerifyMac theo purpose | Công bố secret cho mọi client hoặc dùng lại như khóa AES |
| **Private signing key** | Sign thông điệp/manifest được phép | Dùng như ECDH private key hay RSA decrypt key tùy tiện |
| **Public verification key** | Verify chữ ký với identity/trust đúng | Dùng public key bất kỳ trong request rồi kết luận signer đáng tin |
| **Private agreement key** | KeyAgreement theo đúng giao thức | Dùng trực tiếp shared secret làm AES key, bỏ peer authentication |
| **Root key / KDF IKM** | Derive các khóa con theo label/context | Phát cho mọi microservice hoặc log root vào telemetry |
| **Session/traffic key** | AEAD cho một chiều/giai đoạn kết nối | Dùng lâu dài để mã hóa backup/database |
| **Password-derived key** | Sử dụng đúng phạm vi từ password KDF | Dùng raw password hoặc SHA-256(password) làm AES key |

**Nguyên tắc phân tách miền (domain separation):** khóa khác purpose, role, protocol, tenant hoặc chiều truyền nên được tạo/bảo vệ sao cho không vô tình tái sử dụng cùng một vật liệu khóa trong những hoàn cảnh có rủi ro tương tác.

Tách key theo vai trò còn giảm phạm vi ảnh hưởng khi một khóa hoặc một workload bị chiếm. Tuy nhiên, nếu tất cả các derived keys đều đến từ **cùng root bị lộ**, attacker vẫn có thể dẫn xuất các khóa con tương ứng khi biết context.

## 4. Quy trình sử dụng khóa: kiểm soát trước – trong – sau

Một tác vụ nhạy cảm như giải mã hóa đơn của tenant có thể được triển khai theo ba nhóm kiểm tra.

### 4.1. Trước khi dùng khóa

1. **Xác thực principal/workload:** ai đang gọi yêu cầu?
2. **Phân quyền nghiệp vụ:** principal có được đọc/sửa hóa đơn và tenant đang yêu cầu không?
3. **Chọn khóa đúng:** key reference đã được gắn sẵn với môi trường, tenant, purpose và phiên bản nào?
4. **Kiểm tra trạng thái:** khóa có Enabled/Active theo chính sách? Có đang bị disable hoặc yêu cầu hủy không?
5. **Kiểm tra thuật toán:** key type có phù hợp AES-GCM, RSA-PSS, Ed25519, HMAC hay wrapping không?
6. **Kiểm tra input:** dữ liệu, key ID, nonce, AAD, signature và định dạng có nằm trong giới hạn?
7. **Kiểm tra cryptoperiod:** có được tạo ciphertext/chữ ký **mới** bằng khóa này không?
8. **Giới hạn tài nguyên:** kích thước payload, số lượng tác vụ, quota và rate limit có phù hợp không?

### 4.2. Trong thao tác mật mã

- Chỉ sử dụng **primitive đúng chuẩn**, qua implementation đã được bảo trì.
- Không tắt xác thực tag hay bỏ kiểm tra chữ ký khi gặp lỗi.
- Tách rõ **Encrypt** và **Decrypt** hoặc **Sign** và **Verify** trong policy.
- Không gửi root key, private key hoặc KEK dạng rõ sang workload không cần biết.
- Quản lý nonce/IV duy nhất theo yêu cầu thuật toán.
- Ràng buộc AAD/encryption context với **ngữ cảnh đã được xác thực**.
- Không cung cấp plaintext chưa xác thực cho các bước xử lý nghiệp vụ.
- Không thực hiện thao tác **“thử mọi khóa cho đến khi mở được”** khi chưa có chính sách migration rõ.

### 4.3. Sau thao tác

- Xóa hoặc giảm thời gian tồn tại của **plaintext DEK, shared secret, MAC key hoặc derived key** khi có thể.
- Không ghi private key/DEK/plaintext vào log để debug.
- Ghi **key ID/version, principal, action, resource, kết quả và request ID** vào audit phù hợp.
- Theo dõi lỗi xác thực, lạm dụng quyền và các chỉ số bất thường.
- Không trả nội dung lỗi tiết lộ thông tin tenant khác hoặc chi tiết khóa nội bộ.
- Đánh dấu đối tượng dùng phiên bản khóa nào để hỗ trợ **rotation, migration và phục hồi**.

~~~mermaid
flowchart TD
    A["Yêu cầu dùng khóa"] --> B["Identity + business authorization"]
    B --> C{"Có quyền?"}
    C -->|"Không"| X["Từ chối và ghi sự kiện phù hợp"]
    C -->|"Có"| D["Chọn key ID/version theo policy"]
    D --> E["Kiểm tra state, usage, algorithm, context"]
    E --> F{"Được phép thao tác?"}
    F -->|"Không"| X
    F -->|"Có"| G["KMS/HSM/JCA thực hiện phép mật mã"]
    G --> H{"Xác thực thành công?"}
    H -->|"Không"| Y["Không dùng kết quả, xử lý lỗi an toàn"]
    H -->|"Có"| I["Xử lý dữ liệu đã xác thực"]
    I --> J["Audit metadata; giảm thời gian giữ secret"]
    X --> J
    Y --> J
~~~

**Không dùng kết quả giải mã để quyết định ai có quyền đọc chính dữ liệu ấy.** Quyền phải được quyết định từ principal và resource policy trước hoặc độc lập với thao tác mã hóa.

## 5. Use key cho mã hóa đối xứng: AES-GCM và DEK

### 5.1. Encrypt/Decrypt là hai quyền khác nhau

Trong **AES-GCM**, cùng một DEK bí mật dùng cho cả mã hóa và giải mã, nhưng **quyền cho phép gọi API** có thể tách:

- **Producer:** cần mã hóa thông điệp/bản ghi mới.
- **Consumer:** cần giải mã nội dung được cấp quyền.
- **Auditor:** không cần xem plaintext, chỉ cần metadata và kết quả audit.
- **Key administrator:** quản lý chính sách/rotation, không mặc định được giải mã mọi bản ghi.

Nếu cấp quyền **Decrypt mọi DEK** cho một service chỉ cần Encrypt, khi service đó bị chiếm, attacker có thể đọc dữ liệu lịch sử vượt xa nghiệp vụ.

### 5.2. AES-GCM có bốn thành phần không thể bỏ qua

~~~text
Encrypt(DEK, nonce, plaintext, AAD)
       -> ciphertext + authentication tag

Decrypt(DEK, nonce, ciphertext, tag, expectedAAD)
       -> plaintext CHỈ KHI tag hợp lệ
       -> authentication failure nếu không hợp lệ
~~~

| Thành phần | Cần làm đúng |
| --- | --- |
| **DEK** | Sinh mạnh, đúng độ dài, đúng purpose, quản lý key ID/version |
| **Nonce/IV** | Bảo đảm **không trùng dưới cùng khóa AES-GCM**, kiểm soát số lần mã hóa |
| **AAD** | Metadata không mã hóa nhưng được xác thực; cùng byte khi giải mã |
| **Authentication tag** | Kiểm tra trước khi sử dụng plaintext, không bỏ hoặc rút ngắn tùy tiện |

**Nonce trùng với cùng khóa AES-GCM** là lỗi nghiêm trọng: có thể phá cả tính bí mật lẫn toàn vẹn. Việc thêm AAD hoặc dùng DEK dài 256 bit **không khắc phục nonce reuse**.

Độ dài nonce **96 bit** thường được ưu tiên cho AES-GCM. Với nonce ngẫu nhiên, phải tính tới xác suất va chạm ở khối lượng sử dụng lớn; với nonce dạng counter, phải đảm bảo không trùng sau restart, failover, clone và chạy nhiều instance. Chọn chiến lược nonce theo mô hình vận hành, giới hạn khối lượng dữ liệu và cryptoperiod.

### 5.3. AAD ràng buộc bản mã với ngữ cảnh

Ví dụ hệ thống nhiều tenant:

~~~text
Plaintext = nội dung hóa đơn số 154
AAD       = Encode("billing/v1", "invoice", tenantId="A", recordId="154")
DEK       = DEK dành cho đúng phạm vi
~~~

Nếu server nhận yêu cầu đọc dữ liệu của **tenant B**, nó phải kiểm tra quyền và dựng **expected AAD từ ngữ cảnh đã xác thực**, không chỉ tin trường tenant ID lưu trong record có thể bị sửa. Nếu attacker chuyển **cả ciphertext, tag, nonce và metadata** mà ứng dụng dùng chính metadata đó làm AAD, một kiểu tráo bản ghi vẫn có thể qua xác thực.

Cần quy định byte encoding AAD **không nhập nhằng** như length-prefix, TLV hoặc canonical form; thứ tự trường, Unicode, phiên bản format phải thống nhất.

### 5.4. Authentication tag không chứng minh dữ liệu còn mới

Một bản ciphertext + AAD + nonce + tag hợp lệ có thể **được phát lại nguyên vẹn**. AEAD xác thực tính toàn vẹn dưới khóa, không tự chống **replay/rollback**.

Nếu giao dịch có tác động nghiệp vụ, cần **event ID, sequence, phiên bản, timestamp được kiểm tra, idempotency state hoặc secure counter** theo giao thức. Không dùng timestamp chỉ nằm trong AAD rồi coi replay đã bị chặn.

## 6. Use key cho chữ ký số: Sign và Verify

### 6.1. Private signing key phải có quyền sử dụng hẹp

Với **Ed25519, ECDSA hoặc RSA-PSS**, private signing key được dùng tạo chữ ký; public verification key phù hợp được dùng kiểm tra.

~~~text
Sign(privateSigningKey, exactMessageBytes) -> signature
Verify(trustedPublicKey, exactMessageBytes, signature) -> true/false
~~~

Việc **có private key** hoặc quyền gọi HSM/KMS **Sign** cho phép tạo chữ ký mật mã hợp lệ. Nhưng một chữ ký hợp lệ vẫn có thể chứng thực **nội dung trái phép** nếu service ký bị chiếm hoặc không kiểm tra quyền nghiệp vụ trước khi ký.

Phân tách:

1. **Quyền gọi Sign:** workload có được sử dụng signing key này không?
2. **Quyền ký nội dung:** workload có được phát hành manifest, hóa đơn hay token mang claims này không?
3. **Quyền Verify/trust:** bên nhận có tin public key theo đúng issuer/purpose không?
4. **Tính mới và trạng thái:** message có còn trong thời hạn, chưa bị replay và đúng nghiệp vụ không?

### 6.2. Verification key phải được tin cậy độc lập

Nếu client gửi cả message, signature và một public key bất kỳ, hàm Verify có thể trả **true** ngay cả khi attacker tự tạo cặp khóa và ký dữ liệu giả.

Cần dùng **trust store, X.509 PKI hoặc JWKS endpoint đã được cấu hình tin cậy**. Trường **kid** chỉ chọn khóa trong tập khóa đúng issuer; không được biến **kid/jku/x5u do token tự khai** thành nguồn cấp trust không giới hạn.

Với chứng chỉ X.509 phải kiểm tra chain, identity, validity, key usage và revocation theo chính sách. Với JWT, sau xác minh chữ ký vẫn phải kiểm tra **issuer, audience, exp/nbf, token type và authorization**.

### 6.3. Chữ ký không mã hóa dữ liệu

Chữ ký số giúp kiểm tra sự phù hợp giữa nội dung, chữ ký và khóa xác minh, nhưng **không che nội dung**. Nếu muốn bảo vệ bí mật hóa đơn, vẫn cần AES-GCM hoặc cơ chế mã hóa phù hợp.

Một sản phẩm có thể dùng:

- **Private signing key** trong HSM để ký manifest phần mềm.
- **Public verification key** tại client để kiểm tra manifest.
- **SHA-256** để đối chiếu từng artifact với manifest đã ký.
- **DEK/KEK** riêng nếu artifact chứa dữ liệu cần mã hóa.

Không dùng Ed25519 signing key như KEK hoặc private key ECDH tùy tiện.

## 7. Use key cho HMAC/MAC, KDF và key agreement

### 7.1. HMAC: GenerateMac khác VerifyMac

**HMAC-SHA256** dùng secret key để tạo tag xác thực:

~~~text
mac = HMAC-SHA256(macKey, messageBytes)
valid = ConstantTimeEqual(
    HMAC-SHA256(macKey, receivedBytes), receivedMac)
~~~

Nếu ứng dụng nắm **raw HMAC key**, về mặt mật mã nó có thể **tạo và kiểm tra** tag. Vì thế, phân biệt quyền **GenerateMac** và **VerifyMac** thực sự có ý nghĩa khi khóa được giữ bên trong **KMS/HSM** và dịch vụ cung cấp hai API có quyền riêng, không xuất key material.

Không cấp raw HMAC key cho mọi client chỉ để họ xác minh webhook: bất kỳ client nào có khóa đó cũng có thể **tạo MAC giả**. Nếu cần xác minh công khai, cân nhắc **chữ ký số**.

**Không xây MAC bằng SHA256(secret || message)** hay cấu trúc hash tự chế. Dùng HMAC chuẩn, có ràng buộc purpose, timestamp/event ID và ngữ cảnh đã được ký/MAC theo giao thức.

### 7.2. KDF: quyền dùng root secret rất nhạy cảm

Một **Key Derivation Function** như **HKDF** có thể dẫn xuất các khóa con từ input key material mạnh:

~~~text
rootSecret/IKM
    |
    +-- KDF(info="billing/v1|encrypt|tenant-A") -> DEK hoặc key material A
    +-- KDF(info="billing/v1|audit-mac|tenant-A") -> MAC key B
    +-- KDF(info="billing/v1|wrap|tenant-A") -> KEK-like key C
~~~

Các nhãn chỉ minh họa. Giao thức phải định nghĩa **salt, info, byte encoding, output length** và cách sử dụng an toàn. Không nên dùng một root chung cho mọi mục đích nếu một thao tác DeriveKey quá rộng có thể dẫn xuất mọi khóa con.

**Quyền DeriveKey có thể nguy hiểm ngay cả khi root không xuất được.** Nếu một principal có thể yêu cầu HSM dẫn xuất key cho mọi purpose/tenant, attacker chiếm principal đó có thể sử dụng key material qua API mà không cần biết root raw bytes.

Đầu vào mật khẩu yếu **không nên đưa thẳng qua HKDF nhanh** rồi coi đã chống brute-force. Với password cần loại **password-based KDF** phù hợp như Argon2id, scrypt hoặc PBKDF2 theo chính sách.

### 7.3. KeyAgreement: shared secret chưa phải khóa dùng trực tiếp

Trong thỏa thuận khóa ECDH/X25519:

1. Mỗi bên giữ private key riêng.
2. Hai bên trao đổi public key.
3. Dùng private key của mình và public key peer để tạo **shared secret**.
4. Dẫn xuất traffic keys qua **KDF/key schedule** theo giao thức.
5. Xác thực peer/transcript và dùng AEAD cho dữ liệu.

**Không có peer authentication, ECDH có thể bị MITM.** Cũng không nên lấy trực tiếp shared secret làm AES key hoặc dùng một traffic key cho hai chiều truyền không có key separation. Trong hệ thống Java, thường nên để **TLS 1.3/JSSE** thực hiện toàn bộ authenticated key establishment.

### 7.4. Key wrapping không phải key derivation

**Wrap/Unwrap** dùng KEK bảo vệ một khóa khác (thường là DEK), ví dụ:

~~~text
DEK ngẫu nhiên ──Wrap với KEK──> WrappedDEK
WrappedDEK ──Unwrap với KEK──> DEK ban đầu
~~~

**Derive** lại tạo key material từ secret và KDF parameters. Một DEK có thể được **sinh ngẫu nhiên rồi wrap** hoặc trong một số thiết kế được dẫn xuất theo policy; không được đồng nhất hai thao tác.

Khi wrap, dùng **AES-KW/AES-KWP**, AEAD hoặc API wrapping của KMS/HSM phù hợp. Với cơ chế AEAD, cần nonce/tag và AAD/context theo yêu cầu thuật toán; không tự dùng AES-ECB để “mã hóa khóa”.

## 8. Sử dụng khóa trong envelope encryption

**Envelope encryption** là một mô hình thực tế giúp tách quyền giữa ứng dụng xử lý dữ liệu và hạ tầng quản lý khóa.

### 8.1. Luồng mã hóa dữ liệu

~~~mermaid
sequenceDiagram
    participant A as Java Application
    participant K as KMS/HSM
    participant D as Data Store
    A->>A: Kiểm tra identity, tenant, quyền ghi
    A->>K: GenerateDataKey hoặc Wrap theo policy
    K-->>A: DEK dạng rõ tạm thời + wrapped DEK
    A->>A: AES-GCM Encrypt với DEK, nonce, expected AAD
    A->>D: Lưu ciphertext/tag, nonce, wrapped DEK, key ID/version
    A->>A: Giảm thời gian giữ plaintext DEK
    Note over A,K: KEK không cần xuất khỏi KMS/HSM
~~~

### 8.2. Luồng giải mã dữ liệu

~~~mermaid
sequenceDiagram
    participant A as Java Application
    participant K as KMS/HSM
    participant D as Data Store
    A->>A: Xác thực principal và quyền đọc resource
    A->>D: Lấy ciphertext/tag, nonce, wrapped DEK, version
    D-->>A: Encrypted package
    A->>K: Unwrap/Decrypt wrapped DEK theo policy/context
    K-->>A: DEK dạng rõ tạm thời nếu được phép
    A->>A: AES-GCM Decrypt với expected AAD của resource
    A->>A: Chỉ dùng plaintext nếu tag hợp lệ
    A->>A: Giảm thời gian giữ plaintext DEK
~~~

Lưu ý: nhiều dịch vụ KMS trả **plaintext data key** cho ứng dụng để tự mã hóa nội dung. Trong mô hình đó, ứng dụng vẫn phải bảo vệ DEK trong **RAM, log, heap dump, tracing và crash report**. KMS giữ KEK không xuất được **không đồng nghĩa plaintext DEK không bao giờ xuất hiện ở ứng dụng**.

### 8.3. KMS encryption context

Một số KMS có tham số **encryption context** hoặc **AAD** để ràng buộc wrapped DEK với tenant/purpose. Ví dụ khái niệm:

~~~json
{
  "service": "billing",
  "environment": "production",
  "tenant": "tenant-A",
  "purpose": "invoice-data-key"
}
~~~

- Context này **thường không bí mật**, có thể xuất hiện trong audit; không đưa password, token hoặc dữ liệu nhạy cảm vào.
- Khi unwrap, dịch vụ thường phải cung cấp context phù hợp theo yêu cầu API.
- **KMS context của wrapped DEK không tự thay thế AAD của AES-GCM trên dữ liệu** do ứng dụng mã hóa.
- Tenant ID phải lấy từ ngữ cảnh được **xác thực và phân quyền**, không tin giá trị tùy ý do caller nhập.
- Tính năng, key type và cách xử lý encryption context **phụ thuộc nhà cung cấp KMS**, không nên giả định API nào cũng giống nhau.

### 8.4. Khi nào chọn envelope encryption?

Phù hợp khi:

- Dữ liệu được lưu lâu dài hoặc nhiều bản ghi có vòng đời độc lập.
- Cần giới hạn quyền KMS theo service/tenant.
- Muốn rotation **KEK khác DEK**.
- Có nhu cầu backup/restore và audit thao tác unwrap.
- Muốn giảm phạm vi lộ khóa bằng cách dùng DEK riêng theo đối tượng/nhóm dữ liệu.

Không nên dùng **một root secret hard-code** trong mọi ứng dụng để tự dẫn xuất mọi DEK nếu KMS có thể hỗ trợ ranh giới an toàn rõ hơn.

## 9. Ví dụ Java 17: sử dụng đúng DEK và signing key

Ví dụ dưới đây có hai thao tác khác vai trò:

1. Dùng **AES-256-GCM** với DEK demo để mã hóa và giải mã một hóa đơn theo tenant/record AAD.
2. Dùng **Ed25519** với private signing key demo để ký một thông điệp, và public verification key tương ứng để Verify.

**Giới hạn:** chương trình tạo khóa trực tiếp trong JVM cho dễ chạy. Với production, DEK nên đến từ quy trình bảo vệ khóa (thường là **KMS/envelope encryption**) và private signing key nên được bảo vệ qua **KMS/HSM/keystore** với quyền Sign phù hợp. Ví dụ **không** tạo policy IAM thật, không xác thực người dùng hay thực hiện audit từ dịch vụ bên ngoài.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class UseKeyDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;  // 96 bits
    private static final int TAG_BITS = 128;
    private static final int AAD_VERSION = 1;

    // Demo: record chứa byte[] có thể thay đổi.
    // Production cần defensive copies và serialization an toàn.
    public record EncryptedRecord(
            int aadVersion,
            byte[] nonce,
            byte[] ciphertextAndTag) {}

    private static byte[] aad(String tenant, String invoice)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(AAD_VERSION);
            writeString(out, "billing/invoice-content");
            writeString(out, tenant);
            writeString(out, invoice);
        }
        return bytes.toByteArray();
    }

    private static void writeString(DataOutputStream out, String text)
            throws IOException {
        byte[] value = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(value.length);  // Length-prefix theo byte.
        out.write(value);
    }

    public static EncryptedRecord encrypt(
            SecretKey dek,
            byte[] plaintext,
            String authorizedTenant,
            String authorizedInvoice) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, dek,
            new GCMParameterSpec(TAG_BITS, nonce));

        // Phải cấp AAD trước khi xử lý dữ liệu.
        cipher.updateAAD(aad(authorizedTenant, authorizedInvoice));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return new EncryptedRecord(
            AAD_VERSION, nonce, ciphertextAndTag);
    }

    public static byte[] decrypt(
            SecretKey dek,
            EncryptedRecord stored,
            String authorizedTenant,
            String authorizedInvoice) throws Exception {

        if (stored.aadVersion() != AAD_VERSION ||
                stored.nonce().length != NONCE_BYTES) {
            throw new IllegalArgumentException("Invalid metadata");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, dek,
            new GCMParameterSpec(TAG_BITS, stored.nonce()));

        // Không lấy tenant chỉ từ metadata có thể bị sửa.
        cipher.updateAAD(aad(authorizedTenant, authorizedInvoice));

        // Trả plaintext CHỈ KHI authentication tag hợp lệ.
        return cipher.doFinal(stored.ciphertextAndTag());
    }

    public static byte[] sign(
            java.security.PrivateKey signingKey,
            byte[] exactMessage) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(signingKey);
        signer.update(exactMessage);
        return signer.sign();
    }

    public static boolean verify(
            java.security.PublicKey trustedVerificationKey,
            byte[] exactMessage,
            byte[] signatureBytes) throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedVerificationKey);
        verifier.update(exactMessage);
        return verifier.verify(signatureBytes);
    }

    public static void main(String[] args) throws Exception {
        // Chỉ cho demo. Production: DEK được bảo vệ bằng KMS.
        KeyGenerator aes = KeyGenerator.getInstance("AES");
        aes.init(256);
        SecretKey dek = aes.generateKey();

        byte[] invoice = "invoice=154;amount=250000"
            .getBytes(StandardCharsets.UTF_8);

        EncryptedRecord stored = encrypt(
            dek, invoice, "tenant-A", "invoice-154");

        byte[] restored = decrypt(
            dek, stored, "tenant-A", "invoice-154");

        System.out.println("Authorized context decrypts: " +
            Arrays.equals(invoice, restored));

        try {
            decrypt(dek, stored, "tenant-B", "invoice-154");
            throw new AssertionError("Expected AEAD tag failure");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong tenant rejected: true");
        }

        // Một cặp Ed25519 riêng, không dùng DEK như signing key.
        KeyPairGenerator ed25519 =
            KeyPairGenerator.getInstance("Ed25519");
        KeyPair publisher = ed25519.generateKeyPair();

        byte[] manifest = "release=billing-v1;sha256=example"
            .getBytes(StandardCharsets.UTF_8);

        byte[] signature = sign(publisher.getPrivate(), manifest);
        System.out.println("Valid signature: " +
            verify(publisher.getPublic(), manifest, signature));

        byte[] altered = "release=billing-v2;sha256=example"
            .getBytes(StandardCharsets.UTF_8);
        System.out.println("Modified manifest verifies: " +
            verify(publisher.getPublic(), altered, signature));
    }
}
~~~

Kết quả dự kiến:

~~~text
Authorized context decrypts: true
Wrong tenant rejected: true
Valid signature: true
Modified manifest verifies: false
~~~

### 9.1. Những nguyên tắc thể hiện trong code

1. **Key role separation:** DEK chỉ dùng AES-GCM; Ed25519 private/public key dùng riêng cho Sign/Verify.
2. **Khóa AES đủ mạnh:** demo sinh bằng KeyGenerator + nguồn provider phù hợp thay vì lấy raw password.
3. **Nonce:** 12 byte sinh mới cho mỗi phép mã hóa trong ví dụ. Random nonce **không bảo đảm tuyệt đối duy nhất**; production cần giới hạn khối lượng và chiến lược không lặp với cùng DEK.
4. **AAD:** encode theo thứ tự và length-prefix để tránh nhập nhằng tenant/record.
5. **Không tin metadata record để cấp quyền:** tenant/invoice đi vào hàm phải lấy từ **quyền đã được kiểm tra** ở tầng nghiệp vụ.
6. **Tag check:** doFinal của AES-GCM kiểm tra xác thực; không sử dụng plaintext khi giải mã thất bại.
7. **Signature API:** JCA Signature kiểm tra message bytes theo lược đồ Ed25519, không tự ghép hash/chữ ký.
8. **Public key trust:** ví dụ dùng public key của cùng cặp demo; production phải tải verification key từ **nguồn đã xác thực** (PKI/trust store/JWKS policy).
9. **Cipher instance:** tạo mới cho từng thao tác; không dùng chung đối tượng Cipher cho nhiều thread/requests theo cách không an toàn.
10. **Không in raw keys:** output chỉ gồm boolean để xác nhận hành vi.

### 9.2. Những điều demo chưa làm

- Không có **KMS GenerateDataKey**, wrapped DEK, KMS encryption context hoặc lựa chọn key ID/version.
- Không có xác thực **principal**, IAM, RBAC/ABAC, kiểm tra quyền với hóa đơn thực.
- Không có quota/rate limit, idempotency, chống rollback hoặc vòng đời cryptoperiod.
- Không ghi audit của thao tác KMS/HSM hay quản lý key policy.
- Không cung cấp định dạng lưu trữ bền vững hoặc immutable record API.
- Không làm giả kết nối TLS hay xác thực peer; bài toán truyền tin cần TLS riêng.
- Không bảo đảm **xóa hoàn toàn secret trong JVM**: SecretKey/provider có thể giữ vật liệu khóa trong các bản sao không truy cập được.

**Đoạn mã minh họa primitive đúng cách, không phải dịch vụ quản lý khóa production hoàn chỉnh.** Không triển khai nguyên xi nếu chưa thiết kế quyền, quản lý nonce, lưu trữ và key lifecycle.

## 10. Quản lý khóa ngay trong thời gian đang được sử dụng

### 10.1. Cryptoperiod và key state

Một khóa thường có **cryptoperiod**: thời hạn được phép dùng cho những tác vụ cụ thể. Cần phân biệt:

- **Dùng để bảo vệ dữ liệu mới:** Encrypt, Sign, GenerateMac hoặc Wrap mới.
- **Dùng để xử lý dữ liệu cũ:** Decrypt, Verify hoặc Unwrap cũ khi policy còn cho phép.
- **Bị vô hiệu hóa/thu hồi:** không được sử dụng cho phạm vi đã bị chặn.
- **Đang chờ hủy hoặc đã hủy:** có thể không còn đường khôi phục dữ liệu phụ thuộc.

Một số thiết kế có trạng thái **decrypt-only** hoặc **verify-only** cho khóa cũ sau rotation; một số dịch vụ KMS chỉ có trạng thái Enabled/Disabled áp dụng rộng hơn. Không giả định nhà cung cấp nào cũng hỗ trợ cấp quyền theo state giống nhau.

Ví dụ bảng policy khái niệm:

| Trạng thái ứng dụng | Encrypt/Sign mới | Decrypt/Verify cũ | Ghi chú |
| --- | --- | --- | --- |
| **ACTIVE** | Có theo quyền | Có theo quyền | Trong cryptoperiod cho phép |
| **LEGACY_READ_ONLY** | Không | Có giới hạn nếu policy cho phép | Dùng khi chuyển đổi và phục hồi dữ liệu cũ |
| **SUSPENDED** | Không | Theo quyết định ứng phó, thường không | Chờ điều tra hoặc khôi phục |
| **REVOKED** | Không | Không cho use case bị thu hồi | Cần đánh giá dữ liệu/phụ thuộc |
| **DESTROYED** | Không | Không | Dữ liệu cũ có thể mất khả năng truy cập |

Đây là **trạng thái ở tầng policy của hệ thống**, không phải tên trạng thái chuẩn bắt buộc của mọi KMS/HSM.

### 10.2. Rotation không tự chuyển mọi bản mã sang khóa mới

Khi quay vòng KEK/DEK:

~~~text
Trước rotation:
  plaintext --DEK-v1--> ciphertext-v1
  DEK-v1 --KEK-v1--> wrappedDEK-v1

Sau một kiểu rewrap:
  ciphertext-v1 vẫn giữ nguyên
  cùng DEK-v1 --KEK-v2--> wrappedDEK-v2

Sau re-encrypt:
  plaintext --DEK-v2 + nonce mới--> ciphertext-v2
  DEK-v2 --KEK được phép--> wrappedDEK-v2
~~~

- **Rewrap DEK** thay lớp bọc, không nhất thiết thay ciphertext dữ liệu.
- **Re-encrypt** bằng DEK mới cần đọc dữ liệu cũ, tạo bản mã/tag/nonce mới và cập nhật metadata.
- **Rotate KEK** không tự thay session keys trong TLS.
- **Rotate signing key** không tự làm tất cả các chữ ký lịch sử không hợp lệ; chính sách Verify theo thời điểm và trust evidence phải được xác định.
- Nếu **khóa cũ bị lộ**, rewrap cùng DEK có thể **không đủ**, vì attacker có thể đã lấy DEK hoặc bản bọc cũ.

### 10.3. Việc xóa khóa có thể làm mất dữ liệu

Trước khi disable/destroy KEK, DEK hoặc root:

1. Kiểm kê bản mã nào và backup nào còn phụ thuộc khóa.
2. Kiểm tra key version, wrapped DEK và metadata có đầy đủ.
3. Thử giải mã/restore trong điều kiện kiểm soát.
4. Hoàn tất migration/re-encrypt/rewrap theo kế hoạch.
5. Xem xét retention, yêu cầu pháp lý và dữ liệu đã được công bố.
6. Áp dụng quy trình phê duyệt, giãn thời gian xóa và audit.

Không được hủy KEK cũ chỉ vì **mọi bản ghi đang tạo mới** đã dùng KEK mới; backup và bản ghi cũ vẫn có thể cần KEK cũ.

### 10.4. Key caching: hiệu năng và blast radius

Đọc/unwrap DEK qua KMS có thể tăng độ trễ, nên nhiều hệ thống cache **plaintext DEK** trong memory. Nhưng cache làm kéo dài thời gian tồn tại secret và tăng số dữ liệu có thể bị lộ khi tiến trình bị chiếm.

Cần đánh giá:

- TTL và hạn mức số lần Encrypt/Decrypt dùng một DEK.
- Phạm vi cache theo tenant, data classification, service, process.
- Cách xóa cache khi revoke/disable key hoặc phát hiện sự cố.
- Hạn chế export qua dump/trace/metrics.
- Quản lý nonce khi nhiều worker dùng cùng DEK.
- Giới hạn cấp quyền, quota và theo dõi cache hit/miss **mà không log raw DEK**.

**Cache lâu để giảm chi phí KMS không phải quyết định hiệu năng thuần túy**; nó thay đổi mô hình đe dọa và vòng đời sử dụng khóa.

## 11. Phân quyền khóa: IAM, RBAC/ABAC và separation of duties

### 11.1. Ví dụ ma trận quyền

| Principal/role | Encrypt/GenerateDataKey | Decrypt/Unwrap | Sign | Verify | Quản trị chính sách |
| --- | --- | --- | --- | --- | --- |
| **billing-writer** | Đúng DEK/tenant được phép | Không mặc định | Không | Có thể Verify public key khi cần | Không |
| **billing-reader** | Không mặc định | Chỉ bản ghi đã phân quyền | Không | Có thể | Không |
| **release-signer** | Không | Không | Chỉ signing key release, sau approval | Có thể | Không |
| **release-verifier** | Không | Không | Không | Public key được tin cậy | Không |
| **key-admin** | Không mặc định | Không mặc định | Không mặc định | Không mặc định | Theo quy trình duyệt |
| **security-auditor** | Không | Không | Không | Chỉ metadata/Verify nếu cần | Read-only audit |

Ma trận là mẫu thiết kế. Tên action của IAM khác nhau theo API của từng KMS/HSM. **Không dùng tên action tưởng tượng làm chính sách production**; hãy ánh xạ sang quyền thực tế của provider.

### 11.2. Hai lớp phân quyền không thể thay thế nhau

**Lớp KMS/HSM:** workload nào được gọi thao tác trên key ID nào.

**Lớp nghiệp vụ:** principal đó có được đọc/mã hóa/ký nội dung của tenant hoặc bản ghi cụ thể không.

Một workload có thể được KMS cấp quyền Decrypt một KEK hợp lệ, nhưng ứng dụng vẫn phải từ chối đọc hóa đơn của tenant khác. KMS không phải lúc nào cũng biết toàn bộ quy tắc ownership của hóa đơn trong database.

### 11.3. Key usage phải gắn với purpose

Ví dụ một signing key được phép ký **release manifest**, không nên được dùng ký **access token** chỉ vì cả hai đều dùng Ed25519. Nếu KMS/HSM API không thể biểu diễn toàn bộ purpose theo cách native, hệ thống phải kiểm soát bằng:

- Khóa độc lập cho mỗi purpose quan trọng.
- Workload identity được cấp quyền tối thiểu.
- API ký bao bọc với kiểm tra schema, namespace, issuer và approval.
- Chính sách audit và phát hiện sai mục đích.
- Không chia sẻ quyền Sign chỉ vì key được gắn nhãn “production”.

### 11.4. Phạm vi multi-tenant

Một thiết kế có thể dùng key riêng cho từng tenant, dùng KEK chung nhưng DEK riêng, hoặc dùng derived key tách theo tenant. Các phương án có phạm vi lộ khác nhau:

- **Key per tenant:** có ranh giới vật liệu rõ hơn, chi phí quản trị cao hơn.
- **DEK per record/object:** giới hạn dữ liệu chịu ảnh hưởng khi một DEK bị lộ.
- **KEK chung nhiều DEK:** thuận tiện nhưng quyền unwrap cần giới hạn chặt.
- **Derived keys từ root chung:** giảm số key phải lưu nhưng nếu root bị lộ có thể ảnh hưởng nhiều tenant.

Không có lựa chọn duy nhất tốt cho mọi hệ thống. Cần đánh giá **blast radius, hiệu năng, chính sách quyền, audit, rotation và khả năng khôi phục**.

## 12. Những sai lầm nguy hiểm trong giai đoạn Use key

| Sai lầm | Hậu quả | Phòng tránh |
| --- | --- | --- |
| **Dùng raw password làm AES key** | Khóa dễ đoán, brute-force ngoại tuyến | Password-based KDF hoặc DEK ngẫu nhiên |
| **Dùng một khóa cho nhiều purpose** | Lẫn phạm vi và tăng blast radius | Key separation, domain separation |
| **Nonce trùng dưới cùng AES-GCM key** | Có thể phá bí mật/toàn vẹn | Nonce strategy và giới hạn số lần dùng key |
| **Bỏ xác thực tag khi Decrypt lỗi** | Chấp nhận plaintext không đáng tin | AEAD và fail-closed |
| **AAD chỉ lấy từ record có thể bị sửa** | Không ngăn di chuyển nguyên bản mã sang sai ngữ cảnh | Expected AAD từ principal/resource đã phân quyền |
| **Tin key ID do client chỉ định** | Lựa chọn khóa tenant/môi trường sai | Allowlist và mapping key theo identity/purpose |
| **Giả định Sign đúng nghĩa là nội dung hợp lệ** | Signing service ký nội dung trái phép | Kiểm tra approval/schema/authorization trước Sign |
| **Tin public verification key bất kỳ** | Attacker tự ký rồi tự cấp khóa Verify | PKI/JWKS/trust store đúng issuer |
| **Không chống replay** | Xử lý lại thông điệp/transaction hợp lệ | Timestamp/event ID/idempotency/sequence |
| **Cho GenerateMac và VerifyMac cùng quyền rộng** | Workload verify có thể tạo MAC giả khi có raw key | HSM tách quyền, key scope và API bảo vệ |
| **KMS Decrypt mọi tenant** | Một tài khoản bị chiếm đọc lượng dữ liệu rất lớn | IAM least privilege + business authorization |
| **Cache plaintext DEK vô hạn** | Tăng blast radius và retention của secret | TTL, hạn mức, xóa cache, audit |
| **Log raw key/PRK/DEK/secret** | Bí mật bị sao chép sang log và backup | Redaction, secure observability |
| **Dùng key đã deactivated cho Encrypt mới** | Vi phạm cryptoperiod/chính sách | Key state checks và key selection theo version |
| **Hủy key cũ trước migration** | Mất khả năng mở dữ liệu và backup | Inventory, dependency check, restore rehearsal |
| **Tin TLS thay quyền nghiệp vụ** | Kết nối xác thực nhưng truy cập sai tenant | IAM/authorization ở tầng ứng dụng |
| **Tự thiết kế key exchange** | MITM, downgrade, nhầm role và nonce | TLS 1.3/giao thức AKE đã được phân tích |

### 12.1. “Crypto thành công” không đồng nghĩa nghiệp vụ thành công

AES-GCM có thể giải mã thành công một hóa đơn hoàn toàn hợp lệ của **tenant A**. Nếu request đến từ người dùng **tenant B**, kết quả mật mã vẫn có thể là plaintext đúng **dưới cùng DEK và AAD phù hợp**. Trách nhiệm từ chối nằm ở **chính sách phân quyền**.

Tương tự, chữ ký Ed25519 có thể Verify thành công nhưng thông điệp yêu cầu **thanh toán lại một giao dịch đã xử lý**. Phải kiểm tra anti-replay/idempotency.

### 12.2. Lỗi xác thực không nên làm lộ dữ liệu

Khi nhận **AEADBadTagException**, key ID không tồn tại, chữ ký không hợp lệ hoặc KMS AccessDenied:

- Không thử **bỏ tag/AAD** hay chọn khóa khác ngoài policy để “cứu” yêu cầu.
- Không ghi ra response các secret, plaintext một phần hoặc nội dung request nhạy cảm.
- Không trả thông tin giúp người gọi không có quyền phân biệt dữ liệu của tenant khác.
- Ghi lỗi đã chuẩn hóa, correlation/request ID và thông tin audit phù hợp.
- Nếu tỷ lệ lỗi tăng bất thường, điều tra **migration/schema/config** và dấu hiệu tấn công.

Không phải mọi tag failure là tấn công; có thể do AAD serialization đổi, dùng sai key version, dữ liệu bị hỏng hoặc khác nonce. Nhưng **mọi tag failure đều phải fail closed** đối với plaintext.

## 13. Audit và observability khi sử dụng khóa

### 13.1. Ghi gì vào audit log?

| Thông tin | Có thể ghi? | Lưu ý |
| --- | --- | --- |
| **Timestamp, request/correlation ID** | Có | Hỗ trợ điều tra sự kiện |
| **Principal/workload identity** | Có | Theo chính sách bảo vệ dữ liệu |
| **Key ID/version** | Thường có | Không phải raw key material |
| **Action** (Encrypt, Decrypt, Sign, Unwrap...) | Có | Kèm kết quả/cause |
| **Algorithm, policy version, environment** | Có | Theo mức nhạy cảm |
| **Tenant/resource ID** | Có điều kiện | Có thể là dữ liệu nhạy cảm; áp dụng masking/minimization |
| **KMS encryption context** | Chỉ khi an toàn theo chính sách | Một số context xuất hiện trong cloud audit |
| **Plaintext/DEK/KEK/private key/secret/pepper** | **Không** | Log bí mật phá ranh giới bảo vệ |
| **Access token/password/full signed payload nhạy cảm** | **Không** | Hạn chế lộ thông tin cá nhân và credential |

Audit cần bảo vệ **quyền xem, quyền sửa/xóa, tính toàn vẹn, retention và khả năng truy xuất**. Nếu attacker có thể dùng key rồi sửa/xóa log cùng tài khoản, hệ thống khó chứng minh điều gì đã xảy ra.

### 13.2. Chỉ số đáng theo dõi

- Số lần **Decrypt/Unwrap** theo principal, key ID, tenant và thời gian.
- Tỷ lệ **AccessDenied** hoặc authentication tag failure tăng.
- Số lần **Sign/GenerateMac** bất thường theo workload/purpose.
- Lượng dữ liệu Encrypt dưới một DEK tiến sát giới hạn cryptoperiod/nonce policy.
- Các yêu cầu chọn key ID không tồn tại, key sai state hoặc sai môi trường.
- Thay IAM grants, key policy, trạng thái Enabled/Disabled, lịch rotation và key deletion.
- Những hệ thống còn dùng phiên bản cũ ngoài cửa sổ migration cho phép.
- Kết quả backup/restore test đối với dữ liệu mã hóa.

**Metrics không thay thế authorization**. Phát hiện lạm dụng sau khi xảy ra là lớp bổ sung; trước mỗi thao tác vẫn cần kiểm tra quyền phù hợp.

### 13.3. Key use có thể tạo side-channel hoặc rò qua thao tác phụ

Các hệ thống mật mã nên dùng provider/library phù hợp, tránh tự viết phép so sánh secret bằng vòng lặp dễ tiết lộ timing. Khi so sánh MAC, ưu tiên API như **MessageDigest.isEqual** cho mảng byte có kích thước đã kiểm tra, hoặc chức năng verify được chuẩn hóa.

Đừng trả thông báo lỗi quá chi tiết làm lộ: key version nào dùng được, ciphertext thuộc tenant nào hoặc định danh user có tồn tại hay không. Cũng đừng cho phép caller kiểm tra một số lượng lớn key IDs ngoài phạm vi được cấp quyền để thực hiện **key enumeration**.

## 14. Quản lý khóa khi có sự cố

Một sự cố Use key không nhất thiết xuất phát từ **lộ key material**. Có thể là **lộ quyền sử dụng khóa**, lỗi cấu hình IAM hoặc một đường API nghiệp vụ cấp phép sai.

### 14.1. Phân loại sự cố để chọn hành động

| Sự cố | Rủi ro chính | Hành động cần cân nhắc |
| --- | --- | --- |
| **DEK rõ bị lộ** | Bản mã thuộc DEK có thể bị giải | Thu hồi quyền, thay DEK và re-encrypt dữ liệu liên quan |
| **KEK bị lộ** | Wrapped DEK có thể bị mở | Điều tra wrapped DEKs, thay KEK, đánh giá cần thay DEK |
| **KMS Decrypt grant bị lạm dụng** | Attacker có thể lấy DEK/giải plaintext qua API | Thu hồi principal/grant, audit usage, đánh giá dữ liệu đã đọc |
| **Signing private key bị lộ** | Kẻ tấn công có thể tạo chữ ký giả | Revoke/rotate signing key, cập nhật verifier/trust |
| **Workload Sign bị chiếm nhưng key non-exportable** | Chữ ký giả vẫn có thể được tạo qua HSM | Disable quyền Sign, điều tra signed artifacts/messages |
| **HMAC key bị lộ** | Có thể tạo MAC giả | Rotation, phân tích replay và thông điệp đã chấp nhận |
| **ECDH/session secret bị lộ** | Traffic phiên bị ảnh hưởng | Kết thúc phiên, rekey và đánh giá phạm vi |
| **Root/IKM dẫn xuất bị lộ** | Nhiều derived keys có thể tái tạo | Xác định toàn bộ khóa con, thay root và migration |
| **Nonce AES-GCM bị tái sử dụng** | Có thể mất bí mật/toàn vẹn dữ liệu | Ngừng Encrypt dưới key ảnh hưởng, điều tra và thay key |
| **Hủy key quá sớm** | Mất khả năng phục hồi dữ liệu | Quy trình khôi phục nếu còn bản sao/backup hợp lệ; hậu kiểm |

### 14.2. Quy trình ứng phó tối thiểu

1. **Dừng hành vi đang gây nguy cơ:** vô hiệu hóa principal/grant, dừng tác vụ mã hóa sai hoặc đóng endpoint liên quan.
2. **Xác định loại khóa:** DEK, KEK, signing key, HMAC, static agreement, session hay root.
3. **Xác định phạm vi:** những tenant, record, phiên, backup, wrapped DEK, workload nào chịu ảnh hưởng.
4. **Thu thập audit** về key use, thay policy và request liên quan; bảo vệ bằng chứng.
5. **Thu hồi hoặc hạn chế quyền** khi có thể, không phụ thuộc duy nhất vào việc xóa key.
6. **Tạo key/credential mới**, cập nhật trust và key selection.
7. **Rewrap/re-encrypt/re-sign** nếu cần theo mức độ bí mật đã mất và yêu cầu nghiệp vụ.
8. **Kiểm thử phục hồi** và giám sát dữ liệu/callers dùng phiên bản cũ.
9. **Phân tích nguyên nhân gốc**: code, IAM, KMS grants, nonce strategy, logging, key cache hoặc human process.

**Không tự khẳng định rotation đã làm bí mật trở lại dữ liệu cũ**. Nếu attacker đã sao chép plaintext hoặc DEK và ciphertext cũ, một lớp bọc mới không làm biến mất bản sao của họ.

### 14.3. Trường hợp KMS/HSM không xuất khóa

Một KEK hoặc private signing key **non-exportable** vẫn có thể bị **lạm dụng qua API** nếu caller có quyền thao tác không đúng. Vì thế báo cáo sự cố nên phân biệt:

- **Key material compromise:** attacker có byte của secret.
- **Key usage compromise:** attacker có khả năng gọi Encrypt/Decrypt/Sign/Unwrap/Derive.
- **Policy compromise:** attacker sửa chính sách, grant hoặc trust anchor.
- **Data compromise:** attacker đọc plaintext hoặc thao tác sai dữ liệu, kể cả khi chưa lấy raw key.

Mỗi loại đòi hỏi phương án riêng; chỉ kiểm tra “có xuất raw key không?” là chưa đủ.

## 15. Tình huống thực tế: PaymentService sử dụng DEK/KEK và signing key

### 15.1. Yêu cầu

Một **PaymentService** xử lý nhiều tenant, lưu hóa đơn mã hóa, gửi webhook ký số và giao tiếp HTTPS với đối tác. Hệ thống cần:

- Giữ bí mật nội dung hóa đơn.
- Ngăn tráo hóa đơn giữa tenant.
- Cho phép chỉ định workload nào có quyền đọc/ghi.
- Bảo vệ private signing key để đối tác xác minh webhook.
- Hỗ trợ rotation, backup, audit và xử lý sự cố.
- Giảm ảnh hưởng khi một service account bị chiếm.

### 15.2. Thiết kế theo lớp

~~~mermaid
flowchart TD
    C["Client qua TLS 1.3"] --> API["PaymentService API"]
    API --> AUTH["Identity + tenant authorization"]
    AUTH --> WRITE["Invoice writer"]
    AUTH --> READ["Invoice reader"]
    WRITE -->|"GenerateDataKey / Wrap"| KMS["KMS/HSM: KEK và policy"]
    READ -->|"Unwrap theo quyền"| KMS
    WRITE --> ENC["AES-GCM với DEK, nonce, AAD"]
    ENC --> DB["Database: ciphertext + wrapped DEK + version"]
    DB --> READ
    READ --> DEC["AES-GCM Decrypt + tag check"]
    AUTH --> HOOK["Webhook publisher"]
    HOOK -->|"Sign theo purpose"| SIGN["Private signing key trong KMS/HSM"]
    SIGN --> OUT["Webhook + signature + key ID"]
    OUT --> VERIFY["Đối tác Verify bằng public key đã xác thực"]
    KMS --> AUDIT["Audit key use và policy changes"]
    SIGN --> AUDIT
    AUTH --> AUDIT
~~~

### 15.3. Luồng ghi hóa đơn

1. Request được xác thực và kiểm tra **quyền ghi tenant A**.
2. Service chọn **key reference** theo môi trường/purpose/tenant được cấu hình; không tin key ID tùy ý từ request.
3. KMS cấp DEK ngẫu nhiên và wrapped DEK theo policy, hoặc thực hiện cơ chế tương đương.
4. Service tạo nonce AES-GCM đúng chiến lược và **AAD từ tenant A + invoice ID**.
5. Service Encrypt, lưu ciphertext/tag, nonce, wrapped DEK, version, metadata.
6. Không giữ DEK raw trong cache lâu hơn chính sách, không log DEK hoặc plaintext.
7. Ghi audit kết quả key use và request, không lộ secret.

### 15.4. Luồng đọc hóa đơn

1. Xác thực người đọc và kiểm tra quyền đối với **invoice ID** của tenant A.
2. Lấy record và xác định **key version** theo metadata đã được kiểm soát.
3. Gọi KMS Unwrap/Decrypt wrapped DEK bằng **principal có quyền đọc** và context phù hợp.
4. Decrypt AEAD bằng **expected AAD từ ngữ cảnh được phân quyền**.
5. Chỉ sử dụng plaintext khi tag hợp lệ; thất bại thì fail closed.
6. Ghi audit và giảm thời gian tồn tại DEK.

### 15.5. Luồng gửi webhook ký số

1. Service xác minh sự kiện đã được phê duyệt và payload có định dạng chuẩn.
2. Dùng **private signing key** đúng purpose, có key ID/version và quyền Sign hẹp.
3. Ký exact bytes theo giao thức, gửi chữ ký cùng metadata định danh khóa.
4. Đối tác dùng public key từ **trusted JWKS/trust store/certificate** để Verify.
5. Đối tác kiểm tra **issuer, event ID, timestamp, replay, tenant và quyền nghiệp vụ** riêng.

**Đánh đổi:** nếu một principal có cả quyền Unwrap mọi DEK và Sign mọi webhook, một lỗi ở service có thể ảnh hưởng cả bí mật dữ liệu lẫn tính xác thực thông điệp. Tách principal/key usage giúp giảm blast radius.

## 16. Checklist Use key an toàn

Trước khi đưa một thao tác khóa vào production, hãy kiểm tra:

1. **Role:** đây là DEK, KEK, MAC key, signing key, agreement key, root/derived key hay session key?
2. **Purpose:** key có được phép dùng cho thuật toán, nghiệp vụ và môi trường này không?
3. **Principal:** caller đã được xác thực bằng danh tính workload/user phù hợp chưa?
4. **Business authorization:** caller có quyền với tenant/record/transaction cụ thể không?
5. **Key selection:** key ID/version có được chọn từ registry/config đáng tin, không lấy bừa từ client?
6. **State:** key có Enabled/Active cho loại thao tác hiện tại không?
7. **Cryptoperiod:** có đang tạo ciphertext/chữ ký mới bằng key đã hết giai đoạn bảo vệ mới không?
8. **Least privilege:** Encrypt/Decrypt, Sign/Verify, GenerateMac/VerifyMac, Wrap/Unwrap có được tách quyền phù hợp?
9. **Non-exportable:** key có cần xuất raw material không; có thể thực hiện qua KMS/HSM API không?
10. **DEK handling:** plaintext DEK có thời gian tồn tại ngắn và không vào log/dump không?
11. **AEAD:** AES-GCM/AEAD có đúng chế độ, tag length và fail-closed không?
12. **Nonce:** nonce/IV có bảo đảm không trùng dưới cùng key khi nhiều instance/restart không?
13. **AAD/context:** có ràng buộc tenant, purpose, record và dựng byte theo schema xác định không?
14. **Replay:** ứng dụng có kiểm tra freshness, event ID hoặc sequence khi cần không?
15. **Signature:** signing key được dùng theo approved payload; verifier lấy public key từ trust đúng issuer?
16. **KDF:** derived key có domain separation; raw password có được xử lý bằng password-based KDF nếu cần?
17. **Agreement:** peer identity và transcript được xác thực, không dùng shared secret thô làm AES key?
18. **Wrapping:** KEK dùng đúng wrap API; không tự dùng ECB hay thuật toán không có integrity?
19. **Audit:** key use, policy/grant change, trạng thái và lỗi được ghi mà không lộ bí mật?
20. **Caching:** có TTL, giới hạn số lần dùng key và cơ chế xóa khi revoke/incident?
21. **Rotation:** dữ liệu cũ có biết key version, có policy decrypt-only/verify-only và kế hoạch migration?
22. **Recovery:** backup còn đủ KEK/DEK/wrapped DEK/context để restore; không hủy khóa quá sớm?
23. **Incident:** có phân biệt lộ raw key, lộ quyền dùng API và lộ dữ liệu không?
24. **Testing:** có test sai tenant/AAD, tag bị sửa, signer sai, state sai, permission denied, nonce strategy và key rotation?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Một dịch vụ được cấp quyền KMS Encrypt có tự cần quyền KMS Decrypt không?

**Đáp án:** Không mặc định. Quyền nên theo nghiệp vụ. Service chỉ tạo dữ liệu mã hóa có thể không cần đọc lại mọi dữ liệu; cấp Decrypt rộng làm tăng phạm vi thiệt hại khi workload bị chiếm.

**Câu 2.** KMS giữ KEK non-exportable, nhưng ứng dụng lấy plaintext DEK rồi log vào hệ thống quan sát. Có an toàn không?

**Đáp án:** Không. KMS giữ KEK không xuất được không che chở DEK đã được trả về ứng dụng. Bất kỳ ai truy cập log có thể lấy DEK và giải ciphertext tương ứng.

**Câu 3.** Vì sao cùng một AES-GCM key không được dùng lặp nonce?

**Đáp án:** Nonce reuse dưới cùng key có thể phá tính bí mật và toàn vẹn của GCM. Khóa 256 bit, AAD đầy đủ hay KMS tốt không khắc phục lỗi này.

**Câu 4.** Nếu một record tự khai tenant A và ứng dụng dựng AAD từ chính trường đó, AAD có chắc ngăn tráo nguyên record sang tenant B không?

**Đáp án:** Chưa chắc. Attacker có thể chuyển nguyên ciphertext, tag, nonce và metadata. Bên giải mã phải dựng/đối chiếu expected AAD từ **tenant và resource đã được phân quyền**, không chỉ từ record có thể sửa.

**Câu 5.** Chữ ký Ed25519 Verify thành công với một public key do request đính kèm. Đã xác thực nhà phát hành chưa?

**Đáp án:** Chưa. Public key phải được ràng buộc với danh tính, purpose và trust policy. Kẻ tấn công có thể tự tạo cặp key và ký message giả.

**Câu 6.** HSM giữ private signing key không thể xuất. Workload bị chiếm nhưng có quyền Sign. Có thể ký thông điệp giả không?

**Đáp án:** Có thể. Attacker có thể lạm dụng API Sign dù private key không xuất khỏi HSM. Cần IAM, purpose restriction, kiểm tra nghiệp vụ và audit.

**Câu 7.** Có thể dùng một HMAC key cho cả AES-GCM và HMAC để tiết kiệm số key không?

**Đáp án:** Không nên tự tái sử dụng cùng vật liệu khóa giữa các primitive. Nên tách key theo purpose hoặc dẫn xuất khóa riêng bằng KDF có domain separation theo thiết kế chuẩn.

**Câu 8.** Sau rotation KEK, nếu wrapped DEK đã được rewrap, ciphertext dữ liệu có bắt buộc thay đổi không?

**Đáp án:** Không. Rewrap thay lớp bảo vệ DEK nhưng có thể giữ nguyên DEK và ciphertext dữ liệu. Re-encrypt cần DEK mới và tạo ciphertext/tag/nonce tương ứng.

**Câu 9.** Khóa cũ đã hết hạn dùng cho Encrypt mới. Có thể giữ quyền Decrypt bản ghi cũ không?

**Đáp án:** Có thể nếu policy, key state và cryptoperiod cho phép. Một số kiến trúc có giai đoạn decrypt-only/read-only; cần tránh giữ quyền rộng vô hạn và hủy key khi đã hoàn tất phụ thuộc.

**Câu 10.** Đổi IAM policy nhưng không thay DEK có đủ nếu attacker đã lấy DEK ở dạng rõ không?

**Đáp án:** Không. Thu hồi quyền API chặn thao tác mới nhưng không làm attacker quên DEK. Cần đánh giá dữ liệu/bản mã đã bị lộ, cân nhắc tạo DEK mới và re-encrypt.

**Câu 11.** TLS 1.3 đã xác thực kết nối giữa hai service, có thể bỏ kiểm tra quyền tenant khi giải mã dữ liệu không?

**Đáp án:** Không. TLS bảo vệ kênh và xác thực peer theo cấu hình; quyền đọc hóa đơn theo tenant là vấn đề phân quyền nghiệp vụ riêng.

**Câu 12.** Vì sao không nên xóa KEK cũ ngay khi mọi bản ghi mới đều dùng KEK mới?

**Đáp án:** Dữ liệu và backup cũ có thể vẫn chứa wrapped DEK cần KEK cũ để mở. Phải kiểm kê phụ thuộc, migration và kiểm thử restore trước khi hủy.

**Câu 13.** Vì sao các lỗi tag sai hoặc KMS AccessDenied cần được log nhưng không trả toàn bộ chi tiết cho client?

**Đáp án:** Audit giúp điều tra sai cấu hình/tấn công, còn thông báo quá chi tiết có thể làm lộ cấu trúc khóa, trạng thái bản ghi hoặc thông tin tenant khác. Trả lỗi tổng quát phù hợp và log dữ liệu không nhạy cảm.

**Câu 14.** Phân biệt lộ key material và lộ quyền sử dụng key có ý nghĩa gì?

**Đáp án:** Attacker không cần có raw KEK/private key nếu có quyền gọi Decrypt/Unwrap/Sign/Derive. Cần thu hồi quyền, kiểm tra audit và đánh giá dữ liệu/chữ ký đã bị tạo hay truy cập, bên cạnh việc thay khóa khi cần.

## Kết luận

**Use key là giai đoạn thực thi giá trị của key management và cũng là nơi những sai sót nhỏ có thể phá toàn bộ hệ thống.** Một khóa mạnh chỉ an toàn khi được dùng **đúng thuật toán, đúng mục đích, đúng chủ thể, đúng tenant/tài nguyên, đúng trạng thái vòng đời và đúng tham số mật mã**.

Trong hệ thống Java, sử dụng **JCA/JCE** hoặc API **KMS/HSM** theo kiểu khóa: **DEK cho AES-GCM, KEK cho wrap/unwrap, private signing key cho Sign, public key đáng tin cho Verify, HMAC key cho MAC, KDF/key agreement theo giao thức chuẩn**. Cần đi kèm **IAM least privilege, AEAD nonce/AAD/tag, key ID/version, cryptoperiod, rotation, thu hồi, backup/restore và audit**.

**Quản lý khóa không dừng ở việc giữ khóa bí mật: quyền dùng khóa, ngữ cảnh sử dụng và cách xử lý kết quả mật mã quyết định dữ liệu có được bảo vệ thực sự hay không.**

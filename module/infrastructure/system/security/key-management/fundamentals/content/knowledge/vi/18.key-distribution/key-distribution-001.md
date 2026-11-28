# Phân phối key an toàn — Key Distribution trong hệ thống mật mã

## 1. Phân phối key an toàn là gì?

**Key distribution (phân phối khóa mật mã)** là quá trình đưa **khóa, quyền sử dụng khóa hoặc thông tin cần để thiết lập khóa** đến đúng bên được phép, qua một quy trình có thể xác minh và kiểm toán. An toàn không chỉ có nghĩa “gửi một chuỗi bí mật qua kênh đã mã hóa”, mà còn bao gồm **xác thực bên gửi và bên nhận, đúng mục đích, toàn vẹn, không bị phát lại, hạn chế bản sao, thời hạn sử dụng và khả năng thu hồi**.

Ví dụ, một dịch vụ Java dùng HMAC để kiểm tra webhook từ đối tác. Cả hai phía phải có cùng MAC key hoặc một thỏa thuận khóa thích hợp. Nếu quản trị viên gửi secret qua email, kênh chat không được phê duyệt hoặc sao chép vào tệp cấu hình trong Git, khả năng tạo tag HMAC đúng **không làm secret đã bị lộ trở nên an toàn**. Nếu secret được phân phối nhầm tenant, bên nhận sai vẫn có thể tạo thông điệp xác thực bằng khóa của người khác.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài **Phân phối key an toàn** thuộc chương **Key distribution**. Nó kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán để bảo vệ khóa suốt vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**.

> **Nguyên tắc:** Tốt nhất là **không chuyển raw secret key nếu có thể chuyển quyền sử dụng key handle, wrapped key hoặc thiết lập khóa qua giao thức đã được thẩm định**. Khi buộc phải chuyển key material, phải xác định chính xác ai được nhận, họ nhận gì, bảo vệ bằng gì, tồn tại bao lâu và chứng cứ phân phối thành công là gì.

### 1.1. Phân phối khóa không đồng nghĩa công bố public key

| Vật liệu/thông tin | Có phải bí mật? | Yêu cầu phân phối chính |
| --- | --- | --- |
| **Public verification key** | Thường không | **Tính xác thực nguồn và toàn vẹn**, chống thay khóa giả |
| **Private signing key** | Có | Thông thường **không xuất/chuyển raw key**; cấp quyền Sign qua KMS/HSM |
| **Symmetric DEK/KEK/MAC key** | Có | Giới hạn người nhận, wrap/transport bảo mật, không ghi plaintext key |
| **Wrapped DEK** | Blob được mã hóa/bọc | Toàn vẹn, liên kết đúng KEK/key version và context; kiểm soát unwrap |
| **Certificate chain** | Thường không | Xác minh PKI, danh tính, thời hạn, key usage và trust anchor |
| **Ephemeral public DH key** | Thường không | Xác thực handshake/peer hoặc ràng buộc transcript theo giao thức |
| **KMS key ID / alias** | Thường không phải key secret | Chống tráo tham chiếu, xác minh owner, purpose, environment và quyền |
| **HSM handle / secret reference** | Không nhất thiết là key bytes | Hạn chế quyền thao tác, chống confused deputy và scope creep |

**Public key có thể công khai nhưng không thể tin tùy ý**. Nếu attacker thay public key của người nhận bằng public key của mình, bên gửi có thể vô tình mã hóa DEK cho attacker. Ngược lại, một private key trong HSM non-exportable vẫn có thể bị lạm dụng nếu attacker chiếm được principal có quyền Sign/Decrypt.

### 1.2. Ví dụ mục tiêu cần đạt

Giả sử Payments Service phải phân phối khả năng giải mã dữ liệu hóa đơn tới Reporting Service:

- **Tính bí mật:** Chỉ những principal được phép mới có khả năng lấy DEK hoặc plaintext.
- **Tính xác thực:** Reporting Service phải biết nguồn key material/key grant đúng do Payments hoặc control plane được tin cậy cấp.
- **Tính toàn vẹn:** DEK, key reference, thuật toán, tenant và phiên bản không được bị tráo.
- **Đúng phạm vi:** Chỉ giải mã tập dữ liệu/tenant/purpose được phê duyệt.
- **Kịp thời:** Khóa mới được dùng đúng mốc; key cũ bị chặn theo chính sách thu hồi.
- **Khả năng kiểm toán:** Biết ai cấp quyền, ai nhận, key version nào và kết quả, **không ghi raw key**.

**Chỉ dùng TLS** trong request giữa hai service không tự chứng minh tất cả điều này; TLS bảo vệ một **kênh vận chuyển**, còn authorization, key lifecycle và xử lý secret phía endpoint cần các cơ chế khác.

## 2. Mô hình đe dọa khi phân phối key

Trước khi chọn giao thức, cần biết đối thủ có thể ở đâu: nghe lén mạng, điều khiển một endpoint, đọc pipeline, thay public key hoặc có quyền gọi KMS rộng hơn dự định.

| Kịch bản tấn công | Hậu quả có thể xảy ra | Lớp phòng vệ cần có |
| --- | --- | --- |
| **Eavesdropping**: nghe lén raw key trên mạng | Có key để giải mã hoặc giả mạo MAC | Không gửi raw key qua plaintext; kênh xác thực, wrapping/establishment |
| **Man-in-the-middle**: thay key của người nhận | Key được gửi tới attacker | Xác thực public key/peer, PKI hoặc trust registry |
| **Replay**: gửi lại một gói cấp khóa cũ | Hồi sinh key hết hạn, rollback version hoặc phát lại grant | Freshness, request ID, sequence/version, expiry, trạng thái đã sử dụng |
| **Key substitution**: tráo wrapped key và metadata | Dùng nhầm tenant/KEK/algorithm | Authentication tag, context binding, allowlist, signed metadata |
| **Compromised destination** | Raw key bị sao chép khi đã giao | Giới hạn phân phối, HSM/TEE khi phù hợp, quyền tối thiểu, rotation |
| **Compromised CI/CD** | Key lộ trong artifact/log/environment | Secret provisioning tại runtime, short-lived identity, audit |
| **Insider/excess permission** | Export key hoặc cấp quyền cho principal không hợp lệ | Separation of duties, dual approval, IAM conditions, monitoring |
| **Downgrade/rollback** | Chấp nhận thuật toán hoặc key version yếu | Algorithm policy cố định, version kiểm soát, không fallback tùy tiện |
| **Cross-tenant confusion** | Key của tenant A được cấp cho tenant B | Principal và tenant từ nguồn tin cậy, per-tenant scope/context |
| **Key loss or deletion** | Mất khả năng đọc dữ liệu hợp lệ | Inventory, backup/DR, kiểm tra phụ thuộc trước revoke/destroy |

### 2.1. “Kênh đã mã hóa” chưa bảo vệ endpoint

Một kênh TLS xác thực đúng có thể chống nghe lén và thay đổi dữ liệu trên đường đi. Nhưng khi secret đã được chuyển vào **biến môi trường, file, heap, trace hoặc log** của ứng dụng, rủi ro chuyển sang endpoint. Kẻ chiếm ứng dụng có thể đọc khóa hoặc yêu cầu KMS thực hiện phép toán được phép.

Do đó, phân phối an toàn có **ba ranh giới**:

1. **Nguồn key/control plane:** Sinh và giữ bí mật đúng cách, quyền export hoặc Wrap có kiểm soát.
2. **Kênh/giao thức:** Bảo vệ vận chuyển, xác thực peer, ràng buộc thông điệp và chống replay.
3. **Đích sử dụng:** Lưu khóa/handle an toàn, cấp quyền theo purpose, quản lý bộ nhớ, rotation và audit.

~~~mermaid
flowchart LR
    S["Nguồn key / KMS-HSM<br/>owner, state, policy"] -->|"AuthN + AuthZ"| P["Đóng gói: wrap/establish<br/>key ID, version, context"]
    P -->|"Kênh xác thực<br/>TLS/mTLS/approved protocol"| D["Đích nhận: workload identity"]
    D --> V{"Xác minh key package,<br/>scope, freshness, policy?"}
    V -->|"Không"| REJECT["Từ chối + audit"]
    V -->|"Có"| USE["Import / key handle / unwrap<br/>theo operation được cấp"]
    USE --> INV["Inventory, rotation, revocation,<br/>monitoring, DR"]
~~~

### 2.2. Phân phối nhầm bí mật không thể được sửa bằng đổi tên alias

Nếu MAC key đã được gửi cho đối tác sai, hoặc private key đã bị xuất sang máy không được quản lý, việc đổi **key ID** hay bí mật trong metadata **không thu hồi được bản sao họ đã giữ**. Khi secret exposure được xác nhận hoặc không thể loại trừ theo mô hình rủi ro, cần xử lý **rotation/revocation, data impact và evidence**.

## 3. Key transport, key agreement, key derivation và quyền sử dụng

Các thuật ngữ sau không nên dùng thay cho nhau.

| Cơ chế | Điều được chuyển hoặc tạo | Ví dụ | Giới hạn quan trọng |
| --- | --- | --- | --- |
| **Key transport** | Một bên tạo key rồi bảo vệ/gửi cho bên nhận | RSA-OAEP bọc DEK, AES-KW dưới KEK chia sẻ, KMS wrapped data key | Phải xác thực đúng recipient; xử lý origin/freshness theo protocol |
| **Key agreement** | Các bên dùng đóng góp khóa để tính shared secret | Authenticated ECDHE/X25519 trong TLS 1.3 | Raw DH không tự xác thực peer hoặc ràng buộc transcript |
| **Key derivation** | Dẫn xuất khóa con từ shared secret/key material | HKDF tạo traffic keys, per-purpose keys | Không tự tăng entropy; cần salt/info/context/labels đúng |
| **Key provisioning** | Cấp quyền hoặc key handle cho workload | KMS IAM grant, secret manager reference, PKCS#11 token | Có thể không chuyển raw key; endpoint vẫn có thể lạm dụng API |
| **Public-key distribution** | Cấp public verification/encapsulation key | X.509/PKI, JWKS, registry/pinning | Không bí mật, nhưng **phải xác thực danh tính và nguồn** |

### 3.1. Transport không giống agreement

Với **RSA-OAEP**, người gửi có thể tạo DEK trước, mã hóa nó bằng public RSA của người nhận, rồi gửi **wrapped DEK**; người nhận dùng private RSA giải bọc. Với **X25519**, hai bên thực hiện key agreement, sau đó dùng **KDF** để tạo secret dùng cho AEAD. X25519 **không phải** một API “mã hóa file bằng public key”.

**HPKE** là một giao thức hybrid public-key encryption chuẩn hóa, kết hợp **KEM + KDF + AEAD** theo suite và mode cụ thể. Nó có thể giúp bảo vệ key/payload giữa các bên, nhưng cần xác thực public key người nhận và xem xét chế độ xác thực sender; **base mode không tự chứng minh danh tính người gửi**.

### 3.2. Phân phối một quyền thường an toàn hơn phân phối raw key

Nếu Orders Service và Reports Service đều cần dùng một private signing key tại HSM, thay vì xuất private key cho cả hai, tổ chức có thể:

- Giữ private key **non-exportable trong HSM/KMS**.
- Cấp **đúng quyền Sign** cho một signing service hoặc những workload được phép.
- Kiểm tra **nội dung, tenant, purpose và quyền nghiệp vụ trước khi ký**.
- Thu hồi grant/credential khi một workload không còn nhiệm vụ.

Nhưng cần nhận diện **API abuse**: không xuất private key **không có nghĩa** kẻ chiếm workload không thể dùng key thông qua API được cấp.

### 3.3. Không tự phát minh key exchange

Không tự ghép **ECDH + SHA-256 + AES** mà không có KDF, authentication và transcript binding. Một khóa chung có entropy cao vẫn có thể bị MITM nếu public DH values bị thay. Với network transports, ưu tiên **TLS 1.3/mTLS**; với mã hóa công khai end-to-end, sử dụng **HPKE hoặc giao thức được đánh giá** khi phù hợp.

## 4. Trước khi phân phối: danh tính, key usage và phê duyệt

**Key distribution request** nên có metadata được tạo từ nguồn đã xác thực, không hoàn toàn từ HTTP input.

| Trường | Ví dụ | Mục đích |
| --- | --- | --- |
| **requestId / changeId** | keydist-2026-0142 | Audit, idempotency và chống gửi lại |
| **sourceOwner** | payments-platform | Xác định người quản lý/ủy quyền |
| **recipientPrincipal** | reports-prod-workload | Đúng bên được phép nhận |
| **recipientKeyFingerprint** | SHA-256 của SPKI từ nguồn tin cậy | Khóa đúng recipient |
| **environment/region/tenant** | production / region-a / tenant-a | Ranh giới triển khai |
| **keyPurpose/operations** | decrypt-report / Unwrap | Hạn chế key usage |
| **keyId/version/algorithm** | reports-dek-v3 / 3 / AES-256 | Xác định vật liệu/định dạng |
| **issuedAt / expiresAt** | Mốc thời gian đáng tin cậy | Giới hạn hiệu lực của gói phân phối |
| **policyVersion** | keydist-policy-v2 | Truy vết quy tắc áp dụng |
| **approver(s)** | Owner/Security theo mức nhạy cảm | Separation of duties |

### 4.1. Xác thực người nhận trước khi cấp

Đối với **service-to-service**, xác thực bằng **workload identity** đáng tin cậy: mTLS certificate, OIDC/STS workload tokens, IAM identity hoặc một cơ chế đã được thẩm định. Kênh TLS chỉ bảo vệ được secret đúng chỗ nếu endpoint được xác thực là **service đích phù hợp**.

Đối với **đối tác bên ngoài**, cần xác minh **recipient public key và tổ chức sở hữu** qua CA, signed key directory, out-of-band fingerprint hoặc quy trình đăng ký có phê duyệt. Một tệp “public-key.pem” được gửi trong cùng email không tự chứng minh nó thuộc bên nhận thật.

### 4.2. Kiểm tra quyền là hai lớp

Giả sử Workload Payments có quyền KMS Decrypt/Unwrap:

- **KMS/IAM authorization:** Principal được phép gọi Unwrap với key resource/context này không?
- **Application/data authorization:** Người dùng/dịch vụ nghiệp vụ được phép đọc **hóa đơn cụ thể** của tenant này không?

Một câu trả lời **Allow từ KMS** không thay thế việc kiểm tra dữ liệu thuộc tenant nào. Tương tự, user được phép xem báo cáo không đồng nghĩa backend nên phát raw DEK cho browser.

### 4.3. Tách người đề xuất, phê duyệt và thực thi

Với **production KEK, root key hoặc private signing key quan trọng**, nên áp dụng:

1. Application/Data owner xác nhận **nhu cầu sử dụng và phạm vi**.
2. Security đánh giá key policy, threat model và ngoại lệ.
3. KMS/IAM operator thực thi key grants, Wrap/Unwrap hoặc provisioning.
4. Bên nhận xác minh đúng package/key reference và gửi acknowledgement.
5. Audit ghi yêu cầu, principal, key version, kết quả và hiệu lực.

**Dual control** không đồng nghĩa hai người cùng biết raw key. Trái lại, hệ thống nên cho phép phê duyệt **mà không cần ai xem key bytes**.

## 5. Phân phối key trong nội bộ bằng KMS/HSM và secret manager

### 5.1. KMS giữ KEK, ứng dụng giữ wrapped DEK

Mô hình envelope encryption thường cho ứng dụng:

1. Gọi **GenerateDataKey** của KMS hoặc tạo DEK theo chính sách.
2. Mã hóa payload bằng **DEK** qua AEAD như AES-GCM.
3. Giữ **encrypted/wrapped DEK** cạnh ciphertext và key reference, không lưu raw DEK.
4. Khi đọc, xác thực caller và quyền bản ghi, dùng **KMS Decrypt/Unwrap** đúng KEK và context.
5. Không chuyển raw KEK xuống ứng dụng; giới hạn plaintext DEK trong thời gian sử dụng.

Ở đây “phân phối” thường là phân phối **khả năng sử dụng KEK thông qua IAM và encrypted data keys**, không phải gửi một file chứa KEK cho mọi dịch vụ.

~~~mermaid
sequenceDiagram
    participant Owner as App owner / IAM
    participant Writer as Java writer service
    participant KMS as KMS/HSM
    participant DB as Database / storage
    participant Reader as Authorized reader service
    Owner->>KMS: Cấp grant theo workload, key và context
    Writer->>KMS: GenerateDataKey(approvedKek, context)
    KMS-->>Writer: Plaintext DEK tạm + wrapped DEK
    Writer->>Writer: AEAD encrypt(payload, trusted AAD)
    Writer->>DB: Ciphertext + wrapped DEK + nonce/tag + key ref
    Reader->>Reader: Xác thực và kiểm tra quyền bản ghi
    Reader->>DB: Đọc envelope
    DB-->>Reader: Envelope + metadata
    Reader->>KMS: Decrypt/Unwrap(wrapped DEK, expected context)
    KMS-->>Reader: DEK tạm nếu IAM/policy cho phép
    Reader->>Reader: AEAD decrypt và kiểm tra tag/AAD
~~~

### 5.2. Secret manager: phân phối bí mật theo workload identity

Đối với **MAC keys, database credentials, keystore passwords** hoặc một số bí mật phải được tải vào runtime, một secret manager có thể:

- Lưu versioned secret với encryption at rest và audit.
- Xác thực workload bằng IAM/mTLS/STS, thay vì một master password hardcode trong app.
- Cấp quyền đọc **đúng secret path, environment và version**.
- Hỗ trợ rotation, giới hạn cache và cảnh báo quyền truy cập bất thường.

**Không đồng nhất secret manager với HSM non-exportable**: một secret manager thường có thể **trả nguyên plaintext secret** cho workload. Khi workload bị chiếm, attacker có thể lấy hoặc sử dụng secret đó.

### 5.3. Provisioning tại runtime thay vì đóng gói vào artifact

Không đặt production DEK/MAC key/private key vào:

- Source repository, Dockerfile, build artifact, test fixture dùng lại cho production.
- File cấu hình được commit hoặc in trong log startup.
- CI/CD variable tràn lan không có scope/rotation và audit phù hợp.
- Command-line arguments, shell history, shared notebook hoặc ticket.

Ưu tiên **runtime injection** từ secret manager, HSM provider hoặc KMS handle theo danh tính service. Tuy nhiên, environment variable, file mount hoặc in-memory secret sau khi cấp **vẫn có thể bị đọc** bởi process/OS/quyền không phù hợp; cần kiểm tra ranh giới thực tế.

### 5.4. KMS/HSM không phải dịch vụ tự động cấp tất cả loại khóa

Không phải KMS nào cũng hỗ trợ mọi thuật toán, **Wrap/Unwrap, asymmetric Decrypt, HMAC, ECDH, key import/export** theo cùng giao diện. Khi xây hệ thống, cần xác minh:

- KEK key type, algorithm và usage mode được hỗ trợ.
- Key policy/grants có điều kiện theo encryption context, tenant hoặc resource không.
- Encrypted data key có phải **opaque blob** và có thể di chuyển region/account không.
- Lưu trữ/restore key version, multi-region, backup, revocation và deletion semantics.
- API có xuất plaintext DEK hoặc private key ra ứng dụng không; nếu có thì cần mô hình bảo vệ tương ứng.

**Không thiết kế quy trình bắt KMS phải xuất raw KEK** để “chia sẻ cho service thứ hai” nếu ranh giới KMS yêu cầu khóa không được xuất.

## 6. Đóng gói key material: AES-KW, AEAD, RSA-OAEP và HPKE

Nếu raw DEK cần đi qua một ranh giới tin cậy, nên **wrap hoặc thiết lập key** bằng primitive/giao thức được phê duyệt. Key transport không nên chỉ là **mã hóa một chuỗi Base64 bằng thuật toán tự chế**.

| Phương án | Cơ chế chính | Khi phù hợp | Bẫy cần tránh |
| --- | --- | --- | --- |
| **AES-KW (RFC 3394)** | Bọc DEK dưới KEK đối xứng bằng cơ chế key wrap | Hai phía dùng được KEK dưới chính sách có kiểm soát | Không có AAD tùy ý; không tự ràng buộc tenant/purpose |
| **AES-KWP (RFC 5649)** | Key wrap có padding cho độ dài linh hoạt | Key material có kích thước không phù hợp AES-KW thông thường | Phải dùng đúng algorithm/version để unwrap |
| **AES-GCM wrapping** | AEAD bọc key bytes, có nonce/tag/AAD | Cần xác thực context như tenant, purpose theo thiết kế | Nonce phải duy nhất dưới cùng KEK; chống reuse và kiểm soát limits |
| **RSA-OAEP** | Mã hóa một DEK nhỏ bằng public RSA người nhận | Key transport tới recipient có public key đã xác thực | Chỉ bảo mật cho recipient; **không tự xác thực sender** |
| **HPKE** | KEM, KDF, AEAD theo suite và mode của HPKE | Phân phối bí mật qua public key có xác thực | Cần chọn auth mode/trust phù hợp; không phải mọi mode xác thực sender |
| **KMS/HSM native Wrap/Unwrap** | Operation được thực thi qua key handle, policies | KEK không nên rời KMS/HSM | Phải hiểu chính xác permissions, encrypted blob và context |

### 6.1. AES-KW không tự gắn danh tính người nhận

AES-KW giúp bảo vệ **tính bí mật và phát hiện sửa đổi wrapped key** trong giả định KEK an toàn và dùng đúng. Tuy nhiên, nếu cùng KEK được phép cho hai ứng dụng hoặc tenant, một wrapped DEK có thể bị dùng sai context nếu tầng ứng dụng không kiểm tra key ID/tenant/purpose.

Giải pháp có thể là:

- KEK riêng theo miền tin cậy hoặc tenant.
- Metadata/context được xác thực bởi cơ chế khác.
- Một **KMS encryption context** khi API hỗ trợ và key policy ràng buộc.
- Authorization độc lập theo bản ghi, không để client tự chỉ định kho khóa.

### 6.2. RSA-OAEP bảo vệ DEK cho người nhận, nhưng không ký tên người gửi

Người gửi có public RSA của người nhận đã được xác thực, sinh DEK AES, rồi **RSA-OAEP wrap DEK**. Chỉ người có private RSA tương ứng mới có thể unwrap trong mô hình an ninh của primitive.

Tuy nhiên, **bất kỳ ai có public key đều có thể tạo một gói ciphertext RSA-OAEP hợp lệ cho người nhận**. Vì vậy, bên nhận không được kết luận package chắc chắn đến từ đối tác được phép chỉ vì unwrap thành công. Cần **mTLS, chữ ký số của sender trên manifest/gói, hoặc giao thức authenticated envelope phù hợp**.

**OAEP có các tham số cần khớp**: hash, MGF1 hash và label (nếu dùng). Nên quy định bằng profile giao thức rõ ràng và kiểm thử liên thông; không cho bộ giải mã đoán hàng loạt profile để “tìm cái mở được”.

### 6.3. Public key không tự được xác thực vì nó là public

Nếu Alice lấy được public key giả của Mallory nhưng tưởng là Bob, Alice sẽ wrap DEK cho Mallory. Dù RSA-OAEP hoạt động hoàn hảo, **bí mật đã gửi nhầm người**. Do đó bước **recipient key enrollment/validation** bắt buộc phải có trước khi phân phối.

### 6.4. Một key package không nên che giấu wrapping scheme

Gói phân phối phải có **schema/algorithm identifiers** cố định và kiểm soát qua allowlist. Nếu cho phép người gửi tự chọn yếu tố “AESWrap”, “RSA” hoặc “none”, một hệ thống có thể bị **algorithm downgrade/confusion**.

Đừng dùng mô hình “nếu không unwrap được bằng AES-KW thì thử RSA, rồi cuối cùng coi bytes là raw DEK”. **Không fallback sang raw key** dưới bất kỳ tên lỗi tương thích nào.

## 7. Phân phối trên kênh TLS/mTLS và key agreement

### 7.1. TLS bảo vệ kênh; key management bảo vệ vật liệu khóa

**TLS 1.3** cung cấp một giao thức bảo vệ kênh, bao gồm authenticated handshake và **traffic keys** được thiết lập bằng key schedule theo đặc tả. Với **mTLS**, cả hai phía có thể xác thực bằng certificate phù hợp.

Một ứng dụng có thể đưa **wrapped DEK** hoặc một secret do secret manager cấp qua HTTPS/mTLS, nhưng vẫn phải:

1. Xác thực đúng **hostname/service identity** và certificate/trust chain.
2. Kiểm tra authorization của **người nhận và key purpose** ở tầng ứng dụng.
3. Giới hạn quyền/tuổi thọ raw key trên endpoint sau khi TLS hoàn tất.
4. Định nghĩa retry/idempotency/anti-replay cho lệnh cấp key.
5. Có audit/correlation ID, không log secret trong request hoặc response.

**TLS không tự khiến một lệnh cấp key không thể bị gửi lại**: có thể có attacker chiếm client, replay ở tầng ứng dụng hoặc người dùng gọi lại API. Cần quy tắc freshness và idempotency ở **key distribution protocol**.

### 7.2. mTLS xác thực workload, chưa chắc xác thực user nghiệp vụ

Một dịch vụ Reports có certificate hợp lệ không có nghĩa nó được phép giải mã mọi tenant. Cần ánh xạ mTLS identity sang **service role**, rồi kiểm tra tenant, resource và operation được cấp. Không dùng một root CA quá rộng rồi cho rằng mọi certificate do CA đó cấp đều được phép Unwrap.

Khi làm service-to-service, nên:

- Cấp certificate với **Service ID** hoặc định danh chuẩn của tổ chức.
- Kiểm tra **subject/SAN/URI identity** phù hợp chính sách.
- Định nghĩa trust domain giữa production, staging và DR.
- Thực thi authorization sau mTLS bằng policy engine, IAM hoặc logic được review.
- Xoay vòng chứng chỉ và khóa ký riêng với secret được vận chuyển.

### 7.3. Key agreement khác chuyển một key có sẵn

Trong **authenticated ephemeral ECDH**:

1. Mỗi bên có ephemeral private/public contribution.
2. Public contributions được trao đổi trong handshake đã xác thực.
3. Mỗi bên tính shared secret.
4. **HKDF/key schedule** dẫn xuất traffic keys theo transcript, purpose, hướng gửi/nhận và phiên.

Đây thường không phải việc “Alice tạo AES DEK rồi gửi Bob”. Cả hai bên **thiết lập khóa chung** theo giao thức. Nếu không xác thực public DH values và transcript, attacker có thể làm MITM.

### 7.4. Forward secrecy không mặc nhiên xuất hiện khi gửi khóa qua TLS

TLS 1.3 có thể có forward secrecy cho **traffic encryption** theo handshake phù hợp. Tuy nhiên, nếu ứng dụng gửi một **DEK dài hạn dạng rõ bên trong TLS**, bản DEK đó có thể được endpoint lưu lại hoặc bị lộ về sau. **Forward secrecy của transport không khiến một bí mật dài hạn đã phân phối trở thành ephemeral**.

Để thiết kế đúng, cần phân biệt **traffic keys của TLS**, **application DEK**, **wrapping KEK** và **signing private key**: mỗi loại có vòng đời, phạm vi và nguy cơ khác nhau.

## 8. Công bố và xác thực public key: PKI, certificate, JWKS

**Public key distribution** có vấn đề chính là **tính xác thực và tính toàn vẹn**, không phải che giấu nội dung. Kẻ tấn công không cần lấy private key nếu họ có thể khiến verifier tin một public key giả thuộc đúng issuer.

### 8.1. Chứng chỉ X.509 và PKI

Một quy trình có thể gồm:

- Sinh key pair trong ranh giới được phê duyệt.
- Tạo **CSR** hoặc hồ sơ yêu cầu cấp chứng chỉ theo CA.
- CA kiểm tra quyền sở hữu danh tính và phát hành **X.509 certificate**.
- Bên sử dụng kiểm tra chain tới **trust anchor được cấu hình tin cậy**, định danh endpoint, thời hạn, Key Usage/EKU, thuật toán và chính sách trạng thái thu hồi.

**Certificate hợp lệ về chữ ký không tự đủ** nếu hostname, tenant hoặc service identity sai. Một public key trong certificate của service A không nên được xem như khóa tin cậy của service B.

### 8.2. JWKS/JSON Web Key và chữ ký JWT

Một identity service có thể công bố public verification keys qua **JWKS endpoint**. Với mỗi token, verifier cần:

- Chỉ tin **issuer và JWKS URL đã được cấu hình đáng tin cậy**, không tự tải URL do token chưa xác thực gợi ý.
- Chọn key theo **issuer + key ID + algorithm policy**, không chỉ kid riêng lẻ.
- Ràng buộc thuật toán chữ ký đã được phép; không để header token buộc verifier chấp nhận thuật toán không phù hợp.
- Kiểm tra signature, **audience, issuer, time claims và quyền nghiệp vụ**.
- Quản lý **cache, rotation, revocation** và token đang còn hiệu lực.

**Xóa key v1 khỏi JWKS chưa chắc ngay lập tức chặn mọi verifier** vì cache hoặc client offline. Khi key bị compromised, cần kế hoạch phân phối revocation, không chỉ đăng JWKS mới.

### 8.3. Fingerprint và trust-on-first-use

Fingerprint thường là hash của một encoding public key hoặc certificate. Nó giúp so khớp khóa, nhưng:

- **Phải biết fingerprint tham chiếu đến từ nguồn tin cậy**; gửi fingerprint cùng public key trên một kênh MITM không giải quyết được việc thay cả hai.
- **Trust-on-first-use (TOFU)** có thể phù hợp một số hệ thống đã đánh giá rủi ro, nhưng lần kết nối đầu có thể bị MITM và việc thay key phải có quy trình xác minh.
- Nếu public key pinning được dùng, rotation cần chuẩn bị **khóa mới trước** và cập nhật clients; pinning sai có thể tự gây outage.

### 8.4. Public key compromise khác private key compromise

Public key vốn không phải bí mật; việc nó bị nhiều bên biết **không phải compromise**. Nguy cơ là:

- **Private key bị lộ**, cho phép Sign/Decrypt trái phép.
- **Nguồn public key/truststore bị thay**, khiến recipient hoặc verifier tin khóa giả.
- **Issuer/CA bị xâm phạm**, làm quy trình gán danh tính sai.

Hành động ứng phó khác nhau: private key exposure có thể đòi hỏi **rotation/revocation**; nguồn trust bị tráo cần **khôi phục và phân phối lại thông tin tin cậy** cùng điều tra các thông điệp đã được chấp nhận.

## 9. Gói phân phối khóa phải chống tráo đổi, replay và downgrade

Không chỉ gửi mỗi **wrappedKey**. Một gói phân phối an toàn cần mô tả được **đúng khóa, đúng phiên bản, đúng người nhận, đúng mục đích, đúng thời điểm và đúng thuật toán**.

### 9.1. Mẫu manifest cho key package

~~~json
{
  "packageVersion": 1,
  "distributionId": "dist-2026-0142",
  "issuer": "payments-key-control",
  "recipientPrincipal": "reports-prod-workload",
  "recipientKeyId": "reports-rsa-oaep-v2",
  "environment": "production",
  "tenant": "tenant-a",
  "purpose": "invoice-decryption",
  "keyId": "tenant-a-dek-v7",
  "keyAlgorithm": "AES-256",
  "wrappingAlgorithm": "RSA-OAEP-SHA256-MGF1SHA256",
  "wrappedKey": "base64url-of-wrapped-key",
  "issuedAt": "2026-11-28T00:00:00Z",
  "expiresAt": "2026-11-28T00:15:00Z",
  "policyVersion": "keydist-policy-v3"
}
~~~

Đây là **mẫu minh họa**, không phải schema chuẩn có thể tự sử dụng nguyên trạng. Bản thân JSON này **chưa được ký hoặc xác thực**; nếu attacker sửa issuer, recipient, algorithm hoặc thời gian, gói không đáng tin nếu thiếu lớp xác thực bên ngoài.

### 9.2. Ràng buộc manifest với wrapped key

Các cách làm phụ thuộc giao thức:

- **Signed manifest:** Sender ký **canonical bytes** của manifest, bao gồm hash của wrapped key, recipient, key ID/version, purpose, tenant, thời hạn và policy ID; receiver xác minh bằng public key của sender **đã được tin cậy**.
- **Authenticated envelope:** Dùng AEAD/KMS context/HPKE mode có ràng buộc các trường tương ứng theo đặc tả.
- **mTLS + server-side authenticated state:** Gói được vận chuyển trên kênh xác thực và server giữ bản ghi distribution ID/context không cho client tự sửa; cần chống replay tầng ứng dụng.

**Không mặc định AES-KW có AAD**. Nó bảo vệ wrapped key theo primitive, nhưng nếu cần ràng buộc recipient/tenant ở cấp manifest, phải dùng thêm các lớp thích hợp. **RSA-OAEP cũng không tự xác thực sender**.

### 9.3. Canonicalization và serialization

Khi ký manifest hoặc tính MAC, hai bên phải thống nhất **các byte chính xác**. Không tính signature trên một JSON string của Java rồi để Python/JavaScript bên nhận parse và serialize khác thứ tự/định dạng.

Chọn:

- Một **canonical JSON** có đặc tả và xử lý kiểu số/Unicode rõ ràng, hoặc
- Một định dạng nhị phân có **field length, field ID, version** không mơ hồ, hoặc
- Giao thức phân phối khóa chuẩn hóa đã quy định cách ký/xác thực.

Đừng ghép trực tiếp hai trường chuỗi: **"ab"+"c"** và **"a"+"bc"** cho cùng bytes, dẫn đến nhầm ranh giới. Cần length-prefix và nhãn trường/domain separation khi tự thiết kế encoding ở tầng ứng dụng.

### 9.4. Expiry và replay window

Một gói có **expiresAt** nhưng không có **request ID/one-time-use/idempotency** vẫn có thể bị dùng lại trong cửa sổ hợp lệ. Với lệnh cấp/nhập raw secret nhạy cảm:

1. Xác thực sender và recipient.
2. Kiểm tra thời gian từ đồng hồ tin cậy với độ lệch cho phép đã quy định.
3. Từ chối distribution ID đã dùng hoặc đã bị revoke; lưu trạng thái bền vững khi cần.
4. Kiểm tra **monotonic version/key epoch** để tránh rollback sang key cũ.
5. Ghi acknowledgement không chứa raw secret.

**Không lấy timestamp do attacker tự ký bằng một key chưa tin cậy làm bằng chứng lịch sử**. Đối với chữ ký số cần công nhận sau thu hồi, có thể cần trusted timestamp và chứng cứ revocation riêng.

### 9.5. “Import key thành công” chưa chứng minh đúng đối tượng

Sau khi receiver unwrap/import thành công, vẫn phải kiểm tra:

- Thuật toán và độ dài/format của key được phép.
- Key ID/version/purpose và recipient binding theo trusted manifest.
- Key state còn ACTIVE hoặc được phép theo chính sách.
- Quyền sử dụng được giới hạn sau khi import; không tự cấp Export/Sign/Unwrap rộng hơn.
- Ack tới control plane kèm key reference và kết quả kiểm thử, không chứa key bytes.

Không biến **unwrap success** thành **authorization success**; hai quyết định này phải được kiểm tra riêng.

## 10. Java 17: phân phối DEK cho recipient bằng RSA-OAEP và AES-GCM

Ví dụ dưới đây trình bày **mã hóa lai (hybrid encryption)**: phía gửi tạo một DEK AES-256 để mã hóa payload, sau đó **wrap DEK bằng public RSA-3072 của người nhận**. Phía nhận dùng private RSA tương ứng để **unwrap DEK**, rồi giải mã AES-GCM và kiểm tra tag/AAD.

**Giả định bảo mật của ví dụ:** Public RSA đã được lấy từ **nguồn đáng tin cậy**; private RSA của người nhận được bảo vệ. Đoạn code **không tự thực hiện PKI, đăng ký recipient, kiểm tra authorization, chống replay hay xác thực sender**. Dùng trong học tập về API JCA/JCE, không sao chép nguyên thành giao thức production.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.RSAKeyGenParameterSpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public final class SecureDekTransportDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;
    private static final String RECIPIENT_KEY = "reports-rsa-v1";

    private static final OAEPParameterSpec OAEP_SHA256 =
            new OAEPParameterSpec(
                    "SHA-256", "MGF1",
                    MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT);

    private SecureDekTransportDemo() {}

    record KeyPackage(
            int version,
            String recipientKeyId,
            byte[] wrappedDek,
            byte[] payloadNonce,
            byte[] ciphertextAndTag
    ) {}

    static KeyPair newRecipientKeyPair() throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(
                new RSAKeyGenParameterSpec(
                        3072, RSAKeyGenParameterSpec.F4),
                RNG);
        return generator.generateKeyPair();
    }

    static SecretKey newDek() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static byte[] trustedAad(String tenant, String record) {
        // Length-prefix encoding giảm ambiguity giữa các trường.
        // Tenant và record phải đến từ nguồn đã được server xác thực.
        byte[] t = tenant.getBytes(StandardCharsets.UTF_8);
        byte[] r = record.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(12 + t.length + r.length)
                .putInt(0x4B443031) // "KD01": phiên bản AAD
                .putInt(t.length).put(t)
                .putInt(r.length).put(r)
                .array();
    }

    static KeyPackage senderEncrypt(
            byte[] plaintext,
            byte[] trustedAad,
            PublicKey verifiedRecipientPublicKey
    ) throws Exception {
        SecretKey dek = newDek();
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        Cipher payload = Cipher.getInstance("AES/GCM/NoPadding");
        payload.init(
                Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, nonce));
        payload.updateAAD(trustedAad);
        byte[] ciphertextAndTag = payload.doFinal(plaintext);

        Cipher transport = Cipher.getInstance("RSA/ECB/OAEPPadding");
        transport.init(
                Cipher.WRAP_MODE, verifiedRecipientPublicKey, OAEP_SHA256);
        byte[] wrappedDek = transport.wrap(dek);

        return new KeyPackage(
                1, RECIPIENT_KEY, wrappedDek, nonce, ciphertextAndTag);
    }

    static byte[] recipientDecrypt(
            KeyPackage pkg,
            byte[] expectedTrustedAad,
            PrivateKey recipientPrivateKey,
            String expectedRecipientKeyId
    ) throws Exception {
        // Key ID chỉ là metadata; phải có signed manifest/kênh
        // xác thực và key policy bên ngoài code demo này.
        if (pkg == null || pkg.version() != 1 ||
                !expectedRecipientKeyId.equals(pkg.recipientKeyId()) ||
                pkg.payloadNonce().length != NONCE_BYTES) {
            throw new SecurityException("Invalid key package");
        }

        Cipher transport = Cipher.getInstance("RSA/ECB/OAEPPadding");
        transport.init(
                Cipher.UNWRAP_MODE, recipientPrivateKey, OAEP_SHA256);
        Key recovered = transport.unwrap(
                pkg.wrappedDek(), "AES", Cipher.SECRET_KEY);
        if (!(recovered instanceof SecretKey dek)) {
            throw new SecurityException("Expected AES key");
        }

        Cipher payload = Cipher.getInstance("AES/GCM/NoPadding");
        payload.init(
                Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, pkg.payloadNonce()));
        payload.updateAAD(expectedTrustedAad);
        return payload.doFinal(pkg.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        // DEMO: cặp RSA được sinh cùng process; production cần
        // recipient public key được xác thực trước khi gửi DEK.
        KeyPair recipient = newRecipientKeyPair();
        byte[] message = "Hoa don 42"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = trustedAad("tenant-a", "invoice-42");

        KeyPackage pkg = senderEncrypt(
                message, aad, recipient.getPublic());
        byte[] opened = recipientDecrypt(
                pkg, trustedAad("tenant-a", "invoice-42"),
                recipient.getPrivate(), RECIPIENT_KEY);
        try {
            System.out.println("Round-trip OK: " +
                    MessageDigest.isEqual(message, opened));
            System.out.println("RSA-3072 wrapped key bytes: " +
                    pkg.wrappedDek().length);
        } finally {
            Arrays.fill(opened, (byte) 0);
        }

        try {
            recipientDecrypt(
                    pkg, trustedAad("tenant-b", "invoice-42"),
                    recipient.getPrivate(), RECIPIENT_KEY);
            System.out.println("Unexpected success");
        } catch (AEADBadTagException expected) {
            System.out.println("Wrong context rejected: true");
        }
    }
}
~~~

Kết quả minh họa khi provider hỗ trợ các thuật toán:

~~~text
Round-trip OK: true
RSA-3072 wrapped key bytes: 384
Wrong context rejected: true
~~~

### 10.1. Vì sao có hai thuật toán?

- **AES-256-GCM** mã hóa nội dung hóa đơn, với nonce mới và authentication tag để bảo vệ bí mật và toàn vẹn.
- **RSA-OAEP** wrap **DEK 32 byte**, không mã hóa trực tiếp file/bản ghi lớn. Với modulus **3072 bit**, RSA ciphertext dài **384 byte** trong trường hợp này.
- **OAEPParameterSpec** nêu rõ SHA-256, MGF1 SHA-256 và label mặc định. Những tham số này phải được thống nhất ở hai đầu.
- **trustedAad** ràng buộc tenant/record. Khi bên nhận dùng expected context sai, AES-GCM từ chối.
- **recipientKeyId** chỉ giúp định tuyến/đối soát; **không tự xác thực public key hoặc sender**.

### 10.2. Giới hạn của ví dụ

1. **Không có sender authentication:** Ai có public RSA đúng đều có thể tạo wrapped DEK cho người nhận. Production cần sender identity/signed manifest hoặc giao thức xác thực đã thẩm định.
2. **Không có chống replay:** Gói cũ có thể được gửi lại. Cần distribution ID, key version, freshness và trạng thái đã sử dụng ở hệ thống nhận.
3. **Public RSA được tạo trong cùng process chỉ để demo:** Trong hệ thống phân tán, sender phải xác thực fingerprint/chứng chỉ người nhận qua nguồn tin cậy.
4. **Private RSA ở JVM:** Production có thể cần HSM/KMS non-exportable và thao tác unwrap/decrypt thông qua key handle.
5. **Không có record authorization:** AAD không thay quyết định user được đọc hóa đơn nào.
6. **Các byte arrays trong record có thể bị sửa:** Với production phải dùng parser/immutability, defensive copies, bounds validation và xác thực manifest.
7. **Không chứng minh zeroization hoàn toàn:** Xóa một mảng kết quả không xóa key material bên trong SecretKey, Cipher/provider hoặc snapshot bộ nhớ.
8. **Không triển khai exception mapping hoàn chỉnh:** Production cần phân biệt lỗi định dạng, policy, KMS outage và authentication tag mà không tạo oracle hoặc trả thông tin nhạy cảm.
9. **Không tự mở rộng sang MAC key hay signing private key:** Mỗi key type có chính sách export, purpose và hậu quả khác nhau; không phát private signing key chỉ vì đã có code wrap DEK.

### 10.3. Vì sao không mã hóa DEK trực tiếp bằng AES-GCM với một raw KEK trong app?

Điều đó có thể là một **primitive wrapping được thiết kế đúng** nếu nonce, tag và AAD được kiểm soát. Nhưng đặt raw KEK trong mỗi ứng dụng nhận có thể tạo **bề mặt lộ lớn hơn** so với KMS/HSM. Đối với môi trường managed KMS, nên so sánh rủi ro và dùng dịch vụ **Wrap/Unwrap/GenerateDataKey** theo quyền thay vì sao chép KEK.

## 11. Chữ ký manifest và bằng chứng sender

Nếu sender và recipient cần **xác thực gói phân phối độc lập với transport TLS**, có thể ký một **canonical manifest** chứa hash của wrapped DEK cùng các trường:

- Issuer và recipient identity.
- Key ID/version, thuật toán, purpose, tenant, environment.
- Distribution ID, issuedAt, expiresAt, policy version.
- Fingerprint public key đích hoặc key resource reference.
- Hash của wrapped key blob và những ciphertext/metadata liên quan.

### 11.1. Java 17: xác minh chữ ký Ed25519 của manifest

Ví dụ phụ sau chỉ cho thấy **Verify** một manifest đã ký. Nó không thực hiện canonicalization và không tự cấp trust cho public key signer.

~~~java
import java.security.PublicKey;
import java.security.Signature;

public final class KeyManifestVerifier {
    private KeyManifestVerifier() {}

    // verifiedIssuerKey phải đến từ PKI hoặc registry tin cậy
    // và được ràng buộc với issuer/purpose cụ thể.
    public static boolean verify(
            byte[] canonicalManifest,
            byte[] signatureBytes,
            PublicKey verifiedIssuerKey
    ) throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(verifiedIssuerKey);
        verifier.update(canonicalManifest);
        return verifier.verify(signatureBytes);
    }
}
~~~

**Verify trả true** chỉ chứng minh chữ ký phù hợp **với public key đã cung cấp** trên **các bytes chính xác**. Receiver vẫn phải:

1. Kiểm tra public key signer được tin cậy **cho issuer và quyền phát key package**, không chỉ tồn tại trong một certificate bất kỳ.
2. Kiểm tra đúng manifest schema, recipient, tenant, purpose, key version và thời hạn.
3. So sánh **hash wrapped DEK** và dữ liệu liên quan trong manifest với blob thực tế.
4. Kiểm tra distribution ID chưa dùng và trạng thái key chưa bị thu hồi.
5. Thực thi authorization và lưu acknowledgement/audit.

### 11.2. Không nhầm chữ ký với bảo mật nội dung

**Digital signature không mã hóa wrapped DEK hay plaintext key**. Nó giúp xác thực nguồn gốc/toàn vẹn theo trust policy, còn bí mật của DEK đến từ cơ chế wrapping hoặc transport. Ngược lại, RSA-OAEP bảo vệ DEK cho recipient nhưng không tự xác thực sender. Hai mục tiêu cần thiết kế riêng hoặc dùng giao thức đáp ứng cả hai.

### 11.3. Trường hợp ký public-key registration

Một **signed public-key enrollment record** có thể nêu rõ key mới thuộc workload nào, mục đích, thời hạn, fingerprint và người phê duyệt. Điều này ngăn tình huống attacker chỉ thay URL/địa chỉ public key rồi khiến service gửi DEK cho họ, **nếu bên gửi xác minh bản ghi đăng ký từ nguồn tin cậy**.

Không có lợi ích khi chữ ký được Verify bằng **chính public key do attacker đính kèm mà chưa được tin cậy**; đó là xác thực vòng tròn không tạo được danh tính.

## 12. Key package và policy dưới dạng cấu hình

Một control plane có thể lưu **policy về điều kiện phân phối**, tách khỏi raw key material. Ví dụ:

~~~yaml
# Policy minh họa, KHÔNG phải cấu hình có thể chạy của KMS.
policyId: distribute-key-prod-v2
owner: platform-security
environment: production
scope:
  keyTypes: [data-encryption-key, mac-key, public-verification-key]
  allowedRecipients:
    - workload: reports-prod
      tenant: tenant-a
      purposes: [invoice-decryption]
      allowedOperations: [Unwrap]
distribution:
  requireAuthenticatedSender: true
  requireAuthenticatedRecipient: true
  requireApprovedKeyAlgorithm: true
  requireRecipientKeyValidation: true
  requireUniqueDistributionId: true
  requireExpiryAndAntiReplay: true
  prohibitPlaintextKeyInLogs: true
  prohibitCrossEnvironmentExport: true
approvals:
  ownerApprovalRequired: true
  independentReviewForRootOrKek: true
evidence:
  recordKeyIdAndVersion: true
  recordRecipientAndPolicyVersion: true
  requireAcknowledgement: true
  requirePostDistributionAccessTest: true
~~~

### 12.1. Cấu hình chỉ có giá trị nếu được thực thi

Các cờ YAML trên phải được ánh xạ thành **IAM/KMS policies, code validator, PKI/JWKS trust, transport configuration, logging và các bài kiểm thử âm tính**. Một cấu hình chỉ tồn tại trên wiki không chặn được việc phân phối secret qua kênh không được phép.

### 12.2. Kiểm soát import/export permissions

Những operation cần phân biệt:

- **Generate/Import:** Tạo key mới hoặc nhập material từ nguồn đã được duyệt; cần provenance và thuật toán phù hợp.
- **Wrap/Encrypt:** Bảo vệ DEK cho người nhận hoặc KEK đích.
- **Unwrap/Decrypt:** Có thể trả plaintext DEK; quyền này thường nhạy cảm hơn quyền nhìn thấy wrapped blob.
- **Export:** Đưa vật liệu khóa ra ngoài ranh giới bảo vệ; có thể bị cấm hoàn toàn.
- **Sign/Verify:** Dùng cho khóa ký và public verification; không trao private signing key nếu có thể ký qua API.
- **Disable/Revoke/Destroy:** Các hành động lifecycle, cần thẩm quyền/dual control tùy mức nhạy cảm.

Nếu **KMS/HSM non-exportable**, policy cấp key không được đưa ra yêu cầu “hãy export key để import vào keystore Java”. Cần tìm giao thức **key handle, wrapped DEK hoặc key agreement** đáp ứng yêu cầu và khả năng backend.

## 13. Phân phối cho đối tác, mobile, browser và hệ thống offline

Khả năng bảo vệ khóa sau khi phân phối phụ thuộc đáng kể vào **thiết bị đích**. Không thể áp dụng một quy trình giống nhau cho HSM của doanh nghiệp, một pod Java production và trình duyệt trên máy khách không được quản lý.

### 13.1. Đối tác B2B nhận DEK hoặc MAC key

Nếu hai tổ chức cần trao đổi DEK/HMAC key:

1. Xác minh pháp nhân, đầu mối kỹ thuật và **định danh người nhận** qua quy trình đăng ký được phê duyệt.
2. Thiết lập **trust anchor, public key hoặc authenticated channel** trước khi gửi bí mật.
3. Chọn giao thức dựa trên **key purpose, độ nhạy, hỗ trợ thuật toán và lifecycle**.
4. Định nghĩa **key ID/version, activation time, overlap/revocation policy, expiry**, và quy trình cấp lại khi thay nhân sự.
5. Bảo đảm **gói được bọc cho đúng recipient**, chống replay và có acknowledgement.
6. Yêu cầu bên nhận cam kết nơi lưu secret, quyền sử dụng, incident reporting và cách hủy.

Nếu MAC key đã được chia sẻ cho một đối tác, cả hai bên biết secret. Việc HMAC Verify đúng **không thể phân biệt chính xác bên nào trong hai bên đã tạo tag**, và cũng không cho tính chống chối bỏ như chữ ký số. Khi cần bằng chứng ai đã ký, xem xét **chữ ký số với private keys do từng bên quản lý** và chính sách tin cậy phù hợp.

### 13.2. Trình duyệt web không phải kho chứa long-lived server secret

Một SPA chạy trên browser không nên nhận **production KEK, server-side HMAC signing secret, private signing key hoặc database-wide DEK** để thuận tiện gọi API. JavaScript trong browser, extension, devtools, XSS và người dùng cuối có thể truy cập môi trường chạy ở những mức khác nhau.

Đối với yêu cầu truy cập dữ liệu, nên dùng **short-lived authorization tokens, server-side access checks hoặc giao thức mã hóa đầu cuối được thiết kế riêng**. Nếu mô hình **end-to-end encryption** thật sự đòi hỏi client giữ khóa, hãy xác định rõ **thiết bị/user là trust boundary** và thiết kế quản lý, backup, recovery, thu hồi, chia sẻ nhiều thiết bị và xử lý mất thiết bị tương ứng.

### 13.3. Mobile và hardware-backed key stores

Mobile có thể dùng **hardware-backed keystore, secure enclave hoặc OS key store** tùy nền tảng để giữ private key/khóa cục bộ. Một thiết kế phổ biến là:

- Thiết bị tự sinh **key pair** trong phần cứng/OS keystore nếu được hỗ trợ.
- Đăng ký **public key** với server qua một quy trình xác thực thiết bị/người dùng; xem xét attestation nếu yêu cầu và được hỗ trợ.
- Server wrap một secret **cho public key của thiết bị** đã xác thực.
- Thiết bị unwrap qua API được bảo vệ theo quyền/biometric/device state phù hợp.
- Khi thiết bị bị mất, thu hồi authorization, key distribution grants và đánh giá ciphertext/secrets đã cấp.

**Hardware-backed không tự chứng minh một user request là hợp lệ**; ứng dụng vẫn cần kiểm tra quyền, ràng buộc phiên và chống replay. Attestation cũng có mô hình tin cậy, giới hạn và nguy cơ riêng.

### 13.4. Hệ thống offline và kênh out-of-band

Phân phối key đến máy offline hoặc môi trường air-gapped có thể dùng **thiết bị chuyển giao đã được phê duyệt, protected key container, dual control và kiểm tra fingerprint**. Cần quy trình cụ thể cho:

- Xác nhận **đúng người nhận** và đúng serial/identity của thiết bị.
- Gói đã mã hóa/wrap cho khóa hoặc HSM của đích.
- Signed manifest chứa **distribution ID, expiry, version, checksum/fingerprint**.
- Bảo vệ vật lý, chain of custody và kiểm soát bản sao.
- Acknowledgement, ghi nhận import thành công và hủy bản trung gian.

**Air-gapped không có nghĩa dữ liệu trên USB tự được bảo vệ**. Khi vật liệu khóa đi qua một phương tiện vật lý, bí mật và toàn vẹn phải được bảo vệ bằng primitive/giao thức phù hợp, cùng kiểm soát vận chuyển.

## 14. Multi-tenant, production/test và phân phối theo miền

### 14.1. Phân tách environment là ranh giới bảo mật thực

Một secret dùng tại **development** không nên được coi là production secret chỉ vì application code giống nhau. Cần:

- Tách **key material** giữa dev/test/staging/production trừ khi có mô hình ngoại lệ được phê duyệt.
- Tách workload identity, IAM role và KMS key policies.
- Không cấp staging quyền unwrap **prod KEK** khi copy database production để test.
- Không dùng cùng secret HMAC trong demo webhook và production partner.
- DR được thiết kế như một luồng production recovery riêng, không mặc định tương đương môi trường test.

Nếu cần chuyển dữ liệu từ production sang test, phối hợp **Data owner/Security** về sanitization, tokenization, re-encryption hoặc môi trường khôi phục đặc biệt; không cấp quyền KMS production rộng cho test như cách khắc phục tiện lợi.

### 14.2. Key ID không thay tenant authorization

Một HTTP client có thể gửi:

~~~text
tenantId=tenant-b
wrappedKeyReference=kms/tenant-b/key-v2
~~~

Hai trường này **không tự chứng minh caller có quyền tenant B**. Server phải lấy tenant/resource ownership từ dữ liệu đã được xác thực, kiểm tra principal/request và chỉ khi đó chọn key reference được phép.

Trong KMS có **encryption context**, context nên được dựng từ bản ghi đã xác thực; nó hỗ trợ cryptographic binding nhưng **không thay authorization** khi cùng một principal có quyền truy cập nhiều tenant.

### 14.3. Key cache phải gắn đầy đủ context

Nếu ứng dụng cache plaintext DEK theo mỗi **alias** mà không phân biệt tenant/key version/purpose, một cache hit có thể đưa nhầm khóa tới service/tenant khác. Cache key có thể cần ràng buộc:

- KMS key ID và phiên bản hoặc opaque blob identity.
- Tenant, environment, purpose và encryption context.
- Trạng thái ACTIVE/REVOKED và policy epoch.
- Giới hạn số lượt/bytes sử dụng và thời gian sống.

Với secret đã bị **revoked**, cache phải được invalidated theo khả năng thực tế; không mặc định thu hồi IAM sẽ lập tức xóa DEK đang nằm trong heap của mọi workload.

## 15. Rotation và phân phối key version mới

Phân phối khóa không kết thúc sau khi bên nhận có v1. **Rotation** cần một giao thức chuyển đổi không làm thất lạc dữ liệu và không vô tình kéo dài niềm tin vào khóa cũ.

### 15.1. Planned rotation: thông báo rồi chuyển theo mốc

Ví dụ một HMAC key dùng giữa Payment Gateway và đối tác:

1. **Lập kế hoạch:** Xác định secret v1, bên nhận, hoạt động đang chạy, rủi ro và thời gian cutover.
2. **Sinh v2:** Dùng CSPRNG/secret manager; tách material khỏi v1.
3. **Phân phối v2 an toàn:** Chỉ đúng recipient, có identity, purpose, key ID và acknowledgement.
4. **Chuẩn bị consumer:** Nếu policy cho phép và v1 vẫn an toàn, verifier có thể được cấu hình nhận v2 trước mốc sender dùng v2.
5. **Chuyển sender:** Bắt đầu tạo HMAC với v2 từ mốc đã thống nhất; ghi rõ key ID.
6. **Giám sát:** Tỷ lệ request còn dùng v1, đối tác chưa xác nhận, lỗi xác thực và replay.
7. **Retire v1:** Đóng cửa sổ overlap theo chính sách, vô hiệu hóa secret cũ và kiểm tra bản sao.
8. **Lưu chứng cứ:** Distribution IDs, recipients, mốc cutover, access logs và negative tests.

**Chấp nhận song song v1/v2** có thể hữu ích với planned rotation khi v1 **không bị compromised**, nhưng cần **giới hạn thời gian và quy tắc chọn key**; không dùng fallback thử mọi secret vô hạn.

### 15.2. Compromised key: tránh kéo dài overlap

Nếu v1 đã bị lộ, giữ cửa sổ chấp nhận v1 có nghĩa người biết v1 vẫn có thể tạo tag HMAC hoặc chữ ký giả. Phải ưu tiên **containment, thay key, chặn v1 và thông báo relying parties** theo mức khẩn cấp, ngay cả khi phải xử lý gián đoạn có kiểm soát.

### 15.3. Public signing key rotation

Với JWT/JWKS hoặc chữ ký số:

- Sinh private/public key v2 trong ranh giới được duyệt.
- Phân phối **public key v2** qua issuer/PKI/trust registry đã xác thực.
- Các verifier nhận v2 trước khi sender bắt đầu Sign v2 nếu đó là planned rotation.
- Sau cutover, xử lý token/chữ ký v1 theo expiry và revocation policy.
- Nếu private v1 bị compromise, không tự xem v1 còn an toàn cho đến khi mọi token cũ hết hạn; cần cách chặn theo chính sách.

### 15.4. KEK rotation và rewrap

Đối với **envelope encryption**, thay KEK có thể chỉ cần **rewrap DEK** nếu raw DEK còn an toàn. Quy trình:

1. Kiểm kê wrapped DEK/KEK references.
2. Tạo/cấp quyền KEK mới theo policy.
3. Rewrap mỗi DEK bằng KMS/HSM operation được phép.
4. Cập nhật **wrapped blob và key reference** cùng nhau; có concurrency control.
5. Kiểm thử Unwrap/Decrypt và restore backup.
6. Retire KEK cũ sau khi hết phụ thuộc và retention.

**Rewrap không đổi DEK**, không đặt lại AES-GCM nonce usage budget và không khôi phục bảo mật của raw DEK đã bị lộ. Nếu raw DEK compromised, cần đánh giá **DEK mới và re-encrypt payload**.

### 15.5. Rollback không được đưa key revoked trở lại

Một deploy lỗi có thể khiến hệ thống quay về config chỉ biết v1. Nếu v1 đã **revoked do compromise**, không được bật lại v1 chỉ vì v2 gặp lỗi. Cần có **tested rollback path** vẫn đáp ứng trust policy, và metadata key version/epoch bền vững để deployment cũ không làm sống lại quyền tin cậy đã thu hồi.

## 16. Revocation: ngừng phân phối và ngừng sử dụng key đã lộ

**Thu hồi phân phối** có nhiều lớp:

- **Ngừng cấp thêm:** Control plane từ chối những distribution request mới đối với key cũ.
- **Thu hồi quyền nguồn:** Revoke IAM grants, service identity/session và quyền Sign/Unwrap/Export.
- **Ngừng chấp nhận:** Recipients/verifiers từ chối key/package/token đã revoked theo policy.
- **Xử lý material đã cấp:** Thay MAC key/DEK/private key khi bị lộ, migration dữ liệu và kiểm tra bản sao.
- **Phân phối trạng thái thu hồi:** Key registry, KMS/HSM, JWKS/PKI, cache, DR và bên thứ ba nhận quyết định đúng.

### 16.1. Disable ở KMS không xóa raw key đã được copy

Nếu trước đó đã export raw DEK/HMAC key cho đối tác, **Disable KMS key** không làm bản copy biến mất. Với chữ ký số, một bên vẫn có private key cũ có thể tạo chữ ký hợp lệ về toán học; bên xác minh cần áp dụng **revocation/trust policy** để từ chối.

**Đừng đánh đồng**:

| Hành động | Thực chất |
| --- | --- |
| **Disable** | Hạn chế các operation do KMS/HSM kiểm soát |
| **Revoke grant/session** | Cắt quyền của một principal |
| **Revoke trust** | Yêu cầu verifier không còn chấp nhận một public key/certificate |
| **Rotate key** | Dùng vật liệu khóa mới cho operation mới |
| **Destroy key** | Loại bỏ material trong phạm vi được quản lý theo policy |
| **Re-encrypt** | Mã hóa lại payload với DEK mới để giảm phụ thuộc raw DEK cũ |

### 16.2. Revocation cần có bằng chứng tại nơi nhận

Một record trong key inventory ghi **status=REVOKED** không tự đảm bảo:

- API service đã xóa key cache.
- JWT verifier không còn tin JWK cũ.
- HSM từ chối Sign bằng private key cũ.
- Đối tác offline đã hủy MAC key bản sao.
- DR không khôi phục grants/policy từ backup cũ.

Theo chính sách, cần **acknowledgement, kiểm thử âm tính và theo dõi các bên chưa cập nhật**. Nếu có recipient ngoài phạm vi kiểm soát trực tiếp, ghi **rủi ro tồn dư** thay vì tuyên bố thu hồi tuyệt đối.

### 16.3. Trình tự truyền tin revocation

~~~mermaid
sequenceDiagram
    participant SOC as Security/Incident Response
    participant CTRL as Key distribution control plane
    participant KMS as KMS/HSM & IAM
    participant APP as Receiving workloads
    participant DR as DR / external recipients
    SOC->>CTRL: Revoke key ID/version + incident ID
    CTRL->>KMS: Chặn grants / operations theo policy
    CTRL-->>APP: Revoke event / trust epoch
    CTRL-->>DR: Revocation notice + deadline
    APP->>APP: Invalidate cache, từ chối key cũ
    APP-->>CTRL: Ack + negative test result
    DR-->>CTRL: Ack hoặc báo chưa thể cập nhật
    CTRL-->>SOC: Danh sách đã chặn, chưa chặn, rủi ro tồn dư
~~~

### 16.4. Sự cố phát hiện nhầm và suspension

Một cảnh báo nghi ngờ chưa chắc chứng minh raw key bị lộ. Chính sách có thể yêu cầu **suspend** quyền cấp key/Sign/Unwrap ngay rồi điều tra; nếu false positive, phục hồi theo approval/audit. Khi **compromise đã xác nhận**, không tự đổi lại trạng thái ACTIVE chỉ vì sự cố mạng vừa hết.

## 17. Backup, DR và tiêu hủy material sau phân phối

Key material sau khi phân phối có thể xuất hiện trong **KMS backups, HSM partitions, secret manager versions, snapshots, heap dumps, CI artifacts và bản sao phía đối tác**. Một thao tác “delete” tại nguồn không xóa được mọi bản sao này.

### 17.1. Kế hoạch khôi phục phải biết đúng key version

Ví dụ:

~~~text
T0: Production DB backup chứa ciphertext và wrappedDEK dưới KEK_v1
T1: Production rewrap sang KEK_v2, dữ liệu chính đọc tốt
T2: KEK_v1 bị destroy
T3: Khôi phục backup T0 vào DR
~~~

Nếu không có đường restore hợp lệ cho wrappedDEK ở T0, hệ thống có thể **mất khả năng đọc dữ liệu** dù bản backup tồn tại. Phải cân nhắc **backup retention, rewrap/migration, key recovery mechanism và destruction approval** trước khi hủy KEK cũ.

### 17.2. Khóa nhận được từ hệ thống khác cũng cần inventory

Ngay cả khi secret được cấp bởi đối tác, bên nhận cần metadata:

- **Owner/issuer, recipient identity, key ID/version, purpose**.
- Nguồn/định dạng key và bằng chứng xác thực.
- Activation/expiry/rotation policy, incident contact.
- Storage boundary, backups, export policy và key usage permissions.
- Quy trình revoke/delete khi đối tác kết thúc hoặc phát hiện lộ secret.

Không có inventory, một ứng dụng có thể tiếp tục dùng MAC key cũ của đối tác nhiều năm sau khi người quản trị ban đầu đã nghỉ việc.

### 17.3. DR identity khác môi trường test

Đường **DR production** có thể được phép truy cập production KEK dưới **điều kiện failover và thẩm quyền rõ ràng**. Một môi trường thử nghiệm không được nhận quyền tương tự chỉ vì dùng cùng mã nguồn.

Phải kiểm thử:

1. Failover workload có **identity** được KMS nhận diện đúng.
2. Wrapped key và encryption context hoạt động trong region/account đích theo semantics backend.
3. KMS/HSM key versions cần thiết còn khả dụng trong thời hạn giữ dữ liệu.
4. Restore không làm **revoked keys, grants, trust anchors** được tin lại.
5. Raw key không bị xuất vào vị trí ít bảo vệ hơn để giải quyết sự cố.

### 17.4. Cryptographic erasure có điều kiện

Khi dùng hủy DEK/KEK để khiến dữ liệu không còn giải mã được, phải xét:

- Còn plaintext DEK/KEK ở cache, backup, secret exports hoặc hệ thống đối tác không?
- Có bản wrapped DEK khác dưới KEK còn sống không?
- Có plaintext data copy ngoài lớp mã hóa không?
- Còn legal hold, retention hoặc dữ liệu dùng chung DEK với tenant khác không?
- Đã có approval và evidence rằng phạm vi key material có thể khôi phục đã được xử lý chưa?

**Crypto-shredding không thu hồi bí mật kẻ tấn công đã lấy được**. Nó là kiểm soát trong phạm vi vật liệu/bản sao mà tổ chức thực sự quản lý.

## 18. Case study: phân phối DEK và HMAC key trong hệ thống đặt hàng Java

Một nền tảng thương mại có:

- **Order Service** lưu đơn hàng có PII được mã hóa bằng DEK AES-GCM.
- **KMS** giữ KEK production, có IAM và encryption context.
- **Analytics Service** cần đọc một phần dữ liệu đã được cho phép, không được đọc mọi trường PII.
- **Webhook Gateway** trao đổi thông điệp với một đối tác thanh toán qua HMAC.
- **Identity Service** dùng private signing key trong HSM, công bố public key qua JWKS đã được tin cậy.
- **Data owner, Security và SRE** quyết định retention, chuẩn giao thức, backup và incident response.

### 18.1. Nhu cầu A: cấp quyền truy cập dữ liệu cho Analytics Service

**Bước 1 — Xác minh nhu cầu.** Application owner và Data owner xác định Analytics có thể đọc những trường nào, tenant nào và thời gian bao lâu. Không bắt đầu bằng việc “gửi AES key cho họ”.

**Bước 2 — Chọn cơ chế.** Nếu Analytics nằm trong cùng miền KMS phù hợp, ưu tiên **grant Unwrap/Decrypt đúng key resource/context** thay vì xuất raw KEK. Nếu chỉ cần báo cáo tổng hợp, có thể cung cấp **API dữ liệu đã lọc** để Analytics không cần raw DEK.

**Bước 3 — Cấp quyền.** IAM cấp workload identity cho Analytics, tách production và staging. KMS policy chỉ cho phép thao tác thật sự cần thiết. Service vẫn phải kiểm tra record-level authorization.

**Bước 4 — Sử dụng.** Analytics đọc envelope đã được phép; tạo AAD/context từ nguồn dữ liệu đáng tin cậy, gọi KMS unwrap rồi AES-GCM decrypt. Không log DEK hoặc plaintext dữ liệu nhạy cảm.

**Bước 5 — Audit/rotation.** Theo dõi key ID, grants, chủ sở hữu, tỷ lệ unwrap và kế hoạch thu hồi quyền khi Analytics không còn nhu cầu.

**Sai lầm cần tránh:** Xuất KEK production thành một file để Analytics “tự giải mã cho nhanh” làm mở rộng rất mạnh blast radius, phá ranh giới KMS và khiến thu hồi quyền trở nên khó chứng minh.

### 18.2. Nhu cầu B: cấp HMAC key cho đối tác thanh toán

**Bước 1 — Đăng ký đối tác.** Xác minh danh tính đối tác, người phụ trách kỹ thuật và kênh tiếp nhận secrets. Phân biệt môi trường sandbox/production và tenant.

**Bước 2 — Sinh secret.** Tạo **HMAC key độc lập** bằng nguồn ngẫu nhiên mật mã, key ID/version mới; không lấy password, timestamp hoặc signing private key làm HMAC secret.

**Bước 3 — Phân phối.** Chọn kênh/gói được phê duyệt: có thể qua **portal xác thực/mTLS**, secret manager federated hoặc **wrap cho public key đối tác đã xác thực** theo khả năng. Nếu dùng RSA-OAEP, vẫn cần **xác thực sender/gói phân phối** bằng kênh hoặc chữ ký phù hợp.

**Bước 4 — Quy định thông điệp được MAC.** Hai bên thống nhất các byte bao gồm method/path/body hoặc canonical request, timestamp, request ID, tenant và algorithm/version; tránh ghép chuỗi mơ hồ. HMAC tag được so sánh constant-time khi phù hợp.

**Bước 5 — Chống replay.** Webhook receiver kiểm tra timestamp window, request ID/idempotency, quyền sự kiện và tính hợp lệ giao dịch. **HMAC đúng không tự chống replay**.

**Bước 6 — Rotation.** Có runbook cutover, hai phía xác nhận nhận key v2, giám sát việc dùng key v1 và đóng cửa sổ overlap. Khi v1 bị lộ, cần dừng tin v1 theo incident policy thay vì kéo dài overlap.

### 18.3. Nhu cầu C: cấp public JWT verification key

Identity Service có private key ký JWT trong HSM, nhưng các API chỉ cần **public verification keys**. Quy trình nên:

1. Giữ private signing key ở HSM/KMS; API consumers không được nhận nó.
2. Cấp public key qua **trusted JWKS issuer**, có key ID/version.
3. Verifier kiểm tra issuer, algorithm policy, audience, signature, thời hạn và authorization.
4. Rotation phát public key v2 theo chiến lược chuyển tiếp; khi private v1 bị compromised phải phân phối **revocation/invalidation**.

**Không dùng HMAC shared secret làm “public verification key”**. Với HMAC, bất kỳ consumer có secret Verify cũng có thể tạo MAC tag, khác hẳn mô hình public key chữ ký số.

### 18.4. Sự cố: một workload Analytics bị chiếm

Giả sử audit cho thấy Analytics principal gọi KMS Unwrap bất thường:

1. Incident Response thu hồi credential/grants và cô lập workload.
2. Application owner cung cấp inventory **KEK → wrapped DEK → datasets/tenants** và sự kiện Unwrap liên quan.
3. Security đánh giá kẻ tấn công có raw DEK/plaintext từ API hoặc chỉ truy cập metadata. **Không tự kết luận raw KEK đã lộ** nếu log chỉ chứng minh API abuse.
4. Nếu raw DEK của một dataset đã bị lấy, cân nhắc **DEK mới và re-encrypt dữ liệu**, không chỉ đổi KEK.
5. Kiểm tra data access logs, bản sao dữ liệu, backup và rủi ro còn lại.
6. Không cấp lại IAM grants rộng như cũ; sửa scope, authorization và anomaly detection.
7. Kiểm thử âm tính rằng principal cũ không còn gọi Unwrap được, đồng thời các dịch vụ hợp lệ vẫn hoạt động.

### 18.5. Bảng chấp nhận sau triển khai

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Analytics workload được phép giải mã đúng tenant | Thành công sau KMS và record authorization |
| Analytics thử đọc dữ liệu tenant khác | Bị chặn dù có wrapped DEK hoặc key ID |
| Sandbox workload gọi prod KMS | IAM/KMS từ chối |
| Đối tác nhập HMAC key v2 có manifest sai recipient | Từ chối gói phân phối |
| Webhook dùng HMAC key đúng nhưng request ID đã dùng | Bị từ chối theo replay/idempotency policy |
| API verifier nhận JWT với public key do token chỉ định | Không tin khóa tùy ý; chọn nguồn issuer đã cấu hình |
| Private signing key vẫn non-exportable | API không thể lấy raw key qua đường không được phép |
| KEK rotate và rewrap dữ liệu chính | Wrapped DEK mới đọc được, payload/metadata nhất quán |
| Khôi phục snapshot trước rotation | Có đường recovery được duyệt hoặc đã xử lý retention |
| Key revoked vẫn nằm trong cache | Cache invalidation/policy chặn các thao tác bị cấm |

## 19. Kiểm toán và giám sát phân phối key

Một key package hoặc grant không có audit có thể tạo quyền truy cập khó kiểm soát sau nhiều tháng. **Audit cần đo được hành động phân phối**, không chỉ ghi “thành công” và không được làm lộ secret.

### 19.1. Metadata audit tối thiểu

| Trường | Ý nghĩa |
| --- | --- |
| **distributionId / requestId** | Nhận diện một giao dịch, idempotency và truy vết |
| **issuer / sourceOwner / approvedBy** | Ai đề xuất, phê duyệt và cấp phát |
| **recipientPrincipal / keyFingerprint** | Ai được nhận hoặc có quyền thao tác |
| **keyId / keyVersion / keyPurpose** | Khóa nào được phân phối, dùng để làm gì |
| **environment / tenant / region** | Phạm vi được phép |
| **wrappingScheme / algorithmPolicy** | Giao thức bảo vệ sử dụng |
| **issuedAt / activatedAt / expiresAt** | Mốc phân phối và hiệu lực |
| **KMS/HSM operation / grant ID** | Bằng chứng thao tác tại nơi kiểm soát khóa |
| **acknowledgement / failure code** | Bên nhận đã nhận/cài đặt hay còn lỗi |
| **rotation/revocation/incident reference** | Nối với biến động vòng đời |
| **residualRisk / unacknowledgedTargets** | Đối tác hoặc bản sao chưa cập nhật |

**Không ghi raw DEK/KEK, HMAC secret, private key, token chứa secret hoặc plaintext** vào audit. Wrapped key blob cũng có thể mang metadata/định danh nhạy cảm; chỉ lưu nguyên blob trong audit nếu có nhu cầu và chính sách bảo vệ phù hợp, còn thông thường log key reference/hash an toàn là đủ.

### 19.2. Những hành vi nên cảnh báo

- Cấp key/grant cho principal **không có trong allowlist hoặc không có owner**.
- Sử dụng **root/KEK export** hoặc key import/export ngoài change ticket.
- Distribution request từ **test/staging** nhắm tới production key.
- Tăng đột biến KMS Unwrap, GenerateDataKey hoặc Sign từ một workload.
- Recipient liên tục yêu cầu **cấp lại cùng secret** hoặc dùng distribution ID đã hoàn tất.
- Truy cập vào **expired/revoked key versions**.
- Thay JWKS, certificate fingerprint hoặc trust registry không được phê duyệt.
- Sự khác biệt giữa inventory key state với KMS/HSM state.
- Secret xuất hiện trong CI log, heap dump, build artifact hoặc file chia sẻ.
- DR restore khiến grants, aliases hoặc trust anchors quay về trạng thái trước revoke.

### 19.3. Chỉ số nên theo dõi

- **Distribution completion rate:** Tỷ lệ bên nhận đã xác nhận và vượt kiểm thử nhận khóa.
- **Unacknowledged recipients:** Các bên chưa cập nhật sau cutover/revocation.
- **Provisioning latency:** Thời gian từ approval đến nhận quyền/khóa hợp lệ.
- **Unauthorized grant attempts:** Những lần xin hoặc dùng quyền không đúng.
- **Key version drift:** Workloads vẫn sử dụng v1 sau khi v2 đã active.
- **Revocation propagation lag:** Độ trễ từ quyết định đến khi mọi điểm thực thi chặn.
- **Inventory coverage:** Tỷ lệ keys có owner, tenant/purpose, recipients và state.
- **Sensitive material exposures:** Sự kiện raw key/secret xuất hiện ngoài ranh giới đã duyệt.

Ngưỡng cảnh báo và mục tiêu thời gian cần được xác định theo **threat model, yêu cầu nghiệp vụ, khả năng nhà cung cấp và loại key**; không có một mức TTL hay “thời gian thu hồi ngay lập tức” phù hợp mọi hệ thống phân tán.

## 20. Kiểm thử security và failure modes

### 20.1. Ma trận kiểm thử

| Test case | Kết quả mong đợi |
| --- | --- |
| Đúng recipient public key, đúng manifest và policy | Recipient unwrap/import được key theo quyền |
| Dùng public key giả nhưng cùng tên alias | Trust validation từ chối |
| Sender chưa được phê duyệt tạo một package hợp lệ về RSA | Receiver không chấp nhận vì thiếu sender authorization |
| Tamper một bit wrapped DEK | Unwrap thất bại bởi cơ chế integrity/padding |
| Tamper manifest recipient/tenant/purpose | Signature/AEAD/context hoặc policy từ chối |
| Thay wrapping algorithm sang mode yếu | Không downgrade hay fallback |
| Package đã hết hạn | Từ chối theo freshness policy |
| Replay distribution ID đã nhận | Không cấp lại hoặc kích hoạt lần nữa trái policy |
| Key version v1 cũ hơn minimum accepted epoch | Từ chối rollback |
| Workload staging đọc prod secret | Bị IAM/KMS/secret manager từ chối |
| User không có quyền record nhưng biết key ID | Không giải mã hoặc được cấp DEK |
| Unwrap đúng KEK nhưng AAD tenant sai | Bị từ chối theo KMS context hoặc AEAD, không trả plaintext |
| Recipient certificate hết hạn hoặc không đúng identity | Không được tin theo chính sách |
| Key đã revoked nhưng cache còn bản cũ | Không chấp nhận operation bị cấm; báo drift |
| Rotation planned v1 → v2 | Bên gửi/bên nhận đồng bộ, có audit và cutover |
| Key compromised với overlap v1/v2 | Policy ưu tiên chặn v1, không kéo dài vô hạn |
| KMS outage/throttling | Fail closed, retry/backoff có giới hạn, không plaintext fallback |
| HSM non-exportable bị gọi export | API từ chối theo policy và key attributes |
| Backup restore trước thời điểm revoke | Không làm sống lại key/grants/trust đã thu hồi |
| Destruction khi còn dữ liệu cần mở | Dependency/retention preflight chặn hành động |

### 20.2. Đừng chỉ kiểm thử round-trip

Một phép thử **unwrap(wrap(DEK)) = DEK** chỉ kiểm tra chức năng cơ bản. Nó không chứng minh:

- Người gửi đã được xác thực.
- Public key thuộc đúng recipient.
- Gói không thể bị replay.
- Một principal chỉ được nhận DEK trong tenant của mình.
- Cơ chế rotation và revocation có hiệu lực ở các bên nhận.
- DR/backup không làm hồi sinh key cũ.

**Negative testing** cần chứng minh những trường hợp trái chính sách **bị từ chối**. Tương tự, hãy thực hiện **restore drills và key compromise exercises** để kiểm tra cả an toàn và khả dụng.

### 20.3. Khi lỗi không được trả bí mật vào message

Thất bại như sai certificate chain, key ID không đúng, KMS AccessDenied, GCM tag sai hoặc một package đã dùng nên tạo **lỗi có thể điều tra qua correlation ID**. Không in key bytes, password, plaintext hoặc manifest có trường nhạy cảm lên exception message hoặc trace.

Không thay bảo vệ bằng cách tự động:

- Bỏ hostname/certificate verification.
- Từ chối RSA-OAEP rồi thử RSA không padding.
- Dùng raw DEK từ một file local không được quản lý.
- Bật key v1 đã revoked.
- Cho mọi environment dùng chung KMS key admin role.

Đây là những trường hợp **security downgrade khi lỗi**; cần thiết kế HA/DR, retry giới hạn và migration đúng từ trước.

## 21. Các anti-pattern thường gặp khi phân phối key

| Sai lầm | Hậu quả | Cách thiết kế an toàn hơn |
| --- | --- | --- |
| **Gửi raw KEK/DEK qua email hoặc chat** | Secret bị nhân bản, không kiểm soát người nhận và retention | KMS grants, wrapped key cho recipient đã xác thực hoặc kênh được phê duyệt |
| **Đưa production HMAC key vào source/CI artifact** | Lộ qua Git history, cache, registry hoặc log | Runtime secret manager, identity-based access và scanning |
| **Base64-encode key rồi gọi là encrypted** | Bất kỳ ai đọc Base64 đều lấy được raw key | AES-KW/KWP, AEAD, RSA-OAEP/HPKE hoặc KMS wrapping |
| **Tin public key nhận qua kênh không xác thực** | MITM/key substitution; DEK bị gửi cho attacker | PKI, trusted registry hoặc fingerprint được xác thực độc lập |
| **Coi RSA-OAEP wrap thành công là xác thực sender** | Attacker cũng tạo được package với public recipient key | mTLS, sender signature hoặc giao thức authenticated |
| **Dùng ECDH thuần túy không xác thực peer** | Bị MITM dù shared secret trông ngẫu nhiên | TLS 1.3, authenticated DH/HPKE mode phù hợp |
| **Dùng raw ECDH secret trực tiếp làm AES key** | Thiếu KDF, domain separation và transcript binding | HKDF/key schedule của giao thức |
| **Cùng secret cho Sign, MAC, Encrypt và Wrap** | Mở rộng blast radius, khó rotation và audit | Tách key usage và policy |
| **Phát một MAC key chung cho tất cả đối tác** | Một đối tác bị lộ gây ảnh hưởng các đối tác khác | Key riêng theo partner/tenant và phiên bản |
| **Trao private signing key cho mọi verifier** | Verifier có thể ký giả | Chỉ công bố public verification key; giữ private trong KMS/HSM |
| **Cho browser nhận production KEK để decrypt** | Client không phải trust boundary của server key | Server-side authorization hoặc E2EE với mô hình key riêng |
| **Dùng một tài khoản KMS admin cho mọi service** | Bị chiếm một workload ảnh hưởng mọi key | Least privilege theo principal/key/purpose/tenant |
| **Dùng key ID/alias do client tự nhập để cấp quyền** | Cross-tenant/cross-environment access | Allowlist và policy theo resource ownership đã xác thực |
| **Không ràng buộc manifest với wrapped key** | Attacker tráo recipient/tenant/algorithm hoặc blob | Signed manifest/AEAD context và canonical encoding |
| **Chỉ có expiresAt, không chống replay** | Gói cũ vẫn có thể được phát lại trong cửa sổ | Unique distribution ID, idempotency, used/revoked state |
| **Cho phép fallback sang thuật toán cũ bất cứ khi nào lỗi** | Downgrade attack và policy bypass | Chỉ chấp nhận version/algorithm được duyệt, fail closed |
| **Xác nhận “distributed” ngay khi API trả 200** | Recipient chưa nhận/nhập key hoặc nhập sai scope | Ack, post-import checks và negative tests |
| **Lưu plaintext DEK cache vô hạn** | Revoke KMS không chặn được bản cache | Giới hạn TTL/usage/bytes và invalidation |
| **Coi TLS là đủ để bảo vệ raw secret suốt vòng đời** | Secret còn trong logs, heap, backup và endpoint | Secret lifecycle, memory hygiene, storage/retention policy |
| **Rewrap khi raw DEK đã compromised rồi báo an toàn** | Attacker vẫn dùng DEK cũ với ciphertext cũ | DEK mới/re-encrypt và điều tra dữ liệu đã lộ |
| **Xoay KEK và nghĩ nonce budget của DEK reset** | Có thể vượt giới hạn an toàn của AEAD | Theo dõi usage theo chính DEK |
| **Cấp lại v1 sau khi v1 đã revoked do compromise** | Đối thủ tiếp tục giả mạo/giải mã | Emergency revocation, phân phối v2 và chặn v1 |
| **Không kiểm tra backup/DR trước khi hủy KEK** | Khôi phục dữ liệu lịch sử thất bại | Dependency inventory, migration, restore test, retention |
| **Ghi raw secret vào audit để “có bằng chứng”** | Audit trở thành kênh lộ khóa | Log key ID/version, actor, operation, result và incident ID |

## 22. Checklist thiết kế phân phối key an toàn

Trước khi triển khai một luồng cấp khóa cho production, cần trả lời được:

1. **Đối tượng:** Đang phân phối public key, symmetric DEK, KEK, MAC key, private signing key hay chỉ key handle/quyền sử dụng?
2. **Mục tiêu:** Key cần dùng cho Encrypt/Decrypt, Wrap/Unwrap, Sign/Verify, MAC hay key agreement?
3. **Chủ sở hữu:** Có owner, recipient, issuer, environment, tenant, purpose và application/data classification?
4. **Nguồn sinh:** Key material được tạo bằng CSPRNG/KMS/HSM phù hợp, đúng thuật toán/độ mạnh, không seed yếu?
5. **Xuất khóa:** Có thật sự cần đưa raw secret ra ngoài? Có thể cấp key handle, KMS grant hoặc wrapped DEK thay thế không?
6. **Xác thực recipient:** Public key/certificate/endpoint của bên nhận được kiểm tra bằng trust source nào?
7. **Xác thực sender:** Bên nhận làm sao biết key package được cấp bởi đúng issuer có thẩm quyền, không chỉ bởi người biết public key?
8. **Kênh:** TLS/mTLS hoặc giao thức được duyệt có kiểm tra peer identity và cấu hình an toàn không?
9. **Wrapping mechanism:** AES-KW/KWP, AEAD, RSA-OAEP, HPKE hay KMS-managed có được cấu hình và giới hạn đúng?
10. **KDF/giao thức:** Nếu dùng DH/X25519, có authenticated handshake, HKDF, transcript binding và key separation không?
11. **Manifest:** Có format/version, key ID, recipient, issuer, key purpose, algorithm, expiry và policy version?
12. **Integrity/binding:** Wrapped key được liên kết đúng metadata bằng signed manifest, AEAD hoặc authenticated context phù hợp?
13. **Anti-replay:** Có unique distribution ID, clock policy, trạng thái used/revoked và cách chống rollback?
14. **IAM:** Workload chỉ được Wrap/Unwrap/Sign/ReadSecret đúng key và phạm vi; quyền admin/export/delete tách biệt?
15. **Authorization nghiệp vụ:** User hoặc service có quyền với record/tenant thực tế trước khi nhận DEK hay không?
16. **Public-key distribution:** Có PKI/JWKS/trust registry đáng tin cậy, xác minh issuer/hostname/algorithm và key rotation?
17. **Environment:** Dev/test/staging không tự dùng production secrets, ngoại lệ DR có phê duyệt riêng?
18. **Thiết bị nhận:** Browser/mobile/partner/offline có mô hình bảo vệ và giới hạn khả năng giữ bí mật thực tế?
19. **Storage tại đích:** Raw key có bị ghi vào Git, build, logs, heap dumps, local files hoặc cache vượt policy không?
20. **Rotation:** Có kế hoạch phân phối v2, acknowledgement, cutover, kiểm soát overlap và xử lý v1?
21. **Revocation:** Khi key bị lộ, có thể chặn grant/use/trust tại các bên nhận và thu thập negative-test evidence?
22. **Rewrap/re-encrypt:** Khi đổi KEK có biết trường hợp nào chỉ rewrap được và khi nào phải thay DEK/mã hóa lại?
23. **Data lifecycle:** Key ID/version và quan hệ KEK → DEK → ciphertext có được đưa vào inventory?
24. **Backup/DR:** Có đường restore hợp lệ cho wrapped keys cũ, đồng thời không làm sống lại key revoked?
25. **Destruction:** Trước hủy có kiểm kê bản sao, dữ liệu còn cần, retention và các chấp thuận độc lập?
26. **Audit:** Có distribution ID, issuer/recipient, key reference, approval, timestamps, result và incident links mà không chứa raw secret?
27. **Testing:** Đã thử public key giả, wrong recipient, replay, algorithm downgrade, cross-tenant, KMS outage, stale cache và DR restore?
28. **Monitoring:** Có cảnh báo key export bất thường, unauthorized grants, version drift và recipients chưa xác nhận?
29. **Incident:** Có contacts, runbook, phân biệt raw key exposure với lạm dụng key API và tiêu chí đóng sự cố?
30. **Review:** Chính sách được rà soát theo thay đổi công nghệ, provider, thuật toán, mô hình đe dọa và yêu cầu nghiệp vụ?

## 23. Ghi nhớ

- **Phân phối key an toàn không chỉ là truyền bytes qua HTTPS.** Phải xác thực sender/recipient, kiểm tra quyền, bảo vệ bí mật, toàn vẹn, ngữ cảnh, freshness và vòng đời.
- **Public key không phải secret nhưng phải được xác thực nguồn.** PKI, JWKS, trust registry hoặc pinning đúng cách giúp chống thay khóa giả; parse public key thành công chưa đủ.
- **Key transport, key agreement và key derivation khác nhau.** RSA-OAEP/AES-KW bọc key, ECDH/X25519 thiết lập shared secret và HKDF/key schedule dẫn xuất keys theo giao thức.
- **KMS/HSM và secret manager** giúp cấp key hoặc quyền theo workload identity, nhưng không tự thay application authorization hoặc bảo vệ mọi bản sao secret tại endpoint.
- **Wrapped DEK không phải raw DEK**; envelope encryption cho phép lưu encrypted data key cạnh ciphertext trong khi KEK được quản lý chặt. Raw DEK vẫn cần bảo vệ khi được KMS trả tạm cho ứng dụng.
- **RSA-OAEP bảo vệ key cho đúng recipient đã xác thực, không tự chứng minh sender**. Khi cần nguồn gốc và chống tráo/replay, dùng signed manifest hoặc giao thức authenticated phù hợp.
- **Rotation, revocation và destruction** phải đồng bộ với recipients, key versions, caches, IAM, PKI/JWKS và DR. Rewrap DEK không giống re-encrypt payload.
- **Không có cơ chế thu hồi nào xóa được raw key đã nằm trong tay attacker**. Phải phân tích phạm vi, thay key và xử lý ciphertext/chữ ký phụ thuộc.
- **Audit và negative tests** giúp chứng minh khóa đã tới đúng nơi, đúng quyền, và key cũ không còn được dùng trái chính sách.

Khi thiết kế **phân phối key an toàn**, hãy luôn trả lời ba câu hỏi: **“Ai thực sự có quyền nhận hoặc sử dụng khóa này?”, “Làm sao chứng minh khóa tới đúng đối tượng, đúng mục đích mà không bị thay đổi hoặc phát lại?”, “Khi phải xoay vòng, thu hồi hoặc hủy, chúng ta biết chính xác những bản sao, phiên bản và dữ liệu nào đang phụ thuộc vào khóa đó không?”** Một hệ thống trả lời được bằng **chính sách, kiến trúc KMS/HSM, inventory, kiểm soát truy cập và bằng chứng kiểm thử** mới thực sự có quy trình phân phối khóa an toàn.


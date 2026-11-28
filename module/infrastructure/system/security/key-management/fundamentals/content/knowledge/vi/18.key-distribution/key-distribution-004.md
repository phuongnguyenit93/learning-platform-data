# Authenticated distribution – Phân phối khóa có xác thực nguồn và bên nhận

**Authenticated distribution (phân phối khóa có xác thực)** là quá trình **chuyển giao hoặc cung cấp khả năng sử dụng vật liệu khóa/khóa công khai cho đúng chủ thể**, trong đó bên nhận có thể xác minh **nguồn phát hành hoặc đối tác**, kiểm tra **tính toàn vẹn**, ràng buộc khóa với **danh tính, mục đích, phạm vi và phiên bản** đã được phê duyệt. Với **khóa bí mật**, còn phải bảo vệ **tính bí mật khi truyền**, tránh chuyển nhầm người nhận và giới hạn khả năng sử dụng sau khi cấp phát.

Bài thuộc chương **Key distribution** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Chủ đề liên quan trực tiếp đến vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy khóa**, đồng thời kết nối **mật mã đối xứng, bất đối xứng, chữ ký số, PKI/TLS, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán**.

> **Điểm cốt lõi:** Một khóa được tạo ngẫu nhiên tốt và lưu trong HSM vẫn có thể bị sử dụng sai nếu **đường phân phối cho phép tráo khóa, đánh lừa danh tính người nhận, phát lại phiên bản đã thu hồi hoặc cấp khóa cho principal không có quyền**. Phân phối an toàn phải xác thực **đúng đối tượng và ngữ cảnh**, không chỉ “gửi qua kết nối HTTPS”.

## 1. “Phân phối khóa” thực sự có nghĩa là gì?

Trong hệ thống thực tế, “phân phối khóa” có thể chỉ nhiều hoạt động khác nhau:

1. **Phát hành public key** của một signer để những hệ thống khác xác minh chữ ký số.
2. **Cấp phát DEK đối xứng** đã được KMS sinh cho một workload được phép mã hóa dữ liệu.
3. **Chuyển wrapped DEK** cùng ciphertext sang một kho lưu trữ hoặc môi trường khôi phục.
4. **Cấp quyền sử dụng private key non-exportable** thông qua API Sign/Decrypt của KMS/HSM, **không chuyển bytes khóa**.
5. **Thiết lập khóa phiên** qua giao thức xác thực như TLS 1.3/mTLS, trong đó các bên dẫn xuất shared traffic secrets chứ không gửi plaintext session key.
6. **Nhập hoặc di chuyển key material** giữa HSM/KMS bằng cơ chế secure import/export, key wrapping hoặc recovery được nhà cung cấp hỗ trợ.

Các trường hợp trên có mức bảo vệ khác nhau. Một **public key** không cần giữ bí mật, nhưng phải kiểm tra **nguồn và danh tính**. Một **DEK rõ** là bí mật, nên phải kiểm soát cả **đường truyền, bên nhận, runtime, quyền và thời gian tồn tại**. Với private key được thiết kế **non-exportable**, giải pháp tốt nhất thường là **không phân phối vật liệu khóa**, mà phân phối **quyền gọi phép toán có kiểm soát**.

### 1.1. Năm thuộc tính bảo mật cần phân biệt

| Thuộc tính | Câu hỏi bảo mật | Ví dụ |
| --- | --- | --- |
| **Origin authenticity** | Khóa thực sự được phát hành bởi chủ thể đáng tin nào? | Ledger biết public key S2 là của Payment Service, không phải của attacker. |
| **Integrity** | Key material, ID, version và metadata có bị thay đổi trên đường đi? | Manifest ký số bao phủ cả public key bytes và tenant/purpose. |
| **Recipient authorization/binding** | Người nhận có được phép nhận hoặc dùng đúng khóa đó không? | Worker A không được unwrap DEK của tenant B. |
| **Confidentiality** | Với secret, người nghe lén có lấy được key bytes hay không? | TLS với xác thực đúng, hoặc key wrapping theo người nhận. |
| **Freshness/anti-replay** | Đây có phải phiên bản đang hợp lệ, không phải bản cũ bị phát lại? | Verifier không nhận lại public signing key S1 đã bị thu hồi. |

Ngoài ra cần **availability và auditability**: hệ thống phải biết xử lý khi KMS/PKI gặp lỗi và điều tra được **ai phát hành, ai nhận, đã dùng key version nào, khi nào và theo quyền nào**.

**Integrity không đồng nghĩa authenticity.** Checksum SHA-256 của một public key giúp phát hiện thay đổi so với một giá trị tham chiếu **đã tin**, nhưng attacker có thể thay cả key lẫn checksum nếu nguồn tham chiếu không được xác thực. Tương tự, mã hóa kênh không bảo đảm danh tính nếu ứng dụng chấp nhận chứng chỉ máy chủ giả.

## 2. Threat model cho đường phân phối

Một đường phân phối cần chống những nguy cơ sau.

| Mối đe dọa | Kịch bản | Kiểm soát quan trọng |
| --- | --- | --- |
| **Man-in-the-Middle (MITM)** | Attacker chèn public key của họ vào luồng thiết lập khóa. | TLS/PKI xác thực đúng danh tính hoặc giao thức AKE có xác thực peer. |
| **Key substitution** | Public key trong registry/JWKS bị thay thành key khác. | Chữ ký manifest/trust anchor, quyền xuất bản, audit và kiểm tra issuer. |
| **Unknown key-share / identity misbinding** | Hai bên có chung secret nhưng hiểu sai danh tính đối tác. | Ràng buộc transcript, identities, roles và protocol context trong key schedule. |
| **Replay / rollback** | Đưa lại key version cũ từng hợp lệ sau khi rotate/revoke. | Version monotonic, expiry, issuer state, revocation và nguồn thời gian tin cậy. |
| **Cross-tenant distribution** | DEK hoặc wrapped DEK của tenant A được cấp cho tenant B. | IAM/KMS context + application authorization + metadata integrity. |
| **Key export abuse** | Workload có thể lấy KEK/private signing key không cần thiết. | Non-exportable/key usage policy, chỉ cấp thao tác Sign/Unwrap. |
| **Compromised issuer** | Registry/authority thực sự bị chiếm quyền và phát hành key độc hại. | Tách nhiệm vụ, bảo vệ signing key, alert, recovery root/trust update. |
| **Key leakage in observability** | Log KMS response chứa plaintext DEK. | Không log secret, schema audit allowlist và kiểm soát APM/CI. |
| **Dependency/DR failure** | Key version mới được cấp phát nhưng không có khả năng phục hồi. | Inventory, provider recovery, kiểm thử restore và đồng bộ dữ liệu/metadata. |

**Phạm vi kiểm soát phải theo threat model.** Một ứng dụng nội bộ chỉ cần verify public key release có nhu cầu khác dịch vụ phân phối DEK cho nhiều tenant hoặc HSM migration giữa hai miền quản trị.

### 2.1. Phân biệt “đúng kênh” và “đúng chủ thể”

Một kết nối TLS được mã hóa chỉ bảo vệ chống nghe lén và sửa đổi **nếu client xác minh đúng chứng chỉ/tên máy chủ, certificate chain và giao thức**. Nếu developer tắt certificate validation, `trust-all` hoặc hostname verification, attacker có thể tạo một kết nối được mã hóa **đến chính họ**.

**mTLS** có thể xác thực cả máy khách và máy chủ ở lớp vận chuyển. Tuy nhiên **mTLS không tự quyết định service X có được nhận DEK của tenant Y không**; ứng dụng và KMS vẫn phải kiểm tra resource/operation/purpose tương ứng.

## 3. Phân phối public key và secret key không giống nhau

| Đối tượng | Có cần giữ bí mật khi phân phối? | Bắt buộc chú ý |
| --- | --- | --- |
| **Public key để Verify** | Không. | Nguồn đáng tin, issuer, algorithm, key usage, version, validity, revocation và chống tráo/rollback. |
| **Public encryption/KEM key** | Không về bí mật. | Phải ràng buộc public key với đúng danh tính người nhận trước khi encrypt/encapsulate. |
| **Private signing/decryption key** | **Có**; thường **không nên xuất**. | HSM/KMS custody, secure backup/transfer khi được phê duyệt; giới hạn API Sign/Decrypt. |
| **Symmetric DEK/HMAC/PSK** | **Có**. | Kênh bảo mật, recipient-bound wrapping hoặc AKE/KDF; quyền/retention phù hợp. |
| **KEK/root key** | **Có, rủi ro cao**. | Ưu tiên non-exportable KMS/HSM, strict separation of duties và recovery policy. |
| **Wrapped DEK** | Đã được bảo vệ nhưng vẫn cần kiểm soát. | Authenticated wrap, context, key ref/version, integrity, quyền Unwrap và DR. |
| **KMS key ID/alias** | Thường không bí mật. | ID là metadata, không phải authorization; alias có thể đổi theo vòng đời. |
| **Chứng chỉ X.509/JWKS** | Thường công khai. | Kiểm tra provenance/chain/trust, không chấp nhận key do request tự khai. |

Với **public key distribution**, trọng tâm là **nguồn và tính hợp lệ hiện tại**. Với **secret-key distribution**, phải có cả **confidentiality, origin authenticity và recipient authorization**, đồng thời hạn chế nơi secret xuất hiện.

**Không dùng cùng private signing key cho việc “phân phối” sang mọi container** chỉ vì nhiều dịch vụ cần Verify. Các verifier chỉ cần public key được xác thực; private key nên ở miền signing được bảo vệ.

## 4. Các mô hình phân phối có xác thực

### 4.1. PKI và chứng chỉ cho danh tính public key

Trong **Public Key Infrastructure (PKI)**, một CA tin cậy ký chứng chỉ ràng buộc **public key** với thông tin danh tính, thời hạn và thuộc tính sử dụng. Client phải xác minh chain, tên miền/danh tính đích, key usage và trạng thái tin cậy theo chính sách.

~~~mermaid
flowchart LR
    CA["CA/trust anchor được cấu hình tin cậy"] --> CERT["Chứng chỉ: subject/identity + public key"]
    CERT --> SERVER["Máy chủ TLS"]
    CLIENT["Client có trust store và expected identity"] --> CHECK["Verify chain, identity, validity, usage"]
    SERVER --> CHECK
    CHECK --> SESSION["TLS handshake xác thực + traffic keys"]
~~~

**Chứng chỉ không tự biến mọi dữ liệu public key thành đáng tin.** Nếu CA/trust anchor sai, subject không khớp, issuer bị thu hồi hoặc ứng dụng bỏ qua kiểm tra hostname, tính xác thực đích bị phá vỡ.

**Không pin một chứng chỉ vĩnh viễn mà không có kế hoạch rotation.** Pinning có thể phù hợp ở một số hệ thống, nhưng cần chính sách chuyển trust, backup pins và xử lý revoke.

### 4.2. JWKS/key registry cho khóa xác minh chữ ký

Một signer có thể công bố public key qua **JWKS** hoặc key registry, thường với `kid` để tìm key. Hệ thống nhận không được:

- Chấp nhận **JWKS URL tùy ý từ token** (ví dụ `jku`) mà thiếu policy tin cậy.
- Cho `kid` từ payload quyết định một **nguồn key ngoài allowlist**.
- Dùng public key nằm ngay trong request làm bằng chứng cho chính request đó.
- Bỏ qua `issuer`, `audience`, thuật toán, key usage, thời hạn và trạng thái revoke.

JWKS qua HTTPS **có thể** đủ trong một mô hình đã ghim **issuer URL đáng tin** và xác thực TLS đúng; ở mô hình khác cần **signed metadata** hoặc key transparency/approval độc lập. **Một chữ ký hợp lệ với key attacker tự cung cấp không chứng minh danh tính signer**.

### 4.3. TLS 1.3/mTLS cho giao tiếp dịch vụ

Trong một handshake TLS 1.3, các bên thường dùng key exchange tạm thời, transcript authentication và key schedule để tạo traffic secrets. **Không phải gửi một “AES session key” rõ từ server sang client**.

- **Server-auth TLS:** client xác thực máy chủ; server không nhất thiết xác thực danh tính client bằng chứng chỉ.
- **mTLS:** hai bên có thể xác thực bằng chứng chỉ theo chính sách; application authorization vẫn cần thiết.
- **Ephemeral Diffie–Hellman (DHE/ECDHE):** khi dùng đúng giao thức được đánh giá, đóng góp cho forward secrecy; bản thân trao đổi public values **không xác thực** nếu đứng riêng.
- **HKDF/key schedule:** dẫn xuất khóa theo transcript/context và secrets; không dùng hash một mật khẩu yếu như thể nó là shared secret đủ entropy.

**Không tự thiết kế “X25519 + AES-GCM + chữ ký” từ vài API rời rạc** để thay TLS. Một giao thức authenticated key exchange (AKE) cần kiểm soát danh tính, transcript, algorithm negotiation, key confirmation, replay và các thuộc tính khác.

### 4.4. KMS/HSM cấp quyền dùng khóa thay vì xuất khóa

Với private signing key hay KEK:

~~~text
Application --(workload identity + IAM + key reference)--> KMS/HSM
Application <--(chữ ký / encrypted DEK / kết quả được phép)-- KMS/HSM

Private signing key hoặc KEK không cần rời KMS/HSM.
~~~

Cơ chế này **phân phối khả năng sử dụng khóa**, không nhất thiết phân phối vật liệu khóa. Nó giúp giảm bản sao bí mật, nhưng quyền `Sign` hoặc `Decrypt` bị cấp quá rộng vẫn có thể bị lạm dụng nếu workload bị chiếm quyền.

## 5. Những điều kiện xác thực phải ràng buộc với một khóa

Không nên xem một public key hoặc wrapped DEK là “đủ thông tin” nếu thiếu ngữ cảnh.

### 5.1. Định danh các bên và purpose

Một bản phân phối có thể cần những thành phần:

| Thành phần | Chức năng |
| --- | --- |
| **Issuer/distributor ID** | Ai có thẩm quyền phát hành key material/metadata? |
| **Audience/recipient ID** | Khóa được gửi hoặc công bố cho đối tượng nào? |
| **Tenant/namespace** | Phạm vi dữ liệu được phép dùng khóa. |
| **Purpose/key usage** | Verify release, Sign event, Wrap DEK, Decrypt invoice... |
| **Algorithm/suite** | Ed25519, AES-GCM, RSA-PSS... theo allowlist. |
| **Key ID/version** | Định vị key và lineage/rotation; không thay quyền. |
| **Validity window** | `notBefore`, `expiresAt` và chính sách cryptoperiod. |
| **Revocation state** | Khóa có đang bị thu hồi/vô hiệu hóa bởi nguồn tin cậy? |
| **Provider/format** | SPKI, X.509, JWK hoặc wrapped blob format được hỗ trợ. |
| **Distribution event ID** | Truy vết, chống replay và audit theo workflow. |

**Một key ID giống nhau chưa đủ** để hai hệ thống xác định đang nói về cùng vật liệu khóa. Alias có thể trỏ tới phiên bản mới; một key ID do attacker tự khai không có giá trị xác thực.

### 5.2. Domain separation và chống nhầm ngữ cảnh

Nếu một message ký số chỉ chứa raw public key bytes, có thể thiếu thông tin rằng đó là **key của Payment Service để xác minh sự kiện thanh toán**, thay vì key dùng cho release hoặc dịch vụ khác.

Một manifest được ký nên bao gồm **purpose, issuer, audience, tenant, algorithm, key ID, version, validity và chính bytes public key** theo canonical representation. Với secret/wrapped key, encryption context hoặc AAD phải ràng buộc dữ liệu và recipient/purpose phù hợp.

**Không dùng cùng key cho nhiều purpose chỉ vì tất cả đều “liên quan bảo mật”.** Ví dụ Ed25519 dùng Sign không phải X25519 dùng key agreement; KEK dùng Wrap không nên bị dùng như một HMAC key tùy tiện.

## 6. Phân phối DEK/KEK trong envelope encryption

**Envelope encryption** phân tách hai lớp:

- **DEK (Data Encryption Key)** mã hóa dữ liệu bằng AEAD, ví dụ AES-256-GCM.
- **KEK (Key Encryption Key)** bảo vệ DEK bằng wrap/encrypt key material.
- **Wrapped DEK** là bản DEK được bảo vệ, có thể lưu cùng ciphertext.
- **KMS/HSM** quản lý KEK và quyền Wrap/Unwrap, không cần xuất raw KEK.

~~~mermaid
sequenceDiagram
    participant App as Billing Service
    participant KMS as KMS/HSM
    participant DB as Database
    Note over App: Workload identity và authorization tenant/object
    App->>KMS: GenerateDataKey(approved KEK ref, context)
    KMS-->>App: Plaintext DEK tạm + wrapped DEK
    Note over App: AES-GCM encrypt với nonce riêng + AAD
    App->>DB: Ciphertext/tag + nonce + wrapped DEK + metadata
    Note over App: Hạn chế vòng đời DEK trong RAM; không log
    App->>DB: Đọc object đã có quyền
    DB-->>App: Ciphertext + wrapped DEK + key metadata
    App->>KMS: Unwrap/DecryptDataKey(blob, context)
    KMS-->>App: DEK tạm nếu IAM/context hợp lệ
    Note over App: Verify AES-GCM tag và quyền trước khi trả dữ liệu
~~~

**Phân phối có xác thực ở đây có hai điểm:** KMS chỉ cấp DEK/kết quả cho workload được xác thực và cho phép; ứng dụng chỉ sử dụng nó trên **đúng dữ liệu/tenant/purpose** theo chính sách. KMS IAM không tự biết quyền của user cuối nếu ứng dụng không truyền hoặc kiểm tra đúng ngữ cảnh.

### 6.1. Bảo vệ wrapped DEK khi lưu hoặc chuyển

| Yếu tố | Yêu cầu |
| --- | --- |
| **Authentic KEK reference** | Không cho client tùy ý chọn key ID hoặc key của tenant khác. |
| **Wrap algorithm/API** | Dùng KMS/HSM wrap/unwrap có kiểm tra toàn vẹn theo cơ chế được duyệt. |
| **Encryption context** | Ràng buộc tenant, object, purpose nếu provider hỗ trợ; giá trị thường không bí mật. |
| **Key version** | Giữ khả năng truy đúng KEK/material version cũ khi rotate hoặc restore. |
| **AAD dữ liệu** | Ràng buộc ciphertext AES-GCM với context ổn định; verify tag khi decrypt. |
| **Recipient authorization** | Cả KMS policy và ứng dụng phải kiểm soát ai được unwrap/đọc. |
| **Backup/DR** | Wrapped DEK, ciphertext, metadata và đường phục hồi KEK phải nhất quán. |
| **Audit** | Ghi actor, key ref/version, operation và outcome, không ghi raw DEK/KEK. |

**Wrapped DEK không phải secret rõ**, nhưng không có nghĩa có thể đưa toàn bộ blob vào log hoặc chuyển tùy tiện qua mọi tenant. Nó có thể chứa metadata và tạo thêm bản sao của vật liệu cần được quản lý.

### 6.2. Khi người nhận là vùng DR hoặc dịch vụ khác

Nếu một workload khác cần giải mã dữ liệu, không mặc định cấp quyền Decrypt trên KEK production chung. Có các hướng thiết kế:

1. **Cấp quyền Unwrap có giới hạn** cho đúng workload/key family/tenant qua KMS theo chính sách.
2. **Re-wrap DEK** sang KEK của miền nhận thông qua thao tác KMS/HSM được phép.
3. **Dẫn xuất hoặc sinh DEK mới và re-encrypt dữ liệu** nếu mục tiêu cần thay chính DEK.
4. Dùng **secure import/export hoặc HSM-backed transfer** khi provider hỗ trợ và yêu cầu đặc biệt.

**Re-wrap cùng DEK không thay ciphertext dữ liệu**. Nhưng nếu **DEK đã bị lộ**, việc re-wrap dưới KEK khác không làm dữ liệu cũ an toàn trở lại.

### 6.3. Không chuyển raw KEK giữa các ứng dụng

Nếu một KMS/HSM giữ KEK **non-exportable**, thiết kế không nên có bước “export KEK để đưa cho application”. Các ứng dụng chỉ cần dùng API Wrap/Unwrap hoặc nhận DEK tạm trong ranh giới được phê duyệt.

**Non-exportable không đồng nghĩa không thể bị lạm dụng**: một principal có quyền Unwrap trên nhiều wrapped DEK có thể truy cập dữ liệu lớn. IAM và **data authorization** vẫn là bắt buộc.

## 7. Phân phối public key bằng manifest có chữ ký

Khi nhiều verifier phải tin public key mới của Payment Service, một phương án là **signer/distributor đáng tin phát hành signed key manifest**.

~~~mermaid
flowchart TD
    OWNER["Security/Key owner phê duyệt key S2"] --> REG["Trust registry/issuer"]
    REG --> SIGN["Ký manifest: issuer, audience, purpose, keyId, version, expiry, SPKI"]
    SIGN --> CDN["HTTPS registry / distribution endpoint"]
    CDN --> VERIFY["Ledger kiểm tra chữ ký bằng trust anchor đã biết"]
    VERIFY --> CHECK["Kiểm issuer/audience/tenant/algorithm/expiry/version/revocation"]
    CHECK --> STORE["Ghi trust state mới atomically"]
    STORE --> USE["Verify chữ ký Payment bằng public key S2"]
~~~

Chữ ký giúp bảo vệ **nguồn gốc và toàn vẹn nội dung manifest** nếu verifier đã biết và tin **distribution signing key** từ trước. **Không gửi public key dùng xác minh manifest ngay trong gói rồi tự tin nó**; đó là vòng phụ thuộc tin cậy.

### 7.1. Trust bootstrap từ đâu?

Có thể dùng:

- **PKI/trust store** đã cài theo quy trình đáng tin.
- **Distribution signing public key** được ghim qua cấu hình/triển khai được kiểm soát và có kế hoạch rotation.
- **Issuer URL** được ghim và HTTPS được xác minh đầy đủ, kết hợp chính sách issuer/JWKS; tùy rủi ro có thể thêm signed metadata.
- **HSM/KMS-backed signing root** cùng cơ chế phê duyệt xuất bản và quản trị key registry.

**Trust anchor cần được cấp qua kênh có thẩm quyền độc lập với gói dữ liệu đang xác minh.** Nếu root signing key bị compromise, một chữ ký toán học hợp lệ không còn chứng minh được điều mong muốn; cần incident response và chuyển trust root theo phương án dự phòng.

### 7.2. Chữ ký hợp lệ chưa đủ

Sau Verify, phải kiểm:

- **Issuer** có đúng nguồn được cho phép không?
- **Audience** có đúng hệ thống nhận không?
- **Tenant và purpose** có khớp với quyền/ngữ cảnh không?
- **Algorithm và key usage** có nằm trong allowlist không?
- **Key version** có mới hơn phiên bản cuối được chấp nhận không?
- **Thời gian** có hợp lệ và đồng hồ của hệ thống đáng tin không?
- **Revocation**: khóa đã bị thu hồi sau khi manifest được ký chưa?
- **Authorization nghiệp vụ**: signer có quyền phát hành event đó hay không?

Một **signed manifest cũ từng đúng** vẫn có thể không hợp lệ **hiện tại**, đặc biệt sau sự cố private key bị lộ.

## 8. Java 17: xác minh signed public-key manifest trước khi nhận khóa

Ví dụ sau minh họa **đường phân phối public key có xác thực** bằng Java 17 JCA. Nó chỉ phân phối **public key Ed25519**, không vận chuyển raw private key, KEK hoặc DEK.

**Thiết kế minh họa:**

1. Distributor tạo manifest có **issuer, audience, tenant, purpose, key ID, version, validity và SPKI public key bytes**.
2. Distributor ký **canonical bytes** bằng private key phân phối có thẩm quyền.
3. Verifier kiểm chữ ký bằng **trust anchor đã biết từ trước**, không lấy trust anchor từ manifest.
4. Verifier kiểm issuer/audience/tenant/purpose, thuật toán, hiệu lực và **version monotonic**.
5. Chỉ sau đó mới tạo đối tượng `PublicKey` để cập nhật trust registry.

**Giới hạn:** Demo sinh trust anchor và khóa sử dụng mới ngay trong `main` để minh họa test. **Production phải lấy trust anchor từ PKI hoặc cơ chế provisioning đáng tin và giữ trạng thái version bền vững**. Chữ ký Ed25519 này là chữ ký trên manifest, **không phải một giao thức phân phối secret key**.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;
import java.time.Instant;
import java.util.Arrays;
import java.util.Objects;

public final class AuthenticatedKeyDistributionDemo {
    private static final String ISSUER = "trusted-payment-key-registry";
    private static final String AUDIENCE = "ledger-service";
    private static final String TENANT = "payments";
    private static final String PURPOSE = "payment-event-verify";
    private static final String ALGORITHM = "Ed25519";

    // Public-key manifest; byte[] cần defensive copy khi đi qua boundary.
    public record KeyManifest(
            String issuer,
            String audience,
            String tenant,
            String purpose,
            String keyId,
            String algorithm,
            long version,
            long notBeforeEpochSec,
            long expiresAtEpochSec,
            byte[] publicKeySpki) {

        public KeyManifest {
            Objects.requireNonNull(publicKeySpki);
            publicKeySpki = publicKeySpki.clone();
        }

        @Override public byte[] publicKeySpki() {
            return publicKeySpki.clone();
        }
    }

    public record SignedManifest(KeyManifest manifest, byte[] signature) {
        public SignedManifest {
            Objects.requireNonNull(manifest);
            Objects.requireNonNull(signature);
            signature = signature.clone();
        }

        @Override public byte[] signature() {
            return signature.clone();
        }
    }

    private static void writeField(DataOutputStream out, String field)
            throws Exception {
        Objects.requireNonNull(field);
        byte[] b = field.getBytes(StandardCharsets.UTF_8);
        if (b.length > 4096) {
            throw new SecurityException("Manifest field too long");
        }
        out.writeInt(b.length);
        out.write(b);
    }

    private static byte[] signedBytes(KeyManifest m) throws Exception {
        // Bản mã hóa xác định: prefix độ dài và thứ tự field cố định.
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        writeField(out, "key-distribution-manifest-v1");
        writeField(out, m.issuer());
        writeField(out, m.audience());
        writeField(out, m.tenant());
        writeField(out, m.purpose());
        writeField(out, m.keyId());
        writeField(out, m.algorithm());
        out.writeLong(m.version());
        out.writeLong(m.notBeforeEpochSec());
        out.writeLong(m.expiresAtEpochSec());
        byte[] spki = m.publicKeySpki();
        if (spki.length == 0 || spki.length > 512) {
            throw new SecurityException("Invalid public key encoding size");
        }
        out.writeInt(spki.length);
        out.write(spki);
        out.flush();
        return bytes.toByteArray();
    }

    // Chỉ để tạo dữ liệu demo. Private key này thuộc
    // distributor và KHÔNG được đưa tới verifier.
    private static SignedManifest signForDemo(
            KeyManifest manifest, PrivateKey distributionSigningKey)
            throws Exception {
        Signature signer = Signature.getInstance(ALGORITHM);
        signer.initSign(distributionSigningKey);
        signer.update(signedBytes(manifest));
        return new SignedManifest(manifest, signer.sign());
    }

    public static PublicKey verifyAndExtract(
            SignedManifest signed,
            PublicKey pretrustedDistributorPublicKey,
            long lastAcceptedVersion,
            Instant now) throws Exception {
        Objects.requireNonNull(signed);
        Objects.requireNonNull(pretrustedDistributorPublicKey);
        Objects.requireNonNull(now);

        KeyManifest m = signed.manifest();
        // Luôn xác minh bằng trust anchor đã tin từ ngoài bản nhận.
        Signature verifier = Signature.getInstance(ALGORITHM);
        verifier.initVerify(pretrustedDistributorPublicKey);
        verifier.update(signedBytes(m));
        if (!verifier.verify(signed.signature())) {
            throw new SecurityException("Untrusted key manifest signature");
        }

        if (!ISSUER.equals(m.issuer())
                || !AUDIENCE.equals(m.audience())
                || !TENANT.equals(m.tenant())
                || !PURPOSE.equals(m.purpose())
                || !ALGORITHM.equals(m.algorithm())
                || m.keyId() == null || m.keyId().isBlank()) {
            throw new SecurityException("Wrong key distribution scope");
        }

        long timestamp = now.getEpochSecond();
        if (m.version() <= lastAcceptedVersion
                || m.notBeforeEpochSec() >= m.expiresAtEpochSec()
                || timestamp < m.notBeforeEpochSec()
                || timestamp >= m.expiresAtEpochSec()) {
            throw new SecurityException("Expired or replayed key manifest");
        }

        // Chỉ parse public key sau khi đã xác minh provenance và scope.
        PublicKey candidate = KeyFactory.getInstance(ALGORITHM)
                .generatePublic(new X509EncodedKeySpec(m.publicKeySpki()));

        // Production: chỉ cập nhật registry khi version mới hơn
        // qua transaction/CAS; kiểm tra revocation và policy hiện hành.
        return candidate;
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance(ALGORITHM);
        KeyPair distributor = gen.generateKeyPair(); // Demo trust anchor
        KeyPair paymentSigner = gen.generateKeyPair(); // Key được phát hành

        Instant now = Instant.now();
        KeyManifest manifest = new KeyManifest(
                ISSUER, AUDIENCE, TENANT, PURPOSE,
                "payment-signing-s2", ALGORITHM, 2L,
                now.minusSeconds(60).getEpochSecond(),
                now.plusSeconds(3600).getEpochSecond(),
                paymentSigner.getPublic().getEncoded());

        SignedManifest signed = signForDemo(
                manifest, distributor.getPrivate());

        // Ở production, không lấy trust anchor từ chính manifest.
        PublicKey accepted = verifyAndExtract(
                signed, distributor.getPublic(), 1L, now);

        System.out.println("Accepted public key algorithm: "
                + accepted.getAlgorithm());

        // Kiểm thử: giả mạo metadata/audience nhưng giữ chữ ký cũ.
        KeyManifest tampered = new KeyManifest(
                ISSUER, "attacker-audience", TENANT, PURPOSE,
                manifest.keyId(), ALGORITHM, 2L,
                manifest.notBeforeEpochSec(),
                manifest.expiresAtEpochSec(),
                manifest.publicKeySpki());
        try {
            verifyAndExtract(new SignedManifest(
                    tampered, signed.signature()),
                    distributor.getPublic(), 1L, now);
            throw new AssertionError("Tampering was not rejected");
        } catch (SecurityException expected) {
            System.out.println("Tampered manifest rejected");
        }

        // Không in private key, seed, DEK hoặc secret vào log.
    }

    private AuthenticatedKeyDistributionDemo() {}
}
~~~

### 8.1. Vì sao cách kiểm tra có ý nghĩa?

- **Không tin key tự khai:** distributor public key là **trust anchor từ ngoài gói**, không được chấp nhận vì nằm trong manifest.
- **Chữ ký bao phủ toàn bộ ngữ cảnh:** thay issuer/audience/tenant/purpose/ID/version/SPKI sẽ khiến Verify thất bại.
- **Canonical encoding:** mỗi field có prefix độ dài, tránh nhập nhằng khi nối chuỗi như `"ab"+"c"` và `"a"+"bc"`.
- **Định dạng khóa công khai:** SPKI (`X509EncodedKeySpec`) được parse sau khi manifest đã được xác thực.
- **Chống rollback cơ bản:** version mới phải lớn hơn `lastAcceptedVersion`; giá trị này **phải đến từ state tin cậy và được lưu bền vững**.
- **Kiểm soát validity:** chỉ nhận manifest trong cửa sổ thời gian được phép.
- **Defensive copy:** các `byte[]` public key/signature được clone qua record boundary.
- **Không có secret transport:** private key được dùng để ký và không nằm trong manifest, verifier chỉ nhận public key.

### 8.2. Những phần bắt buộc bổ sung trước production

Ví dụ **không phải giao thức chuẩn để tự triển khai thành dịch vụ phân phối khóa sản xuất**. Cần một giải pháp PKI/JWKS/registry đáng tin hoặc signed metadata đã được đánh giá, cùng:

1. **Trust-anchor provisioning và rotation:** CA hoặc distribution signing key phải được cấp phát, bảo vệ, thay thế và thu hồi theo cơ chế độc lập.
2. **Persistent monotonic state:** cập nhật `lastAcceptedVersion` bằng **CAS/transaction**, không để hai request cạnh tranh làm rollback hoặc mất cập nhật.
3. **Revocation và issuer state:** bản manifest còn hạn vẫn phải bị từ chối nếu key/issuer đã compromised hoặc bị thu hồi.
4. **Key selection:** `keyId` phải gắn với đúng tenant, algorithm, usage, issuer và verifier policy.
5. **Trusted time:** lệch đồng hồ/availability phải được xử lý theo yêu cầu dịch vụ; không tự bỏ qua expiry khi gặp lỗi.
6. **Request authentication và authorization:** xác định bên phát hành và bên nhận theo chuẩn giao thức, không chỉ verify signature của một blob.
7. **Transport security:** HTTPS/TLS xác thực đúng endpoint vẫn cần cho availability, metadata privacy và các operation khác.
8. **Replay controls:** version monotonic hữu ích nhưng chưa giải quyết mọi trường hợp phát lại cùng version hoặc khi nhiều key IDs đồng thời; có thể cần distribution event ID và state theo key family.
9. **Audit:** keyRef, issuer, audience, version, decision và request ID; không log private key hay sensitive payload.
10. **DoS limits:** giới hạn kích thước, rate và thuật toán; bảo vệ quá trình tải/cập nhật key registry.
11. **Trust policy cụ thể:** không biến chữ ký manifest thành quyền phát hành tùy ý; approval và signing role cần tách biệt khi rủi ro yêu cầu.

**Điểm học quan trọng:** Một **chữ ký hợp lệ** chứng minh dữ liệu được ký bằng key tương ứng, còn **quyền được sử dụng public key đó** do trust anchor, issuer policy, thời điểm và ngữ cảnh quyết định.

## 9. Xác thực phía người nhận và key confirmation

Với **phân phối secret hoặc thiết lập khóa phiên**, không chỉ xác thực nguồn phát hành mà còn phải biết **bên nhận đúng là ai**.

### 9.1. Recipient binding

Một gói cấp phát DEK cho tenant A có thể cần:

- Định danh workload nhận từ **mTLS identity, service account hoặc IAM principal**.
- Định danh **tenant/namespace** và resource/dataset được phép.
- **Purpose/operation**: Encrypt, Decrypt, Unwrap hay GenerateDataKey.
- **Key reference/version** từ registry đáng tin.
- **Thời hạn/cryptoperiod**, audit và revocation policy.
- **Recipient-specific wrapping** hoặc KMS policy ngăn người nhận khác unwrap.

**Chỉ đưa `recipientId` vào JSON mà không xác thực caller** không có ý nghĩa bảo mật. Identity phải được ràng buộc bởi KMS/IAM hoặc giao thức đã đánh giá.

### 9.2. Key confirmation

Trong một số giao thức AKE, **key confirmation** chứng minh bên kia sở hữu hoặc có thể sử dụng cùng secret vừa được dẫn xuất. Điều đó không tự chứng minh danh tính nếu **handshake không gắn đúng peer identity**.

Một giao thức an toàn cần liên kết:

~~~text
peer identities + roles
       +
handshake transcript + negotiated algorithms
       +
ephemeral key shares + authenticated public keys
       |
       v
  KDF / key schedule
       |
       v
  traffic keys + key confirmation / channel binding
~~~

Không nên gửi **raw derived key** để “so sánh hai bên có cùng khóa hay không”. Dùng **key confirmation/finished messages** theo giao thức chuẩn.

### 9.3. Phòng chống unknown key-share và key-substitution

Ví dụ Alice và Bob cùng chia sẻ một secret sau trao đổi khóa nhưng Alice tưởng đang kết nối với Carol. **Chỉ có shared secret đúng chưa đủ**; giao thức phải xác thực danh tính hai đầu và ràng buộc vào transcript/KDF.

Đối với public signing key, cùng lỗi nhận dạng có thể xảy ra nếu Ledger nhận một public key thật nhưng gắn nó với **issuer hoặc tenant sai**. Kết quả Verify toán học hợp lệ nhưng quyết định nghiệp vụ sai.

## 10. Rotate, revoke và phân phối phiên bản mới

Một hệ thống có thể phân phối khóa đúng ở thời điểm phát hành nhưng vẫn bị **rollback** khi key đã thay hoặc bị thu hồi.

### 10.1. Trình tự chuyển signing key S1 → S2

1. Security/owner phê duyệt key mới và **purpose/algorithm**.
2. KMS/HSM tạo private/public key pair S2 từ nguồn entropy phù hợp.
3. Registry/issuer đáng tin công bố **public key S2 với key ID/version và validity**.
4. Verifiers tải/nhận S2 qua đường có xác thực, kiểm issuer/trust và sẵn sàng Verify.
5. Payment Service chuyển thao tác **Sign mới** sang S2.
6. Trong cửa sổ chuyển tiếp, verifiers có thể Verify S1/S2 theo policy và lịch sử.
7. Khi S1 bị compromise/revoke, cập nhật **trust và acceptance policy** thay vì chỉ chờ `expiresAt`.
8. Audit đối soát signer key version với các sự kiện/phát hành và ngừng chấp nhận hành vi mới ngoài policy.

**Một public key cũ từng hợp lệ không mặc nhiên được dùng cho chữ ký mới vô thời hạn**. Trạng thái revoke và chính sách tại thời điểm ký/kiểm tra phải được phân biệt.

### 10.2. Trình tự đổi KEK và phân phối wrapped DEK

Khi KEK v3 → v4:

- Các **new writes** nên dùng v4 theo policy.
- Wrapped DEK cũ có thể được **re-wrap dưới KEK v4** bằng KMS/HSM API đã được kiểm tra.
- Ứng dụng phải lưu đúng **wrapped DEK + key reference/version + context** một cách nhất quán.
- **DEK không đổi khi re-wrap thuần túy**, nên ciphertext dữ liệu thường không đổi nếu AAD được thiết kế ổn định.
- Các backup/snapshot lịch sử có thể còn cần v3; không destroy v3 cho tới khi dependencies được giải quyết.

**Nếu DEK đã bị lộ**, re-wrap không đủ; cần đánh giá DEK rotation và re-encryption.

### 10.3. Anti-rollback cho trust registry

Một registry cần có cách chống chấp nhận trạng thái cũ:

| Biện pháp | Mục đích | Giới hạn |
| --- | --- | --- |
| **Monotonic version** | Từ chối key publication cũ hơn state đã tin. | State phải bền vững và nhất quán; không dựa vào bản ghi do request cung cấp. |
| **Expiry/notBefore** | Giới hạn cửa sổ chấp nhận. | Không thay được revoke khẩn cấp. |
| **Current revocation feed** | Từ chối key bị compromise. | Nguồn revoke cũng cần xác thực/khả dụng. |
| **Transparency/append-only log** | Hỗ trợ phát hiện công bố key trái phép hoặc lịch sử bị sửa. | Cần quy trình giám sát/đối chiếu; không tự quyết định quyền nghiệp vụ. |
| **Atomic trust update** | Không tạo trạng thái partial giữa key và metadata. | Cần transaction/CAS thực tế. |
| **Issuer policy** | Hạn chế ai được phát hành key family/tenant nào. | Một authority bị compromise vẫn cần incident response. |

Một bản JWKS hoặc manifest được ký bằng nguồn từng đáng tin **có thể không được chấp nhận hiện tại** nếu issuer/key đã bị thu hồi. Không đồng nhất **tính toàn vẹn lịch sử** với **quyền sử dụng ở thời điểm hiện tại**.

## 11. BYOK, HSM migration và phân phối key material đặc quyền

**Bring Your Own Key (BYOK)** và di chuyển khóa giữa KMS/HSM là tình huống cần kiểm soát đặc biệt: vật liệu khóa có thể phải đi qua các ranh giới bảo mật khác nhau.

### 11.1. Trước khi chuyển khóa

Cần xác định:

1. **Nguồn sinh khóa/entropy** có đáng tin và còn an toàn không?
2. **Origin và ownership**: ai sở hữu material, ai giữ bản gốc hoặc backup?
3. **Key usage**: khóa được phép Encrypt/Decrypt/Wrap/Sign hay không?
4. **Exportability**: có được xuất theo loại key/provider/policy?
5. **Import/wrap mechanism**: provider cung cấp cơ chế secure import nào?
6. **Recipient authenticity**: wrapping public key/import token có đúng nguồn tin cậy của HSM/KMS đích không?
7. **Approval/quorum**: có yêu cầu nhiều người hoặc dual control không?
8. **Recovery/retention**: nếu imported material bị xóa/hết hạn thì sao?
9. **Audit**: ai export/import, key ref/version nào, result và bằng chứng nào?

**Không tự export plaintext KEK/private key** sang một file rồi đặt mật khẩu zip để “chuyển nhanh”. Nếu HSM non-exportable, phải dùng phương án provider-native được phê duyệt hoặc kiến trúc khác.

### 11.2. Key wrapping không tự xác thực người nhận

Mã hóa DEK cho một **recipient public key** chỉ an toàn nếu public key đó **thực sự thuộc recipient đã được xác thực**. Nếu attacker thay public key đích, dữ liệu có thể được wrap đúng toán học nhưng **chỉ attacker giải bọc được**.

Trình tự đúng phải gồm **xác thực recipient key/certificate hoặc import parameters**, kiểm tra purpose/key usage và policy trước khi gọi Wrap/Encrypt, rồi ghi audit.

### 11.3. Không nhầm backup với distribution

Backup bảo đảm khả năng khôi phục trạng thái; distribution đưa khóa/khả năng sử dụng tới một bên. **Replication KMS** có thể giúp availability nhưng không tự là backup độc lập nếu delete/compromise lan theo replica.

Mọi **đường recovery** phải được thiết kế từ trước; không nên đến lúc mất KEK mới cố chuyển key qua một cơ chế chưa được KMS/HSM hỗ trợ.

## 12. Phân quyền, trách nhiệm và kiểm toán

Quản lý phân phối khóa không chỉ thuộc Developer hoặc KMS administrator.

| Vai trò | Trách nhiệm | Không nên có quyền mặc định |
| --- | --- | --- |
| **Security/key owner** | Duyệt origin, key usage, trust anchor, rotation/revocation và ngoại lệ. | Tự thao tác mọi hệ mà không cần kiểm soát độc lập. |
| **KMS/HSM operator** | Quản trị key objects, secure import, availability và policy được phê duyệt. | Truy cập plaintext dữ liệu hoặc tự ký giao dịch tùy ý. |
| **IAM/platform team** | Workload identity, mTLS/roles, key usage permissions và môi trường. | Tự xuất private key ngoài policy. |
| **Developer/application owner** | Verify peer/key metadata, kiểm tenant/object authorization, AAD và xử lý version. | Thay trust root hoặc export KEK không cần thiết. |
| **PKI/issuer operator** | Cấp phát chứng chỉ/public key registry, quản lý issuer và revocation. | Tự phát hành signing key cho mọi tenant không qua phê duyệt. |
| **SRE/DR** | Giám sát distribution, rollout, rollback hợp lệ, restore drills. | Bỏ certificate validation để khôi phục dịch vụ nhanh. |
| **Auditor/SOC** | Theo dõi bất thường, audit provenance, kiểm tra sự cố. | Raw DEK, private signing key, HSM recovery shares. |

### 12.1. Audit nên ghi gì?

Một mẫu sự kiện:

~~~json
{
  "eventType": "AUTHENTICATED_KEY_DISTRIBUTION",
  "issuerRef": "trusted-payment-key-registry",
  "recipientRef": "ledger-service",
  "tenantRef": "payments",
  "keyRef": "payment-signing-s2",
  "keyPurpose": "VERIFY_EVENT",
  "keyVersion": 2,
  "authMethod": "ED25519_SIGNED_MANIFEST",
  "operation": "ACCEPT_PUBLIC_KEY",
  "outcome": "ACCEPTED",
  "policyVersion": "payment-trust-v4",
  "correlationId": "opaque-event-id"
}
~~~

**Không log** raw DEK/KEK, private key, seed, bearer token, HSM recovery shares, plaintext dữ liệu hoặc KMS response nguyên khối. Key ID và tenantRef là metadata có thể nhạy cảm theo mô hình vận hành, cần phân loại quyền xem.

### 12.2. Đối chiếu application audit và KMS/provider audit

Khi Billing unwrap DEK, audit provider có thể biết **workload X gọi Decrypt trên KEK Y** nhưng không biết **user cuối có quyền xem invoice Z hay không**. Ứng dụng cần ghi quyết định authorization trên object/tenant và liên kết qua correlation ID.

Khi Ledger nhận public key S2, application audit ghi **đã kiểm issuer/trust/algorithm/version**; registry/PKI audit ghi **ai phát hành và phê duyệt S2**. Hai luồng kết hợp mới giúp truy trách nhiệm.

## 13. Kiểm thử đường phân phối có xác thực

Một bài test “client kết nối được” chưa đủ. Cần kiểm thử đường thất bại và sự thay đổi trust theo thời gian.

| Kiểm thử | Kết quả an toàn mong đợi |
| --- | --- |
| Public key manifest bị thay một byte | Chữ ký xác thực thất bại, không cập nhật trust state. |
| Attacker ký manifest bằng key của họ | Không được chấp nhận nếu public key attacker không phải trust anchor. |
| `issuer` không khớp | Từ chối, dù chữ ký toán học hợp lệ dưới key khác. |
| `audience` hoặc tenant không khớp | Từ chối phân phối/tiếp nhận. |
| Key ID/algorithm/key usage bị tráo | Từ chối, không chọn key ngoài allowlist. |
| Manifest cũ được phát lại sau version mới | Từ chối rollback theo persistent trusted state. |
| Manifest còn hạn nhưng signer đã revoked | Từ chối theo current revocation policy. |
| Chứng chỉ TLS có hostname sai | TLS client từ chối; không bật trust-all fallback. |
| mTLS workload đúng nhưng tenant sai | Application/KMS policy từ chối cấp DEK. |
| Wrapped DEK của tenant A dùng cho tenant B | Context/authorization/integrity từ chối. |
| KMS AccessDenied hoặc key disabled | Không thử export KEK hoặc dùng default key. |
| KMS timeout | Retry/backoff trong giới hạn, không giảm yêu cầu xác thực. |
| Data AES-GCM tag sai | Không trả plaintext; không bỏ qua tag. |
| HSM secure import token/recipient key không hợp lệ | Từ chối, không chuyển raw secret ra file. |
| Rotation S1 → S2 | Verifier nhận S2 từ nguồn đúng trước khi signer chuyển sang S2. |
| Backup có key version cũ | Restore dùng đúng key/metadata và kiểm tra quyền hiện hành. |
| Audit exporter/trace capture | Không chứa raw key, token hoặc sensitive response. |
| Nhiều publication cạnh tranh | Registry cập nhật version atomically, không rollback. |

### 13.1. Kiểm thử TLS/PKI

Các lỗi thường phải đưa vào regression tests:

- Chuỗi chứng chỉ có CA không tin cậy.
- Chứng chỉ hết hạn hoặc chưa hợp lệ.
- Tên máy chủ/service identity không khớp.
- Chứng chỉ dùng sai purpose hoặc client certificate bị revoke theo policy.
- Dịch vụ đổi chứng chỉ nhưng consumer chưa cập nhật trust.
- Client vô tình tắt hostname verification hoặc trust manager chấp nhận mọi certificate.

**Không “chữa” lỗi TLS bằng cách bỏ xác thực peer.** Nếu hệ thống cần đường khẩn cấp, phải thiết kế **break-glass/trust-recovery** có phê duyệt và audit, không đặt một bypass thường trực.

### 13.2. Kiểm thử key agreement và protocol binding

Với TLS/mTLS hoặc AKE được đánh giá, cần kiểm:

- Từ chối downgrade/thuật toán không được cho phép.
- Xác thực danh tính đúng bên.
- Transcript/channel binding đúng theo giao thức.
- Không reuse secret/nonce trái giới hạn.
- Key confirmation và expiry theo chuẩn.
- Chặn session/token replay theo ứng dụng/giao thức.
- Không log traffic secrets hoặc session keys.

Các thuộc tính như forward secrecy và key confirmation **phụ thuộc giao thức cụ thể**, không suy từ việc sử dụng ECDH ở một đoạn mã đơn lẻ.

## 14. Tình huống thực tế: Payment, Ledger và Billing

Một nền tảng có ba thành phần:

- **Payment Service:** ký payment events bằng private signing key S1/S2 trong KMS/HSM.
- **Ledger Service:** xác minh chữ ký để quyết định ghi sổ.
- **Billing Service:** mã hóa invoice bằng DEK; DEK được KMS bọc bởi KEK.

### 14.1. Sai lầm khi phát hành signing key mới

Payment chuyển sang S2 và cập nhật endpoint `/keys`. Ledger tải một public key mới từ URL trong event payload, rồi Verify thành công. Attacker có thể **tự tạo cặp key và một event giả**, công bố public key riêng tại URL do họ kiểm soát.

Lỗi không ở Ed25519: thuật toán đã Verify đúng chữ ký của **key sai nguồn**. Cách sửa là:

1. Chỉ dùng **issuer/registry URL** đã được cấu hình tin cậy.
2. Xác thực TLS/PKI đúng và/hoặc verify signed key manifest bằng trust anchor độc lập theo policy.
3. Kiểm tra key S2 gắn **Payment issuer, event-signing purpose, audience Ledger, tenant và version**.
4. Kiểm **signature trên canonical event**, issuer/audience/tenant/permissions và chống replay.
5. Ghi audit việc nhận S2 và quyết định Verify, không log private key hoặc full token.

### 14.2. Sai lầm khi phân phối wrapped DEK cho nhiều tenant

Billing lưu encrypted object của tenant A nhưng endpoint trả cả wrapped DEK cho một request của tenant B. Wrapped DEK có thể không phải key rõ, nhưng nếu một workload có quyền KMS Decrypt rộng hoặc context không ràng buộc tenant, việc phân phối sai sẽ góp phần gây **cross-tenant data exposure**.

Giải pháp phối hợp:

- **Application authorization** từ danh tính đã xác thực trước khi query/read.
- **KMS IAM** hạn chế workload/key usage theo policy.
- **AAD/context** gắn tenant, object, purpose với ciphertext/wrapped DEK theo cách ổn định.
- **Key inventory** biết dữ liệu và versions nào đang phụ thuộc KEK.
- **Audit correlation** liên kết quyết định ứng dụng với KMS operation.

### 14.3. Sự cố key signer S1 bị lộ

Sau khi S1 bị nghi compromise:

1. Security quyết định scope ảnh hưởng, hạn chế hoặc vô hiệu hóa quyền Sign S1.
2. Payment tạo S2 theo chính sách, công bố public key qua đường có xác thực.
3. Ledger cập nhật trust state, xử lý manifest cũ/revocation và chữ ký trong giai đoạn rủi ro.
4. Thực hiện rollout/rollback theo **current trust policy**, không tin S1 vô thời hạn chỉ vì key từng được phân phối đúng.
5. Đối chiếu audit và các event đã được chấp nhận; xem xét nghĩa vụ thông báo/phản ứng theo yêu cầu tổ chức.

**Một chữ ký cũ có thể vẫn kiểm tra đúng về mặt toán học sau khi private key bị lộ**; chính sách phải quyết định **giá trị tin cậy nghiệp vụ** của chữ ký trong các khoảng thời gian liên quan.

## 15. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách phòng ngừa |
| --- | --- | --- |
| Nhầm HTTPS với xác thực bất kỳ key nào do client nhận | Chấp nhận key sai issuer/tenant nếu endpoint bị chọn tùy ý. | Trust anchor, issuer allowlist, kiểm tra danh tính và purpose. |
| Tắt certificate/hostname validation | MITM có thể thay public key và dữ liệu. | TLS validation chuẩn, không dùng trust-all. |
| Dùng chữ ký hợp lệ dưới public key cùng gói làm bằng chứng nguồn | Attacker tự ký và tự cung cấp key. | Trust anchor được provision độc lập. |
| Dùng `kid` để tải key từ URL không tin cậy | Key substitution, algorithm/key confusion. | Key registry/JWKS chỉ từ issuer đã duyệt. |
| Không ràng buộc audience/tenant/purpose | Key hợp lệ bị dùng sai đối tượng. | Signed metadata, context, IAM và app authorization. |
| Chỉ kiểm expiry, không kiểm revoke | Nhận key compromised còn hạn. | Revocation/trust updates có thẩm quyền. |
| Không có anti-rollback state | Attacker phát lại key version đã retire. | Monotonic version/atomic update và current policy. |
| Coi checksum là chữ ký số | Attacker có thể thay key lẫn checksum. | MAC/signature với trust anchor được bảo vệ. |
| Dùng X25519/ECDH thuần rồi coi peer đã được xác thực | MITM/identity misbinding. | AKE/TLS chuẩn, peer identity và transcript binding. |
| Gửi raw DEK qua kênh không được xác thực hoặc log response | Secret bị người không có quyền lấy. | KMS/HSM, mTLS/TLS, recipient binding, no-secret logging. |
| Xuất KEK/private key từ HSM để “gửi nhanh” | Phá ranh giới lưu trữ và mở rộng blast radius. | Native key operation hoặc secure migration được duyệt. |
| Một KEK cho mọi tenant không có scope | Workload bị chiếm quyền ảnh hưởng nhiều dữ liệu. | Phân vùng key hoặc context + IAM + app authorization theo threat model. |
| Tin KMS Decrypt thành công là user được đọc object | Lộ dữ liệu nghiệp vụ. | Authorization trước KMS và đối chiếu audit. |
| Không lưu key reference/version cùng ciphertext | Khó khôi phục khi rotate. | Wrapped DEK + key metadata + format + AAD. |
| Dùng alias current thay lịch sử key material | Decrypt/Verify nhầm version. | Registry version/lineage được xác thực. |
| Re-wrap DEK rồi coi DEK đã thay | Ciphertext vẫn được bảo vệ bằng cùng DEK. | Phân biệt KEK/DEK rotation và re-encryption. |
| Không đánh giá DEK khi KEK bị compromise | Bỏ qua DEK có thể đã bị unwrap. | Incident analysis theo dependency inventory. |
| Phân phối public signing key nhưng không cập nhật verifier | Consumer từ chối chữ ký mới. | Publish-before-switch và readiness tests. |
| Giữ private signing key ở mọi verifier | Nhiều nơi có thể tạo chữ ký giả. | Chỉ phân phối public key; private key ở signer/KMS. |
| Coi replication KMS là backup độc lập | Xóa/compromise có thể lan theo replica. | Recovery strategy, failure-domain analysis, DR drill. |
| Log private key/DEK/token trong quá trình phân phối | Bí mật lan sang SIEM/APM/CI. | Typed audit allowlist, secret scanning và access control. |

## 16. Checklist thiết kế authenticated distribution

Trước khi triển khai, cần trả lời:

1. **Key type:** phân phối public key, wrapped DEK, secret hay chỉ quyền dùng key trong KMS/HSM?
2. **Origin:** bên nhận chứng minh nguồn phát hành bằng trust anchor/PKI hoặc cơ chế nào?
3. **Recipient:** danh tính người nhận được xác thực qua IAM/mTLS/giao thức như thế nào?
4. **Purpose:** key usage, thuật toán và phạm vi dữ liệu được ràng buộc bằng cách nào?
5. **Tenant:** có đường nào chuyển khóa hoặc quyền Decrypt giữa hai tenant không?
6. **Confidentiality:** secret có được truyền và nhận trong ranh giới bảo mật phù hợp không?
7. **Integrity:** key bytes, ID, version, validity và metadata có được xác thực cùng nhau không?
8. **Trust bootstrap:** public key xác minh issuer có được cấp độc lập với manifest đang đọc không?
9. **TLS:** cert chain, hostname/service identity và thuật toán có được xác minh không?
10. **JWKS/registry:** URL, issuer, `kid`, algorithm và key usage có allowlist không?
11. **Freshness:** có expiry, monotonic state và cập nhật revocation kịp thời không?
12. **Key agreement:** nếu dùng AKE/TLS, transcript, peer identity, HKDF và key confirmation thuộc giao thức chuẩn không?
13. **KMS:** workload có least privilege, không cần export private key/KEK không?
14. **Envelope:** wrapped DEK, key reference/version, nonce/tag, AAD và context được lưu nhất quán không?
15. **Rotation:** có đường publish-before-switch, rewrap/reencrypt và read compatibility không?
16. **Compromise:** nếu issuer/key bị lộ, có khả năng revoke trust, rotate và xác định dữ liệu bị ảnh hưởng không?
17. **DR:** backup và key versions có thể phục hồi theo điểm dữ liệu nhất quán không?
18. **Audit:** có issuer/recipient/keyRef/operation/outcome/correlation ID mà không log secret không?
19. **Negative tests:** các trường hợp MITM, key substitution, replay/rollback, wrong tenant và revoked key đã được kiểm thử chưa?
20. **Ownership:** ai phê duyệt issuer, trust anchor, key publication, rotation và hủy khóa?

## 17. Câu hỏi tự kiểm tra

1. **Authenticated distribution** khác việc đơn thuần truyền dữ liệu qua HTTPS ở điểm nào?
2. Vì sao public key không cần giữ bí mật nhưng vẫn phải xác thực nguồn?
3. Tại sao SHA-256 checksum đi kèm key không tự chứng minh key do đúng issuer phát hành?
4. Một verifier có thể tin chữ ký do attacker tạo nếu lấy public key từ chính request không?
5. **Origin authenticity**, **recipient authorization** và **confidentiality** khác nhau như thế nào?
6. Vì sao mTLS không thay application authorization với dữ liệu theo tenant?
7. Tại sao X25519/ECDH riêng lẻ không xác thực danh tính đối tác?
8. Trong TLS 1.3, các bên có nhất thiết truyền raw traffic key cho nhau không?
9. Tại sao JWKS `kid` không được phép quyết định một URL tải key tùy ý?
10. Signed manifest cần ràng buộc những trường gì ngoài public key bytes?
11. Vì sao trust anchor phải đến từ nguồn độc lập với gói cần Verify?
12. Nếu signed manifest có chữ ký hợp lệ nhưng đã bị revoke, nên chấp nhận không?
13. Version monotonic chống replay/rollback đến đâu, và cần state nào để đáng tin?
14. Trong KMS envelope encryption, **wrapped DEK** khác **plaintext DEK** ở đâu?
15. Khi cấp wrapped DEK cho tenant khác, cần kiểm tra những lớp quyền/ngữ cảnh nào?
16. Có được xuất KEK/private key non-exportable để phân phối nhanh cho ứng dụng không?
17. Khi rotate KEK và re-wrap DEK, ciphertext dữ liệu có nhất thiết thay không?
18. Nếu DEK đã bị lộ, re-wrap bằng KEK mới có bảo vệ dữ liệu cũ không?
19. Khi chuyển signing key S1 → S2, vì sao cần cập nhật verifier trước khi signer đổi?
20. Key distribution audit phải ghi gì để điều tra, và phải tránh ghi gì?

**Ghi nhớ:** **Authenticated distribution** không chỉ là “khóa được gửi đi”, mà là **khóa hoặc quyền dùng khóa được cấp cho đúng bên, từ đúng nguồn, đúng mục đích, không bị tráo, phát lại hay vượt phạm vi**. Với public key, phải có **trust anchor/PKI/issuer validation, version và revocation**; với secret key/DEK, phải thêm **confidentiality, KMS/HSM custody, recipient binding và application authorization**. Quản lý đúng **key ID/version, envelope encryption, rotation, backup/DR và audit** giúp khóa được tạo, cấp phát, sử dụng, thu hồi và hủy an toàn trong toàn bộ vòng đời.

# Key import: đưa khóa mật mã vào hệ thống an toàn và có thể kiểm chứng

## 1. Tại sao cần import key thay vì luôn tạo khóa mới?

Một nền tảng Java đang chuyển các dịch vụ mã hóa thanh toán từ trung tâm dữ liệu tự quản sang một dịch vụ **KMS/HSM**. Dữ liệu cũ được mã hóa bằng các DEK nằm dưới **KEK do tổ chức tự quản lý**. Để tiếp tục giải mã các bản sao lưu, tổ chức không thể chỉ sinh một KEK ngẫu nhiên rồi thay tên của khóa cũ: ciphertext lịch sử vẫn phụ thuộc **vật liệu khóa gốc**.

Ở một trường hợp khác, doanh nghiệp muốn giữ quyền quyết định quá trình tạo vật liệu khóa, sau đó **import** nó vào KMS cloud theo cơ chế **Bring Your Own Key (BYOK)**. Đây có thể là yêu cầu vận hành, hợp đồng hoặc quản trị nội bộ. Tuy nhiên, nếu đội kỹ thuật gửi raw KEK qua HTTP, lưu nó trong file tạm trên máy cá nhân hoặc không xác minh khóa công khai dùng để bọc khóa nhập, chính quy trình import có thể phá hỏng ranh giới an toàn.

**Key import** là quy trình đưa **vật liệu khóa mật mã đã được sinh hoặc sở hữu ở một ranh giới khác** vào một hệ thống quản lý hoặc sử dụng khóa đích, cùng với **metadata, mục đích, quyền sử dụng, bằng chứng nguồn gốc và kế hoạch vòng đời** cần thiết.

Key import **không chỉ là copy file PEM hay gọi một API**. Quy trình tốt phải chứng minh được:

1. **Đúng vật liệu khóa** từ nguồn được phê duyệt.
2. **Đúng hệ thống đích**, key reference, tenant, environment và security boundary.
3. Khóa được bảo vệ **bí mật và toàn vẹn trong quá trình vận chuyển**.
4. Key type, algorithm, key size, usage và exportability khớp **chính sách mật mã**.
5. Không có quyền hoặc bản sao nào ngoài dự kiến sau import.
6. Khóa được **kiểm tra chức năng** bằng cơ chế phù hợp trước khi kích hoạt.
7. Owner, custodian, IAM, audit, backup, expiry và recovery đã có kế hoạch.
8. Khi import thất bại, không bị **lộ raw key** hoặc vô tình làm dữ liệu cũ không thể giải mã.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, key import nằm giữa **key generation**, **key distribution**, **KMS/HSM custody**, **envelope encryption**, **rotation**, **recovery** và **key destruction**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **key generation, key import, key export, key wrapping, key rewrap, key migration và key rotation**.
- Giải thích khác biệt giữa **import public key**, **import symmetric/private secret** và **import key reference**.
- Thiết kế luồng BYOK/KMS/HSM có **trusted destination wrapping key**, transport protection, import policy và audit.
- Nhận diện vai trò của **RSA-OAEP, AES-KW/AES-KWP, AEAD, PKCS#8, SPKI/X.509, PKCS#12, PKCS#11** mà không nhầm định dạng với cơ chế bảo vệ.
- Đánh giá **provenance, entropy, type, usage, size, key pair consistency, non-exportability và key ownership**.
- Hiểu giới hạn của tuyên bố **“imported key đã trở thành non-exportable”** khi nguồn vẫn giữ một bản raw key.
- Kiểm tra rủi ro **key substitution, replay, wrong-region import, shared material, thiếu key version và expiry của imported material**.
- Thiết kế Java 17 demo dùng **trusted RSA-OAEP recipient public key** để chuyển AES-256 key đã sinh tại nguồn tới bên nhận, kèm negative tests.
- Lập **import acceptance gates, audit evidence, IAM/SoD, incident response và rollback plan**.
- Phân biệt việc import được key với việc **có quyền sử dụng key để Decrypt/Unwrap/Sign**.

## 2. Những thuật ngữ dễ bị nhầm lẫn

| Thuật ngữ | Bản chất | Điều cần ghi nhớ |
| --- | --- | --- |
| **Key generation** | Tạo key material mới từ nguồn sinh được phê duyệt | Key mới không thể tự giải ciphertext tạo dưới key cũ |
| **Key import** | Đưa material đã tồn tại từ nguồn khác vào ranh giới đích | Cần bảo vệ material trên đường đi và kiểm tra đúng identity/purpose |
| **Key export** | Đưa key material ra khỏi hệ quản lý ban đầu | Có thể bị cấm; non-exportable key không được “xuất tạm” cho tiện |
| **Key wrapping** | Bảo vệ key material bằng KEK hoặc public wrapping key | Cần confidentiality, integrity và đúng recipient/context |
| **Unwrap** | Khôi phục key material trong boundary được phép | Có thể không trả raw key về application nếu KMS/HSM nhập trực tiếp |
| **Key reference import** | Đăng ký ID/handle/certificate/public key vào một service | Chưa chắc đã nhập secret material |
| **Key migration** | Chuyển use case, keys và dữ liệu giữa systems/providers | Thường cần metadata, permissions, key version, backup và cutover |
| **Rewrap** | Thay lớp bảo vệ DEK bằng KEK khác | Có thể giữ nguyên ciphertext dữ liệu |
| **Re-encrypt** | Giải mã rồi mã hóa data dưới DEK khác | Thay data ciphertext; dùng khi DEK cần thay |
| **Key rotation** | Chuyển sang dùng key version/material mới cho operations theo policy | Không đồng nghĩa import hoặc xóa vật liệu cũ |
| **BYOK** | Tổ chức tạo/kiểm soát nguồn material rồi đưa vào provider | Không đồng nghĩa toàn bộ vận hành/usage đều nằm ngoài provider |
| **HYOK** | “Hold Your Own Key” trong một số thiết kế sản phẩm | Semantics tùy nhà cung cấp; không xem là tên giao thức chuẩn chung |

**Đặc biệt:** Import **KEK** khác import **DEK**. KEK thường là key bảo vệ nhiều DEKs, có blast radius và recovery phụ thuộc lớn hơn. Import **private signing key** lại có yêu cầu identity và non-repudiation/issuer controls khác import một khóa AES.

### 2.1. Import vật liệu khác import bí danh

Đăng ký một **public verification key**, thêm một certificate vào trust store hoặc khai báo KMS key ID là thao tác **đăng ký/nhập tham chiếu**; nó không có nghĩa đã nhập **private key**. Trong tài liệu dự án, luôn xác định:

- **Imported public material:** public RSA/Ed25519/ECDSA key, certificate hoặc JWKS.
- **Imported secret material:** AES/HMAC/KEK, private signing key hoặc static agreement secret.
- **Imported wrapped blob:** key material đang được bảo vệ dưới wrapping key; destination phải hiểu và xử lý đúng format.
- **Imported handle/reference:** chỉ là địa chỉ API tới khóa nằm trong provider khác.

Nhầm lẫn bốn trường hợp này dễ khiến team dùng sai kiểu API hoặc đánh giá thấp rủi ro lộ secrets.

## 3. Vì sao phải có ranh giới nguồn – vận chuyển – đích?

~~~mermaid
flowchart LR
    S["Nguồn đã phê duyệt: KMS/HSM/key ceremony"] --> E["Export/wrap theo quyền và policy"]
    E --> CH["Protected transfer: authenticated recipient + wrapped key"]
    CH --> V["KMS/HSM đích: verify import parameters"]
    V --> I["Import key material trong secure boundary"]
    I --> T["Validate key attrs/PCT + approve usage"]
    T --> A["Activate key for approved workload"]
    P["Policy + owner/custodian + SoD"] --> E
    P --> V
    L["Evidence + audit"] --- E
    L --- V
    L --- T
~~~

Có ít nhất ba nơi cần phân tích:

**Nguồn (source):** Ai đã sinh key? Có bằng chứng về CSPRNG/HSM, key attributes và người giữ khóa? Material có thể export hợp pháp và hợp policy không? Có bao nhiêu bản sao ngoài dự kiến?

**Kênh chuyển (transfer):** Material được **wrap cho đúng đích** bằng public key/KEK đáng tin, có bảo vệ integrity và freshness không? Có bị ghi vào log, ticket, clipboard, email, CI artifacts hay shell history không?

**Đích (destination):** KMS/HSM có thực sự import vào **đúng key ID, đúng account/region/partition**, type/usage và chính sách không? Import token, wrapping key, expiration và attestation có được xác minh? Ai được dùng key sau khi import?

Một lớp TLS bảo vệ **giao tiếp client–server** nhưng không tự kiểm tra rằng **nội dung key blob** đúng recipient/key type, hoặc không bị sao chép ở endpoints. Vì vậy với secret material thường cần **key wrapping được chứng thực ở tầng ứng dụng/protocol** bên cạnh transport security, tùy thiết kế của KMS/HSM.

### 3.1. Threat model theo từng boundary

| Threat | Ví dụ | Kiểm soát cần có |
| --- | --- | --- |
| **Key exfiltration tại nguồn** | Kỹ sư xuất AES KEK ra file chung | Export authorization, HSM wrapping, custody, evidence |
| **Recipient substitution** | Attacker thay public wrapping key của KMS | Trust anchor/pinning/attestation/verified provider response |
| **Key blob tampering** | Wrapped blob bị sửa trong lưu chuyển | OAEP/key-wrap integrity, authenticated import protocol |
| **Replay / wrong target** | Gửi blob của account A sang account B | Bind key ID, request/token/context, freshness, policy |
| **Wrong key type/size** | Nhập 128-bit key khi profile yêu cầu 256-bit | Structural validation và explicit import metadata |
| **Unauthorized usage** | Import thành công nhưng role reporting có Decrypt | IAM effective-permission review, least privilege |
| **Source copy remains** | Raw KEK vẫn trên backup laptop | Copy inventory, secure deletion policy, incident readiness |
| **Availability loss** | Imported material hết hạn, KMS không Decrypt nữa | Expiry monitoring, re-import/recovery/rollback plan |
| **Wrong old key mapping** | Alias trỏ key mới, backup cần key cũ | Key version mapping, rewrap/restore testing |
| **Trust store takeover** | Public key verifier bị thay | Approval, key fingerprint, certificate/JWKS provenance |
| **Transport logging** | Secret nằm trong HTTP debug trace | No secret logging, restricted evidence refs |
| **Cross-tenant import** | Tenant B import key vào namespace tenant A | Strong identity/resource scope, authorization |

### 3.2. Không suy diễn từ tên “secure transfer”

Một API đặt tên **ImportKeyMaterial** chưa tự chứng minh hệ thống an toàn. Reviewer cần biết:

- Material gửi đi là plaintext, wrapped bytes hay key block?
- Public wrapping key có được xác thực là của **đích đúng**?
- Wrapping algorithm có phù hợp key type/size và không downgrade?
- Transport dùng TLS với identity validation?
- Import operation có gắn **target key ID/version và authorization**?
- Material được unwrap ở **đâu**, có bị lộ trong application RAM không?
- Thành công có làm phát sinh **phiên bản/key reference mới** hay ghi đè key cũ?
- Provider có giới hạn import key type/region, origin/expiry hoặc re-import?
- Có audit trail và rollback nếu destination import sai?

Không có câu trả lời cho các câu này thì chưa thể khẳng định “khóa đã phân phối an toàn”.

## 4. Những kiểu khóa có thể import và khác biệt rủi ro

### 4.1. Symmetric key: AES, DEK và KEK

AES key material thường là một chuỗi byte bí mật có độ dài hợp lệ cho profile AES. Nhưng nhận **đúng 32 byte** chưa chứng minh đó là key có 256 bit entropy: nó có thể sinh từ seed yếu hoặc đã bị lộ.

Cần đánh giá:

- Nguồn entropy/CSPRNG và thời điểm sinh.
- Key type, key length, use case, **DEK hay KEK**.
- Quyền Encrypt, Decrypt, Wrap, Unwrap của destination.
- Raw material có thể export/re-import không.
- Key ID/version, ownership, data/backup dependencies.
- Nonce usage limits nếu imported key từng dùng AES-GCM trước đó.

**Cảnh báo về nonce reuse:** Khi import **cùng AES-GCM key** vào hai dịch vụ, cả hai có thể độc lập sinh nonce rồi tình cờ lặp **nonce dưới cùng key**. Import đúng material **không đồng nghĩa có chiến lược nonce liên hệ giữa các replicas**. Đặc biệt với DEK dùng nhiều lần, cần định nghĩa nonce allocation và usage bounds xuyên các nơi dùng khóa.

### 4.2. KEK và root/derivation key

Import KEK/root có **blast radius** lớn vì một key có thể bọc hoặc dẫn xuất nhiều DEKs. Cần:

- Source provenance, escrow/recovery materials và tất cả bản sao.
- Key purpose separation: root/KEK không bị dùng để encrypt data trực tiếp ngoài policy.
- Non-exportable policy ở destination và quyền Wrap/Unwrap/DeriveKey.
- SoD/quorum/dual control cho export/import.
- KMS/HSM attributes và evidence sau import.
- Dependency index: những wrapped DEKs hoặc ciphertext phiên bản cũ có cần material này?
- Điều kiện destroy/suspend khi source bản copy bị compromise.

Nếu imported root key **từng bị lộ**, việc đặt bản sao trong HSM đích không làm nó trở lại bí mật. Có thể cần tạo root mới và tái dẫn xuất/đổi khóa dữ liệu liên quan.

### 4.3. Private signing key

Import private Ed25519/ECDSA/RSA signing key có rủi ro **giả mạo danh tính**:

- Có được phép chuyển private signer giữa HSM partitions không?
- Xuất khóa khỏi nguồn có phá yêu cầu non-exportable hoặc chứng nhận không?
- Public key/certificate hiện tại có thực sự khớp private key sau import?
- Sign PCT/challenge có được thử theo quyền phù hợp?
- Key purpose và allowed payload/algorithm có khớp?
- Signatures lịch sử, trust chain, certificate serial/key usage và issuer có được duy trì?
- Có cần đổi identity/certificate hoặc revoke khi nguồn key không còn an toàn?

**Một cặp ký Verify=true chưa chứng minh issuer identity** nếu public key được đưa từ nguồn chưa tin cậy. Review cả **private Sign access** và **trusted verification key registry**.

### 4.4. HMAC secret

Một hệ thống webhook legacy có thể import HMAC key để tiếp tục xác minh chữ ký MAC. Khác chữ ký số, **mọi bên sở hữu raw HMAC key đều có thể GenerateMac**. Cân nhắc provider hỗ trợ **GenerateMac và VerifyMac qua API** mà không xuất secret cho các verifier nếu cần tách quyền.

Khi import phải định nghĩa **old/new key IDs, cửa sổ chấp nhận tag cũ, event timestamp/id chống replay, rate limits và raw key copies**. HMAC không có public verification key theo nghĩa bất đối xứng.

### 4.5. Asymmetric public keys và certificate

**Public key không cần bí mật**, nên việc nhập nó có thể đơn giản hơn nhập private key. Tuy nhiên **đúng nguồn trust** vẫn là điều bắt buộc:

- RSA/EC/Ed25519 key parsed đúng thuật toán, định dạng và parameters.
- Key đi kèm certificate chain hoặc registry entry được xác thực.
- Fingerprint được phân phối theo nguồn tin cậy, không chỉ qua chính payload cần xác minh.
- Key usage/extended key usage, issuer/audience/hostname và expiration được kiểm tra theo protocol.
- Revocation và rollover public keys đã có chính sách.
- Không để attacker chỉ định **URL/JWKS tùy ý** rồi coi public key tải được là đáng tin.

### 4.6. Ephemeral agreement/session keys

Thông thường các key ephemeral của TLS 1.3 hoặc X25519/ECDH nên được tạo và sử dụng theo **giao thức/key schedule được phê duyệt**, không lưu rồi import lại như một key dài hạn. Việc vận chuyển **session secrets** ra nhiều hệ thống có thể phá kỳ vọng **forward secrecy**.

Nếu use case có **PSK/shared secret dài hạn** cần phân phối, phải dùng protocol/cơ chế bảo vệ phù hợp và cân nhắc replay, expiration, identity và compromise blast radius. **ECDH shared secret** không tự trở thành AES key nếu chưa qua KDF/profile phù hợp.

## 5. Key import, BYOK và quyền kiểm soát thực sự

**BYOK** có nghĩa tổ chức kiểm soát hoặc tham gia giai đoạn tạo vật liệu khóa rồi nhập vào dịch vụ đích. Nó **không tự đồng nghĩa**:

- Provider không thể vận hành mọi thao tác với key.
- Tất cả bí mật chỉ thuộc về khách hàng và không bao giờ nằm trong RAM của service.
- Key có thể được thu hồi ngay khỏi mọi cache/backup.
- Source không còn bản copy sau import.
- KMS đích hỗ trợ export hoặc migration reverse theo cách tương đương.
- Một key imported được phép dùng cho mọi thuật toán/công cụ.
- Một claim “FIPS/HSM” bao phủ cả ứng dụng và IAM.

### 5.1. Các mô hình thường gặp

| Mô hình | Key được sinh ở đâu? | Bên nào vận hành operations? | Rủi ro/câu hỏi chính |
| --- | --- | --- | --- |
| **Provider-generated key** | Trong KMS/HSM đích | Provider/KMS trong boundary được cung cấp | Kiểm soát nguồn, privileges, recovery và provider policy |
| **BYOK import into KMS** | Bên ngoài KMS đích | KMS đích sau import | Transfer path, source copies, expiry, re-import và policy |
| **External key store / HYOK-like** | Trong key store bên ngoài theo mô hình cụ thể | Có thể đòi external key manager tham gia mỗi operation | Availability/network/trust/dependency giữa hai hệ |
| **HSM-to-HSM secure migration** | Nguồn HSM | Đích HSM sau transfer đã được phê duyệt | Supported key block/wrapping domain, attestation, quorum |
| **Application key loading** | File/keystore/provider khác | JVM/provider ứng dụng | Plaintext material trong process, keystore password, host compromise |

Tên sản phẩm và hỗ trợ cụ thể thay đổi theo provider; khi thiết kế phải đọc **tài liệu chính thức của chính phiên bản KMS/HSM đang dùng**, không áp dụng một chuỗi API duy nhất cho mọi hệ thống.

### 5.2. “Non-exportable after import” có giới hạn gì?

KMS/HSM đích có thể đánh dấu key imported là **non-exportable**, nghĩa là **đích** không cho xuất material qua các API theo ranh giới được bảo đảm. Nhưng nếu nguồn **đã có raw AES key** và còn backup, nó vẫn có thể bị lộ từ nguồn. Do đó:

1. Inventory nơi vật liệu từng tồn tại trong quá trình sinh/export/import.
2. Chứng minh access controls trên nguồn, temporary storage và cleanup.
3. Xác định liệu các bản sao nguồn **cần giữ theo recovery policy** hay phải hủy theo approval.
4. Nếu cần key độc quyền tồn tại trong HSM đích từ lúc sinh, **provider-generated non-exportable** hoặc quy trình secure generation phù hợp có thể đáp ứng hơn BYOK raw material.
5. Không dùng một nhãn non-exportable của đích để khẳng định “khóa chưa từng tồn tại ngoài HSM”.

### 5.3. Re-import và expiry có thể gây mất availability

Một số cơ chế imported material dùng **import token/wrapping key có thời hạn**, key material expiration hoặc thao tác **re-import** riêng theo provider. Những thông số này phải được kiểm tra khi thiết kế:

- Token hết hạn có ảnh hưởng **chỉ đến thao tác import** hay đến key material đã nhập?
- Material có được đặt **expiration** trong KMS không?
- Re-import có yêu cầu **đúng key material**, key ID hoặc scheme không?
- Nếu material bị xóa khỏi KMS nhưng ứng dụng vẫn có ciphertext, có thể khôi phục từ source backup được không?
- Provider có hỗ trợ import key types, key versions và cross-region replication như mong muốn không?
- Có thể thay đổi origin/exportability sau creation không?

**Không giả định imported key luôn tồn tại vĩnh viễn trong KMS.** Theo dõi key material expiration và recovery dependency như một rủi ro vận hành riêng.

## 6. Giai đoạn 0: quyết định có nên import hay không

Trước khi chạm vào key material, trả lời:

1. **Use case:** Vì sao không thể generate key mới ở destination? Có phải để đọc dữ liệu cũ hay vì governance?
2. **Data dependency:** Ciphertext, wrapped DEKs, signatures hoặc backups nào đang phụ thuộc key cũ?
3. **Key type:** DEK, KEK, HMAC, signing, root, public verification hay certificate?
4. **Algorithm/length/usage:** Destination có hỗ trợ profile tương thích không?
5. **Source custody:** Ai giữ key, nó có được phép export không, có HSM migration mechanism không?
6. **Destination custody:** Ai sở hữu KMS key ID/account/region, ai có quyền import, Sign/Decrypt?
7. **Transfer profile:** Approved wrapping scheme, recipient binding và provenance là gì?
8. **Lifecycle:** Key đang active, decrypt-only, verify-only, expired, revoked hay compromised?
9. **Rollback/recovery:** Import thất bại thì dữ liệu hiện tại có tiếp tục đọc được không?
10. **Risk decision:** Có tạo thêm bản sao secret hoặc mở rộng blast radius không?

### 6.1. Khi nên chọn generate-and-migrate

Nếu key không thể export hoặc đã bị compromise, thay vì cố import raw material cần cân nhắc:

- Tạo **KEK mới** bên KMS đích.
- Mở dữ liệu tại **source boundary đã được phê duyệt**.
- **Rewrap DEKs** bằng destination KEK mà không lộ plaintext key ngoài ranh giới cần thiết.
- Nếu DEK yếu/bị lộ, tạo **DEK mới và re-encrypt data**.
- Giữ source key để restore ciphertext cũ đến khi hoàn tất migration, theo policy.
- Kiểm tra tính nhất quán và cutover before retirement.

**Không phá một key non-exportable bằng cách xuất private key trái chính sách** chỉ để giảm số bước migration.

### 6.2. Khi chỉ cần import public key

Nếu mục tiêu là xác minh webhook hoặc chữ ký của đối tác, thường chỉ cần **public verification key hoặc certificate** đã được xác thực. Không yêu cầu đối tác đưa private signing key vào hệ thống của mình.

Nguyên tắc **lấy ít quyền/vật liệu nhất cần thiết** có giá trị ngay từ giai đoạn quyết định import.

## 7. Chuẩn bị key material: nguồn gốc, phân loại và tính hợp lệ

### 7.1. Nguồn sinh phải có bằng chứng

Không thể chứng minh entropy chỉ bằng cách kiểm tra chuỗi byte trông “ngẫu nhiên”. Nên thu:

- Key generation mechanism: HSM/provider/CSPRNG approved path.
- Algorithm, parameters, key length và module version khi chính sách yêu cầu.
- Creation timestamp và key ceremony/ticket references.
- Owner, custodian và export authorizers.
- Key copy inventory và mục đích mỗi bản sao.
- Original usage history nếu key đã được dùng.
- Key state, cryptoperiod, data dependencies và compromise status.

**Một key 32 byte có thể chỉ chứa rất ít entropy** nếu sinh từ timestamp hoặc mật khẩu yếu. Import và wrap bằng RSA-OAEP không làm tăng entropy của nó.

### 7.2. Kiểm tra định dạng theo loại khóa

| Key class | Điều kiện cấu trúc cần kiểm tra | Lưu ý |
| --- | --- | --- |
| **AES** | Độ dài 128/192/256 bit theo profile, usage và origin | Không tự coi byte length là entropy |
| **HMAC** | Độ dài/algorithm/entropy theo profile và semantics MAC | Key raw không nên cấp cho bên chỉ cần Verify khi có API phù hợp |
| **RSA public** | Modulus/exponent, SPKI X.509 encoding, params | Dùng đúng OAEP/PSS purpose; không chấp nhận key bất kỳ |
| **RSA private** | Private key format, matching public key, import policy | Non-exportable source có thể không cho export; tránh plaintext PEM |
| **EC public/private** | Named curve, point/domain validation và pairwise consistency | Khác nhau giữa ECDSA/ECDH và X25519 |
| **Ed25519** | Named parameter set, public/private pair mapping | Không dùng như X25519 key agreement |
| **X25519** | Key format, public input handling và all-zero shared secret check | Không tự coi shared secret là AES key |
| **KEK/root** | Key type/purpose/length/custody và wrapping/derivation semantics | Blast radius lớn, nên có SoD/quorum |
| **Wrapped key blob** | Wrapping profile, recipient ID, context, integrity | Không unwrap bằng fallback mode khi lỗi |

### 7.3. Những định dạng hay gặp

- **SPKI / X.509 SubjectPublicKeyInfo:** định dạng chuẩn hóa để biểu diễn public key, thường được JCA đọc qua **X509EncodedKeySpec**.
- **PKCS#8:** định dạng private key; **PKCS#8 DER chưa mã hóa là material bí mật**, không phải cơ chế truyền an toàn.
- **Encrypted PKCS#8:** thêm lớp bảo vệ private key theo cấu hình được phê duyệt; chất lượng phụ thuộc password/KDF/algorithm.
- **PKCS#12:** container có thể bảo vệ private key/certificate theo password; phải đánh giá password protection và cách load vào process.
- **PEM:** cách biểu diễn Base64 với header/footer; **PEM tự nó không mã hóa**.
- **PKCS#11:** API để ứng dụng dùng keys trong token/HSM; **không phải file format để paste raw key**.
- **JWK/JWKS:** biểu diễn keys trong JSON; nhiều trường public, nhưng **JWK chứa private parameters là secret**.
- **KMS key blob/provider key block:** thường opaque và gắn với provider/algorithm/target; không giả định có thể chuyển trực tiếp giữa mọi providers.

**Nhớ phân biệt “format” với “protection”**: một private key ở dạng PKCS#8/PEM hợp lệ vẫn có thể đang tồn tại plaintext.

### 7.4. Key check value (KCV) không phải chứng nhận an toàn

Một số ngành dùng **KCV** hoặc fingerprint giới hạn để đối soát cùng key material sau vận chuyển. Nhưng:

- KCV không chứng minh **entropy, nguồn gốc, recipient trust hoặc key usage**.
- KCV không thay một MAC/chữ ký số bảo vệ toàn bộ thông điệp import.
- Cách tạo/độ dài KCV có thể làm lộ thông tin hoặc không phù hợp key type; phải tuân thủ profile đã được thẩm định.
- Không được tự thiết kế “KCV = vài byte của AES encrypt zero block” rồi coi là bằng chứng cryptographic authentication đầy đủ.

Ưu tiên **provider-verified integrity, signed attestation, trusted key IDs và functional checks** theo import protocol. KCV nếu có là tín hiệu bổ trợ, không là điều kiện duy nhất.

## 8. Giai đoạn 1: nhận diện và xác thực đích import

Một lỗi cực kỳ nguy hiểm là bọc một secret cho **public key không đúng người nhận**. Attacker có thể thay public wrapping key trong response rồi lấy wrapped blob, giải mã bằng private key của họ.

### 8.1. Chứng minh recipient key thuộc đúng KMS/HSM

Tùy API, nguồn bằng chứng có thể là:

- TLS peer identity/certificate và provider endpoint được cấu hình trước.
- Provider API trả **public wrapping key + import token** theo một request có key ID.
- Certificate/attestation của HSM hoặc token có chữ ký và trust chain được kiểm tra.
- Fingerprint của public wrapping key được phê duyệt **ngoài kênh**.
- Account/region/partition/key ID được so với approved request, không lấy từ input chưa tin.
- Freshness/expiration của import token hoặc challenge khi provider hỗ trợ.

**Không tự chọn public key từ email, log hoặc request body của đối tác** để bọc DEK/KEK nếu chưa có trust binding. RSA-OAEP bảo vệ secret **với người nắm private key tương ứng**, nhưng nếu recipient public key thuộc attacker thì cơ chế vẫn thực hiện đúng toán học trong khi bảo mật thất bại.

### 8.2. Gắn import request với đúng key slot

Một số KMS yêu cầu trước:

1. Tạo/đăng ký **key resource đích** với origin/import mode phù hợp.
2. Yêu cầu wrapping public key và import token cho **đúng key ID**.
3. Bọc material bằng wrapping algorithm được provider hỗ trợ.
4. Gửi wrapped material, token, expiry option và target key ID.
5. Kiểm tra key state/attributes sau khi nhập.

Đây là **mô hình khái niệm**, không phải API contract của mọi cloud KMS. Có nền tảng HSM cung cấp secure key block import với cơ chế khác. Không sao chép nguyên tên field hoặc dùng token của key A để import vào key B khi nhà cung cấp không cho phép.

## 9. Giai đoạn 2: bọc khóa bằng thuật toán phù hợp

### 9.1. Tại sao cần key wrapping chứ không chỉ Base64/TLS?

**Base64/PEM** chỉ là encoding. Dữ liệu encoded vẫn là secret nếu chứa raw key. TLS bảo vệ kênh trong quá trình truyền nhưng hai endpoints và loggers vẫn có thể xử lý raw bytes.

Một **wrapping protocol** được phê duyệt có thể giới hạn người nhận cuối cùng của secret, bảo vệ integrity của blob và giảm exposure của material ở các hệ thống trung gian. Tuy vậy, nếu nguồn đã có plaintext key trong memory, wrapping **không xóa được bản sao ở nguồn**.

### 9.2. Những lựa chọn phổ biến

| Cơ chế | Mục đích | Điều cần đánh giá |
| --- | --- | --- |
| **RSA-OAEP** | Bọc secret nhỏ dưới recipient public key | Recipient trust, modulus/profile, hash/MGF1/label, payload size, token binding |
| **AES-KW** | Wrap key material bằng shared KEK | KEK phân phối thế nào, key wrap integrity, access control |
| **AES-KWP** | Wrap key material với padding | Đúng length/profile, phân biệt với CBC/ECB padding |
| **AEAD (ví dụ AES-GCM)** | Mã hóa key bytes dưới KEK + AAD | Nonce uniqueness dưới KEK, tag verification, context binding |
| **HSM secure key block/protocol** | Import/export giữa boundaries với key usage/attributes | Supported mechanism, approved wrapping domains, quorum, attestation |
| **Provider import API** | KMS nhận wrapped blob và token theo policy | Algorithm và key material constraints của provider cụ thể |

**Không bao giờ lấy tên “RSA” làm đủ:** encryption scheme, hash, MGF, label, key size và provider API phải đồng bộ. **RSA-PSS là cho chữ ký, RSA-OAEP là cho mã hóa/bọc dữ liệu nhỏ**, không thay thế nhau.

**RSA-OAEP không tự xác thực người gửi.** Nó bảo vệ key material cho người nắm private key đích; danh tính và quyền của bên gửi phải được xác minh bằng **provenance, authenticated workflow, approval và audit** độc lập. Không lấy việc unwrap thành công làm bằng chứng rằng material đến từ key owner được ủy quyền.

### 9.3. RSA-OAEP và công thức giới hạn input

Với RSA modulus có độ dài \(k\) byte và OAEP dùng hash output dài \(hLen\) byte, plaintext phải có chiều dài:

\[
mLen \le k - 2hLen - 2.
\]

Ví dụ RSA 3072-bit có \(k=384\) byte, SHA-256 có \(hLen=32\) byte, nên giới hạn về mặt OAEP là:

\[
mLen \le 384 - 64 - 2 = 318\ \text{byte}.
\]

Một AES-256 key raw dài 32 byte phù hợp với giới hạn này. **Không dùng RSA-OAEP trực tiếp mã hóa file lớn**; dùng envelope/hybrid encryption.

### 9.4. Import RSA-OAEP phải thống nhất tham số

Một điểm dễ sai trong Java/provider: tên transformation **OAEPWithSHA-256AndMGF1Padding** không đủ để suy ra mọi provider dùng cùng hash **MGF1**. Khi lập giao thức, nên quy định **digest, MGF digest, label/PSource và key type** rõ ràng và đối chiếu chính xác tài liệu đích.

Một profile minh họa:

~~~text
Recipient key: RSA 3072-bit public encryption key đã xác thực
OAEP main digest: SHA-256
MGF: MGF1 with SHA-256
OAEP label: empty nếu approved protocol yêu cầu
Material: exact 32-byte AES-256 key của ví dụ
Recipient binding: trusted key ID + account/region + import token ở workflow
~~~

Nếu KMS yêu cầu profile khác, **phải dùng chính profile đó**, không ép đoạn mã minh họa thành cơ chế phổ quát.

### 9.5. AEAD wrapping cần hai domain riêng

Nếu KEK dùng AES-GCM để wrap DEK và DEK dùng AES-GCM để mã hóa data:

~~~text
Tầng key:
  KEK + nonceWrap + AADWrap -> wrappedDEK + tagWrap

Tầng data:
  DEK + nonceData + AADData -> ciphertext + tagData
~~~

- **KEK và DEK là hai vật liệu khóa khác nhau**.
- Nonce ở **mỗi tầng** phải duy nhất theo **khóa của chính tầng đó**.
- AADWrap ràng buộc purpose, recipient, key class, tenant hoặc object/version theo policy.
- AADData ràng buộc resource, tenant, schema/purpose theo use case.
- KMS encryption context là API-specific; **không mặc nhiên giống AADData**.
- Tag hợp lệ không tự ngăn **replay/rollback** của một bản wrapped blob hợp lệ cũ.

### 9.6. Không tự fallback khi import bị từ chối

Khi unwrap OAEP/tag/key-block verification không hợp lệ:

- Không thử RSA PKCS#1 v1.5, ECB/CBC hoặc các mode khác chỉ để “đọc được”.
- Không nhận key size bất kỳ và “bổ sung zero bytes”.
- Không lấy material từ logs hoặc file khác rồi import thử không có approval.
- Không tự hủy key resource đang có dữ liệu nếu import thất bại.
- Ghi error code/audit metadata, đưa blob vào **quarantine có kiểm soát** nếu retention cho phép.

**Integrity failure phải fail closed.** Nếu cần migration legacy, đó phải là **workflow riêng có scope, owner và thời hạn**, không là fallback trên lỗi bảo mật.
## 10. Giai đoạn 3: thực hiện import và kiểm tra trạng thái đích

### 10.1. Luồng BYOK kiểu KMS khái niệm

~~~mermaid
sequenceDiagram
    participant O as Key owner / approver
    participant S as Source HSM / key custodian
    participant C as Import client
    participant K as Destination KMS / HSM
    participant A as Security auditor
    O->>C: Approved request + target key ID/profile
    C->>K: Request wrapping key / import parameters
    K-->>C: Wrapping public key + token + metadata
    C->>C: Authenticate destination / import params
    S->>C: Securely wrapped export workflow / approved material
    C->>C: Wrap raw key for authenticated destination
    C->>K: Import wrapped key + required token/context
    K->>K: Validate token, target, algorithm, key attributes
    K-->>C: Import status + key reference
    C->>K: Describe attributes / allowed operations / key state
    K-->>C: Key metadata and status
    C->>A: Evidence: key refs, events, not raw material
    O->>A: Approval / ownership / recovery plan
    Note over C,K: Production implementation may keep key material inside approved HSM boundaries
~~~

**Lưu ý:** Trong một số HSM-to-HSM workflows, source có thể wrap material **trực tiếp** cho import wrapping key của destination, nên ứng dụng không bao giờ nhìn raw key. Trong các mô hình BYOK khác, source client có thể tạm nắm plaintext key để wrap; đây là rủi ro cần đánh giá, không được che bằng sơ đồ “tất cả đều an toàn trong HSM”.

### 10.2. Các giai đoạn cụ thể

**Bước 1 — Tạo/chuẩn bị target resource.** Xác định target key ID hoặc import slot, key spec/usage, origin, account/region và approval. Kiểm tra destination hỗ trợ nhập loại material đó.

**Bước 2 — Thu wrapping parameters đáng tin.** Lấy recipient public key/token/algorithm theo provider, kiểm tra nguồn TLS/identity, binding với target và expiration. Nếu không thể xác thực wrapping key, **dừng**.

**Bước 3 — Xuất hoặc chuẩn bị material ở nguồn.** Chỉ khi policy cho phép, sử dụng HSM secure wrapping/key ceremony hoặc export path được ủy quyền. Không đặt raw key vào chat, email, clipboard, ticket hoặc CI variables lâu dài.

**Bước 4 — Wrap cho destination.** Dùng cơ chế được hỗ trợ, đúng OAEP/AES-KW/secure key block profile. Không đổi thuật toán theo phản hồi từ blob không tin cậy.

**Bước 5 — Import trong boundary đích.** Gửi wrapped payload và các parameters/token bắt buộc. Theo dõi lỗi và audit, không tự retry bằng cách xuất plaintext key ra nơi khác.

**Bước 6 — Verify actual material/attributes.** Đọc key state, algorithm, origin, exportability, allowed operations, imported material expiry, key reference và region. Khi cần, thực hiện **functional test hoặc pairwise consistency** trong phạm vi cho phép.

**Bước 7 — Đăng ký và phê duyệt activation.** Ghi inventory, owner/custodian, cryptoperiod, recovery/re-import obligations, IAM scope và evidence.

**Bước 8 — Cutover có kiểm soát.** Chỉ cho workload mới sử dụng key sau acceptance. Với dữ liệu cũ, test decrypt/verify/unwrap đúng key version; không retire source sớm.

### 10.3. Nếu nhận được thông báo Import thành công

Một câu trả lời thành công chỉ cho biết provider chấp nhận một thao tác trong phạm vi API. Nó **không tự xác nhận**:

- Material đến từ CSPRNG tốt hoặc chưa từng bị lộ.
- Khóa nhập đúng purpose nghiệp vụ trong toàn hệ thống.
- Trường exportability luôn đúng như kỳ vọng.
- IAM grants chỉ cấp cho đối tượng cần thiết.
- Có recovery copy đủ tin cậy cho expiry/mất region.
- Các ciphertext cũ dùng đúng key material này.
- Public verification identity đã được xác thực.
- Các bản sao ở nguồn đã được quản lý/xóa đúng.

Cần **post-import acceptance**, không chỉ kiểm tra exit code hoặc HTTP 200.

### 10.4. Không sửa trạng thái cũ bằng import bừa

Với key đã ACTIVE hoặc có dữ liệu lịch sử, import lần hai có thể tạo **new version**, **ghi vào một target slot**, hoặc **bị provider từ chối**. Không được giả định re-import luôn “thay key material của key ID hiện tại” mà không ảnh hưởng ciphertext. Phải kiểm tra semantics và backup/rollback của provider cụ thể.

## 11. Ví dụ Java 17: import AES-256 key bằng RSA-OAEP với người nhận đã xác thực

### 11.1. Bài toán minh họa

Giả sử một bên **Source** đã sinh một AES-256 key cho mục đích học tập. Bên **Destination** có cặp RSA 3072-bit làm **transport/wrapping key pair** để nhận key material. Source phải:

1. Nhận public key của destination từ nguồn được tin.
2. Kiểm tra **SHA-256 fingerprint** với giá trị đã được phê duyệt ở kênh đáng tin.
3. Kiểm tra RSA modulus và import target ID.
4. Dùng **RSA-OAEP với SHA-256 + MGF1(SHA-256)** để bọc 32 byte AES key.
5. Destination dùng private key tương ứng để unwrap, xác minh kích cỡ.
6. Thử **AES-GCM encrypt/decrypt** với key trước/sau chuyển.
7. Sửa wrapped blob hoặc dùng private key người khác phải **không thể import thành công**.
8. Không in raw keys và xóa best-effort các mảng byte tạm.

**Mục đích:** Minh họa cơ chế vận chuyển có xác thực người nhận ở cấp **key material** và phép kiểm tra chức năng. Ví dụ này **không phải SDK KMS/HSM**, không triển khai issuer certificate validation thực hay quy trình audit/approval production. Hơn nữa, source AES key là một khóa local được phép export, **không phải non-exportable KEK**.

### 11.2. Mã nguồn hoàn chỉnh

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

public final class KeyImportDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    private static final String TARGET_ID = "destination-import-key-1";
    private static final String PURPOSE = "demo-aes-dek";
    private static final int AES_BYTES = 32;
    private static final int GCM_NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;

    record ImportPacket(
            String targetId,
            String purpose,
            byte[] wrappedMaterial) {}

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new SecurityException(message);
        }
    }

    private static KeyPair createRecipientKeyPair() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072, RANDOM);
        return generator.generateKeyPair();
    }

    private static SecretKey newAesKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RANDOM);
        return generator.generateKey();
    }

    private static byte[] sha256(byte[] input) throws Exception {
        return MessageDigest.getInstance("SHA-256").digest(input);
    }

    // Demo: fingerprint đến từ trusted local registration.
    // Production: pin/fetch fingerprint bằng nguồn độc lập đáng tin
    // và xác minh certificate/attestation/import token theo provider.
    private static PublicKey validatedRecipientKey(
            byte[] receivedSpkiDer,
            byte[] trustedFingerprint) throws Exception {

        byte[] actual = sha256(receivedSpkiDer);
        require(MessageDigest.isEqual(
                actual, trustedFingerprint),
            "Recipient wrapping public key is not trusted");

        PublicKey parsed = KeyFactory.getInstance("RSA")
            .generatePublic(new X509EncodedKeySpec(receivedSpkiDer));

        require(parsed instanceof RSAPublicKey,
            "Expected an RSA wrapping public key");
        RSAPublicKey rsaKey = (RSAPublicKey) parsed;
        require(rsaKey.getModulus().bitLength() >= 3072,
            "RSA wrapping key is below the approved size");
        return rsaKey;
    }

    // Bind OAEP label to the intended target and purpose in DEMO.
    // Real KMS imports often require an exact provider-specified
    // OAEP label; never invent a label for a real provider.
    private static OAEPParameterSpec oaepParams(
            String targetId, String purpose) {

        String label = "key-import-demo-v1|" +
            targetId + "|" + purpose;

        return new OAEPParameterSpec(
            "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
            new PSource.PSpecified(
                label.getBytes(StandardCharsets.UTF_8)));
    }

    private static ImportPacket wrapForDestination(
            SecretKey sourceAesKey,
            PublicKey trustedRecipient,
            String targetId,
            String purpose) throws Exception {

        require(TARGET_ID.equals(targetId)
                && PURPOSE.equals(purpose),
            "Unapproved import target or purpose");
        require("AES".equalsIgnoreCase(
                sourceAesKey.getAlgorithm()),
            "Only AES source keys are allowed");

        // getEncoded chỉ dành cho khóa exportable của demo.
        // Không xuất raw key từ HSM/KeyStore bị policy cấm.
        byte[] material = sourceAesKey.getEncoded();
        require(material != null,
            "Demo source key material is not exportable");

        try {
            require(material.length == AES_BYTES,
                "Demo requires AES-256 source material");
            Cipher transport = Cipher.getInstance(
                "RSA/ECB/OAEPPadding");
            transport.init(
                Cipher.ENCRYPT_MODE, trustedRecipient,
                oaepParams(targetId, purpose), RANDOM);

            byte[] wrapped = transport.doFinal(material);
            return new ImportPacket(targetId, purpose, wrapped);
        } finally {
            Arrays.fill(material, (byte) 0);
        }
    }

    private static SecretKey importAtDestination(
            ImportPacket packet,
            java.security.PrivateKey destinationPrivate,
            String approvedTarget,
            String approvedPurpose) throws Exception {

        require(packet != null
                && approvedTarget.equals(packet.targetId())
                && approvedPurpose.equals(packet.purpose()),
            "Import target/purpose mismatch");
        require(packet.wrappedMaterial() != null,
            "Missing wrapped material");

        Cipher transport = Cipher.getInstance(
            "RSA/ECB/OAEPPadding");
        transport.init(
            Cipher.DECRYPT_MODE, destinationPrivate,
            oaepParams(approvedTarget, approvedPurpose));

        byte[] material = transport.doFinal(
            packet.wrappedMaterial());

        try {
            require(material.length == AES_BYTES,
                "Imported key is not AES-256 material");

            // Local demo: SecretKeySpec sẽ copy raw key bytes.
            // Production HSM should import inside its boundary.
            return new SecretKeySpec(material, "AES");
        } finally {
            Arrays.fill(material, (byte) 0);
        }
    }

    private static byte[] nonce() {
        byte[] bytes = new byte[GCM_NONCE_BYTES];
        RANDOM.nextBytes(bytes);
        return bytes;
    }

    private static byte[] encryptTestData(
            SecretKey key, byte[] plaintext,
            byte[] iv, byte[] aad) throws Exception {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key,
            new GCMParameterSpec(GCM_TAG_BITS, iv));
        cipher.updateAAD(aad);
        return cipher.doFinal(plaintext);
    }

    private static byte[] decryptTestData(
            SecretKey key, byte[] ciphertextWithTag,
            byte[] iv, byte[] aad) throws Exception {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key,
            new GCMParameterSpec(GCM_TAG_BITS, iv));
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextWithTag);
    }

    public static void main(String[] args) throws Exception {
        // Hai identity được giả lập trong cùng process cho demo.
        // Thực tế chúng thuộc hai security boundaries khác nhau.
        KeyPair destination = createRecipientKeyPair();
        KeyPair unrelated = createRecipientKeyPair();
        SecretKey sourceKey = newAesKey();

        // Trusted fingerprint được đăng ký trực tiếp từ key do
        // destination đã được phép đưa vào registry.
        byte[] destinationSpki =
            destination.getPublic().getEncoded();
        byte[] trustedFingerprint = sha256(destinationSpki);

        PublicKey trustedPublic = validatedRecipientKey(
            destinationSpki, trustedFingerprint);

        ImportPacket packet = wrapForDestination(
            sourceKey, trustedPublic, TARGET_ID, PURPOSE);

        SecretKey imported = importAtDestination(
            packet, destination.getPrivate(), TARGET_ID, PURPOSE);

        byte[] message =
            "public-demo-message-not-sensitive"
                .getBytes(StandardCharsets.UTF_8);
        byte[] aad = "demo|tenant-A|file-41"
            .getBytes(StandardCharsets.UTF_8);
        byte[] iv = nonce();

        byte[] ciphertext = encryptTestData(
            sourceKey, message, iv, aad);
        byte[] recovered = decryptTestData(
            imported, ciphertext, iv, aad);
        require(MessageDigest.isEqual(message, recovered),
            "Import did not preserve AES key functionality");

        System.out.println("Trusted recipient check: PASS");
        System.out.println("RSA-OAEP key import: PASS");
        System.out.println("AES-GCM test after import: PASS");

        // Negative test: người có private key KHÁC không unwrap.
        try {
            importAtDestination(packet, unrelated.getPrivate(),
                TARGET_ID, PURPOSE);
            throw new AssertionError(
                "Unrelated recipient decrypted the wrapped key");
        } catch (GeneralSecurityException expected) {
            System.out.println("Wrong recipient private key: REJECTED");
        }

        // Negative test: thay ciphertext RSA-OAEP bị từ chối.
        byte[] tampered = packet.wrappedMaterial().clone();
        tampered[tampered.length - 1] ^= 1;
        ImportPacket modified =
            new ImportPacket(TARGET_ID, PURPOSE, tampered);

        try {
            importAtDestination(modified, destination.getPrivate(),
                TARGET_ID, PURPOSE);
            throw new AssertionError("Tampered key was imported");
        } catch (GeneralSecurityException expected) {
            System.out.println("Tampered wrapped key: REJECTED");
        }

        // Negative test: target sai bị từ chối trước khi unwrap.
        try {
            importAtDestination(packet, destination.getPrivate(),
                "some-other-import-key", PURPOSE);
            throw new AssertionError("Wrong target was accepted");
        } catch (SecurityException expected) {
            System.out.println("Wrong target ID: REJECTED");
        }

        // Không ghi raw AES key hoặc RSA private key vào log.
    }
}
~~~

Kết quả dự kiến:

~~~text
Trusted recipient check: PASS
RSA-OAEP key import: PASS
AES-GCM test after import: PASS
Wrong recipient private key: REJECTED
Tampered wrapped key: REJECTED
Wrong target ID: REJECTED
~~~

### 11.3. Những tính chất ví dụ minh họa

1. **SPKI X.509** được parse thành RSA public key qua JCA.
2. **Fingerprint** được đối chiếu trước khi dùng recipient public key.
3. RSA 3072-bit dùng để vận chuyển khóa **AES-256 32 byte**, không encrypt file.
4. **OAEP main hash và MGF1 hash** đều được chỉ định SHA-256 qua OAEPParameterSpec.
5. **OAEP label** ràng buộc target/purpose trong phạm vi demo; không tự đưa label này vào KMS import thực.
6. **Private key người nhận** cần tương ứng public key đã được tin cậy.
7. Destination kiểm tra material length trước khi tạo SecretKeySpec.
8. AES-GCM sanity test cho thấy secret sau import tương ứng secret trước import.
9. Wrong recipient, wrong target ID và wrapped ciphertext bị sửa đều được từ chối.
10. Không phải xuất RSA private key hoặc in raw AES material để kiểm tra.
11. Raw byte[] tạm được xóa **best-effort**, nhưng JCA/provider có thể có bản sao.
12. Đường import không tự cấp IAM quyền dùng AES key cho mọi caller.

### 11.4. Điều ví dụ tuyệt đối không chứng minh

- **Không có remote trust enrollment thực:** trusted fingerprint trong main được tạo từ một keypair cùng JVM. Production phải lấy pin/certificate/attestation qua **nguồn tin cậy đã cấu hình**; lấy fingerprint và public key từ cùng request chưa tin rồi so chúng không có giá trị xác thực.
- **Không có KMS import token hoặc key state:** không ràng buộc token, expiration, account, region, provider key resource, import quota.
- **Không có HSM boundary:** plaintext AES key tồn tại trong RAM ở source và destination; nguồn/dích cùng JVM chỉ là mô phỏng.
- **Không chứng minh entropy:** SHA-256 fingerprint và OAEP chỉ kiểm tra/bao bọc dữ liệu; AES key vẫn cần nguồn CSPRNG đáng tin.
- **Không có provider audit/approval:** không ghi owner/custodian, IAM, SoD, recovery, expiry hoặc incident logs.
- **Không kiểm tra vật liệu nguồn đã từng bị lộ hay chưa.**
- **Không có state replay/copy tracking** cho nhiều lần import cùng vật liệu.
- **Không chứng minh rằng AES key sau import có tính non-exportable.**
- **Không kiểm tra nonce uniqueness xuyên các ứng dụng có cùng AES key**; sanity test chỉ tạo một nonce.
- **Không chứng minh data cipher hợp lệ trên mọi dữ liệu lịch sử**; chỉ test một message vô hại.
- **Không đảm bảo xóa key tuyệt đối khỏi heap/native memory**.
- **Không áp dụng HSM-specific key block format, PKCS#11 import hoặc real BYOK SDK**.

Nếu khóa đích phải **non-exportable**, sản phẩm thật thường cần **HSM/KMS-native ImportKey/UnwrapKey** bên trong boundary, thay vì xây SecretKeySpec từ raw bytes như demo.

## 12. Java KeyStore, PKCS#11 và import certificate: dùng đúng lớp abstraction

### 12.1. Import public key với JCA

Một public key RSA ở dạng **SubjectPublicKeyInfo DER** có thể được parse qua:

~~~java
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;

// bytes DER của SPKI đã được lấy từ nguồn đáng tin.
// Parse đúng cấu trúc chưa đồng nghĩa tin đúng danh tính.
PublicKey publicKey = KeyFactory.getInstance("RSA")
    .generatePublic(new X509EncodedKeySpec(trustedSpkiDer));
~~~

**Không bỏ qua trust binding.** Nếu cần certificate chain, hostname/issuer/usage validation, dùng **PKI/X.509 validation phù hợp use case**. Việc parse key bằng KeyFactory **không tự xác nhận CA/certificate**.

### 12.2. Khi dùng KeyStore

JCA KeyStore cung cấp abstraction cho keys/certificates, có thể dùng provider **PKCS12** hoặc HSM-backed provider. Nhưng:

- **PKCS#12** là container; việc được bảo vệ bởi password phụ thuộc algorithm/PBE và secret handling.
- **Encrypted private key** không thể coi là an toàn nếu password lưu hard-code cùng file.
- **PKCS#8 DER chưa mã hóa** chứa private key material dạng rõ; không đưa vào source repository.
- Import một private key vào **software KeyStore** có thể khiến nó tồn tại trong RAM/application process; không đồng nghĩa key non-exportable.
- Certificate trong KeyStore cần trust/issuer policy rõ: một self-signed cert được “add vào trust store” có thể trở thành trust anchor của ứng dụng.

**Không tự coi mọi KeyStore trong Java là HSM.** Chọn provider và xác minh key handle/attributes theo môi trường.

### 12.3. PKCS#11

**PKCS#11** mô tả interface tới cryptographic tokens/HSM. Với nhà cung cấp JCA hỗ trợ PKCS#11, ứng dụng có thể sử dụng **key handles** để gọi Sign/Decrypt/Unwrap mà không cần raw key bytes.

Tuy nhiên:

- Setup provider và token/PIN/session là **vendor- and environment-specific**.
- Cơ chế import/wrap được phép phụ thuộc HSM mechanism list và key attributes.
- Một key non-extractable **không thể tự nhiên bị chuyển thành extractable** bằng cách gọi getEncoded().
- HSM may require **dual control/quorum** hoặc secure key block format.
- Không đặt HSM PIN/credential trong Java source, logs hoặc test fixtures.
- Cần review quyền tạo object, import/wrap/unwrap, export, destroy và audit.

**PKCS#11 là interface**, không là một chuẩn duy nhất đảm bảo mọi loại key có thể được import vào mọi HSM bằng cùng lệnh.

### 12.4. Imported private key dùng để ký

Với private signing key, sau import có thể cần **pairwise consistency check**:

~~~text
Destination HSM private Sign(test challenge)
          |
          v
Trusted public verification key + Verify(signature)
          |
          +-- PASS -> đúng cặp key trong phạm vi operation
          +-- FAIL -> điều tra alias/version/format/provider
~~~

**PCT không chứng minh public key thuộc danh tính đối tác** và không đo entropy. Key certificate/trust distribution cần được duyệt riêng.

## 13. Post-import acceptance gates: không tự kích hoạt key vừa nhập

### 13.1. Sáu nhóm kiểm tra

~~~mermaid
flowchart TD
    A["Provider import reports success"] --> P{"Policy/profile đúng?"}
    P -->|No| Q["Quarantine + finding"]
    P -->|Yes| O{"Origin/provenance và transport evidence?"}
    O -->|No| Q
    O -->|Yes| T{"Key attributes/usage/exportability đúng?"}
    T -->|No| Q
    T -->|Yes| F{"Functional check/PCT phù hợp?"}
    F -->|No| Q
    F -->|Yes| IAM{"IAM/owner/custodian/recovery đầy đủ?"}
    IAM -->|No| Q
    IAM -->|Yes| E{"Audit evidence + approval?"}
    E -->|No| Q
    E -->|Yes| ACT["Activate cho approved workload"]
~~~

| Gate | Điều kiện đạt | Ví dụ evidence |
| --- | --- | --- |
| **Policy** | Key type/algorithm/size/purpose được phép | Approved import request, policy version |
| **Provenance/transport** | Nguồn, recipient, wrapping/token và integrity đáng tin | Attestation/custody record, provider logs |
| **Attributes** | Key ID/version, origin, exportability, usage/state đúng | DescribeKey/HSM object metadata |
| **Function** | Đúng material hoặc pairwise operation theo use case | Wrapped test DEK, challenge signature, test decrypt |
| **Governance** | Owner, custodian, IAM least privilege, expiration/recovery | Inventory, effective grants, recovery plan |
| **Approval/audit** | Bằng chứng có provenance, người duyệt có thẩm quyền | Audit event, change ticket, immutable manifest |

**Key import thành công không mặc nhiên chuyển khóa sang ACTIVE ở tầng nghiệp vụ.** Nếu KMS đích tạo key trạng thái Enabled, application/KMS policy vẫn phải giới hạn quyền production cho đến khi các gates đạt.

### 13.2. Functional checks theo key type

| Key type | Test có thể phù hợp | Điều không được suy diễn |
| --- | --- | --- |
| **Imported AES DEK** | Giải mã test ciphertext từ nguồn hoặc test challenge có kiểm soát | Không chứng minh entropy hoặc không có bản source copy |
| **Imported KEK** | Unwrap một **test wrapped DEK** được chuẩn bị đúng provider/profile | Không tự chứng minh toàn bộ backups sẽ restore |
| **HMAC secret** | Verify test MAC, reject modified message | Không chứng minh key chỉ người Verify nắm |
| **Private Ed25519/RSA signing key** | Sign challenge và Verify với trusted public mapping | Không chứng minh signer trust chỉ từ Verify=true |
| **Public verification key** | Parse/profile/trust chain và test signature đúng nguồn | Không cần hay không nên nhập private key |
| **Root/derivation key** | HSM/provider attestation và allowed DeriveKey test phù hợp | Không cần xuất master secret để kiểm tra |
| **X25519 static key** | Provider key agreement check trong test được phê duyệt | Không thay peer authentication/protocol review |

Không phải mọi provider hỗ trợ test raw operations trước activation. Khi thiếu evidence bắt buộc, ghi **NOT_EVALUATED/INSUFFICIENT_EVIDENCE**, không ghi PASS cho đẹp báo cáo.

### 13.3. Phân biệt key state ở KMS với business readiness

Ví dụ:

~~~text
KMS key state       = ENABLED
Application registry = PENDING_VALIDATION
IAM production       = DENY import target pending approval

Sau acceptance:
KMS key state       = ENABLED
Application registry = ACTIVE
IAM production       = ALLOW đúng key/action/context
~~~

Đây là **mẫu kiến trúc**, không phải tên state chung của mọi KMS. Cần bảo đảm application không thể bỏ qua registry bằng cách gọi KMS trực tiếp qua credential quá rộng.

## 14. IAM, dual control và trách nhiệm khi import

### 14.1. Tách người đề xuất, người xuất và người nhập

| Vai trò | Trách nhiệm | Quyền không nên tự động có |
| --- | --- | --- |
| **Key owner** | Phê duyệt purpose, target, cryptoperiod và risk | Raw secret hoặc quyền nhập mọi key |
| **Source custodian** | Quản trị vật liệu nguồn, export/wrapping ceremony, audit | Quyền Decrypt toàn bộ data ở đích |
| **Destination custodian** | Tạo target resource, import theo runbook, backup/recovery | Tự chấp nhận rủi ro hoặc đọc toàn bộ plaintext |
| **KMS/HSM administrator** | Cấu hình key policy, key state và IAM theo approval | Tự cấp Decrypt/Sign rồi tự xóa logs |
| **Application owner** | Xác định workload và quyền cần, kiểm tra use case | Thay private key/trust tùy ý |
| **Security reviewer** | Thẩm định provenance, transport, attributes, IAM | Phải nắm raw key |
| **Risk/exception approver** | Chấp nhận ngoại lệ đúng phạm vi/expiry | Bỏ qua audit hoặc phá non-exportable rules |
| **Auditor** | Xác minh independent evidence và closure | Import/Export trực tiếp nếu không cần |

### 14.2. Separation of duties (SoD)

Các tổ hợp nguy hiểm:

- **Export raw KEK + Import + tự phê duyệt**.
- **Import private signer + sửa public trust registry + Sign tùy ý**.
- **Create/UpdateGrant + Decrypt imported key + xóa audit**.
- **Destroy source key + phá recovery backup + xác nhận migration đã hoàn tất**.
- **Quản trị key và cùng lúc là approver duy nhất của exception**.

Đối với root/KEK/signing key trọng yếu có thể cần **two-person control, split knowledge, M-of-N quorum, protected key ceremony và independent verification** theo thiết kế HSM. **Dual approval** (chia trách nhiệm quyết định) không tự tương đương **split knowledge** (chia vật liệu/khả năng tái tạo secret).

### 14.3. Phân quyền import và quyền sử dụng là hai việc khác nhau

Một workload chỉ cần Encrypt/GenerateDataKey có thể không cần quyền ImportKeyMaterial hoặc Unwrap mọi DEK lịch sử. Ngược lại, người được phép import không nên tự nhiên có quyền Sign/Decrypt dưới key đó.

Review effective permissions gồm identity policies, resource key policies, assumed roles, cross-account grants, session policies và administrative escalation paths theo provider.

### 14.4. KMS encryption context không thay business authorization

Nếu nhập KEK phục vụ tenant A và sau đó Unwrap DEK:

- Key policy phải giới hạn **principal/key/action**.
- Context/AAD của wrapping phải gắn **purpose, tenant, environment** theo provider.
- Application vẫn xác thực **principal–tenant–object** trước khi gọi KMS.
- Data ciphertext có thể dùng **AAD-data riêng** để ràng buộc object.
- Caller không được tự lấy tenant từ header chưa tin rồi coi đã được phân quyền.

**Import đúng key vào đúng KMS không bảo đảm mọi use case sau đó tự an toàn.**

## 15. Vòng đời của imported material: expiration, re-import, rotation, destruction

### 15.1. Key lifecycle không bắt đầu lại từ số không

Một key đã tồn tại ở source có **tuổi, usage history, cryptoperiod và compromise history**. Import không biến nó thành “new cryptographic key material” với vòng đời hoàn toàn mới.

Ví dụ:

~~~text
2025: AES KEK-v1 generated tại source HSM
2025–2026: KEK-v1 Wrap dữ liệu mới theo cryptoperiod
2026: Import cùng material vào destination KMS
2026: Destination tiếp tục Unwrap legacy DEKs
2027: Migration hoàn tất, old KEK có thể retire/destroy
~~~

Trong ví dụ, năm import **không tự trở thành ngày sinh vật liệu** để kéo dài cryptoperiod. Cần lưu cả **original generation time** và **destination import time**, nếu có thể xác minh.

### 15.2. Imported material expiry khác wrapping token expiry

Một số provider có thể có hai thời hạn:

- **Wrapping key/import token expiry:** thời gian mà **một yêu cầu import** còn có thể dùng wrapping parameters đó.
- **Imported key material expiration:** thời điểm **vật liệu đã nhập** có thể bị vô hiệu/xóa theo cấu hình dịch vụ.

Hai thời hạn không giống nhau. Nếu imported material hết hạn trong KMS và ciphertext còn phụ thuộc, **Unwrap/Decrypt có thể thất bại** dù encrypted data vẫn nguyên.

Những câu hỏi cần đáp:

1. Provider hỗ trợ expiry options nào?
2. Có thể gia hạn hoặc re-import không, và cần material nào?
3. Material backup có còn an toàn và đúng quyền không?
4. Nếu re-import, key ID/alias/version có đổi?
5. Nếu source đã hủy, có còn recovery path hợp lệ?
6. Có cảnh báo trước expiry, chặn deletion và test restore?

Không suy luận provider behavior từ tên field “expiresAt” của một tài liệu không chính thức.

### 15.3. Import, rewrap và re-encrypt sau migration

~~~text
Case A — Import same KEK material:
    Old wrapped DEKs có thể tiếp tục được mở nếu format/provider
    tương thích và key references/attributes được ánh xạ đúng.

Case B — Create new destination KEK:
    Unwrap old DEKs ở source, Wrap lại dưới destination KEK.
    Data ciphertext có thể giữ nguyên -> rewrap.

Case C — DEK material bị lộ/yếu:
    Tạo DEK mới, Decrypt + Encrypt data thành ciphertext mới.
    -> re-encrypt.

Case D — Private signing key không export được:
    Tạo signing key đích và cập nhật trust/cert/verification
    theo policy, không ép xuất private key nguồn.
~~~

Đừng nhầm **đổi KEK** với **đổi DEK**. Rewrap cùng DEK không sửa được sự cố raw DEK đã bị lộ.

### 15.4. Quy tắc không destroy source quá sớm

Trước khi source KEK/private key bị hủy:

- Inventory dữ liệu/signatures/backup còn phụ thuộc.
- Đánh giá khả năng key material thật sự chuyển được và **provider compatibility**.
- Chạy test decrypt/verify/unwrap những mẫu phù hợp.
- Thử **restore** từ backup cần giữ, gồm wrapped DEK, nonce/tag/AAD và context.
- Đảm bảo rollback/cutover, concurrent writers và key mapping không lỗi.
- Có approval của owner/custodian và audit độc lập.
- Chỉ destroy sau khi không còn phụ thuộc hoặc đã có recovery đã phê duyệt.

**Một encrypted backup có checksum đúng vẫn không dùng được khi mất khóa để unwrap DEK.**

## 16. Import KEK trong envelope encryption

Một trường hợp phổ biến là chuyển một **KEK cũ** sang KMS mới để tiếp tục đọc DEKs lịch sử.

~~~mermaid
flowchart TD
    DATA["Old ciphertext AES-GCM"] --> PACKAGE["Envelope: nonce/tag/AAD + wrappedDEK + old KEK ref"]
    KOLD["Old KEK material tại source"] --> IMPORT["Approved secure key import/migration"]
    IMPORT --> KNEW["Destination KMS key / key reference"]
    PACKAGE --> RESOLVE["Trusted mapping old ref -> destination key"]
    KNEW --> UN["KMS Unwrap old wrapped DEK nếu compatible"]
    RESOLVE --> UN
    UN --> DEK["DEK trong authorized boundary"]
    DEK --> READ["AES-GCM Decrypt + expected AAD"]
    READ --> VALID["Authenticated plaintext only"]
~~~

### 16.1. Tính tương thích không tự đến từ việc key bytes giống nhau

Để unwrap một blob cũ, cần có:

- **Đúng KEK material** hoặc migration path hợp lệ.
- **Đúng wrapping algorithm**, IV/nonce/tag, padding/label hoặc provider-specific format.
- **Đúng key ID/version mapping** và encryption context.
- **Đúng key permissions và key state**.
- **Đúng key attributes/purpose** cho Unwrap.
- Metadata đầy đủ để dựng context đúng.
- Kiểm soát input không cho untrusted blob chọn key tùy ý.

Một blob được tạo bởi provider A có thể là **opaque/provider-specific**, không chắc có thể Unwrap bởi provider B chỉ vì nhập cùng raw KEK. Đôi khi cần **Unwrap tại source rồi Wrap tại destination** dưới một workflow được phê duyệt, thay vì import nguyên bytes.

### 16.2. Rewrap có thể tránh import raw KEK

Nếu source HSM không cho xuất root/KEK, giải pháp có thể là:

1. Source HSM **Unwrap DEK** trong boundary được cho phép.
2. Chuyển DEK sang destination bằng secure key transfer hoặc approved rewrap path.
3. Destination KMS **Wrap DEK** dưới KEK mới.
4. Thay metadata envelope có tính nhất quán.
5. Giữ data ciphertext/nonce/tag không đổi.
6. Kiểm tra khả năng Decrypt và backup/rollback.

Đây vẫn là một quy trình **key distribution cho DEKs**, nhưng tránh cố export source KEK non-exportable. Không giả định mọi cặp HSMs có thể chuyển DEK mà không từng lộ plaintext ở trung gian; cần xác minh design thực tế.

### 16.3. Bảo vệ dữ liệu nhiều tenant

Một KEK dùng chung có thể bọc DEKs của nhiều tenants. Import nó sang một KMS mới **không tự tạo tenant isolation**. Xem xét:

- KEK per-tenant hoặc key scopes được IAM ràng buộc khi threat model cần.
- Business authorization principal→tenant→object.
- Trusted mapping từ envelope đến key resource.
- Context/AAD theo tenant/object.
- Audit Decrypt/Unwrap usage và rate limits.
- Không cache plaintext DEKs xuyên tenant không có isolation.

**KMS encryption context, AES-GCM data AAD và IAM/business authorization là ba kiểm soát bổ trợ, không thay thế nhau.**

## 17. Audit và key inventory sau import

### 17.1. Một bản ghi key inventory minh họa

~~~yaml
keyId: imported-billing-kek-example
keyClass: KEK
service: billing
environment: production
sourceOrigin: EXTERNAL_APPROVED_HSM
sourceKeyRef: "source-hsm://opaque-key-reference"
originalGenerationRef: "evidence://source-creation"
destinationProviderRef: "kms://account/region/imported-key"
destinationImportTime: "2026-11-28T03:00:00Z"
materialOriginType: EXTERNAL_IMPORT
approvedAlgorithmProfile: approved-kek-profile-v2
purpose: wrap-legacy-billing-deks
currentUse: UNWRAP_LEGACY_ONLY
nonExportableAtDestination: true
ownerRole: billing-platform
sourceCustodianRole: crypto-operations-source
destinationCustodianRole: crypto-operations-destination
importApprovalRef: "change://key-import-approved"
transportEvidenceRef: "evidence://wrapped-transfer-record"
keyAttributesEvidenceRef: "evidence://destination-attributes"
functionalEvidenceRef: "evidence://legacy-unwrap-test"
materialExpiryRef: "policy://imported-material-expiry"
recoveryPolicyRef: "policy://imported-key-recovery"
dependentDataIndexRef: "inventory://wrapped-dek-index"
status: PENDING_APPROVAL
~~~

Đây là **metadata giả định**. Không đưa **raw AES/KEK/DEK, private signing key, HMAC secret, HSM recovery shares, password hoặc import secret token còn dùng được** vào inventory.

### 17.2. Evidence manifest cho một lần import

| Sự kiện | Bằng chứng cần lưu theo quyền |
| --- | --- |
| Request/approval | Key class, purpose, target ID, policy version, owner |
| Source generation/ownership | Source key reference, custody, provider/health evidence |
| Export/wrapping ceremony | Who/when/approved mechanism, transport profile |
| Recipient wrapping key | Trusted fingerprint/attestation, target, token expiry metadata |
| Import API call | Actor, target key ID, environment, success/error, request ID |
| Post-import attributes | Algorithm/size/usage/exportability/origin/state |
| PCT/functional test | Test ID/result trên dữ liệu giả, không raw key |
| IAM grants | Effective access snapshot, approver, least privilege |
| Backup/recovery | Source copies, expiry monitoring, restore-test outcome |
| Activation/cutover | Policy decision, workload routing, rollback plan |
| Revoke/destroy | Dependency check, approval và destruction evidence |

### 17.3. Không làm rò key khi cố chứng minh “chúng tôi đã import đúng”

Không nên đính kèm:

- File private key PEM/PKCS#8 chưa mã hóa vào ticket.
- Dòng log chứa hex/base64 AES KEK.
- Import token có giá trị sử dụng thực tế và authentication credentials.
- Certificate private key hoặc HSM recovery shares.
- Dump bộ nhớ của JVM chứa raw DEK/KEK.
- Plaintext data để minh họa Decrypt thành công.
- ECDH shared secrets hoặc session traffic keys.

Thay bằng **opaque key reference, provider signed/immutable audit, key attributes, test identifiers, redacted metadata, approval và evidence integrity**.

Một **Key Check Value** hoặc hash/fingerprint nếu dùng phải theo scheme phù hợp, không thay chứng cứ nguồn gốc và không được tiết lộ quá mức cần thiết.

### 17.4. Sự kiện phải cảnh báo sau import

- Import vào account/region/partition không đúng policy.
- Grant Decrypt/Unwrap/Sign mở rộng khi key trở thành ACTIVE.
- Imported material hoặc import token sắp hết hạn.
- Key ID/alias đổi đích không có approval.
- Source key còn raw copies ở những nơi không được quản lý.
- Decrypt/Unwrap volume đột biến sau migration.
- Wrapped DEK legacy không còn mở được khi restore.
- Provider key state chuyển DISABLED/PENDING_DELETION ngoài kế hoạch.
- Public signing/verification key registry bị thay trái phép.
- Re-import, export, destroy hoặc key material deletion ngoài change window.

**Key import phải đi kèm giám sát vòng đời**, không kết thúc ở lần đầu provider báo thành công.
## 18. Import thất bại hoặc nghi bị lộ key: xử lý ra sao?

### 18.1. Phân loại failure trước khi retry

~~~mermaid
flowchart TD
    F["Import failure / suspicious event"] --> B["Stop activation + preserve metadata/audit"]
    B --> D{"Loại vấn đề?"}
    D -->|"Wrong algorithm/size/format"| FORMAT["Check approved profile; reject invalid material"]
    D -->|"OAEP/tag/recipient mismatch"| TRANS["Check trusted recipient, token, wrapping params"]
    D -->|"IAM/approval mismatch"| IAM["Restrict grants, verify role and target"]
    D -->|"Material expired / lost"| REC["Recovery and re-import feasibility assessment"]
    D -->|"Suspected key exposure"| INC["Immediate incident response + scope assessment"]
    FORMAT --> Q["Quarantine until independent review"]
    TRANS --> Q
    IAM --> Q
    REC --> Q
    INC --> Q
    Q --> R{"Approved safe remediation?"}
    R -->|"Yes"| RET["New trusted wrapping params / re-import / migrate"]
    R -->|"No"| HOLD["Remain disabled; escalate and protect dependent data"]
    RET --> TEST["Revalidate key, IAM, restore, audit"]
    TEST --> A{"All gates pass?"}
    A -->|"Yes"| ACTIVE["Controlled activation"]
    A -->|"No"| HOLD
~~~

Một import operation lỗi **không tự có nghĩa material đã lộ**, nhưng cũng không tự chứng minh không có sự cố. Cần tìm bằng chứng trước khi quyết định:

- **Key mismatch:** có thể do sai wrapping public key, OAEP params/label, import token hoặc key material.
- **Expired token:** có thể chỉ cần request wrapping parameters mới; không phải tự nhiên raw key bị compromise.
- **Unsupported key type:** không thể sửa bằng cách đổi nhãn; phải chọn mechanism/provider được phê duyệt.
- **BadPadding/AEAD tag failure:** xem blob integrity/recipient binding, không được fallback sang insecure padding.
- **Wrong account/region:** tạm cô lập key ở đích sai, kiểm tra IAM và sự tồn tại của mọi bản copy.
- **Source secret unexpectedly visible:** xem xét key material compromise, ứng phó sự cố, rekey/re-encrypt.
- **Re-import bị từ chối:** kiểm tra provider constraints, source backup, key ID/versions và recovery workflow.
- **Data decrypt sau import fail:** có thể do key material sai, envelope format, AAD/context, nonce/tag hoặc wrong key mapping.

### 18.2. Điều không nên làm khi import thất bại

Không:

1. Thử truyền **raw key trực tiếp** qua API không đúng policy.
2. Paste key hex/Base64 vào ticket để nhờ đội khác kiểm tra.
3. Chuyển từ RSA-OAEP sang RSA PKCS#1 v1.5 chỉ vì provider đang trả lỗi.
4. Tắt certificate validation để fetch wrapping public key.
5. Thử mọi alias/KEKs trong production cho tới khi một key giải mã được.
6. Tự tái sử dụng import token đã hết hạn hoặc thuộc target khác.
7. Xóa source key vì “đích đã import thành công” mà không restore test.
8. Dùng cùng nguyên liệu khóa đã nghi lộ để tiếp tục bảo vệ dữ liệu mới.
9. Giữ temporary import files và build artifacts chứa raw secrets trên CI.
10. Kết luận PASS khi chưa có đủ evidence về origin, recipient và usage.

### 18.3. Quy trình nếu raw material có thể đã bị lộ

Nếu raw KEK/DEK/private signer đã xuất hiện trong logs, file share hoặc endpoint bị chiếm:

- **Containment:** cô lập principals, tạm dừng import/use và bảo vệ evidence.
- **Inventory:** xác định nơi key material được tạo, xuất, wrap, nhập và sao lưu.
- **Scope:** tìm dữ liệu/ciphertext, wrapped DEKs, signatures, tickets và backups phụ thuộc.
- **Risk:** key đó là DEK, KEK, root, signing hay HMAC? Nguồn lộ có cho phép attacker đọc/giả mạo gì?
- **Remediation:** có thể cần **new DEK + re-encrypt**, **new KEK + rewrap**, **signing key rotation/trust update** hoặc **HMAC key replacement**, tùy scope.
- **Credential control:** sửa IAM/grants/transport pipeline đã làm material lộ.
- **Recovery:** tránh destroy key cũ nếu chưa có đường restore dữ liệu hợp lệ.
- **Audit:** lưu bằng chứng và người ra quyết định, không tiếp tục phát tán raw secret.

**Rewrap một DEK đã bị lộ dưới KEK mới không làm DEK đó an toàn trở lại.** Tương tự, import một raw KEK nghi lộ vào HSM đích không xóa rủi ro với ciphertext và wrapped DEKs đã bị sao chép.

## 19. Tình huống thực tế A: attacker thay public wrapping key

### 19.1. Bối cảnh

Một đội đang thực hiện BYOK import KEK từ source HSM sang cloud KMS. Script tải public wrapping key từ một URL do tham số deployment chỉ định, không xác thực hostname/certificate đúng cách. Attacker có thể sửa endpoint hoặc response, cung cấp RSA public key của chính họ.

Script dùng RSA-OAEP để wrap KEK. Phép toán thành công và có ciphertext hợp lệ, nhưng **đã wrap cho attacker**.

### 19.2. Phân tích sự cố

- **RSA-OAEP có thể hoạt động chính xác:** OAEP không tự quyết định ai là recipient đáng tin.
- **TLS sai trust:** script tin endpoint không hợp lệ, mở đường key substitution.
- **Raw secret có thể đã lộ cho attacker** khi attacker nhận ciphertext và có matching private key.
- KMS thật có thể từ chối blob, nhưng việc nó từ chối **không xóa việc key đã được wrap cho attacker**.

### 19.3. Thiết kế đúng

1. Chỉ lấy wrapping params từ **provider endpoint/SDK đã xác thực**, đúng account/region/key ID.
2. Kiểm tra token/attestation hoặc public key fingerprint bằng **nguồn tin cậy độc lập**.
3. Ràng buộc target/purpose/wrapping profile trước khi xuất vật liệu nguồn.
4. Không gửi wrapped blob tới endpoint bất kỳ chưa được duyệt.
5. Thu chứng cứ receipt/response và source/destination audit.
6. Nếu nghi recipient substitution đã xảy ra, **coi secret có khả năng compromised** và xử lý theo incident scope; không chỉ retry import.

**Bài học:** “Đã mã hóa secret trước khi gửi” là chưa đủ; phải biết chính xác **secret được mã hóa cho ai**.

## 20. Tình huống thực tế B: imported KEK hết hạn trong khi backup vẫn phụ thuộc

### 20.1. Bối cảnh

Một tổ chức dùng imported KEK để mở wrapped DEKs của dữ liệu nhiều năm. Khi import, team đặt **expiration** quá ngắn vì nhầm với thời hạn wrapping token. Key hoạt động ổn ở ngày đầu, sau đó material hết hiệu lực trong KMS.

Đến khi cần khôi phục backup, hệ thống vẫn có:

~~~text
data ciphertext + nonce/tag + AAD schema
wrapped DEK + KEK reference
backup checksum valid
~~~

Nhưng thiếu **KEK material có thể dùng để Unwrap** tại destination.

### 20.2. Hướng xử lý và phòng ngừa

- Phân biệt **import token expiration** với **key material expiration**.
- Giữ source material backup theo policy, hoặc xác định provider re-import path đã được thử.
- Đặt cảnh báo trước expiry và kiểm soát pending deletion.
- Duy trì **key dependency map** tới datasets/backups/retention.
- Thử restore từ backup đại diện, không chỉ kiểm tra hash.
- Không hủy source HSM key khi chưa xác nhận destination recovery và dữ liệu lịch sử.
- Nếu material có thể bị xóa, thiết kế giải pháp **migrate/rewrap** trước mốc đó.

Một import “đúng và an toàn” vẫn có thể là sự cố **availability** nếu không kiểm tra vòng đời material.

## 21. Tình huống thực tế C: private signing key không thể export

### 21.1. Bối cảnh

ReleaseService dùng private Ed25519 signing key non-exportable trong HSM nguồn. Đội triển khai muốn chuyển sang cloud KMS, nhưng KMS không có một workflow tương thích để đưa **raw private key** từ HSM nguồn sang đích mà giữ nguyên ranh giới non-exportability.

### 21.2. Không nên phá policy chỉ để giữ khóa cũ

Không nên:

- Giả mạo một đường raw export từ HSM.
- Ghi private key ra PKCS#8 PEM không mã hóa trên laptop.
- Tắt non-extractable attribute và coi đó là thay đổi vô hại.
- Dùng shared credential để export key ngoài approval.
- Nhập public key rồi tuyên bố đã import private signer.

### 21.3. Các chiến lược hợp lý

| Lựa chọn | Khi nào phù hợp? | Điều phải giải quyết |
| --- | --- | --- |
| **Giữ HSM nguồn để Sign** | Cần giữ identity cũ và provider tương thích vẫn có thể vận hành | Latency, IAM, audit, availability, expiry |
| **Secure HSM-to-HSM migration** | Cả hai hỗ trợ mechanism/attributes được phê duyệt | Quorum, key block/trust, attestation, không lộ raw material ngoài boundary |
| **Tạo signing key mới ở đích** | Không thể hoặc không được export private key cũ | Cập nhật trust/certificate/JWKS, key IDs, signed artifacts historical verification |
| **Chuyển use case theo giai đoạn** | Client cũ chưa cập nhật trust được cùng lúc | New signing key activation, old Verify-only policy, revocation plan |

**Signatures lịch sử** có thể cần public verification key/trust evidence của khóa cũ dù private signing key không còn tạo chữ ký mới. Đây là một **vấn đề identity và trust rollover**, không chỉ import bytes.

## 22. Tình huống thực tế D: import cùng DEK vào hai nơi, nonce bị trùng

### 22.1. Bối cảnh

Hai khu vực xử lý dữ liệu độc lập import **cùng AES-256 DEK** để tạo ciphertext. Cả hai nhóm dùng AES-GCM với nonce là counter bắt đầu từ 0, và không có cơ chế phân chia không gian nonce.

Khi hai khu vực cùng Encrypt:

~~~text
Region A:
    key = shared DEK; nonce = 000...001; plaintext = A
Region B:
    key = shared DEK; nonce = 000...001; plaintext = B
~~~

Đây là **nonce reuse dưới cùng key AES-GCM** dù key import, length và provider đều hợp lệ.

### 22.2. Hậu quả và xử lý

- Trùng nonce có thể làm tổn hại nghiêm trọng **confidentiality và integrity** của GCM.
- Việc import thành công không kiểm tra được chiến lược nonce toàn hệ thống.
- Không sửa bằng cách chỉ rotate KEK bọc DEK; raw **data key vẫn là cùng DEK**.
- Cần đánh giá dữ liệu/ciphertexts affected, tạo **DEKs mới**, re-encrypt khi phù hợp.
- Kiến trúc nên dùng DEK-per-object/region hoặc chiến lược nonce được thiết kế/chứng minh phù hợp.
- Theo dõi key usage và giới hạn số Encrypt mỗi DEK.

**Bài học:** Imported key material có lịch sử sử dụng và domain sử dụng thực tế. Không thể coi mỗi bản import là một namespace GCM nonce mới.

## 23. Các anti-pattern khi triển khai key import

| Sai lầm | Vì sao nguy hiểm? | Cách cải thiện |
| --- | --- | --- |
| **Gửi AES/KEK raw qua email/ticket** | Secret bị lưu nhiều bản, khó thu hồi | Secure wrapping và approved transfer path |
| **Base64 key rồi gọi là encrypted** | Base64 không bảo vệ bí mật | AEAD/key wrap/RSA-OAEP theo profile |
| **Tin wrapping public key từ request bất kỳ** | Key được bọc cho attacker | Verified recipient/attestation/pinning |
| **Tắt TLS certificate validation** | MITM/key substitution | Endpoint identity validation |
| **OAEP dùng tham số không rõ** | Không tương thích, downgrade, import failure | Explicit hash/MGF/label profile |
| **Fallback sang ECB/CBC/RSA v1.5** | Có thể tạo key exposure hoặc oracle | Fail closed, migration legacy riêng |
| **Import key type không được provider hỗ trợ** | Thất bại/không có metadata đúng | Capability check trước khi export |
| **Gán lại tên key ID để che mismatch** | Ciphertext/trust có thể giải sai key | Validate material, alias/version binding |
| **Import key nhưng quên history/cryptoperiod** | Dùng quá hạn, bỏ qua compromise history | Original generation/usage refs |
| **Coi non-exportable đích xóa source copy** | Raw key vẫn có thể lộ tại nguồn | Source custody/copy inventory |
| **Giữ temporary raw files trên CI** | Artifacts/logs/backup làm lộ key | Controlled in-memory/HSM mechanism |
| **Người import tự cấp Decrypt rồi tự xóa logs** | Self-escalation và che lạm dụng | SoD, key policy review, immutable audit |
| **Import key rồi bỏ qua PCT/functional test** | Wrong material hoặc wrong mapping | Test đúng key type và trust |
| **So KCV rồi coi key an toàn** | KCV không chứng minh entropy/trust | Provenance + cryptographic integrity |
| **Cho caller chọn tenant/key ID từ header** | Cross-tenant key misuse | Trusted policy/resource mapping |
| **Import vào mọi region với cùng DEK GCM** | Nonce collisions xuyên region | Key/domain separation hoặc nonce plan |
| **Không theo dõi imported material expiration** | KMS mất khả năng mở ciphertext | Alert, re-import/recovery |
| **Xóa source key ngay sau Import=SUCCESS** | Backup/ciphertext cũ chưa verified | Restore + dependency check |
| **Nhầm import KEK với DEK re-encrypt** | Đánh giá sai rủi ro lộ data key | Tách material import/rewrap/re-encrypt |
| **Coi transport TLS đủ bảo vệ nội dung key** | Raw key có thể lộ ở endpoint/logs | Wrap cho authenticated recipient, minimize copies |
| **Public key parse được thì đáng tin** | Chấp nhận signer giả | Certificate/JWKS provenance và issuer binding |
| **Import private key PEM vào source repository** | Secrets bị nhân bản và khó xóa | HSM/secure keystore với lifecycle/approval |
| **Import lỗi rồi thử mọi alias cho đến khi mở được** | Key confusion và oracle | Trusted key mapping, quarantine |
| **Không có cutover/rollback plan** | Mất availability, inconsistent versions | Staged migration, atomic updates |
| **Key acceptance chỉ nhìn HTTP 200** | Bỏ IAM/provenance/recovery gaps | Multi-gate post-import review |

## 24. Checklist triển khai key import an toàn

### Quyết định và xác minh nguồn

1. Xác định **vì sao phải import** thay vì generate key mới tại đích?
2. Key class là **DEK, KEK, root, HMAC, private signer, public key** hay handle?
3. Có phân biệt **secret material import** và đăng ký public key/reference?
4. Owner/custodian và source generation provenance đã được phê duyệt?
5. Material được sinh qua CSPRNG/HSM phù hợp, không dùng seed yếu?
6. Có kiểm tra algorithm, key length, curve, usage, format và cryptoperiod?
7. Có biết material từng được dùng để Encrypt/Sign/Wrap ở những nơi nào?
8. Source key có thể export đúng policy hay cần HSM-secure migration?
9. Có kiểm kê các raw copies, backup, escrow, temporary files tại nguồn?
10. Có impact analysis nếu source key đã nghi lộ hoặc bị revoke?

### Đích, transport và wrapping

11. Có xác minh **KMS/HSM destination account/region/partition/key ID**?
12. Destination có hỗ trợ import loại khóa và profile đó?
13. Public wrapping key/attestation được lấy từ **nguồn đáng tin**?
14. Có so recipient fingerprint/chain/token với target được duyệt?
15. Có kiểm tra import token/wrapping key freshness và binding?
16. Có dùng đúng AES-KW/KWP, RSA-OAEP hoặc provider secure key block?
17. OAEP hash, MGF1, label và wrapping parameters được nêu rõ?
18. Có tránh Base64/PEM raw secret qua chat/ticket/CI artifacts?
19. Có TLS peer authentication và bảo vệ endpoint/logging/credentials?
20. Có confidentiality, integrity và replay/target binding theo protocol?
21. Import failure có fail-closed, không fallback cipher/padding yếu?
22. Hệ thống không yêu cầu xuất raw non-exportable key trái chính sách?

### Acceptance và quyền truy cập

23. Key import thành công được xác minh bằng metadata từ provider?
24. Algorithm, size, origin, exportability, allowed operations đúng profile?
25. Có PCT/functional sanity test phù hợp, bằng dữ liệu test?
26. Với private signer, có xác minh trusted public key mapping?
27. Với public verification key, có issuer/trust/expiry/revocation validation?
28. Có owner/custodian, service purpose, key ID/version trong inventory?
29. IAM effective grants chỉ cấp **principal–key–operation** cần thiết?
30. Quyền Import/Export/CreateGrant/ChangePolicy có SoD?
31. Imported material expiration/re-import obligations được theo dõi?
32. Business authorization principal–tenant–object vẫn được thực thi?
33. Có phân biệt KMS wrapping context với data AAD?
34. Key không bị route production traffic trước approval?
35. Evidence có source/time/scope/integrity, không chứa raw secrets?

### Migration và vòng đời

36. Data/backup/signature dependencies của source key đã được thống kê?
37. Có phân biệt **same material import**, **DEK rewrap**, **DEK re-encrypt**?
38. Nếu KEK đã lộ cùng wrapped DEKs, có đánh giá data/DEK compromise?
39. Nếu DEK yếu/lộ, có kế hoạch tạo DEK mới và re-encrypt phù hợp?
40. AES-GCM nonce uniqueness được kiểm soát xuyên các nơi dùng cùng key?
41. Cutover/rollback, alias/version và concurrent writers được kiểm thử?
42. Có restore test với đúng KEK/version, context, nonce/tag/AAD?
43. Không destroy source key trước khi migration/recovery được xác minh?
44. Có audit key import, Unwrap, usage, grants, expiration và destruction?
45. Có runbook quarantine/incident nếu key bị gửi tới recipient sai?

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Key import khác key generation như thế nào?

**Đáp án:** Generation tạo key material mới; import đưa **material đã có** vào ranh giới đích. Import không tự thay key bytes, không xóa compromise history hoặc làm lại cryptoperiod từ đầu.

**Câu 2.** Vì sao một key AES-256 dài đúng 32 byte vẫn chưa đủ điều kiện import vào production?

**Đáp án:** Độ dài không chứng minh **nguồn entropy, quyền sở hữu, purpose, lịch sử lộ/usage, allowed operations, non-exportability và recovery**. Cần provenance và policy acceptance.

**Câu 3.** Private signing key và public verification key có cần cùng quy trình import không?

**Đáp án:** Không. Public key không cần bảo mật bí mật nhưng cần **trust/identity binding**; private key là secret cần secure transfer/custody, quyền Sign và pairwise consistency theo policy.

**Câu 4.** BYOK có nghĩa imported key chỉ còn một bản trong KMS không?

**Đáp án:** Không. Source có thể vẫn giữ material/backup. Non-exportable ở đích chỉ bảo vệ theo boundary của đích; phải quản lý **source copies và custody**.

**Câu 5.** RSA-OAEP có bảo vệ raw KEK khi attacker thay public wrapping key không?

**Đáp án:** Không. OAEP mã hóa cho private key tương ứng với public key được dùng. Nếu key đó là của attacker, attacker có thể unwrap. Phải **xác thực recipient** trước khi wrap.

**Câu 6.** Vì sao cần xác định OAEP hash và MGF1 hash riêng?

**Đáp án:** Hai thành phần có thể được cấu hình độc lập theo provider. Sai profile làm import không tương thích và có thể dẫn đến fallback nguy hiểm. Cần thỏa thuận **thuật toán chính xác**, bao gồm label.

**Câu 7.** Một file private key định dạng PEM đã được mã hóa chưa?

**Đáp án:** Chưa chắc. PEM chỉ là encoding/container thể hiện bằng Base64 và headers; một PEM có thể chứa **raw private key chưa mã hóa**. Cần kiểm tra đúng format và protection mechanism.

**Câu 8.** Import KEK vào KMS mới có bảo đảm mở được wrapped DEKs từ provider cũ không?

**Đáp án:** Không. Ngoài raw material còn cần **wrapping algorithm, padding/IV/tag, provider-specific blob format, context và key version**. Một blob opaque có thể không portable.

**Câu 9.** Khi nào nên rewrap thay vì import KEK cũ?

**Đáp án:** Khi có thể **Unwrap DEK ở source và Wrap lại bằng destination KEK** theo workflow được phép, nhất là khi source KEK non-exportable hoặc không muốn nhân thêm bản sao KEK. Data ciphertext có thể giữ nguyên.

**Câu 10.** Rewrap DEK cũ bằng KEK mới có giúp xử lý việc raw DEK đã lộ không?

**Đáp án:** Không. Attacker có raw DEK vẫn có thể giải mã ciphertext cũ. Cần đánh giá **tạo DEK mới và re-encrypt**, không chỉ thay lớp wrapping.

**Câu 11.** KMS trả Import=SUCCESS có chứng minh key được sinh từ CSPRNG tốt không?

**Đáp án:** Không. KMS chỉ xác nhận thao tác theo contract. Nguồn entropy/provenance cần có bằng chứng riêng.

**Câu 12.** Import token hết hạn có đồng nghĩa imported material trong KMS bị xóa không?

**Đáp án:** Không nhất thiết. Token expiry và **material expiration** là hai khái niệm khác; semantics cụ thể phải xác minh từ provider.

**Câu 13.** Có thể dùng cùng AES-GCM DEK ở hai region, mỗi region bắt đầu nonce counter từ 0 không?

**Đáp án:** Không an toàn. Cùng key + nonce trùng giữa các phép Encrypt tạo rủi ro nghiêm trọng. Cần tách key/domain hoặc nonce allocation được thiết kế đúng.

**Câu 14.** Vì sao một verifier có thể import public key mà không yêu cầu private key?

**Đáp án:** Chữ ký số được **Verify bằng public key** và Sign bằng private key. Bên chỉ xác minh không nên được giao secret signing material; vẫn phải kiểm tra source trust/identity.

**Câu 15.** KMS non-exportable có chặn toàn bộ lạm dụng key không?

**Đáp án:** Không. Principal có quyền **Decrypt/Unwrap/Sign/GenerateMac** có thể yêu cầu KMS thực hiện thao tác trái phép. Cần least privilege, business authorization và audit.

**Câu 16.** Một KCV khớp có chứng minh khóa không bị lộ trên đường đi không?

**Đáp án:** Không. KCV chủ yếu là tín hiệu đối soát theo profile, không thay **recipient authentication, transport integrity, source custody và incident checks**.

**Câu 17.** Tại sao không xóa source key ngay khi đích báo import thành công?

**Đáp án:** Dữ liệu/backups cũ có thể còn phụ thuộc key, import có thể chưa được kiểm tra thực tế, và recovery ở đích có thể thiếu. Cần **restore tests, key dependency inventory và owner approval**.

**Câu 18.** Một private signing key nguồn non-exportable cần chuyển sang cloud. Có bắt buộc export raw key không?

**Đáp án:** Không. Có thể **giữ Sign tại source, dùng HSM-to-HSM secure migration nếu hỗ trợ, hoặc tạo signing key mới** và chuyển trust/certificate/JWKS theo kế hoạch được duyệt.

**Câu 19.** Vì sao một Java KeyStore lưu private key không mặc nhiên là HSM?

**Đáp án:** KeyStore là abstraction; software PKCS#12 có thể chứa private material trong file/RAM. Một HSM-backed provider có boundary và attributes riêng. Cần xác minh **provider và khả năng export** thực tế.

**Câu 20.** Thế nào là một key import được nghiệm thu?

**Đáp án:** Import có **đúng source/recipient/algorithm/target**, actual key attributes phù hợp; key function/trust được kiểm tra trong phạm vi, IAM và owner/custodian đúng, expiry/recovery/backup có kế hoạch, audit evidence và approval hợp lệ. HTTP success không đủ.

## 26. Kết luận

**Key import là quá trình chuyển quyền quản lý và/hoặc vị trí sử dụng của vật liệu khóa đã tồn tại**, không phải một thao tác tải tệp đơn giản. Nó đòi hỏi bảo đảm **nguồn gốc, recipient trust, cơ chế wrapping, key type/usage, provenance, tính toàn vẹn, IAM, audit, recovery và lifecycle**.

Trong ứng dụng Java, JCA/JCE có thể mô phỏng **RSA-OAEP wrapping AES-256 key, import key bytes tại destination và AES-GCM functional test**, nhưng không thay **KMS/HSM-native key import, attestation, import token, key custody hoặc bảo đảm non-exportable**. Với **KEK/DEK envelope encryption**, phải phân biệt import cùng vật liệu khóa, rewrap DEK và re-encrypt dữ liệu; một lỗi ở key version/context hoặc premature destruction có thể khiến backup không thể phục hồi.

**Một khóa chỉ được import an toàn khi biết chính xác nó đến từ đâu, được bọc cho ai, đã đi qua những ranh giới nào, có quyền sử dụng ra sao và hệ thống vẫn kiểm chứng được khả năng bảo vệ cũng như khôi phục dữ liệu sau khi chuyển.**


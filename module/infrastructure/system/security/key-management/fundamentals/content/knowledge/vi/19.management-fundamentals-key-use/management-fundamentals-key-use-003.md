# Signing key chỉ dùng để sign — Ràng buộc mục đích sử dụng khóa ký số

## 1. Vì sao signing key chỉ được dùng để ký?

**Signing key** là khóa được cấp phát để thực hiện **chữ ký số (digital signature)**, qua đó cho phép bên nhận kiểm chứng rằng một thông điệp chưa bị sửa và chữ ký được tạo bởi chủ thể có quyền sử dụng khóa ký tương ứng. Trong mật mã bất đối xứng, cần phân biệt rõ **private signing key** — bí mật dùng để tạo chữ ký — với **public verification key** — công khai nhưng phải có nguồn tin cậy, dùng để kiểm tra chữ ký.

Nguyên tắc **“Signing key chỉ dùng để sign”** nghĩa là: **private key được cấp cho mục đích ký số phải được giới hạn ở phép toán Sign của thuật toán và giao thức đã phê duyệt**, không tái sử dụng chính vật liệu đó như khóa giải mã, khóa thỏa thuận bí mật, khóa bọc DEK, HMAC secret hoặc khóa mã hóa dữ liệu. Public key tương ứng được dùng cho **Verify**, chứ không phải một “secret” để phát lại phép ký.

Ví dụ, một **Billing Service** dùng **Ed25519** để ký sự kiện hóa đơn gửi sang đối tác. Private signing key nằm trong HSM; service được phép **Sign** sau khi kiểm tra quyền nghiệp vụ. Đối tác nhận public verification key từ PKI hoặc registry được xác thực rồi gọi **Verify**. Không có lý do để Billing Service dùng private key đó làm DEK mã hóa database, hay yêu cầu HSM cho **Decrypt** bằng cùng key.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học thuộc chương **Key use** và nối trực tiếp với vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Đúng key usage không chỉ là thuộc tính thuật toán; nó cần được phản ánh trong **key inventory, thiết kế API, IAM/KMS/HSM policies, chứng chỉ/JWKS, kiểm toán, ứng phó sự cố và dữ liệu lịch sử**.

> **Nguyên tắc kiến trúc:** **Một khóa — một loại mục đích mật mã đã xác định; một thao tác — một quyền riêng; một ranh giới tin cậy — một cách kiểm chứng.** Private signing key nên là **non-exportable** khi mô hình rủi ro yêu cầu, nhưng non-exportability không thay thế authorization đối với nội dung được ký.

### 1.1. Ký không phải mã hóa

| Primitive | Mục đích | Bí mật dùng để làm gì? | Công khai dùng để làm gì? |
| --- | --- | --- | --- |
| **Digital signature** | Xác thực nguồn gốc/toàn vẹn dữ liệu theo trust policy | Private signing key tạo chữ ký | Public verification key xác minh |
| **Public-key encryption** | Giữ bí mật một thông điệp hoặc khóa cho người nhận | Private decryption key giải mã | Public encryption key mã hóa |
| **Key agreement** | Thiết lập shared secret giữa các bên | Private DH/ECDH key đóng góp vào phép thỏa thuận | Public DH/ECDH key được trao đổi theo giao thức |
| **MAC/HMAC** | Xác thực dữ liệu giữa các bên cùng biết secret | Cùng một MAC secret tạo và kiểm tra tag | **Không có public verification key** |
| **Symmetric AEAD** | Mã hóa và xác thực payload | AES/AEAD DEK mã hóa và giải mã | Không có public key |

Một chữ ký số là **signature bytes**, không phải “ciphertext cần giải mã bằng public key”. Ngược lại, **RSA-OAEP ciphertext** là dữ liệu bảo mật cho người nhận, không thể dùng làm chữ ký hợp lệ.

### 1.2. “Chỉ dùng để sign” áp dụng cho ai?

- **Private signing key:** Chỉ thực hiện **Sign** theo purpose và thuật toán được cấp; không export/raw reuse hay làm operation khác.
- **Public verification key:** Được phép **Verify** trong đúng **issuer/tenant/application/purpose và thời hạn tin cậy**; không coi public key bất kỳ là khóa đã được phê duyệt.
- **KMS/HSM administrator:** Được phép quản trị theo nhiệm vụ, không mặc nhiên được yêu cầu ký thay ứng dụng hoặc xuất vật liệu khóa.
- **Application/workload:** Chỉ được gọi Sign sau khi hoàn tất **xác thực người gọi, authorization đối với dữ liệu và kiểm soát key status**.
- **Verifier/relying party:** Chỉ kiểm tra chữ ký bằng khóa từ **nguồn đáng tin**, sau đó kiểm tra nội dung, thời hạn và quyền nghiệp vụ riêng.

## 2. Tách Sign, Verify, Encrypt, Decrypt và DeriveKey

Một hệ thống thường có nhiều loại khóa cùng tồn tại; tên file “private.key” hoặc thuật toán “RSA” **không đủ để quyết định cách dùng**.

### 2.1. Phân biệt key usage với key algorithm

| Loại khóa / thuật toán | Operation được chọn theo thiết kế | Operation không được gộp chỉ vì cùng chương trình |
| --- | --- | --- |
| **Ed25519 private/public pair** | Private **Sign**, public **Verify** | Không sử dụng như X25519/ECDH, AES/HMAC hoặc RSA-OAEP |
| **ECDSA P-256/P-384 pair** | Private **Sign**, public **Verify** | Không tái sử dụng cùng EC private scalar cho ECDH nếu key purpose là ký |
| **RSA-PSS signing pair** | Private **Sign**, public **Verify** với tham số PSS đúng | Không dùng cùng RSA private key làm RSA-OAEP decryption key |
| **RSA-OAEP encryption pair** | Public **Encrypt/Wrap**, private **Decrypt/Unwrap** | Không dùng private decryption key để Sign |
| **ECDH/X25519 pair** | **Key agreement** trong giao thức xác thực | Không dùng để ký Ed25519/ECDSA hoặc làm key mã hóa payload trực tiếp |
| **AES DEK / AES KEK** | **AEAD Encrypt/Decrypt** hoặc **Wrap/Unwrap** theo key purpose | Không coi là private signing key |
| **HMAC key** | **MAC generation/verification** | Không cấp nó dưới dạng public verification key hoặc private signing key |

**RSA đáng lưu ý:** Một RSA key pair có cấu trúc toán học liên quan đến cả họ chữ ký và mã hóa. Một provider có thể cho phép sử dụng vật liệu RSA với nhiều cơ chế nếu không bị giới hạn. **Điều đó không có nghĩa ứng dụng được phép tái sử dụng cùng RSA key cho cả RSA-PSS và RSA-OAEP.** Cần cấp **hai key pairs khác nhau** và khóa operation qua chính sách, HSM attributes hoặc key service.

### 2.2. Domain separation không thay key separation

Ngay cả khi hai thông điệp đều dùng chữ ký số, ứng dụng cần ràng buộc **mục đích**. Ví dụ một private key ký **JWT access token** không nên được dùng mặc nhiên ký **lệnh chuyển tiền**.

Có thể áp dụng cả:

1. **Key separation:** Signing key riêng cho JWT, invoice, release artifact, webhook hoặc các miền rủi ro khác.
2. **Context/domain separation:** Nội dung được ký phải bao gồm hoặc liên kết với **loại thông điệp, issuer, audience, phiên bản schema và domain nghiệp vụ**, theo encoding không mơ hồ.
3. **Authorization:** Chỉ issuer/workload hoặc user có quyền mới tạo được loại chữ ký tương ứng.

Việc thêm tiền tố “invoice:” trước message **không biến cùng một key có quyền quá rộng thành kiến trúc an toàn**. Key separation và domain separation giải quyết các rủi ro khác nhau và thường cần dùng kết hợp.

### 2.3. Phân biệt key usage với credential/identity

Một private key có thể được liên kết với:

- **Certificate X.509** mang public key và danh tính.
- **Key resource ID** trong KMS/HSM.
- **JWK/JWKS key ID** để verifier chọn public key.
- **Workload principal** có quyền gọi API Sign.

Những metadata đó **không phải bản thân private key**. Một certificate có trường KeyUsage đúng không thể ngăn một người đã có raw RSA private key dùng nó trong thư viện khác; phải bảo vệ **vật liệu khóa và API thực thi**.

## 3. Threat model của việc dùng sai signing key

Giới hạn key usage giúp giảm **blast radius**, tránh kết hợp primitive không được phân tích an toàn và giảm cơ hội lạm dụng quyền.

| Tình huống | Nguy cơ | Kiểm soát |
| --- | --- | --- |
| **RSA key vừa Sign vừa Decrypt** | Hai giao thức có oracle/định dạng khác nhau, tăng rủi ro cross-protocol và khó rotate | Key pairs tách riêng, hạn chế Sign và Decrypt theo resource |
| **Ed25519 key bị dùng như seed X25519** | Tái sử dụng bí mật xuyên giao thức, giả định an toàn/ownership bị phá | Sinh riêng Ed25519 và X25519; không tự convert secret |
| **Một signing key ký cả JWT và lệnh thanh toán** | Chữ ký hợp lệ bị diễn giải sai miền hoặc service Sign trở thành oracle | Key riêng, context binding, content authorization |
| **Workload Sign bị chiếm** | Attacker tạo chữ ký giả dù private key ở HSM | IAM, signing authorization, rate/operation audit và containment |
| **Raw private key bị export** | Attacker ký bên ngoài KMS/HSM, không còn phụ thuộc IAM | Non-exportable khi cần, bảo vệ backup/log, rotate/revoke |
| **Verifier tin public key từ request** | Attacker cung cấp public key của chính mình rồi ký giả | Trusted issuer/PKI/JWKS và algorithm allowlist |
| **Chỉ Verify chữ ký, bỏ kiểm tra claims** | Dữ liệu được ký nhưng không có quyền hoặc sai audience | Authorization và semantic validation sau Verify |
| **Trộn HMAC và bất đối xứng** | Key confusion, dùng public key như MAC secret trong verifier lỗi | Tách JWT algorithm families, fixed alg policy và key types |
| **Signing key bị hủy quá sớm** | Không còn đường ký mới; có thể mất bằng chứng cần thiết tùy kiến trúc | Rotation runbook, giữ public verification evidence theo retention |

### 3.1. Cross-protocol misuse

Một private key được dùng trong nhiều primitive có thể trở thành **đối tượng bị thử qua nhiều oracle**. Dù một triển khai RSA-PSS và RSA-OAEP được cấu hình riêng đều đúng tiêu chuẩn, việc dùng chung raw private RSA key:

- Trái nguyên tắc **key-purpose separation** khi chính sách đã xác định.
- Tăng độ phức tạp của quyền và giám sát: ứng dụng nào có Sign, ứng dụng nào Decrypt?
- Khi private key lộ, ảnh hưởng **cả chữ ký và bí mật mã hóa**.
- Rotation một chức năng có thể làm hỏng chức năng còn lại.
- Khó chứng minh các giả định giao thức vẫn đúng trong toàn hệ thống.

**Không cần chờ có exploit cross-protocol cụ thể mới cấm tái sử dụng signing key.** Đây là quy tắc phòng ngừa có thể kiểm chứng ở mức key policy.

### 3.2. Signing oracle: private key vẫn an toàn trong HSM nhưng hành động ký không an toàn

Một HSM có private key non-exportable ngăn hoặc hạn chế việc **trích xuất raw key** theo khả năng thiết bị. Tuy nhiên, nếu attacker chiếm workload đang được phép Sign, họ có thể gửi thông điệp giả và yêu cầu HSM ký.

Vì vậy cần:

1. **Xác thực request** bằng identity đáng tin.
2. **Kiểm tra authorization** theo user, tenant, resource và loại chứng từ.
3. **Kiểm tra nội dung ký** theo schema và business invariants.
4. **Chặn dữ liệu chưa canonicalize hoặc vượt giới hạn**.
5. **Giới hạn quyền Sign** theo key ID, môi trường và purpose.
6. **Audit** principal, key version, operation, kết quả, message digest/correlation ID phù hợp.
7. **Theo dõi bất thường** như đột biến lượng ký hoặc signer mới không được phê duyệt.

**Sign thành công chỉ chứng minh một key đã ký đúng bytes.** Nó không chứng minh người yêu cầu ký có thẩm quyền phê duyệt chuyển tiền, hóa đơn hợp pháp hay tuyên bố trong nội dung là sự thật.

### 3.3. Khi private signing key đã bị lộ

Nếu raw private key bị lộ, attacker có thể tạo chữ ký ở ngoài HSM. **Revoke IAM grant không thu hồi được bytes họ đã giữ.** Cần:

- Ngừng cho Sign mới bằng key cũ.
- Sinh signing key mới ở ranh giới đáng tin cậy.
- Phân phối public verification key mới và trạng thái thu hồi key cũ.
- Điều tra token, tài liệu hoặc sự kiện đã được ký trong khoảng ảnh hưởng.
- Áp dụng chính sách xác minh chữ ký lịch sử, trusted timestamp, retention và rủi ro còn lại.

Hủy bản private key trong KMS chỉ làm mất khả năng dùng key tại KMS; **không xóa bản sao attacker đã trích xuất**.

## 4. Thiết kế signing key purpose trước khi tạo khóa

Một bản **key design record** nên làm rõ các thông tin sau:

| Trường | Ví dụ | Vì sao cần? |
| --- | --- | --- |
| **keyId / version** | billing-signer-prod-v3 | Chọn và audit đúng vật liệu khóa |
| **keyType / algorithm** | asymmetric / Ed25519 | Tránh nhầm sang RSA-OAEP/ECDH/HMAC |
| **purpose** | sign-invoice-event | Cấm dùng để ký JWT hoặc lệnh khác |
| **allowedPrivateOperations** | [Sign] | Hạn chế ở key service/HSM khi có thể |
| **allowedPublicOperations** | [Verify] | Verifier chỉ dùng đúng public key |
| **owner / environment / tenant** | billing / production / tenant-a | Cô lập phạm vi và trách nhiệm |
| **storage boundary** | managed HSM, non-exportable | Xác định đường tồn tại private material |
| **issuer / trust source** | billing trusted key registry | Public key phải được xác thực |
| **algorithm parameters** | Ed25519 hoặc RSA-PSS SHA-256/MGF1-SHA256/salt32 | Hai phía Sign/Verify cùng profile |
| **activation / retirement** | Thời gian và key state | Rotation, Verify và kiểm soát cache |
| **rotation / incident policy** | signing-rotation-v2 | Có phương án khi lộ khóa |
| **audit owner / data retention** | billing security on-call / signed records policy | Truy vết và xác minh lịch sử |

### 4.1. Mẫu key usage policy

~~~yaml
# Ví dụ chính sách nội bộ; không phải YAML API chuẩn của một KMS.
keyId: billing-sign-prod-v3
version: 3
owner: billing-platform
environment: production
type: asymmetric-signing
algorithm: Ed25519
purpose: sign-invoice-event
privateKeyStorage: managed-hsm
privateKeyExportAllowed: false
allowedPrivateOperations: [Sign]
allowedPublicOperations: [Verify]
allowedWorkloads:
  - billing-sign-service
messagePolicy:
  schema: invoice-event-v2
  requireAuthorizedTenant: true
  requireCanonicalEncoding: true
  maxMessageBytes: 65536
lifecycle:
  state: ACTIVE
  rotationPolicy: billing-sign-key-rotation
  emergencyRevokeEnabled: true
audit:
  recordKeyIdVersionPrincipalResult: true
  prohibitPrivateKeyAndPlaintextLogs: true
~~~

**Điều kiện quan trọng:** Các trường như `allowedPrivateOperations`, `privateKeyExportAllowed` và `maxMessageBytes` là **yêu cầu chính sách**, không phải bằng chứng thiết bị thật đã thực thi. Phải ánh xạ chúng sang **KMS/HSM key attributes, IAM policies, code validation, API gateway controls và test**.

### 4.2. “Sign-only” cần giới hạn cả dữ liệu được ký

Một private key dùng đúng operation Sign vẫn có thể bị sử dụng sai **mục đích nghiệp vụ**:

- Service ký hóa đơn nhưng cho phép ký **payload JSON tùy ý**.
- JWT signer chấp nhận mọi `audience`, `issuer` hoặc `subject` do caller tự chỉ định.
- Service phát hành chứng chỉ ký vào một CSR không chứng minh đúng danh tính.
- Release signing service cho phép ký hash của artifact không được build/provenance kiểm chứng.

Do đó, **key usage ở tầng mật mã** và **data/message authorization ở tầng ứng dụng** phải được kiểm tra độc lập.

## 5. Thực thi giới hạn Sign-only bằng KMS/HSM và IAM

**Không nên chỉ dựa vào một dòng comment trong mã nguồn** nói rằng private key dành để ký. Một thiết kế tốt áp dụng **defense in depth**:

~~~mermaid
flowchart TD
    AO["Application owner + Security<br/>Key purpose và policy"] --> INV["Key inventory<br/>Sign-only, key ID/version, owner"]
    INV --> ID["Workload identity và IAM<br/>Chỉ cho phép Sign đúng key"]
    ID --> API["Signing service<br/>Xác thực, authorization, schema, canonical bytes"]
    API --> HSM["KMS/HSM<br/>Private signing key non-exportable<br/>Sign được phép; Decrypt/Derive/Export bị chặn"]
    HSM --> SIG["Signature + key ID/version"]
    SIG --> V["Verifier<br/>Trusted public key + Verify + policy"]
    API --> AUDIT["Audit<br/>Principal, purpose, key, result"]
    HSM --> AUDIT
    V --> AUDIT
~~~

### 5.1. Key attributes / operation permissions

Một số KMS/HSM cho phép xác định **algorithm family**, **key usage** hoặc **operations** khi tạo key. Ví dụ khái niệm:

| Cấp kiểm soát | Điều cần cấu hình | Điều cần kiểm thử |
| --- | --- | --- |
| **KMS asymmetric signing key** | Key resource thuộc nhóm ký/xác minh; thuật toán được duyệt | Không có API Decrypt/Unwrap/Derive dùng cùng key |
| **HSM / PKCS#11 object** | Thuộc tính `CKA_SIGN=true`, `CKA_DECRYPT=false`, `CKA_DERIVE=false`; cấm export khi phù hợp | Thử operation sai phải bị từ chối và có evidence |
| **IAM grant/role** | Workload chỉ được Sign key cụ thể trong environment/purpose | Không được CreateKey, DeleteKey, Export, ChangePolicy |
| **Signing API** | Chỉ nhận request có authorization, schema và context đúng | Raw arbitrary bytes và loại message sai bị chặn |
| **Verifier** | Chỉ Verify bằng public key trusted, đúng thuật toán/purpose | Không nhận key tự khai báo hoặc algorithm downgrade |
| **Audit** | Ghi key ID, operation, actor, request result và change ID | Có thể phát hiện Sign bất thường mà không lộ secret |

**Ví dụ PKCS#11 là minh họa về attributes:** Cú pháp tạo object, khả năng thay đổi attributes và cơ chế sao lưu phụ thuộc token/HSM/provider. Ngoài `CKA_SIGN`, có thể cần khóa **`CKA_SENSITIVE`, `CKA_EXTRACTABLE=false`**, loại key và những cơ chế `CKM_...` được phép theo policy. Không coi việc gọi một thuộc tính trong Java là bằng chứng HSM thực sự đã khóa mọi đường sử dụng.

### 5.2. Sign-only operation chưa đủ nếu HSM hỗ trợ nhiều thuật toán ký

Một private RSA key có thể thực hiện **RSA-PSS** hoặc những cơ chế signature khác tùy provider. Dù key bị giới hạn ở nhóm `Sign`, ứng dụng vẫn nên **chốt thuật toán, hash, padding, salt length, MGF1 và encoding** theo profile được duyệt.

Với **Ed25519**, algorithm tương đối rõ ràng, nhưng vẫn cần xác định **message domain, key ID, issuer, signing context và business policy**. Không tự giả định Ed25519 key dùng được như X25519 key.

### 5.3. Non-exportable: giảm rủi ro rò vật liệu, không loại bỏ ký giả

Private signing key **non-exportable** có lợi vì ứng dụng không cần và thường không thể lấy raw private bytes qua API thông thường. Nhưng:

- Workload bị chiếm **vẫn có thể gọi Sign** nếu IAM còn cho phép.
- Nhân sự quản trị có thể thay policy hoặc cấp grant sai nếu thiếu separation of duties.
- Nếu key được **sinh ngoài HSM rồi import**, từng tồn tại bản sao private key ngoài ranh giới HSM; bật non-exportable sau đó không xóa được lịch sử ấy.
- Key backup/replication của HSM có cơ chế riêng; không suy từ nhãn non-exportable ra kết luận tuyệt đối rằng không có bản sao được quản lý khác.

Giới hạn **who can Sign**, **what can be signed**, **which key and algorithm**, **how many operations** và **when operations are allowed**.

### 5.4. Không cấp quyền Sign cho cả verifier

Một microservice chỉ cần kiểm tra JWT hoặc hóa đơn thường chỉ cần **public verification key** và quyền **Verify** cục bộ. Không có lý do nó được cấp **Sign/Export** ở KMS hoặc tải private signing key về.

Nếu nhiều service đều cần Sign các loại message khác nhau, thường nên:

1. Cấp **signing key riêng** theo miền hoặc dịch vụ, hoặc
2. Cấp quyền cho **signing service tập trung** có kiểm soát nội dung và tenant.

Chọn mô hình theo blast radius, policy, độ trễ và khả năng audit. Không dùng một key resource chung cho toàn tổ chức với quyền Sign rộng chỉ vì tiết kiệm việc cấp phát.

## 6. Chứng chỉ X.509: KeyUsage và Extended Key Usage

Trong PKI, **X.509 certificate** gắn public key với subject và các ràng buộc được CA chứng nhận. Những trường mở rộng quan trọng:

| Trường | Ý nghĩa khái quát | Khi nào liên quan? |
| --- | --- | --- |
| **KeyUsage: digitalSignature** | Public key được dự kiến để xác minh các chữ ký số phù hợp | TLS handshake signatures, xác thực thông điệp theo policy |
| **KeyUsage: contentCommitment** (tên cũ: nonRepudiation) | Chỉ ra mục đích chữ ký gắn với cam kết nội dung | Một số hệ thống ký tài liệu/giao dịch có quy chế riêng |
| **KeyUsage: keyEncipherment** | Dùng cho hoạt động vận chuyển khóa theo loại public-key scheme được cấp | Mật mã mã hóa khóa, thường gặp trong hệ TLS cũ |
| **KeyUsage: dataEncipherment** | Chỉ thị mục đích mã hóa dữ liệu theo profile | Không phải thay thế mặc định cho digitalSignature |
| **KeyUsage: keyAgreement** | Chỉ thị sử dụng cho thỏa thuận khóa | ECDH/kiểu agreement theo chứng chỉ phù hợp |
| **Extended Key Usage (EKU)** | Giới hạn ngữ cảnh sử dụng, như serverAuth, clientAuth, codeSigning | Khi certificate profile/giao thức yêu cầu |

**Không có EKU phổ quát cho mọi chữ ký ứng dụng tùy ý.** Một certificate chỉ có `serverAuth` không tự trở thành chứng chỉ ký hóa đơn hợp lệ. Với TLS, mTLS hay code signing phải kiểm tra **certificate profile đúng ngữ cảnh** và KeyUsage/EKU theo giao thức.

### 6.1. Trường KeyUsage không phải HSM permission

CA có thể phát hành certificate với **digitalSignature** nhưng private RSA key vẫn là raw key trong file và một thư viện có thể thử dùng nó cho giải mã nếu có quyền truy cập bytes.

Do đó cần hai lớp:

- **Lớp tin cậy/verifier:** Xác minh certificate chain, danh tính, KeyUsage/EKU, validity và trạng thái thu hồi khi yêu cầu.
- **Lớp giữ private key:** HSM/key provider/IAM chỉ cho phép thao tác Sign với thuật toán đã duyệt, cấm Export/Decrypt/Derive nếu không phù hợp.

Chỉ nhìn certificate rồi kết luận “private key không thể Decrypt” là sai ranh giới kỹ thuật.

### 6.2. Kiểm tra trust trước khi Verify

Một public key có thể được mã hóa dưới dạng **SubjectPublicKeyInfo**, certificate X.509 hoặc JWK. Việc parse thành công chỉ chứng minh encoding hợp lệ; phải kiểm tra:

1. **Nguồn tin cậy:** CA/trust anchor, issuer registry hoặc key enrollment được xác minh.
2. **Danh tính:** Subject/SAN/issuer/application nào thật sự sở hữu key?
3. **Mục đích:** Đây là key cho Verify loại chữ ký đang xử lý, không phải key của tenant hoặc service khác?
4. **Thuật toán:** Key type, algorithm, parameters và crypto policy có khớp?
5. **Hiệu lực:** Certificate/key version có active hoặc được phép Verify lịch sử?
6. **Trạng thái tin cậy:** Revocation, trust epoch và cache có cập nhật theo yêu cầu?

Không chọn public key bằng `kid` đơn độc qua toàn bộ các issuers. Một `kid` có thể trùng giá trị ở các issuer hoặc môi trường khác.

## 7. JWK/JWKS: `use=sig`, `key_ops` và algorithm policy

Trong hệ JWT/JWS, public verification key có thể được công bố qua **JSON Web Key Set (JWKS)** của issuer. JWK chứa những trường mô tả mục đích, chẳng hạn:

~~~json
{
  "kty": "OKP",
  "crv": "Ed25519",
  "kid": "billing-sig-v3",
  "use": "sig",
  "key_ops": ["verify"],
  "alg": "EdDSA",
  "x": "<base64url-public-key-bytes>"
}
~~~

**Đây là ví dụ public JWK, không có private key `d`.** Trường `use: "sig"` diễn tả mục đích ký/xác minh, còn `key_ops: ["verify"]` mô tả thao tác của **public key** được phân phối. Các trường metadata **không tự bảo đảm an toàn nếu JWKS endpoint không được tin cậy**.

### 7.1. Public JWK không được chứa private signing material

Một JWKS công khai cho JWT verification **không nên xuất** các trường private key như `d` của OKP/EC/RSA (hoặc thành phần RSA private tương ứng). Những trường đó thuộc private signing key và không dành cho verifier công khai.

Nếu private key bị công bố, đổi trường JWK từ `key_ops: ["sign"]` sang `["verify"]` **không thu hồi được key đã lộ**. Cần rotate và xử lý toàn bộ relying parties.

### 7.2. Algorithm confusion trong JWT

Một lỗi nguy hiểm là verifier lấy thuật toán từ header của token chưa xác thực rồi:

- Chấp nhận `alg=none` khi hệ thống yêu cầu chữ ký.
- Dùng **RSA public key** làm một **HMAC secret** trong nhánh HS256 nếu thư viện/cấu hình sai.
- Dùng public key của issuer khác chỉ vì `kid` trùng.
- Tải public key từ URL do token chưa xác thực chỉ định (ví dụ qua một đường header không được allowlist).

Thiết kế an toàn phải **chốt allowable algorithms theo issuer và loại key**, từ chối thay đổi giữa các họ asymmetric/HMAC, không tin key source do token tùy ý cung cấp, và kiểm tra **issuer/audience/expiry/nbf/claims + authorization** theo ứng dụng.

### 7.3. JWT signing key không được tái sử dụng cho mọi token

Một issuer có thể có nhiều loại token: **access, ID, refresh, service-to-service assertion**. Không mặc định mọi loại token đều dùng cùng một signing key, đặc biệt khi chúng có **audience, issuer, scope và vòng đời khác nhau**.

Tùy threat model, tách key hoặc áp dụng **type/domain-specific validation** để tránh token dành cho endpoint A được chấp nhận bởi endpoint B. Chữ ký hợp lệ là điều kiện cần để tin nguồn, **không phải toàn bộ chính sách chấp nhận token**.

## 8. Dữ liệu được ký: canonicalization, schema và domain separation

Signing service phải biết **những byte chính xác được ký** và **ý nghĩa nghiệp vụ** của chúng.

### 8.1. Tránh ký chuỗi ghép mơ hồ

Ví dụ hai bộ trường:

~~~text
tenant="ab", invoice="c"
tenant="a",  invoice="bc"
~~~

Nếu ứng dụng ký **`tenant + invoice`**, cả hai có cùng bytes `abc`. Verifier có thể diễn giải khác nhau dù chữ ký hợp lệ.

Giải pháp: dùng **canonical encoding** có **schema version, field names hoặc độ dài, content type, purpose** rõ ràng. Có thể sử dụng length-prefix nhị phân, canonical JSON đã đặc tả hoặc format chuẩn có test vectors. Cả signer và verifier phải sử dụng **cùng bytes**, không ký một object rồi để bên kia serialize tùy ý.

### 8.2. Mẫu nội dung có ràng buộc miền

~~~text
domain = "com.example.billing.invoice-signature.v2"
issuer = "billing-prod"
audience = "partner-accounts"
tenantId = "tenant-a"
invoiceId = "inv-42"
schemaVersion = 2
issuedAt = 2026-11-28T00:00:00Z
payloadHash = SHA-256(canonical_invoice_bytes)
~~~

Đây là **mẫu minh họa**, chưa có encoding chính thức. Trong hệ thống thực, các trường phải được mã hóa dưới một chuẩn **canonical** không mơ hồ và được đưa vào vùng thực sự được ký. Nếu chữ ký chỉ bao phủ `payloadHash` mà không bao phủ `issuer`, `audience`, `tenant` hoặc `purpose`, attacker có thể thử gắn cùng chữ ký vào ngữ cảnh khác.

### 8.3. Chữ ký không che giấu dữ liệu

Chữ ký số xác thực **nội dung và nguồn theo khóa được tin cậy**, nhưng **không giữ bí mật plaintext**. Một hóa đơn chứa PII vẫn cần bảo vệ bằng **TLS/AEAD/envelope encryption và kiểm soát truy cập** phù hợp. Private signing key không được “dùng luôn” để mã hóa dữ liệu đó; nếu cần mã hóa, dùng **DEK/KEK hoặc recipient encryption key riêng**.

### 8.4. Chống replay ở tầng giao thức

Một attacker có thể gửi lại **cùng message và chữ ký hoàn toàn hợp lệ**. Chữ ký **không tự chống replay**. Với thao tác tiền tệ hoặc command nhạy cảm, cần:

- **Request ID/transaction ID** để kiểm tra đã xử lý.
- **Timestamp và expiry window** từ nguồn có khả năng đánh giá.
- **Sequence/version** khi cập nhật trạng thái.
- **Idempotency và kiểm tra trạng thái nghiệp vụ**.
- Ràng buộc **recipient/audience/tenant/purpose** trong nội dung được ký.

**Thêm timestamp nhưng không ký trường timestamp** không giúp chống việc attacker thay thời gian.

## 9. Java 17: Ed25519 signing với policy Sign-only

Đoạn mã này minh họa **hai lớp kiểm soát**:

1. **Cryptographic operation:** Dùng `Signature.getInstance("Ed25519")`, private key chỉ được đưa vào `initSign`, public key chỉ được đưa vào `initVerify`.
2. **Application authorization:** Trước khi Sign, kiểm tra **key state, purpose, environment, workload và tenant**. Bytes để ký được tạo bởi server theo một encoding cố định.

Mã dùng một private key sinh trong JVM **chỉ để học API**. Trong production, nếu yêu cầu non-exportable, thay bước ký bằng **KMS/HSM Sign API với key handle/resource ID**, giữ cùng kiểm tra quyền và schema.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Set;

public final class SigningKeyOnlyDemo {
    private SigningKeyOnlyDemo() {}

    enum KeyState { PRE_ACTIVE, ACTIVE, RETIRED, REVOKED }

    record Workload(
            String principal,
            String environment,
            Set<String> authorizedTenants
    ) {}

    record SigningPolicy(
            String keyId,
            String environment,
            String purpose,
            KeyState state,
            Set<String> allowedSigningPrincipals
    ) {}

    record SignedInvoice(String keyId, byte[] signature) {}

    private static byte[] canonicalInvoiceBytes(
            String tenantId,
            String invoiceId,
            byte[] invoicePayload
    ) {
        // Encoding học tập: marker "SIG1", các trường length-prefixed.
        // Production cần bounds checks và format đã được hai bên thống nhất.
        byte[] domain = "billing.invoice.v1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] tenant = tenantId.getBytes(StandardCharsets.UTF_8);
        byte[] invoice = invoiceId.getBytes(StandardCharsets.UTF_8);

        return ByteBuffer.allocate(
                4 + 4 * 4 + domain.length + tenant.length
                        + invoice.length + invoicePayload.length)
                .putInt(0x53494731)
                .putInt(domain.length).put(domain)
                .putInt(tenant.length).put(tenant)
                .putInt(invoice.length).put(invoice)
                .putInt(invoicePayload.length).put(invoicePayload)
                .array();
    }

    static SignedInvoice signInvoice(
            Workload caller,
            SigningPolicy policy,
            String tenantId,
            String invoiceId,
            byte[] invoicePayload,
            PrivateKey privateSigningKey
    ) throws GeneralSecurityException {
        if (caller == null || policy == null ||
                tenantId == null || invoiceId == null ||
                invoicePayload == null || privateSigningKey == null ||
                policy.state() != KeyState.ACTIVE ||
                !"sign-invoice".equals(policy.purpose()) ||
                !"production".equals(policy.environment()) ||
                !policy.environment().equals(caller.environment()) ||
                caller.principal() == null ||
                policy.allowedSigningPrincipals() == null ||
                !policy.allowedSigningPrincipals().contains(caller.principal()) ||
                caller.authorizedTenants() == null ||
                !caller.authorizedTenants().contains(tenantId)) {
            throw new SecurityException("Signing policy denied");
        }

        byte[] toSign = canonicalInvoiceBytes(
                tenantId, invoiceId, invoicePayload);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateSigningKey);
        signer.update(toSign);
        return new SignedInvoice(policy.keyId(), signer.sign());
    }

    static boolean verifyInvoice(
            String expectedTenant,
            String expectedInvoice,
            byte[] expectedPayload,
            byte[] signatureBytes,
            PublicKey trustedVerificationKey
    ) throws GeneralSecurityException {
        byte[] toVerify = canonicalInvoiceBytes(
                expectedTenant, expectedInvoice, expectedPayload);
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(trustedVerificationKey);
        verifier.update(toVerify);
        return verifier.verify(signatureBytes);
    }

    public static void main(String[] args) throws Exception {
        KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair(); // DEMO: production ưu tiên HSM theo policy.

        Workload billing = new Workload(
                "billing-sign-prod", "production", Set.of("tenant-a"));
        SigningPolicy active = new SigningPolicy(
                "billing-sign-v3", "production",
                "sign-invoice", KeyState.ACTIVE,
                Set.of("billing-sign-prod"));

        byte[] invoice = "Invoice 42: amount=100"
                .getBytes(StandardCharsets.UTF_8);
        SignedInvoice signed = signInvoice(
                billing, active, "tenant-a", "inv-42",
                invoice, pair.getPrivate());

        System.out.println("Correct context: " +
                verifyInvoice("tenant-a", "inv-42", invoice,
                        signed.signature(), pair.getPublic()));
        System.out.println("Wrong tenant: " +
                verifyInvoice("tenant-b", "inv-42", invoice,
                        signed.signature(), pair.getPublic()));

        SigningPolicy revoked = new SigningPolicy(
                "billing-sign-v3", "production",
                "sign-invoice", KeyState.REVOKED,
                Set.of("billing-sign-prod"));
        try {
            signInvoice(
                    billing, revoked, "tenant-a", "inv-42",
                    invoice, pair.getPrivate());
            System.out.println("Unexpected success");
        } catch (SecurityException expected) {
            System.out.println("Revoked key cannot sign: true");
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
Correct context: true
Wrong tenant: false
Revoked key cannot sign: true
~~~

### 9.1. Vì sao code không gọi `Cipher` với private signing key?

Trong ví dụ, **Sign và Verify** là hai phép toán của một signature scheme. `Cipher` với RSA-OAEP/AES-GCM phục vụ mục đích **mã hóa/giải mã**, không thuộc operation của private signing key Ed25519.

**Không kiểm tra nguyên tắc Sign-only bằng cách thử trích xuất key bytes hoặc biến private key thành SecretKeySpec.** Thay vào đó, triển khai **key policy** và kiểm thử rằng các API không phù hợp bị từ chối ở nơi giữ key.

### 9.2. Những giới hạn của ví dụ

1. **Workload object phải đến từ nguồn xác thực** như IAM/STS/mTLS context. Nếu client tự tạo `Workload("billing-sign-prod")`, toàn bộ kiểm tra mất ý nghĩa.
2. **Danh sách authorizedTenants chưa chứng minh quyền ký một hóa đơn cụ thể.** Trong thực tế phải kiểm tra invoice ownership, trạng thái phê duyệt, người yêu cầu và giới hạn nghiệp vụ.
3. **Policy object phải có integrity và freshness.** Có thể xảy ra race giữa check và HSM Sign; HSM/IAM nên thực thi trạng thái/purpose độc lập.
4. **Code demo ký bằng raw private key trong JVM.** Với private key HSM non-exportable, thay `PrivateKey` bằng key handle và API Sign phù hợp.
5. **Byte arrays trong record không immutable sâu.** Production cần defensive copy, parser có giới hạn kích thước và encoding chuẩn đã công bố.
6. **Ed25519 signature verification không tự xác thực public key.** `trustedVerificationKey` phải đến từ PKI/trust registry đúng issuer/key version.
7. **Policy Verify khác Sign.** Một key đã RETIRED có thể vẫn được dùng để Verify chữ ký lịch sử theo chính sách; không sao chép điều kiện `ACTIVE` của Sign sang mọi hoạt động Verify.
8. **Không có chống replay** trong đoạn demo. Nếu chữ ký thể hiện một mệnh lệnh thực thi, hệ thống nhận phải có idempotency/request ID/expiry phù hợp.
9. **Không có rate limit hoặc audit persistence.** Các lớp đó phải được triển khai ngoài phép toán JCA.

### 9.3. Ký theo kiểu canonical và versioned schema

Trong code, các trường được nối dưới dạng **marker + độ dài + bytes** để ngăn `"ab"+"c"` bị nhầm với `"a"+"bc"`. Tuy nhiên, điều kiện ký và diễn giải phải được **quy định ở cấp giao thức**: encoding, Unicode normalization (nếu cần), timezone, kiểu số, thứ tự các trường và schema version.

Nếu một hệ thống ký JSON, hãy chọn một **canonical JSON profile** hoặc dạng bytes/serialization được chuẩn hóa; đừng chỉ serialize object Java bằng thứ tự map tùy biến.

## 10. Java 17: RSA-PSS signing key với tham số rõ ràng

RSA có nhiều operation và padding; vì thế **một khóa RSA dành cho signing phải được khóa ở RSA-PSS** (hoặc profile ký được duyệt), **không được dùng chung để Decrypt RSA-OAEP**.

Ví dụ sau tạo **RSA-3072 signing pair** và ký/xác minh theo **RSASSA-PSS, SHA-256, MGF1-SHA-256, salt length 32 bytes**. Cấu hình được đưa ra tường minh, tránh phụ thuộc các giả định không rõ về provider.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import java.security.spec.RSAKeyGenParameterSpec;

public final class RsaPssSignOnlyDemo {
    private RsaPssSignOnlyDemo() {}

    static final PSSParameterSpec PSS_SHA256 =
            new PSSParameterSpec(
                    "SHA-256",
                    "MGF1",
                    MGF1ParameterSpec.SHA256,
                    32,
                    PSSParameterSpec.TRAILER_FIELD_BC);

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(new RSAKeyGenParameterSpec(
                3072, RSAKeyGenParameterSpec.F4));
        KeyPair signingKeyPair = generator.generateKeyPair();

        byte[] canonicalDocument = "billing.invoice.v2|invoice=42"
                .getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.initSign(signingKeyPair.getPrivate());
        signer.setParameter(PSS_SHA256);
        signer.update(canonicalDocument);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.initVerify(signingKeyPair.getPublic());
        verifier.setParameter(PSS_SHA256);
        verifier.update(canonicalDocument);
        System.out.println("PSS verifies: " +
                verifier.verify(signature));

        Signature tamperedVerifier =
                Signature.getInstance("RSASSA-PSS");
        tamperedVerifier.initVerify(signingKeyPair.getPublic());
        tamperedVerifier.setParameter(PSS_SHA256);
        tamperedVerifier.update(
                "billing.invoice.v2|invoice=43"
                        .getBytes(StandardCharsets.UTF_8));
        System.out.println("Tampered message verifies: " +
                tamperedVerifier.verify(signature));
    }
}
~~~

Kết quả:

~~~text
PSS verifies: true
Tampered message verifies: false
~~~

### 10.1. RSA signing key không được chuyển thành RSA decryption key

Một hệ thống có thể có:

~~~text
billing-rsa-pss-sign-v3     -> Sign/Verify document (RSA-PSS)
billing-rsa-oaep-decrypt-v4 -> Encrypt/Decrypt wrapped DEK (RSA-OAEP)
~~~

Hai tên này phải tương ứng **hai key pairs độc lập**, không chỉ hai alias trỏ đến **cùng một private RSA modulus/exponent**. Nếu backend hỗ trợ key usage riêng ở HSM/KMS, thiết lập mục đích ngay khi tạo key.

### 10.2. Thuật toán đúng chưa đủ cho chữ ký nghiệp vụ

RSA-PSS Sign/Verify hoạt động không tự trả lời:

- Document có được người có quyền phê duyệt trước khi ký không?
- Nội dung ký có bị thiếu trường quan trọng không?
- Verifier đang dùng **đúng public key của đúng issuer/purpose** không?
- Chữ ký này còn được tin ở thời điểm hiện tại hoặc thời điểm lịch sử không?
- Có cần trusted timestamp, countersignature, audit trail hay hồ sơ pháp lý không?

Một chữ ký số hợp lệ về toán học **không tự bảo đảm tính chống chối bỏ về mặt pháp lý**. Chính sách định danh, kiểm soát private key, phê duyệt và chứng cứ thời gian là những phần không thể bỏ qua.

### 10.3. Lưu ý an toàn khi dùng ECDSA

Đối với **ECDSA**, chữ ký phụ thuộc vào một giá trị nội bộ thường gọi là **nonce `k`**. Một lỗi về tính ngẫu nhiên hoặc việc tái sử dụng `k` giữa các thông điệp có thể làm lộ private signing key. Nên dùng **provider được thẩm định** và cơ chế sinh `k` phù hợp chuẩn/giao thức; không tự lập thuật toán ký.

**Ed25519** có thiết kế ký xác định theo scheme và không yêu cầu ứng dụng tự quản lý ECDSA nonce. Nhưng điều đó **không cho phép tái sử dụng Ed25519 secret làm X25519 key** và cũng không bảo vệ trước việc raw private key bị xuất ra môi trường không an toàn.

## 11. Signing key trong TLS, JWT, tài liệu và software supply chain

Cùng có chữ ký số nhưng **miền tin cậy và dữ liệu được ký khác nhau**. Vì vậy, “key chỉ dùng để sign” còn có nghĩa **không lấy một private signing key được cấp cho miền này đi ký dữ liệu của miền khác**.

### 11.1. TLS 1.3: private certificate key ký handshake, không mã hóa traffic trực tiếp

Trong một TLS 1.3 handshake sử dụng certificate authentication, private key gắn với certificate của server thường được dùng để **ký thông điệp xác thực handshake** theo giao thức. Những **traffic encryption keys** được tạo từ **key schedule** gắn với key agreement và transcript, không phải lấy private certificate signing key làm AES DEK.

~~~mermaid
sequenceDiagram
    participant C as TLS client
    participant S as TLS server
    participant K as HSM / private TLS signing key
    C->>S: ClientHello + key share
    S-->>C: ServerHello + key share
    Note over C,S: Handshake secret qua TLS key schedule
    S-->>C: Server certificate chain
    S->>K: Sign CertificateVerify context
    K-->>S: Handshake signature
    S-->>C: CertificateVerify + Finished
    C->>C: Verify chain, hostname, KeyUsage/EKU, signature
    Note over C,S: Traffic AEAD keys từ key schedule, không từ private signing key
~~~

Từ đây có ba yêu cầu:

1. Chứng chỉ/phần mềm TLS phải dùng **đúng key pair và KeyUsage/EKU** cho handshake.
2. Không tái sử dụng private TLS signing key để ký **hóa đơn, JWT hoặc release artifact**.
3. Khi rotate certificate/private key TLS, phải kiểm tra **SSLContext reload, session/connection lifecycle và client trust**; việc thay file keystore chưa đủ.

**Ngoại lệ giao thức lịch sử:** Một số phiên bản/cipher suites TLS cũ từng sử dụng RSA key transport. Không dùng thiết kế này để suy ra **TLS 1.3 cũng dùng RSA certificate key giải mã traffic**. Phân biệt rõ phiên bản giao thức và key usage khi nâng cấp hệ thống.

### 11.2. JWT signing

Với JWS/JWT, signing key có trách nhiệm ký **protected header và payload theo chuẩn**, còn verifier dùng trusted public key kiểm tra signature và claims.

Các biện pháp quan trọng:

- Private signing key chỉ dành cho **issuer và token class** được cho phép.
- Không cho client tự chọn `alg`, `kid`, `iss`, `aud` hoặc `scope` mà không qua policy server-side.
- Verifier **ghim allowed algorithm và issuer trust source**, không coi `kid` là đường dẫn file hoặc URL tùy ý.
- Ngoài Verify còn kiểm tra expiration, not-before, audience, token type, revocation/session state nếu hệ thống yêu cầu.
- Không phát private signing key qua JWKS; chỉ công bố **public verification keys**.

### 11.3. Chữ ký chứng từ và hóa đơn

Một hệ thống ký hóa đơn cần xác định ai có thẩm quyền:

- **Soạn và trình duyệt:** Người tạo chứng từ không mặc nhiên là người được quyền ký.
- **Phê duyệt:** Điều kiện nghiệp vụ phải hợp lệ trước khi ký.
- **Canonical bytes:** Những trường quan trọng được bao phủ bởi chữ ký theo định dạng rõ.
- **Key usage:** Private signing key của hóa đơn chỉ được Sign loại chứng từ được phê duyệt.
- **Verification:** Đối tác lấy đúng public key/certificate, kiểm tra chữ ký và các quy tắc nghiệp vụ.
- **Bằng chứng dài hạn:** Lưu chữ ký, key/certificate information, timestamp và revocation evidence khi chính sách cần.

Chữ ký không tự xác minh **tính đúng đắn của hóa đơn**: một tài liệu có giá trị sai vẫn có thể được ký hợp lệ nếu control plane không kiểm tra business rules.

### 11.4. Code signing và artifact attestation

Private signing key dùng ký **software release/container artifact** không nên đồng thời ký JWT. Một release signature hợp lệ có thể chứng minh artifact được ký bởi key được tin, nhưng nếu signing pipeline bị chiếm, attacker có thể ký artifact độc hại.

Vì vậy cần **build provenance, approved CI identities, protected branches/reviews, policy ký artifact và audit**. Một HSM signing key non-exportable chỉ ngăn trích xuất raw key; nó không tự đánh giá artifact đã qua review hay chưa.

## 12. Kiến trúc signing service an toàn

Một mô hình phổ biến tách:

- **Business application:** Xác thực người yêu cầu và xác định dữ liệu/ý nghĩa nghiệp vụ.
- **Signing service:** Áp dụng policy signing theo purpose, key, schema, principal, tenant và idempotency.
- **KMS/HSM:** Giữ private signing key, thực hiện operation Sign theo quyền.
- **Verifier:** Dùng public key từ registry/PKI/JWKS, xác minh và kiểm tra yêu cầu nghiệp vụ.
- **Audit/Key inventory:** Theo dõi lifecycle, ai ký, key version, trạng thái và sự cố.

~~~mermaid
flowchart TD
    REQ["User / service request"] --> AUTH["AuthN + business authorization<br/>tenant, document, action"]
    AUTH --> VALID["Signing service<br/>schema, purpose, canonical bytes, key status"]
    VALID --> POLICY["IAM + KMS policy<br/>principal allowed to Sign key ID"]
    POLICY --> HSM["KMS/HSM private signing key<br/>Sign only; no Export/Decrypt/Derive"]
    HSM --> RESULT["Signature + key version + manifest"]
    RESULT --> RECIPIENT["Relying party / verifier"]
    TRUST["Trusted PKI / JWKS / key registry"] --> RECIPIENT
    RECIPIENT --> VERIFY["Verify signature + issuer + purpose<br/>claims/business policy"]
    VALID --> AUDIT["Audit, alerts, key inventory"]
    HSM --> AUDIT
    VERIFY --> AUDIT
~~~

### 12.1. API thiết kế theo nghiệp vụ, không chỉ nhận `byte[]` tùy ý

Một API Sign quá rộng có thể trông như:

~~~text
POST /sign
body = { "keyId": "...", "message": "arbitrary bytes" }
~~~

Nếu application principal có quyền Sign, attacker chiếm principal có thể dùng endpoint này như **signing oracle** cho mọi nội dung. Một API an toàn hơn nên:

- Nhận **loại hành động nghiệp vụ** và ID tài nguyên, không chỉ message bytes không ngữ cảnh.
- Tự truy xuất dữ liệu từ nguồn tin cậy hoặc kiểm tra schema/provenance.
- Suy ra **key ID/version và signing purpose** từ policy, không tin key tùy ý từ client.
- Kiểm tra **quyền của người yêu cầu** trên tài nguyên cụ thể.
- Tạo **canonical message bytes** nội bộ.
- Thực thi rate limits, expiry, nonce/idempotency tùy giao thức.
- Trả **signature + metadata đã được xác thực**, không trả raw private key.

### 12.2. Ký message hay ký digest?

Các API KMS/HSM có thể khác nhau:

| Kiểu API | Cách hoạt động | Cần lưu ý |
| --- | --- | --- |
| **Sign message** | Provider tự xử lý hashing/encoding/signature theo scheme | Không tự hash rồi đưa vào như raw message nếu API sẽ hash lại |
| **Sign precomputed digest** | Ứng dụng tính digest, provider ký digest theo thuật toán cho phép | Phải kiểm tra `messageType=DIGEST`, thuật toán hash, kích thước và scheme phù hợp |
| **Streaming/local Signature API** | `Signature.update` rồi `sign` | Provider thực hiện đúng encoding/algorithm, key usage phải được giới hạn |
| **Sign structured object** | Dịch vụ tạo canonical representation theo schema trước khi ký | Phải chuẩn hóa trường và quyền nghiệp vụ |

**Không nhầm digest của payload với private signing key.** Một API nói “Sign a digest” vẫn sử dụng private key để ký; digest chỉ là đầu vào theo scheme. Nếu tính hai lần hash sai, chữ ký có thể không liên thông hoặc không phù hợp profile, và bên Verify có thể kiểm tra sai bytes.

Với **Ed25519**, cần dùng **API Ed25519 đúng chuẩn**; không tự tính SHA-256(message) rồi gọi nó là Ed25519ph hoặc Ed25519 signing chuẩn. Ed25519, Ed25519ctx và Ed25519ph có các quy tắc riêng, không tự hoán đổi.

### 12.3. Ngăn confused deputy khi ký thay service khác

Nếu Signing Service có nhiều key IDs, một client có thể thử yêu cầu ký bằng key của tenant khác. Phải áp dụng **server-side routing**:

~~~text
principal billing-A -> purpose invoice -> tenant A -> approved signer A
principal billing-B -> purpose invoice -> tenant B -> approved signer B
principal report-X  -> purpose report  -> approved report signer
~~~

Không quyết định signer chỉ từ `keyId` trong HTTP request. Key lookup phải đối chiếu **principal, environment, tenant, purpose, key state và key version**, cùng authorization với nội dung.

### 12.4. Audit đúng mức

Signing service nên ghi:

- Correlation/request ID, principal/role, tenant/operation, key ID/version.
- Thuật toán và signing profile (có thể dùng reference thay vì lặp tham số).
- Loại tài liệu, content hash hoặc document reference theo chính sách dữ liệu.
- Policy decision, thời điểm, kết quả API Sign, error category và incident reference.

**Không ghi raw private key, HSM PIN, secret token hay nội dung chứng từ nhạy cảm chỉ để chứng minh việc ký.** Hash của nội dung cũng có thể tiết lộ thông tin qua dictionary attack với thông điệp đơn giản; phân loại và retention log phải phù hợp.

## 13. Phân phối và xác minh public key sau khi ký

“Private signing key chỉ dùng Sign” có nghĩa phía **Verify không cần private key**. Bằng cách đó, public key có thể được phân phối đến nhiều relying parties mà không làm tăng số bản sao bí mật.

### 13.1. Quy trình cho một signing key mới

1. Sinh key pair trong **rủi ro/ranh giới được phê duyệt**.
2. Khai báo **purpose=sign-only**, algorithm, allowed operations, issuer, environment và owner.
3. Giữ **private key** trong KMS/HSM/keystore được bảo vệ; hạn chế Export/Decrypt/Derive.
4. Đăng ký **public verification key** qua PKI/JWKS/trusted registry.
5. Bên Verify kiểm tra **issuer, KeyUsage/EKU hoặc JWK use/key_ops khi phù hợp**, cùng nguồn trust.
6. Kích hoạt ký mới chỉ khi relying parties có thể Verify theo kế hoạch triển khai.
7. Theo dõi key ID/version và thời điểm, chuẩn bị rotation/revocation.

### 13.2. Key ID không phải chứng cứ trust

`kid="sign-v3"` là metadata để chọn key, không tự xác thực key hoặc issuer. Nếu kẻ tấn công điều khiển được JWKS source, họ có thể công bố public key của mình dưới cùng `kid`. Verifier phải **ràng buộc `kid` với issuer đã tin và policy version**, bảo vệ đường fetch/cache, và kiểm tra thuật toán được phép.

### 13.3. Giữ public verification evidence cho chữ ký lịch sử

Nếu private signing key bị **destroy** khi hết thời hạn ký mới, **public verification key vẫn có thể đủ để Verify chữ ký về mặt toán học**, nếu chữ ký, message và thuật toán còn được lưu. Nhưng kết luận chữ ký có hợp lệ tại thời điểm phát hành còn phụ thuộc **certificate chain, revocation evidence, timestamp, policy, sự cố compromise và các yếu tố pháp lý**.

Do đó:

- Không xóa public trust/cert history chỉ vì private key đã hủy.
- Không coi key đã RETIRED cho Sign đồng nghĩa mọi chữ ký đã tạo phải bị từ chối.
- Khi key bị COMPROMISED, phải có chính sách phân biệt chữ ký trước/sau thời điểm ảnh hưởng với **bằng chứng thời gian đáng tin** nếu cần.
- Không tin `signedAt` do nội dung tự khai báo như bằng chứng độc lập rằng chữ ký xảy ra trước compromise.

## 14. Vòng đời của signing key: tạo, cấp phát, sử dụng, xoay vòng, thu hồi và hủy

Key usage là một thuộc tính phải được bảo vệ **suốt vòng đời**. Một signing key có thể được tạo đúng với policy `Sign-only`, nhưng một thay đổi IAM hoặc backup sau đó có thể phá ranh giới.

| Giai đoạn | Điều phải bảo đảm | Bằng chứng phù hợp |
| --- | --- | --- |
| **Generation** | CSPRNG/HSM/provider đáng tin, thuật toán và key usage ký đã duyệt | Key creation approval, algorithm, key ID/version |
| **Provisioning** | Phân phối **public key** cho verifier; private key chỉ qua protected handle/quyền Sign | IAM policy, HSM attributes, trusted registry |
| **Storage** | Private material không xuất/log trái phép; backup/DR được kiểm soát | Key inventory, HSM/keystore policy, secret scan |
| **Usage** | Chỉ Sign đúng purpose, schema, principal/tenant và message authorization | KMS Sign logs, business approvals, tests |
| **Rotation** | Tạo **cặp signing key mới**, cập nhật public trust và mốc cutover | Key versions, JWKS/certificate change, rollout result |
| **Suspension/revocation** | Chặn Sign cũ, phát trust change, điều tra chữ ký đang được tin | Disable/grant revoke, cache invalidation, negative tests |
| **Destruction** | Hủy private material khi đủ điều kiện, giữ verification evidence khi cần | Owner approval, destruction status, archive plan |
| **Review/audit** | Không phát sinh quyền Decrypt/Export/Derive; kiểm tra drift | Periodic IAM/HSM audit và key inventory |

### 14.1. Sinh key pair: tách mục đích từ đầu

**Không tạo một RSA key pair chung rồi sau đó cấp cho mọi ứng dụng** với giải thích “RSA dùng được cả ký lẫn mã hóa”. Nếu môi trường cần đồng thời:

- Ký invoice: **invoice-signing-key** (Ed25519 hoặc RSA-PSS/ECDSA theo chính sách).
- Mã hóa DEK cho recipient: **recipient-encryption-key** hoặc KMS KEK.
- Thỏa thuận phiên TLS: **ephemeral key shares** do giao thức TLS quản lý.
- Mã hóa DB: **AES DEK** riêng, có thể được bọc bởi KMS KEK.

Sinh các key materials phù hợp, tách theo **environment/tenant/purpose** khi threat model yêu cầu. **Key separation không chỉ là đặt tên khác nhau cho cùng raw material**.

### 14.2. Cấp phát: verifier nhận public key, signer nhận quyền

- **Signer:** Được cấp quyền **Sign** với private key handle, hạn chế theo workload identity, môi trường, thuật toán và business API.
- **Verifier:** Nhận **public key/certificate/JWKS** qua nguồn tin cậy, không cần quyền KMS Sign.
- **Key administrator:** Quản lý vòng đời/hạ tầng theo separation of duties, không tự ra quyết định ký nội dung nghiệp vụ.
- **Auditor:** Đọc metadata và chứng cứ, không cần raw private key hay quyền Sign.

Không gửi private key qua email hoặc secret sharing không được phê duyệt chỉ vì verifier nói cần “cùng key để xác minh”. **Verifier cần public key, không cần private key** đối với chữ ký số bất đối xứng.

### 14.3. Dùng khóa: kiểm soát scope và thời gian

Mỗi Sign request nên được gắn với **principal, tenant, document/transaction ID, schema, key ID/version, purpose và policy decision**. Nếu signed message có hiệu lực trong một khoảng thời gian, application protocol phải ràng buộc **issuedAt/expiry** theo bytes được ký và kiểm tra phía nhận.

Với một signing key dài hạn, **không nhầm thời hạn của key resource với thời hạn của từng chữ ký hoặc từng JWT**. Token có thể hết hạn trong vài phút trong khi signing key được dùng lâu hơn; ngược lại, việc retire signer không tự hủy mọi token đã ký trước đó.

### 14.4. Rotation: chuẩn bị đường Verify trước khi chuyển Sign

Trong **planned rotation**:

1. Sinh key pair **v2 mới** trong HSM/KMS theo policy.
2. Đăng ký/công bố **public verification key v2** tại trust source.
3. Cho các verifier chuẩn bị chấp nhận chữ ký từ v2 theo mốc được duyệt.
4. Chuyển **Sign mới** sang private v2; service ngừng Sign bằng v1.
5. Theo dõi issuer, key ID/alg, cache và tỷ lệ Verify failure của người nhận.
6. Giữ public verification material v1 theo policy với chữ ký lịch sử hoặc token chưa hết hạn nếu v1 vẫn an toàn.
7. Retire/destroy private v1 khi không còn cần Sign và các phê duyệt hoàn tất.

Nếu **v1 compromised**, có thể phải cắt ngắn hoặc bỏ cửa sổ chấp nhận theo kế hoạch, đồng thời thông báo/bảo vệ relying parties. Đừng giữ key lộ chỉ vì các client cũ chưa nâng cấp.

### 14.5. Destroy private key khác retire public verification key

Hủy private signing key khiến tổ chức **không thể ký mới bằng chính key đó** qua hệ thống đã hủy. Nhưng bên nhận vẫn có thể **Verify chữ ký đã tạo** bằng public key nếu đủ dữ liệu.

Với chữ ký cần xác minh dài hạn, phải dự trù **certificate chain, revocation status, timestamps, algorithm policy và verification software**. Hủy private key **không tự tạo crypto-erasure của dữ liệu đã ký** vì chữ ký không phải cơ chế mã hóa bí mật.

## 15. Rotation, revocation và xử lý signing key compromise

### 15.1. Phân biệt planned rotation và emergency revocation

| Tình huống | Trọng tâm | Hướng xử lý |
| --- | --- | --- |
| **Rotation định kỳ** | Crypto agility, key lifetime, operational hygiene | Chuẩn bị v2 trước, chuyển Sign có kiểm soát, giữ Verify lịch sử khi phù hợp |
| **Private signing key nghi lộ** | Containment nhanh, đánh giá độ tin cậy của chữ ký mới | Tạm khóa Sign, hạn chế grant, điều tra và chuẩn bị key mới |
| **Raw private key bị lộ xác nhận** | Chữ ký giả có thể được tạo ngoài HSM | Chặn trust/signing, rotate, điều tra chữ ký và người nhận |
| **Workload Sign bị chiếm, raw key chưa lộ** | Lạm dụng HSM Sign API | Revoke IAM principal, điều tra request/log, kiểm tra quyền nội dung |
| **Public key registry/JWKS bị tráo** | Verifier có thể tin attacker public key | Khôi phục trust source, invalidation cache, điều tra tokens/signatures |
| **Certificate hết hạn** | Verifier có thể không còn chấp nhận chứng chỉ theo profile | Reissue/rotate theo chính sách, không bỏ validation |
| **Đổi thuật toán ký** | Security policy, compatibility và migration | Key pair/algorithm mới, issuer/verifier rollout, versioned profiles |

### 15.2. Workflow ứng phó sự cố

~~~mermaid
flowchart TD
    ALARM["Phát hiện ký bất thường / lộ key / JWKS bị sửa"] --> TRIAGE["IR xác định loại sự cố<br/>raw key, API abuse, trust substitution"]
    TRIAGE --> SCOPE["Application owner cung cấp<br/>key ID/version, issuer, consumers, signed assets"]
    SCOPE --> BLOCK["HSM/IAM/Issuer chặn Sign cũ<br/>cập nhật trust/revocation"]
    BLOCK --> NEW["Sinh private/public signing key mới<br/>với approved purpose + policy"]
    NEW --> ROLL["Phân phối trusted public key<br/>chuyển signer và verifier"]
    ROLL --> TEST{"Negative tests: Sign cũ bị chặn?<br/>Verify policy/caches và artifacts đã kiểm tra?"}
    TEST -->|"Chưa"| SCOPE
    TEST -->|"Đạt"| CLOSE["Đánh giá chữ ký lịch sử,<br/>incident evidence và rủi ro tồn dư"]
~~~

### 15.3. Những câu hỏi Incident Response phải có câu trả lời

- Key **nào**: key ID/version, algorithm, purpose, provider, environment, owner và trạng thái?
- Phạm vi đã ký **gì**: JWT, invoice, release artifact, chứng chỉ, webhook, thời điểm, tenant, issuer và đối tác?
- Kẻ tấn công có thể đã có **raw private key** hay chỉ **KMS Sign permission**?
- Còn **cache public key, tokens chưa hết hạn, verifier offline hoặc truststore cũ** nào chưa cập nhật?
- Có chứng cứ độc lập về **thời điểm ký** không? Hay timestamp do chính payload có thể bị forged?
- Điều kiện nào đủ để **đóng sự cố**: HSM từ chối Sign cũ, verifier từ chối key revoked, rotation hoàn tất, audit dữ liệu?
- Có cần giữ **public verification evidence** hoặc signed artifacts cho retention/legal hold không?

### 15.4. Negative test sau thu hồi

Không chỉ kiểm tra `status=REVOKED` trong registry. Cần thử:

1. Workload cũ yêu cầu **Sign** bằng key v1 → phải bị từ chối.
2. Workload chỉ Verify yêu cầu **Sign/Export/Decrypt/Derive** → phải bị từ chối.
3. JWT verifier nhận token mới được ký bằng key compromised v1 → xử lý theo policy thu hồi, không fallback về cache cũ.
4. Sản phẩm ký tài liệu nhận chữ ký mới với issuer/key sai → phải từ chối.
5. DR restore bản backup cũ → không được làm sống lại grants/trust đã bị thu hồi.

### 15.5. Chữ ký lịch sử không thể được “rotate” như ciphertext

Khi đổi signing key từ v1 sang v2, những chữ ký cũ **không tự được ký lại** và không nên âm thầm thay đổi nội dung đã ký. Nếu một tài liệu cần được xác minh lâu dài:

- Giữ **original signed bytes**, signature bytes, certificate/public key và metadata cần thiết.
- Lưu **trusted timestamp và revocation evidence** khi được hệ thống/pháp lý yêu cầu.
- Xác định rủi ro nếu private key v1 bị lộ: một chữ ký tạo sau đó có thể giống về mặt toán học với chữ ký hợp lệ trước đó nếu không có chứng cứ thời gian.
- Không tự chấp nhận `createdAt` trong DB do một admin có thể sửa là chứng cứ thời gian độc lập.

**Một key v1 bị compromised có thể làm suy yếu tính tin cậy của chữ ký chưa có bằng chứng thời gian**, ngay cả khi public verification algorithm vẫn kiểm tra thành công.

## 16. Backup, DR và việc không nhân bản private signing key

### 16.1. Mục tiêu backup khác nhau giữa signer và decryption key

Với **private decryption key**, mất khóa có thể đồng nghĩa không mở được ciphertext cũ. Với **private signing key**, mất khóa chủ yếu làm mất khả năng **ký mới bằng identity/version đó**; các chữ ký cũ vẫn có thể được kiểm tra bằng public key nếu chứng cứ và chính sách được lưu.

Điều này không có nghĩa có thể hủy private signer bất kỳ lúc nào: có thể còn yêu cầu continuity hoặc không thể đổi key ngay vì clients chưa cập nhật. Nhưng **không nên xuất raw private signer tràn lan chỉ để dễ khôi phục**.

### 16.2. HSM backup theo cơ chế được phê duyệt

Một HSM có thể hỗ trợ secure backup/replication thông qua **key domain, wrapping hoặc quorum** và có thuộc tính non-exportability với những semantics riêng. Không tự biến private signing key thành file PKCS#12 để đem qua DR nếu chính sách yêu cầu **key material không rời HSM**.

Cần xác minh:

- Backup có giữ private key material trong một protected domain không?
- Ai có quyền restore và activation Sign sau failover?
- DR có cấp Sign cho đúng production workload hay mở rộng sang test/staging?
- Trạng thái **REVOKED/disabled** có được phản ánh khi restore không?
- Key version/public trust của signer mới có khả dụng cho các verifier không?

### 16.3. KMS outage: fail closed với thao tác ký

Khi KMS/HSM không sẵn sàng, signing service nên:

- Báo lỗi có kiểm soát; không bỏ yêu cầu ký hoặc ký bằng key test.
- Áp dụng retry/backoff, circuit breaker và DR đã được phê duyệt.
- Không tự chuyển sang **private key hardcode** hoặc ký bằng một HMAC secret không đúng policy.
- Không dùng v1 đã REVOKED làm fallback để hoàn thành giao dịch.
- Ghi audit failure và cảnh báo cho owner/on-call, tránh log payload/private material.

Nếu nghiệp vụ đòi hỏi availability rất cao, phải chuẩn bị **HA, failover runbook, key routing và key trust propagation** từ trước, không giải quyết outage bằng giảm yêu cầu chữ ký.

## 17. Case study: nền tảng Payments dùng ba signing keys tách biệt

Một nền tảng Java có các thành phần:

- **Identity Service:** Phát hành JWT access token bằng private signing key **identity-sign-v3**.
- **Payments Service:** Phê duyệt lệnh thanh toán và phát hành signed payment receipt bằng private key **payments-receipt-sign-v2**.
- **Artifact Service:** Ký container/release manifest bằng private key **release-sign-v4**.
- **KMS/HSM:** Quản lý cả ba private keys dưới các key resources/roles khác nhau; không xuất raw material.
- **Verifier:** API Gateway Verify JWT, đối tác Verify payment receipts, deployment pipeline Verify release signatures.
- **Security/IAM/SRE/Audit:** Định nghĩa policy, workload identities, incident response, backup và audit.

### 17.1. Rủi ro nếu dùng một private key chung

Giả sử cả ba service đều có quyền Sign cùng private RSA key:

1. Nếu JWT issuer bị chiếm, attacker có thể yêu cầu Sign dưới một key **cũng được đối tác tin cho payment receipt**.
2. Một lỗi **cross-protocol validation hoặc canonical encoding** có thể khiến chữ ký được diễn giải nhầm mục đích.
3. Khi phải revoke JWT signing key, tổ chức có thể bị buộc revoke cả **payment receipt** và **software release trust**.
4. Khó xác định blast radius từ một Sign API call: đó là token, biên nhận hay artifact?
5. Quyền IAM rộng hơn mức tối thiểu và khó kiểm toán separation of duties.

Tách key pairs giúp giảm phạm vi ảnh hưởng, nhưng **chưa đủ**: nếu một signing service nhận arbitrary bytes và có quyền ký tất cả mục đích, nguy cơ signing oracle vẫn tồn tại ở cấp orchestration.

### 17.2. Thiết kế key inventory và grants

| Key resource | Purpose | Workload được Sign | Public verifier | Không được dùng cho |
| --- | --- | --- | --- | --- |
| `identity-sign-v3` | JWT access token | identity-issuer-prod | API Gateway/Auth services theo trusted issuer JWKS | Receipt, release, RSA-OAEP Decrypt |
| `payments-receipt-sign-v2` | Signed payment receipt | payments-approval-prod | Đối tác/finance verifier có trusted certificate | JWT, release, DEK Unwrap |
| `release-sign-v4` | Artifact provenance | approved-release-pipeline | Deployment policy controller | JWT, payment, DB encryption |

Mỗi key có **owner, environment, algorithm/profile, state, rotation policy, incident contact và audit scope** riêng. Một verifier không có quyền Sign chỉ vì cần public key.

### 17.3. Luồng ký một payment receipt

~~~mermaid
sequenceDiagram
    participant User as Người dùng đã xác thực
    participant API as Payments API
    participant Signer as Receipt signing service
    participant KMS as KMS/HSM
    participant Registry as Trusted verification registry
    participant Partner as Partner verifier
    User->>API: Xác nhận thanh toán payment-42
    API->>API: Kiểm tra balance, quyền, trạng thái payment
    API->>Signer: Request sign receipt theo payment ID
    Signer->>Signer: Xác minh workload, purpose, tenant, schema
    Signer->>Signer: Tạo canonical receipt v2
    Signer->>KMS: Sign bằng payments-receipt-sign-v2
    KMS-->>Signer: Signature bytes
    Signer-->>API: Receipt + signature + key ID/version
    API-->>Partner: Gói biên nhận đã ký
    Partner->>Registry: Lấy trusted public key đúng issuer/purpose
    Registry-->>Partner: Public verification material
    Partner->>Partner: Verify signature + payment semantics + anti-replay
~~~

**Điểm mấu chốt:** Sign chỉ diễn ra sau authorization của lệnh thanh toán và schema receipt. Key ID được hệ thống routing dựa trên purpose, **không lấy trực tiếp một tên key do người dùng tùy chọn**.

### 17.4. Tình huống JWT issuer bị xâm nhập

Giả sử Identity Service principal bị đánh cắp, attacker phát hành JWT giả qua Sign API:

1. **IR** thu hồi credential/grant Sign của identity workload.
2. **KMS/HSM** chặn Sign mới với principal bị xâm nhập; nếu raw key chưa xuất, đánh giá dạng lạm dụng API, không tự kết luận private bytes đã lộ.
3. **Identity owner** rotate `identity-sign-v3` sang v4 theo mức rủi ro; cập nhật trusted JWKS/issuer policies và cache.
4. **Gateway/verifiers** xử lý những token có chữ ký v3 theo revocation policy và kiểm tra phiên hoạt động.
5. **Payments receipt** và **release signatures** không cần rotate chỉ vì chung nhà cung cấp HSM, nếu key materials/permissions thật sự độc lập và không bị ảnh hưởng.
6. Audit điều tra Sign records của JWT issuer và đánh giá những token đã phát hành trong khoảng sự cố.

Tách key-purpose giúp hạn chế phạm vi sự cố nhưng **không thay thế phân tích cross-account IAM hoặc rủi ro HSM admin compromise**. Nếu attacker chiếm quyền quản trị có thể cấp Sign tới tất cả keys, phải mở rộng phạm vi điều tra.

### 17.5. Nếu cùng lúc cần mã hóa receipt thì sao?

**Không lấy payments receipt signing key làm khóa mã hóa.** Chọn:

- **DEK AES-GCM** mã hóa nội dung receipt khi cần bí mật.
- **KEK KMS/HSM** để wrap DEK hoặc key establishment/hybrid scheme phù hợp người nhận.
- **Signing key** ký canonical receipt hoặc cryptographic manifest theo giao thức.

Thứ tự **Sign-then-encrypt / encrypt-then-sign** có những hàm ý bảo mật khác nhau; sử dụng một **giao thức đã thẩm định** thay vì tự ghép tùy tiện. Điều bắt buộc trong mọi trường hợp là **không chia sẻ raw key material giữa signing và encryption purposes**.

## 18. RACI và quản trị quyền của signing key

“Chỉ dùng để sign” là yêu cầu liên phòng ban, không chỉ việc của lập trình viên viết `Signature.initSign`.

### 18.1. Mẫu phân công trách nhiệm

| Hoạt động | Application owner | Security/PKI | KMS/HSM admin | Developer/SRE | Data/Business owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Xác định domain và nội dung được ký | **A** | C | I | R | C |
| Chọn signing algorithm/KeyUsage profile | R | **A** | C | C | I |
| Tạo private signing key trong approved boundary | C | C | **A/R** | I | I |
| Cấp/thu hồi IAM Sign grants | **A** | C | R | R | I |
| Triển khai canonicalization và Sign/Verify | **A** | C | C | R | C |
| Phân phối public verification key | **A** | C | R | R | I |
| Đánh giá nội dung nghiệp vụ trước khi ký | C | I | I | R | **A** |
| Planned key rotation & consumer rollout | **A** | C | R | R | C |
| Incident response liên dịch vụ | R | **A** | R | R | C |
| Hủy private key sau phê duyệt | R | C | **A/R** | C | C |

**RACI chỉ là ví dụ quản trị, không phải policy IAM được áp dụng tự động.** Trong tổ chức cụ thể, vai trò `A` có thể khác; cần xác định một người chịu trách nhiệm mỗi hoạt động và **các chấp thuận bổ sung** đối với thông tin/pháp lý khi cần.

### 18.2. Separation of duties

- **Người yêu cầu ký** không tự phê duyệt một giao dịch giá trị cao khi quy trình yêu cầu phê duyệt độc lập.
- **KMS/HSM admin** có thể tạo/rotate key nhưng không được tự dùng Sign API ký dữ liệu nghiệp vụ.
- **Developer** không có quyền xuất private key hoặc thay key policy production chỉ vì họ viết integration.
- **Verifier/Auditor** được đọc public key và audit, không cần quyền Sign.
- **Break-glass** cần phạm vi, thời hạn, phê duyệt/hậu kiểm và audit riêng.

Một signing key private **non-exportable** và quyền Sign hẹp có thể khiến một cuộc tấn công chỉ làm lạm dụng một loại thao tác, thay vì lấy bí mật để ký vô hạn ngoài hạ tầng kiểm soát. Để đạt được điều đó cần **test thực tế cả key attributes và IAM**.

### 18.3. Quản lý exceptions

Nếu một hệ thống legacy đã dùng chung RSA private key cho ký và giải mã:

1. Kiểm kê **mọi mục đích hiện tại** và phụ thuộc ciphertext/chữ ký.
2. Đánh giá threat model và thẩm quyền phê duyệt ngoại lệ tạm thời.
3. Thiết kế **signing pair mới** và **decryption pair mới**, với key IDs/versions và policies riêng.
4. Chuyển Sign trước/Verify routing theo kế hoạch và chuyển dữ liệu mã hóa bằng key cũ nếu cần.
5. Chặn cross-use tại HSM/IAM/app và loại bỏ grants/export paths cũ.
6. Xác minh ciphertext/backup vẫn đọc được, chữ ký lịch sử có chứng cứ hợp lệ.
7. Đóng ngoại lệ khi có test evidence, không chỉ đổi tên alias.

**Không chỉ chuyển cùng RSA private key thành hai file có tên khác**. Key separation đòi hỏi **vật liệu khóa độc lập**.

## 19. Kiểm thử Sign-only ở tầng thuật toán, policy và nghiệp vụ

Một **unit test ký rồi xác minh thành công** chỉ chứng minh primitive hoạt động với dữ liệu đó. Nó **không chứng minh** HSM chặn Decrypt/Export, workload khác không ký được, JWT verifier chặn key giả hay quy trình thu hồi hoạt động trong DR.

### 19.1. Kiểm thử chức năng mật mã

| Bài kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Private Ed25519 Sign, public Ed25519 Verify cùng bytes | Verify thành công |
| Sửa 1 byte của message hoặc signature | Verify thất bại |
| Dùng public key khác để Verify | Verify thất bại |
| RSA-PSS đúng SHA-256/MGF1-SHA256/salt32 | Verify thành công với đúng profile |
| RSA-PSS sai message hoặc profile verify | Không chấp nhận signature |
| Ký ECDSA qua provider được duyệt | Verify được; không tự kiểm soát nonce `k` bằng RNG yếu |
| Data có Unicode/JSON và nhiều định dạng | Canonical bytes nhất quán, không diễn giải khác nhau |
| Schema version/meaning không hợp lệ | Không ký hoặc không chấp nhận chữ ký như thông điệp nghiệp vụ hợp lệ |

### 19.2. Kiểm thử key usage và authorization

| Bài kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Signing workload có quyền Sign đúng key | Sign thành công sau authorization nghiệp vụ |
| Workload chỉ Verify thử gọi Sign | IAM/KMS/HSM chặn |
| Signing key bị yêu cầu Decrypt/Unwrap RSA-OAEP | HSM/KMS/provider policy từ chối |
| Signing key bị yêu cầu DeriveKey/ECDH | Bị từ chối |
| Signing key bị yêu cầu Export raw material | Bị từ chối theo key attributes và quyền |
| Key ở trạng thái PRE_ACTIVE/REVOKED dùng Sign mới | Bị từ chối |
| Service Sign yêu cầu key của tenant khác | Bị từ chối bởi routing, IAM và business policy |
| Service Sign với message type không được phép | Bị từ chối trước khi gọi HSM |
| Client tự đặt `keyId` của private key khác | Không được Sign nếu không có quyền và đúng purpose |
| Request ký cùng transaction nhiều lần | Áp dụng idempotency/replay policy theo thiết kế |
| File keystore private key bị lộ cho người chỉ cần Verify | Không có đường xuất qua API công khai; phát hiện exposure nếu có |
| Build/test environment yêu cầu Sign bằng production signer | Bị IAM/HSM policy từ chối |

### 19.3. Kiểm thử xác minh public key/trust

| Bài kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| `kid` có thật nhưng issuer không đúng | Không dùng key của issuer khác |
| Verifier nhận public key trong payload chưa xác thực | Từ chối key source tùy ý |
| JWT có `alg=none` hoặc HS256 thay cho RS256/EdDSA | Từ chối nếu issuer policy chỉ cho asymmetric signatures |
| Certificate đúng chain nhưng SAN/EKU/KeyUsage sai | Từ chối theo giao thức/profile áp dụng |
| Public signing key bị đổi trong registry không có approval | Bị chặn/phát hiện bằng integrity và audit |
| Public key v2 được đăng trước mốc Sign v2 | Verifier sẵn sàng theo rollout |
| Signing key v1 REVOKED nhưng verifier còn cache | Policy revocation/invalidation xử lý đúng |
| Token hợp lệ signature nhưng sai `aud`/`iss`/expiry | Từ chối theo validation policy |
| Chữ ký trên invoice A bị gắn vào invoice B | Verify hoặc domain/business authorization từ chối |

### 19.4. Kiểm thử vận hành và sự cố

1. **KMS outage:** Signing service fail closed, không ký bằng key test/hardcode.
2. **HSM API abuse:** Tăng đột biến Sign từ principal lạ phát cảnh báo; có correlation ID.
3. **Disable key:** Sign mới bằng key cũ không thành công sau khi state có hiệu lực.
4. **Rotation:** Sign v2/Verify v2 hoạt động; Verify lịch sử v1 theo chính sách.
5. **Emergency compromise:** Verifiers không tin chữ ký mới từ key v1 bị thu hồi, kể cả có cache cũ.
6. **DR restore:** Không hồi sinh grants, key aliases, trust anchors hay signer v1 đã revoked.
7. **Audit:** Có key ID/version, principal, purpose, operation, result; không lộ private key hoặc nội dung bí mật.
8. **Đồng thời:** Nhiều instance ký có cùng policy version, không instance nào tiếp tục dùng key đã retire sau cutover.
9. **Hủy key:** Private material được xử lý đúng quy trình, public verification evidence cần giữ vẫn còn.
10. **Tamper content:** Signed schema, canonical bytes, timestamp, domain và recipient bị sửa đều được kiểm tra chính xác.

### 19.5. Không dùng negative test nguy hiểm trên production key

Khi kiểm tra **Export/Decrypt/Derive bị cấm**, nên dùng **test key với cùng policy** hoặc API kiểm tra quyền/metadata phù hợp thay vì cố trích xuất private material của production key vào môi trường ứng dụng.

Production validation có thể dựa trên **KMS/HSM policy introspection, restricted operation dry run/negative call được phê duyệt và audit evidence**. Đừng tạo mới một đường rò raw key để “thử xem nó có được bảo vệ không”.

## 20. Anti-patterns: các lỗi đi ngược nguyên tắc signing key chỉ dùng Sign

| Sai lầm | Rủi ro | Biện pháp đúng |
| --- | --- | --- |
| **Dùng cùng RSA private key để Sign và Decrypt** | Cross-protocol misuse, blast radius và rotation phức tạp | Tạo key pairs riêng; enforce key usage |
| **Dùng Ed25519 secret làm X25519 key** | Tái sử dụng bí mật xuyên giao thức | Sinh riêng signing và key-agreement material |
| **Dùng signing key làm AES/HMAC key** | Không đúng primitive và nguy cơ lộ bí mật | Tạo DEK/MAC key riêng bằng KMS/CSPRNG |
| **Phát private signing key cho verifier** | Verifier có thể tạo chữ ký giả | Chỉ công bố trusted public verification key |
| **Một private key ký JWT, invoice và release** | Compromise một miền ảnh hưởng tất cả | Tách key theo purpose/domain |
| **Chỉ dùng alias khác nhau nhưng raw private key giống nhau** | Tưởng đã tách khóa, thực tế chưa | Sinh material độc lập, đối soát fingerprint/public key |
| **HSM key không export nên Sign API được phép mọi request** | Signing oracle, có thể ký nội dung gian lận | Business authorization, signing schema, rate limits |
| **Client tự chọn `keyId` và `purpose`** | Confused deputy, vượt tenant/issuer | Server-side key routing và allowlist |
| **Ký chuỗi ghép không có phân cách** | Có thể diễn giải nhiều bộ trường thành một signature input | Canonical encoding có độ dài/nhãn/phiên bản |
| **Bỏ `audience`/`purpose` khỏi vùng được ký** | Chữ ký hợp lệ bị dùng sai ngữ cảnh | Domain separation, schema và semantic validation |
| **Cho JWT header quyết định key/algorithm tùy ý** | HS/RS confusion, `alg=none`, SSRF/key injection | Fixed alg/key type và trusted issuer/JWKS |
| **Tin public key do payload tự gửi** | Attacker tự ký và tự Verify thành công | PKI/trusted registry, issuer validation |
| **Coi chữ ký số như mã hóa bảo mật dữ liệu** | Plaintext vẫn bị đọc | AEAD/TLS/envelope encryption bằng key khác |
| **Coi HMAC là chữ ký bất đối xứng** | Bên Verify có secret cũng có thể giả mạo | Dùng digital signature nếu cần public Verify |
| **Tự sinh nonce ECDSA từ timestamp/Random yếu** | Rò private key qua nonce | Provider được thẩm định, nonce strategy chuẩn |
| **Không chốt RSA-PSS parameters** | Interoperability lỗi hoặc policy không nhất quán | Fixed hash/MGF1/salt/trailer profile |
| **Ký digest hai lần hoặc nhầm RAW/DIGEST API** | Chữ ký sai nghĩa, verify không đúng thông điệp | Theo API contract, test vectors và canonical source |
| **Chỉ Verify signature, không kiểm tra claims/quyền** | Token/tài liệu ký hợp lệ nhưng bị dùng sai | Semantic validation và authorization |
| **Coi `KeyUsage=digitalSignature` đủ cấm Decrypt** | Raw private key có thể bị dùng bên ngoài PKI | Enforce ở HSM/provider/IAM và bảo vệ bytes |
| **Bỏ qua certificate hostname/EKU khi Verify TLS** | Tin endpoint giả | Kiểm tra đúng chain, identity và profile |
| **Giữ signer v1 sau compromise để tương thích** | Attacker tiếp tục tạo chữ ký giả | Emergency revocation và trust propagation |
| **Chỉ disable HSM key, không cập nhật verifier** | Relying parties vẫn tin v1 hoặc attacker đã có raw key | Rotate/trust update, cache invalidation, incident response |
| **Dùng một policy ACTIVE cho Sign và Verify lịch sử** | Mất khả năng Verify tài liệu cũ hợp lệ hoặc cho Sign trái phép | Tách signing-state với verification trust policy |
| **Hủy public trust/certificate khi hủy private key** | Mất chứng cứ xác minh chữ ký lịch sử | Retention của public verification evidence |
| **Log raw private key hoặc request token nhạy cảm** | Lộ vật liệu, mở rộng blast radius | Log metadata tối thiểu, redaction, access control |
| **Failover sang signing key test khi KMS outage** | Phá trust, có thể tạo chữ ký được tin sai | HA/DR approved, fail closed |
| **Khôi phục backup đưa revoked signer về ACTIVE** | Hồi sinh khóa bị thu hồi | Revocation epoch/tombstone và reconciliation |

## 21. Checklist thiết kế và vận hành signing key chỉ dùng Sign

Trước khi nghiệm thu một ứng dụng ký số, hãy đánh giá các điểm sau:

1. **Định nghĩa mục đích:** Signing key dùng cho JWT, hóa đơn, TLS handshake, webhook signature hay release artifact? Các mục đích không liên quan có key riêng?
2. **Phân biệt primitive:** Private signing key chỉ **Sign**, public key chỉ **Verify**; encryption/KEK/DEK/MAC/ECDH có keys và API riêng?
3. **Key generation:** Thuật toán Ed25519/ECDSA/RSA-PSS, curve/key size, CSPRNG và provider được chọn theo policy?
4. **Key material separation:** Các alias/key resource khác nhau có thật sự chứa **material độc lập**, không chỉ cùng private key copy?
5. **Key inventory:** Có key ID/version, owner, issuer, environment, tenant, algorithm, purpose, operation và trạng thái rõ?
6. **Non-exportability:** Private signer có cần sinh trong KMS/HSM, có key attributes cấm Export và ghi nhận provenance?
7. **HSM/KMS operations:** Có thể chứng minh private signing key không được Decrypt/Unwrap/Derive/Export trong scope hiện tại?
8. **IAM least privilege:** Workload chỉ có quyền Sign key cần thiết; Verify-only service không có quyền Sign?
9. **Key admin separation:** Create/Rotate/Disable/Delete/ChangePolicy không được cấp cho service chỉ cần ký?
10. **Algorithm profile:** RSA-PSS hash/MGF1/salt/trailer, ECDSA curve, Ed25519 mode có được quy định tường minh?
11. **Public key trust:** Verifier nhận public key qua issuer PKI/JWKS/registry đáng tin; không lấy từ request tùy ý?
12. **X.509 profile:** Nếu dùng certificate, KeyUsage/EKU/chain/SAN/validity có được kiểm tra theo giao thức?
13. **JWT policy:** Có fixed algorithms, issuer/audience validation, chống HS/RS confusion và key source injection?
14. **Message schema:** Bytes được ký có encoding/canonicalization ổn định, version, type, purpose và domain?
15. **Business authorization:** Trước Sign, user/workload có được kiểm tra tenant, resource, approval và trạng thái giao dịch?
16. **Signing API:** API có tránh arbitrary raw bytes và key ID tự khai báo khi không có kiểm soát không?
17. **Replay:** Request/tài liệu có idempotency, nonce/sequence/expiry phù hợp, và các trường đó thuộc vùng được ký?
18. **Monitoring:** Có rate limits và cảnh báo tăng Sign, principal/tenant lạ, key policy drift, Sign sau cutover?
19. **Audit:** Log key ID/version, principal, purpose, document reference/hash, result, thời gian mà không log private key?
20. **Rotation:** Có runbook sinh v2, phát public v2, chuẩn bị verifier, chuyển Sign mới và retire v1?
21. **Historical verification:** Có chính sách Verify chữ ký cũ, certificate/timestamp/revocation evidence và retention?
22. **Emergency compromise:** Có thể chặn Sign API, revoke grants, phát trust change và kiểm tra relying-party caches?
23. **Public key registry:** Thay đổi JWKS/certificate/key fingerprint có phê duyệt, audit và rollback an toàn?
24. **Environment:** Test/staging không có quyền Sign bằng production private key; DR được thiết kế riêng?
25. **Backup:** HSM backup/replication giữ đúng non-exportable boundary, không tạo private key file không kiểm soát?
26. **Fail closed:** Khi KMS/HSM outage, không fallback sang signing key yếu, key test hoặc tắt Verify?
27. **Negative tests:** Có test operation sai, wrong tenant, wrong purpose, revoked key, wrong key source và algorithm downgrade?
28. **Incident evidence:** Có thể phân biệt raw key compromise, HSM Sign API abuse và public trust registry tampering?
29. **Destruction:** Trước khi hủy private signer, đã đánh giá continuity và kế hoạch giữ public verification evidence?
30. **Review:** Application owner/Security/KMS/IR có lịch đối soát quyền, key purpose, grants, algorithms và exception records?

### 21.1. Năm câu hỏi kiểm tra nhanh trong code review

**Câu hỏi 1 — Vì sao service này cần private key?** Nếu chỉ Verify, không nên cấp private key hoặc quyền Sign.

**Câu hỏi 2 — Mã nguồn có thể dùng same RSA private key với Cipher không?** Nếu có, xem xét lại resource separation và enforce operation tại provider/HSM.

**Câu hỏi 3 — Ai quyết định nội dung được ký?** Không nên để client tự gửi raw bytes và chọn arbitrary signer mà không có schema/authorization.

**Câu hỏi 4 — Khi key bị revoked, request mới thực sự bị từ chối tại đâu?** Không chỉ nhìn một cờ status; phải kiểm tra IAM/HSM, application caches và verifier trust.

**Câu hỏi 5 — Nếu cùng khóa ký được dùng cho JWT và payment receipt, sự cố sẽ lan bao xa?** Nếu câu trả lời là nhiều miền nghiệp vụ độc lập, cần tách signing keys và policies.

## 22. Ghi nhớ

- **Signing key chỉ dùng để Sign** là nguyên tắc **key-purpose separation**. Private signing key không được dùng để mã hóa dữ liệu, Unwrap DEK, thực hiện ECDH hay làm HMAC secret.
- **Private signing key tạo chữ ký; public verification key Verify.** Public key có thể công bố nhưng phải được xác thực nguồn qua PKI/JWKS/trusted registry và key usage đúng.
- **RSA có thể hỗ trợ nhiều primitive ở mức thuật toán, nhưng không nên tái sử dụng cùng raw RSA private key cho RSA-PSS và RSA-OAEP.** Với Ed25519/X25519, càng phải phân biệt scheme ký và scheme thỏa thuận khóa.
- **HSM/KMS non-exportable giảm nguy cơ trích xuất raw private key**, nhưng một workload có quyền Sign bị chiếm vẫn có thể lạm dụng signing oracle. Cần kiểm tra **ai được ký và nội dung gì được ký**.
- **IAM/KMS key attributes, X.509 KeyUsage/EKU và JWK use/key_ops** cung cấp các lớp mô tả hoặc ràng buộc khác nhau; không lớp metadata riêng lẻ nào thay thế toàn bộ cơ chế thực thi.
- **Chữ ký hợp lệ không tự chứng minh quyền nghiệp vụ hay tính đúng đắn của dữ liệu.** Signer phải có domain separation, canonical bytes, authorization, và verifier phải kiểm tra issuer/audience/purpose, thời hạn, replay hoặc semantics phù hợp.
- **TLS 1.3 dùng private certificate key để xác thực handshake bằng chữ ký**, không dùng nó làm khóa AES mã hóa traffic; DEK/KEK của envelope encryption thuộc miền khóa riêng.
- **Rotation/revocation tách quyền ký mới khỏi việc Verify lịch sử.** Khi private signer bị lộ, cần đồng thời chặn Sign, cập nhật trusted public keys/cache và đánh giá chữ ký đã phát hành.
- **Audit, separation of duties, backup/DR và negative tests** giúp chứng minh signing key không bị dùng sai, không chỉ tồn tại một dòng comment “sign only”.

Ba câu hỏi quan trọng nhất đối với một hệ thống dùng signing key là: **“Private key này được sinh và giữ ở đâu, ai thật sự có thể yêu cầu Sign?”, “Những message/purpose nào được phép ký và bên nhận xác thực public key bằng cách nào?”, “Nếu private key bị lộ hoặc phải thu hồi, chúng ta có thể chặn ký giả và đánh giá các chữ ký lịch sử không?”** Khi các câu hỏi có lời giải bằng **kiến trúc, chính sách KMS/HSM, key inventory, quyền ứng dụng và bằng chứng kiểm thử**, nguyên tắc **Signing key chỉ dùng để sign** mới thực sự được bảo đảm trong hệ thống.








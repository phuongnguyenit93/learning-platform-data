# Key generation policy

> **Chương:** Key policy  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Key generation policy là gì?

**Key generation policy (chính sách sinh khóa mật mã)** là tập hợp những quy tắc xác định **ai được tạo khóa, tạo loại khóa nào, bằng thuật toán và nguồn ngẫu nhiên nào, ở đâu, dùng cho mục đích gì và phải quản lý khóa vừa sinh như thế nào**. Chính sách này áp dụng trước, trong và ngay sau thao tác sinh khóa, nhằm ngăn một khóa yếu hoặc được tạo sai phạm vi trở thành nền tảng của hệ thống bảo mật.

Ví dụ: một nhóm phát triển muốn sinh khóa AES-256 dùng mã hóa dữ liệu khách hàng trong production. Họ không được tùy ý chạy `new Random().nextBytes(...)`, chép khóa vào `application.yml` rồi cấp quyền giải mã cho toàn bộ service. Chính sách có thể yêu cầu **DEK sinh bằng CSPRNG được phê duyệt**, **KEK tồn tại trong KMS/HSM**, khóa chỉ dùng cho một mục đích và tenant/phạm vi xác định, key ID/version được đăng ký trong inventory, quyền được cấp theo least privilege, mọi thao tác nhạy cảm có audit và vòng đời được định nghĩa.

Điều này nối bước **generation** với các giai đoạn **provisioning → activation → usage → rotation → revocation → destruction**. Khóa có 256 bit được tạo sai cách không tự trở nên an toàn chỉ vì sau đó được cất trong KMS. Ngược lại, khóa đủ ngẫu nhiên nhưng bị xuất ra log hoặc được cấp quyền `Decrypt` quá rộng cũng không được bảo vệ đúng.

### Cần phân biệt ba lớp chính sách

| Lớp | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Generation policy** | Có được sinh khóa này không, sinh ở đâu, kiểu gì và với thuộc tính nào? | Chỉ HSM được tạo private signing key không xuất được |
| **Usage/access policy** | Ai được thực hiện thao tác mật mã nào với key/version nào? | Billing service chỉ được `WrapKey`, không được `Sign` |
| **Lifecycle/retention policy** | Khóa bắt đầu và kết thúc dùng khi nào; xử lý rotation, revocation, backup ra sao? | KEK mới active ngày T; KEK cũ chỉ unwrap dữ liệu cũ |

**Generation policy không thay thế hai lớp còn lại**. Một hệ thống hoàn chỉnh phải kết nối chúng bằng **key ID/version, policy revision, owner, purpose, key state và audit trail**.

### Mục tiêu học tập

Sau bài này, bạn có thể thiết kế một key generation policy tối thiểu, lựa chọn thuật toán và vùng sinh khóa, phân biệt CSPRNG với entropy yếu, giải thích **exportability/non-extractability**, xây dựng preflight có thể kiểm toán, hiểu các yêu cầu cho **DEK/KEK, HMAC, private signing key và khóa thỏa thuận**, cùng một ví dụ Java 17 minh họa nguyên tắc **deny by default**.

## 2. Tại sao cần chính sách thay vì chỉ gọi API tạo khóa?

Một lời gọi `KeyGenerator.getInstance("AES")` hoặc `KeyPairGenerator.getInstance("RSA")` chỉ thể hiện **cách yêu cầu tạo khóa**, không tự đảm bảo rằng:

- Người gọi **có quyền** tạo loại khóa đó cho môi trường/tenant hiện tại.
- Thuật toán, độ dài và provider **đã được phê duyệt**.
- Nguồn entropy đủ mạnh và cơ chế sinh khóa đáp ứng yêu cầu tuân thủ thực tế.
- Private key **không xuất được** nếu chính sách yêu cầu HSM.
- Khóa được dùng đúng **purpose** và không tái sử dụng cho các mục đích không tương thích.
- Khóa được đăng ký, kích hoạt, gắn version, lưu backup hoặc bảo vệ theo retention.
- Một bản sao khóa không bị **ghi vào file, log, crash dump, CI artifact**.
- Có thể **thu hồi, chuyển khóa và kiểm tra dữ liệu/chữ ký lịch sử**.

Vì thế, chính sách cần một **điểm ra quyết định được thực thi (enforcement point)**. Một file JSON mô tả mong muốn mà ứng dụng có thể bỏ qua **không phải hàng rào bảo mật**.

### 2.1. Mối đe dọa cần tính đến

| Rủi ro | Ví dụ | Hậu quả |
| --- | --- | --- |
| Sinh khóa bằng RNG không mật mã | `Math.random()`, `Random`, seed từ timestamp | Khóa dễ đoán dù dài 256 bit |
| Sai thuật toán hoặc cỡ khóa | RSA quá ngắn, thuật toán lỗi thời, cấu hình provider ngoài policy | Độ mạnh thực tế dưới mức cần thiết |
| Key export ngoài vùng bảo vệ | Private signing key sinh trong JVM rồi lưu PEM trên đĩa | Có thể bị lấy để ký giả |
| Sai purpose | Cùng key dùng HMAC, AES-GCM, ký JWT | Cross-protocol misuse, tăng phạm vi sự cố |
| Không tách tenant/môi trường | Một KEK dùng chung staging và production | Rò rỉ ở môi trường yếu ảnh hưởng production |
| Không có owner/inventory | Không biết ciphertext nào phụ thuộc key nào | Không rotate/thu hồi/hủy an toàn |
| Cấp quyền quá rộng | Mọi workload được `Decrypt/Sign` | Lạm dụng API mật mã dù key không bị xuất |
| Sai chính sách backup | Xóa KEK đang bọc DEK trong backup | Mất khả năng khôi phục dữ liệu |
| Thiếu kiểm soát vòng đời | Sinh key mới nhưng vẫn dùng key cũ vô hạn | Tăng cryptoperiod và phạm vi rủi ro |

**Cách đặt câu hỏi phù hợp:** không chỉ hỏi “Key có được tạo thành công không?”, mà hỏi “Key có **đủ điều kiện được tạo, cấp phát và kích hoạt** theo chính sách đã phê duyệt không?”.

## 3. Những thành phần bắt buộc trong một key generation policy

Chính sách cần được **định nghĩa theo từng profile** thay vì một lệnh chung `generateKey(bits)`. Profile là sự kết hợp giữa mục đích, thuật toán, môi trường và mức kiểm soát cần thiết.

| Nhóm thuộc tính | Trường gợi ý | Ý nghĩa |
| --- | --- | --- |
| Định danh | `policyId`, `policyVersion`, `requestId` | Có thể truy vết quyết định và thay đổi |
| Chủ thể tạo | `principal`, `workloadIdentity`, `approvedBy` | Ai được gọi tạo khóa và phê duyệt |
| Phạm vi | `environment`, `tenantScope`, `service`, `region` | Ngăn tạo hoặc dùng sai ranh giới |
| Loại và purpose | `keyType`, `keyUsage`, `algorithm` | Chỉ rõ AES, HMAC, RSA, Ed25519, ECDH... |
| Độ mạnh | `keyLength`, `curve`, `parameterSet` | Quy định độ mạnh đúng theo từng họ thuật toán |
| Nguồn sinh | `rngSource`, `provider`, `generationLocation` | Chứng minh dùng CSPRNG/DRBG/KMS/HSM phù hợp |
| Bảo vệ vật liệu | `exportable`, `nonExtractable`, `storageClass` | Cấm/giới hạn xuất key material khi cần |
| Vòng đời | `activationAt`, `newUseUntil`, `rotationPolicy` | Kết nối cryptoperiod và state |
| Phân quyền | `allowedOperations`, `owner`, `keyPolicyRef` | Áp dụng least privilege và separation of duties |
| Lưu trữ/khôi phục | `backupPolicy`, `recoveryPlan`, `retentionClass` | Tránh vừa lộ khóa vừa mất dữ liệu |
| Giám sát | `auditRequired`, `inventoryRequired`, `alerts` | Bắt buộc đăng ký và truy vết |

**Không phải mọi dịch vụ KMS/HSM có đúng tên trường như bảng trên.** Đây là mô hình quản trị; khi triển khai cần ánh xạ sang API, trạng thái, key type và quyền thực của nhà cung cấp. Nếu KMS không cho thiết lập thuộc tính cần thiết, phải **từ chối yêu cầu hoặc chọn kiến trúc khác**, không lưu một trường metadata giả rồi tự tin rằng bảo vệ đã được thực thi.

### 3.1. Key generation request khác với key inventory record

- **Request:** ý định được cấp phép để **tạo một khóa mới**. Ví dụ `purpose=JWT_SIGNING`, `location=HSM`, `exportable=false`.
- **Inventory record:** trạng thái **khóa đã tồn tại** và bằng chứng quá trình sinh/cấp phát, ví dụ `keyId`, `version`, `createdAt`, `providerRef`, `lifecycleState`.

Không dùng `status=ACTIVE` trong request như một cách bỏ qua preflight. Thông thường, key material được tạo trong trạng thái chờ, metadata được đăng ký và **activation** diễn ra sau khi điều kiện riêng được đáp ứng.

## 4. Chọn thuật toán, độ dài và key usage đúng mục đích

Không có một “độ dài khóa chuẩn” áp dụng cho mọi cơ chế. **256 bit AES** và **256 bit public key trên đường cong elliptic** không có cùng cách quy đổi sang mức an toàn, còn RSA cần các thông số và kích thước khác.

| Profile ví dụ | Thuật toán / cơ chế | Chính sách sinh khóa |
| --- | --- | --- |
| **DEK mã hóa dữ liệu** | AES-256 cho AES-GCM | Sinh key ngẫu nhiên 256 bit; quản lý nonce/khối lượng dữ liệu theo key |
| **DEK hiệu năng cao/compatibility** | AES-128 hoặc AES-256 theo policy | Không tùy chọn độ dài bởi client không tin cậy |
| **HMAC key** | Khóa ngẫu nhiên riêng cho HMAC-SHA-256 | Không dùng cùng key với AES, JWT hay dữ liệu tenant khác |
| **Private signing key** | Ed25519, ECDSA P-256 hoặc RSA-PSS với tham số được duyệt | Sinh bằng provider/KMS/HSM hỗ trợ, giới hạn quyền `Sign` |
| **RSA cho use case tương thích** | RSA 3072-bit (ví dụ policy), RSA-OAEP hoặc RSA-PSS theo purpose | Không dùng cùng key cho cả ký và giải mã khi policy cấm |
| **Key agreement** | X25519 hoặc ECDH trên nhóm/curve được duyệt | Private key riêng, không chia sẻ raw secret; KDF và xác thực peer |
| **KEK trong KMS/HSM** | Thuật toán wrapping/encryption do nền tảng hỗ trợ và policy duyệt | Ưu tiên key material sinh trong vùng quản lý, đúng export policy |
| **Password-derived key** | Argon2id/PBKDF2/scrypt theo chính sách | **Không phải thay thế** cho việc sinh random DEK có entropy cao |

Các thuật toán và ví dụ ở bảng là **hồ sơ thiết kế tham khảo**, không phải tuyên bố mọi môi trường đều được phép sử dụng chúng. Chọn profile theo **tiêu chuẩn hiện hành, yêu cầu tuân thủ, threat model, kỳ hạn lưu trữ và khả năng tương thích**; kiểm tra lại chính sách khi thuật toán hoặc rủi ro lượng tử thay đổi.

### 4.1. Tách purpose ngay từ lúc tạo

Một chính sách mạnh quy định **key usage khi sinh**, thay vì cho phép khóa rồi quyết định mục đích tùy ý:

~~~text
Policy A — data-encryption
  keyType: symmetric AES-256
  uses: ENCRYPT, DECRYPT
  owner: data-service
  environment: production

Policy B — signing
  keyType: Ed25519 private/public pair
  uses: SIGN (private), VERIFY (public)
  owner: identity-service
  location: HSM/KMS theo chính sách
  exportPrivateKey: false

Không dùng một vật liệu khóa cho cả A và B.
~~~

**Một key AES hoạt động tốt với GCM không làm nó thích hợp làm HMAC key.** Tương tự, private key ký số nên tách với key giải mã, kể cả cùng họ RSA. Khi một thành phần bị lộ, **key separation** hạn chế số nhiệm vụ và hệ thống bị ảnh hưởng.

### 4.2. Đường cong, RSA và thuật toán hậu lượng tử

**Ed25519** là lược đồ chữ ký; **X25519** phục vụ thỏa thuận khóa. Chúng không được dùng như hai tên hoán đổi cho một key. Với ECDSA, phải chỉ định curve và hash phù hợp; với RSA-PSS, phải xác định thêm hash/MGF/salt length khi sử dụng, không chỉ ghi `algorithm=RSA`.

Nếu hệ thống có dữ liệu cần bảo vệ trong thời gian dài, chính sách nên có **algorithm agility**: trường phiên bản, mục đích và định dạng cho phép thay profile khi tiêu chuẩn hoặc rủi ro thay đổi. Chuyển sang thuật toán **hậu lượng tử/hybrid** cần profile/khả năng provider và giao thức được phê duyệt riêng, không chỉ tăng `keySize` trong một trường tổng quát.

## 5. Entropy, CSPRNG và yêu cầu về nguồn sinh

**Entropy** đo độ bất định thực của nguồn. Một mảng 32 byte không có nghĩa chứa 256 bit entropy nếu được tạo bằng seed có thể đoán được. **CSPRNG/DRBG** được thiết kế để tạo byte khó dự đoán khi trạng thái được khởi tạo đúng từ nguồn entropy đủ chất lượng.

### 5.1. Những nguồn không được dùng cho secret key

~~~java
// CÁC VÍ DỤ SAI — KHÔNG DÙNG CHO KHÓA/SECRET:
// new java.util.Random().nextBytes(key);
// Math.random();
// System.currentTimeMillis();
// UUID.randomUUID().toString().getBytes();
// sha256(username + processId + timestamp);
~~~

Ghép nhiều dữ liệu công khai hoặc băm một nguồn yếu **không tự tạo thêm entropy bí mật**. UUID v4 có cấu trúc và độ dài ngẫu nhiên nhất định; nó phù hợp làm ID, **không phải API thay thế KeyGenerator cho AES-256**.

### 5.2. Nguồn được phép và cách xác minh

- Trong Java, ưu tiên `SecureRandom` từ **JDK/OS/provider được cấu hình phù hợp** hoặc `KeyGenerator/KeyPairGenerator` đã được cung cấp nguồn random mật mã.
- Nếu policy yêu cầu tạo khóa **trong KMS/HSM**, sử dụng API `GenerateKey/GenerateDataKey/CreateKey` tương ứng **nếu dịch vụ hỗ trợ**, thay vì tạo key trong JVM rồi import và giả định tương đương non-extractability.
- Với môi trường có yêu cầu **FIPS**, đánh giá **module cryptographic/provider, phiên bản, chế độ vận hành và phạm vi chứng nhận thực tế**; tên `SecureRandom` hoặc “HSM” không tự chứng minh toàn bộ đường sinh đáp ứng yêu cầu.
- Chọn cơ chế **reseed, health monitoring, khôi phục sau VM snapshot/fork** theo provider, hệ điều hành và mô hình triển khai.
- Nếu RNG hoặc KMS không sẵn sàng, thao tác sinh secret **phải thất bại an toàn**. Không fallback ngầm sang `Random`, timestamp hay key cố định.

### 5.3. SecureRandom là API, không phải thuật toán cố định

`new SecureRandom()` chọn provider theo cấu hình runtime. `getInstanceStrong()` dựa trên cấu hình thuật toán “strong” của môi trường, **không phải lựa chọn bắt buộc cho mọi request** và có thể có đặc điểm latency/block khác. Chính sách phải nêu rõ yêu cầu bảo mật, hiệu năng và provider được phê duyệt, thay vì buộc mọi workload gọi một tên phương thức chưa kiểm thử.

**Đừng đánh giá CSPRNG chỉ bằng việc nhìn kết quả hoặc chạy kiểm tra phân bố đều.** Một PRNG dễ đoán vẫn có thể tạo phân bố trông rất đều. Chất lượng đến từ **thiết kế thuật toán, entropy source, provider, cấu hình và kiểm soát vận hành**.

### 5.4. Ngẫu nhiên và duy nhất là hai yêu cầu riêng

Đối với AES-GCM và ChaCha20-Poly1305, chính sách sinh **key** phải kết nối với chính sách **nonce**. Nonce thường không cần bí mật, nhưng **cặp (key, nonce) không được lặp** trong những chế độ này. Sinh nonce bằng `SecureRandom` không chứng minh tuyệt đối không va chạm, đặc biệt ở quy mô nhiều node.

Nếu dùng nonce ngẫu nhiên 96 bit cho AES-GCM, xác suất xấp xỉ có ít nhất một collision sau `q` lần sinh độc lập, đều, khi xác suất còn nhỏ:

\[
P(\text{collision}) \approx \frac{q(q-1)}{2^{97}}
\]

Chính sách cần chỉ rõ **giới hạn bản tin/khóa, namespace/counter nếu dùng, xử lý reset/snapshot, key rotation và audit**. Không nhầm khóa mới mỗi đối tượng với nonce mới cho mỗi thông điệp dưới cùng key.

## 6. Chọn nơi tạo khóa: trong JVM, KMS hay HSM?

**Địa điểm sinh** ảnh hưởng trực tiếp đến vùng nào có thể quan sát key material.

| Địa điểm | Có thể phù hợp khi | Rủi ro/chính sách cần quản lý |
| --- | --- | --- |
| **Java/JCA trong tiến trình** | Secret tạm thời hoặc DEK dùng trong phạm vi được cho phép | Key material tồn tại trong RAM ứng dụng; cần bảo vệ heap/dump/log, phân quyền và giải phóng |
| **KMS managed key generation** | KEK hoặc key dùng API mật mã/bao khóa do dịch vụ quản lý | Kiểm tra kiểu khóa, quyền API, vùng/region, khả năng xuất, audit và retention |
| **HSM tạo key tại chỗ** | Private key ký, root key hoặc KEK cần ranh giới bảo vệ cao | Kiểm tra phần cứng/provider, non-extractability, dual control, availability và backup |
| **Key import/BYOK** | Có lý do về sở hữu/chuyển giao key material | Đường import, wrapping, xuất/xóa bản sao nguồn và trách nhiệm về entropy |
| **Key agreement (ECDHE)** | Thiết lập secret phiên qua giao thức chuẩn | Dùng thư viện TLS/SSH/AKE, key authentication và KDF; không đưa raw shared secret vào inventory vĩnh viễn |

**Non-extractable không đồng nghĩa “không thể bị lạm dụng”**. Một private key ở HSM không xuất được vẫn có thể bị gọi `Sign` trái phép nếu IAM/policy không kiểm soát đúng workload. Cần tách **khả năng lấy byte khóa** với **quyền ra lệnh dùng khóa**.

### 6.1. Khi nào nên yêu cầu key không xuất được?

Ví dụ chính sách có thể yêu cầu:

- **Root KEK / private signing key:** sinh bên trong HSM/KMS và không xuất raw key material ra JVM.
- **DEK cho mã hóa dữ liệu dung lượng lớn:** KMS có thể cấp DEK tạm thời/DEK wrapped theo mô hình provider; raw DEK chỉ tồn tại ngắn hạn trong trusted workload nếu kiến trúc cho phép.
- **Ephemeral session secrets:** do TLS stack giữ/thiết lập theo giao thức; không mặc định mọi secret TLS đều ở HSM chỉ vì private signing key của server ở HSM.

Không thể áp một cờ `exportable=false` trong metadata của ứng dụng rồi khẳng định private key sinh trong Java đã trở thành non-extractable. **Bảo đảm này phải được nhà cung cấp/kiểu key thực thi** và kiểm chứng bằng các thao tác không được phép.

### 6.2. Khóa được sinh và khóa được import khác nhau

Nếu policy yêu cầu **key generated within approved HSM boundary**, một khóa được sinh ở laptop rồi import vào HSM **không đáp ứng cùng điều kiện nguồn sinh**. Khóa đó đã từng tồn tại ở vùng không kiểm soát; dù HSM bảo vệ tốt sau khi import, bản sao ngoài vùng đó có thể vẫn còn.

Với BYOK/HYOK, phải mô tả rõ **ai sinh, dùng RNG nào, wrap/import qua giao thức nào, nơi giữ bản sao, quyền xóa và backup**. Không chỉ ghi “KMS: yes” trong inventory.

## 7. Chính sách cho DEK/KEK, chữ ký số, HMAC và thỏa thuận khóa

### 7.1. DEK và envelope encryption

Trong **envelope encryption**, DEK mã hóa plaintext bằng AEAD; KEK bảo vệ (wrap/encrypt) DEK. Một generation policy có thể quy định:

1. **DEK ngẫu nhiên mới** cho từng đối tượng hoặc một phạm vi dữ liệu/cryptoperiod đã giới hạn.
2. **KEK được quản lý trong KMS/HSM**, với quyền unwrap/wrap tách theo workload.
3. **Key ID/version và AAD** gắn với tenant/resource/context; nonce phải duy nhất dưới DEK.
4. Chỉ giữ raw DEK trong RAM đủ lâu để mã hóa/giải mã; không ghi ra log/config.
5. Payload lưu **wrapped DEK, nonce, ciphertext/tag, algorithm version** và reference để giải mã sau này.

~~~mermaid
flowchart LR
    Req[Request mã hóa] --> Auth[Authorization + generation policy]
    Auth -->|Đạt policy| KMS[KMS/HSM: KEK + Generate/Wrap DEK]
    KMS --> DEK[DEK ngẫu nhiên tạm thời]
    DEK --> AEAD[AEAD encrypt + nonce + AAD]
    AEAD --> CT[(Ciphertext + tag)]
    KMS --> Wrapped[(Wrapped DEK + KEK reference)]
    Wrapped --> DB[(Lưu metadata theo key version)]
    CT --> DB
    Auth -.-> Audit[Audit actor / policy revision / key ID]
~~~

**Sinh khóa đúng chưa đủ**: nếu bỏ qua quyền đọc tenant hoặc dùng nonce trùng, dữ liệu vẫn có thể bị lộ hoặc bản mã mất xác thực. Nếu KEK bị lộ cùng wrapped DEK, chỉ rewrap bản đang tồn tại **không xóa các bản copy cũ** mà attacker đã lấy; cần đánh giá thay DEK và re-encrypt dữ liệu.

### 7.2. Private signing key và public key distribution

Private key dùng RSA-PSS, ECDSA hoặc Ed25519 cần:

- **Mục đích `SIGN` rõ ràng**; không dùng lại key làm encryption key khi policy cấm.
- **Vùng sinh/lưu phù hợp**; nhiều hệ thống yêu cầu HSM/KMS và non-extractability.
- **Owner, danh tính, chứng thư/public key binding** và quy trình công bố public key đáng tin.
- **Cryptoperiod** cho việc tạo chữ ký mới; khả năng **verify lịch sử** sau rotation khi phù hợp.
- **Audit thao tác `Sign`**, approval hoặc giới hạn đối tượng được ký theo nghiệp vụ.

**Chữ ký hợp lệ toán học không tự chứng minh quyền ký.** Một ứng dụng ký thanh toán phải kiểm tra người yêu cầu, ngữ cảnh, chính sách giao dịch và dữ liệu được ký trước khi gọi HSM.

### 7.3. HMAC/PSK và bí mật dùng chung

Khóa HMAC hay PSK cần **entropy đủ cao**, phạm vi phân phối xác định và chính sách **separation**. Một PSK dùng chung tất cả thiết bị IoT có thể khiến việc mất một thiết bị ảnh hưởng toàn bộ fleet; nên xét **PSK riêng theo thiết bị/tenant** hoặc cơ chế xác thực mạnh hơn.

Không sinh PSK từ username, serial number, MAC address hoặc timestamp rồi giả định bí mật. Nếu cần dẫn xuất nhiều khóa con từ **keying material có entropy cao**, dùng **HKDF với context separation**; không tự nối `serviceName + masterKey` rồi băm tùy tiện.

### 7.4. Mật khẩu và password-derived key

**Mật khẩu do con người đặt không phải nguồn sinh random DEK có entropy tương đương AES-256**. Nếu dùng passphrase để bảo vệ file, cần **PBKDF2/Argon2id/scrypt** theo thiết kế, salt ngẫu nhiên và khả năng chống đoán offline; tốt hơn trong nhiều hệ thống lưu trữ là sinh **DEK ngẫu nhiên** rồi bảo vệ nó qua KMS hoặc password-derived wrapping key.

Không được dùng trực tiếp `SHA-256(password)` làm AES key hoặc seed `SecureRandom` từ password để thay một KDF chuyên dụng.

## 8. Workflow sinh khóa có kiểm soát

Một luồng sinh khóa an toàn phải có **điểm chặn trước khi key material được tạo**, và **bằng chứng sau khi sinh**.

~~~mermaid
flowchart TD
    A[Workload / owner yêu cầu tạo khóa] --> B[Xác thực principal + scope]
    B --> C{Policy profile hợp lệ?}
    C -->|Không| DENY[Từ chối + audit]
    C -->|Có| D[Kiểm tra algorithm, usage, strength, location]
    D --> E{Approval, IAM, quotas, compliance đạt?}
    E -->|Không| DENY
    E -->|Có| F[Generate trong approved RNG/KMS/HSM]
    F --> G{Có key reference + evidence hợp lệ?}
    G -->|Không| FAIL[Quarantine/rollback an toàn + alert]
    G -->|Có| H[Register key ID/version, owner, policy revision]
    H --> I[Pre-active + kiểm tra key usage / permissions]
    I --> J{Đủ điều kiện activation?}
    J -->|Không| PENDING[Giữ trạng thái chờ]
    J -->|Có| K[Active đúng thời điểm theo policy]
    K --> L[Audit, monitoring, rotation plan]
~~~

### 8.1. Bước 1 — Tiếp nhận yêu cầu

Yêu cầu có **identity, environment, tenant, key purpose, key class, algorithm profile, export policy, activation plan**. Không cho client tùy ý gửi tên thuật toán rồi chọn một trong mọi thuật toán mà provider hỗ trợ.

### 8.2. Bước 2 — Authorize và phê duyệt

Kiểm tra **IAM/service identity**, owner và phạm vi nghiệp vụ. Một dịch vụ được `Encrypt` không nhất thiết có quyền **sinh root KEK** hay **tạo private signing key**. Với các khóa nhạy cảm, áp dụng approval/dual control hoặc separation of duties khi chính sách yêu cầu.

### 8.3. Bước 3 — Sinh trong trusted boundary

Dùng **RNG/DRBG và thuật toán được phê duyệt**, không xuất raw key nếu policy yêu cầu non-extractable. Ghi nhận **key reference** và bằng chứng từ provider, không in key bytes để “xác minh chất lượng”.

### 8.4. Bước 4 — Inventory, pre-active và activation

Đăng ký key ID/version, owner, algorithm, purpose, policy revision, `createdAt`, `activationAt`, `newUseUntil`, location và audit. Không tự gán key `ACTIVE` khi chưa hoàn tất kiểm soát kích hoạt và quyền. Trong phân tán, phải xử lý cache, clock skew và policy propagation.

### 8.5. Bước 5 — Sử dụng, giới hạn và rotation

Khi Active, key chỉ được dùng cho những operation đã phê duyệt. Có **cryptoperiod** và giới hạn dùng, đặc biệt nonce/record count với AEAD. Tạo successor trước hạn; giữ khả năng decrypt/unwrap/verify dữ liệu cũ khi policy cần và chỉ destroy sau kiểm tra backup/retention.

## 9. Ví dụ policy-as-code: yêu cầu và quyết định

Một tổ chức có thể định nghĩa profile ở control plane. Ví dụ JSON dưới đây **chỉ minh họa cấu trúc**, không phải cấu hình trực tiếp cho bất kỳ cloud KMS nào:

~~~json
{
  "policyId": "production-key-generation",
  "policyVersion": 12,
  "defaultAction": "DENY",
  "profiles": [
    {
      "id": "data-dek-v2",
      "keyClass": "SYMMETRIC",
      "algorithm": "AES",
      "sizeBits": 256,
      "purposes": ["ENCRYPT_DATA", "DECRYPT_DATA"],
      "allowedEnvironments": ["production"],
      "generationLocation": "APPROVED_KMS_OR_RUNTIME",
      "requireCSPRNG": true,
      "allowPlaintextExport": false,
      "ownerRequired": true,
      "tenantScopeRequired": true,
      "inventoryRequired": true,
      "auditRequired": true
    },
    {
      "id": "invoice-signing-v3",
      "keyClass": "ASYMMETRIC",
      "algorithm": "Ed25519",
      "purposes": ["SIGN", "VERIFY"],
      "generationLocation": "APPROVED_HSM",
      "privateKeyExportable": false,
      "productionApproval": "TWO_PERSON",
      "inventoryRequired": true,
      "auditRequired": true
    }
  ]
}
~~~

**Giải thích giới hạn cấu trúc:** trường `allowPlaintextExport` của profile DEK là một **ràng buộc triển khai**, không thể kết luận nó tương thích với mọi API `GenerateDataKey`. Một số mô hình envelope encryption **cần DEK ở dạng rõ tạm thời trong workload** để mã hóa dữ liệu; một số dùng KMS/HSM để thực hiện thao tác mà không xuất DEK. Nếu chọn cấu trúc có `allowPlaintextExport=false`, **phải triển khai đường sinh/dùng DEK phù hợp**, không âm thầm xuất raw DEK rồi coi như đã tuân thủ. Chính sách thật cần làm rõ cách truyền/giữ key material.

### Quy tắc policy-as-code

- **Default deny:** không nhận một yêu cầu không khớp profile đã phê duyệt.
- **Versioned:** policy mới có revision/approval; event hoặc cache cũ không được tự rollback cấu hình.
- **No caller-controlled override:** owner/workload không được tự tắt `auditRequired` hoặc đổi `APPROVED_HSM` thành `LOCAL`.
- **Immutable evidence:** log lý do và kết quả phê duyệt, key reference và trạng thái thực; không log key bytes.
- **Provider-verified:** kiểm tra thuộc tính được **thực thi ở KMS/HSM**, không chỉ khai báo trong JSON.
- **Separate environment:** policy production không bị ghi đè bằng test config hoặc tài khoản CI thiếu kiểm soát.

## 10. Ví dụ Java 17: thực thi policy trước khi tạo khóa

Ví dụ dưới đây cho thấy cách **khóa việc sinh key cục bộ nếu sai profile**, cách tạo **AES-256** và cặp khóa **Ed25519** bằng JCA trong **môi trường demo**. Nó **không mô phỏng việc bảo vệ HSM/KMS** và **không nên dùng để sinh private signing key production**. Nếu policy yêu cầu `HSM`/non-extractable, code **từ chối trước khi gọi generator**.

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Set;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class KeyGenerationPolicyDemo {
    enum Purpose { DATA_DEK, DOCUMENT_SIGNING }
    enum Target { LOCAL_DEMO, MANAGED_KMS_HSM }

    record GenerationRequest(
            String owner, String environment, String tenant,
            Purpose purpose, Target target, String keyId,
            boolean nonExtractableRequired) {}

    record Policy(
            long revision, Set<String> permittedEnvironments,
            Set<Purpose> permittedPurposes) {
        Policy {
            if (revision < 1 || permittedEnvironments == null
                    || permittedPurposes == null) {
                throw new IllegalArgumentException("Invalid policy");
            }
            permittedEnvironments = Set.copyOf(permittedEnvironments);
            permittedPurposes = Set.copyOf(permittedPurposes);
        }
    }

    static void enforceBeforeGeneration(GenerationRequest req, Policy policy) {
        if (req == null || policy == null
                || req.owner() == null || req.owner().isBlank()
                || req.tenant() == null || req.tenant().isBlank()
                || req.keyId() == null || req.keyId().isBlank()
                || req.environment() == null
                || req.purpose() == null || req.target() == null
                || !policy.permittedEnvironments().contains(req.environment())
                || !policy.permittedPurposes().contains(req.purpose())) {
            throw new SecurityException("Key generation denied");
        }

        // Bài demo CHỈ hỗ trợ local keygen ở môi trường dev;
        // production phải gọi adapter KMS/HSM riêng được kiểm chứng.
        if (req.target() != Target.LOCAL_DEMO
                || !"dev".equals(req.environment())
                || req.nonExtractableRequired()) {
            throw new SecurityException(
                    "Use approved managed key generation path");
        }
    }

    static SecretKey newAes256ForDemo(SecureRandom rng) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, rng);
        return generator.generateKey();
    }

    static KeyPair newEd25519ForDemo() throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("Ed25519");
        return generator.generateKeyPair();
    }

    public static void main(String[] args) throws Exception {
        Policy policy = new Policy(
                12, Set.of("dev"), Set.of(
                        Purpose.DATA_DEK, Purpose.DOCUMENT_SIGNING));

        GenerationRequest aesRequest = new GenerationRequest(
                "sample-service", "dev", "sample-tenant",
                Purpose.DATA_DEK, Target.LOCAL_DEMO,
                "demo-dek-v1", false);
        enforceBeforeGeneration(aesRequest, policy);
        SecretKey dek = newAes256ForDemo(new SecureRandom());

        GenerationRequest signingRequest = new GenerationRequest(
                "sample-service", "dev", "sample-tenant",
                Purpose.DOCUMENT_SIGNING, Target.LOCAL_DEMO,
                "demo-signing-v1", false);
        enforceBeforeGeneration(signingRequest, policy);
        KeyPair pair = newEd25519ForDemo();

        // Chỉ xuất metadata, tuyệt đối không in raw key/private key.
        System.out.println("Generated AES: " + dek.getAlgorithm());
        System.out.println("Generated signing key: "
                + pair.getPublic().getAlgorithm());
        System.out.println("Policy revision: " + policy.revision());
        System.out.println("Recorded at: " + Instant.now());

        GenerationRequest prohibited = new GenerationRequest(
                "sample-service", "production", "sample-tenant",
                Purpose.DOCUMENT_SIGNING, Target.LOCAL_DEMO,
                "production-signing", true);
        try {
            enforceBeforeGeneration(prohibited, policy);
            throw new AssertionError("Production key must be rejected");
        } catch (SecurityException expected) {
            System.out.println("Production local keygen: denied");
        }
    }
}
~~~

### 10.1. Code minh họa được gì?

1. **Deny trước khi sinh:** `enforceBeforeGeneration` kiểm tra owner, tenant, environment, purpose, location và điều kiện non-extractability.
2. **Đúng API chuyên dụng:** dùng `KeyGenerator` cho AES, `KeyPairGenerator` cho Ed25519 thay vì tự tính key bytes từ timestamp.
3. **Không in key material:** chỉ metadata như thuật toán và revision được hiển thị.
4. **Thử trường hợp từ chối:** request production yêu cầu non-extractable **không được chuyển ngầm thành local keygen**.
5. **Không nhầm policy và provider:** demo không thực thi IAM, HSM attestation, secure storage, key inventory thật hoặc cryptoperiod; các bước đó cần control plane và SDK thực.

### 10.2. Điều production phải bổ sung

**Không được sao chép thẳng code demo làm dịch vụ key management.** Ngoài chính sách local ở trên, production cần:

- Danh tính workload xác thực (không tin trường `owner` do client nhập), quyền tạo key riêng, approved profiles và approval workflow.
- SDK KMS/HSM để tạo key **trong vùng tin cậy đúng yêu cầu**; xác minh thuộc tính non-extractable, key type, purpose và state.
- Quản lý **transaction/idempotency**: request retry không được tạo ra hàng loạt key mà không có tracking.
- Đăng ký **key ID/version, policy revision, provider reference, `createdAt`, activation plan và audit**.
- Policy kiểm tra ở **thời điểm dùng khóa**, không chỉ lúc tạo, và ứng dụng kiểm tra authorization của tenant/resource.
- Kế hoạch quota, rate limiting, cost và rollback an toàn khi provider tạo key thành công nhưng inventory ghi lỗi.
- Hạn chế raw key tồn tại trong heap, log, trace, dump; với non-extractable phải tránh xuất từ đầu, không dựa vào `Arrays.fill` để giả lập HSM.

## 11. Chứng minh chính sách đã được thực thi

Chỉ có policy document và sự kiện `SUCCESS` từ SDK chưa đủ. Hệ thống nên có **bằng chứng được kiểm tra và có thể truy vết**:

| Kiểm chứng | Thao tác cần thử | Kỳ vọng |
| --- | --- | --- |
| **Sai algorithm** | Yêu cầu thuật toán ngoài allowlist | Từ chối trước khi sinh |
| **Sai size/curve** | Xin AES-64 hoặc đường cong không được duyệt | Từ chối |
| **Sai environment** | Dùng profile dev trong production | Từ chối |
| **Sai tenant/owner** | Workload A xin khóa cho tenant B trái quyền | Từ chối |
| **Sai purpose** | Signer xin `Decrypt` hoặc DEK xin `Sign` | Từ chối |
| **Sai generation location** | Xin private signing key non-extractable trong JVM | Từ chối |
| **Không đạt approval** | Tạo root KEK chưa được phê duyệt | Từ chối và audit |
| **Provider RNG lỗi** | RNG/KMS không khả dụng | Fail closed; không fallback yếu |
| **Export trái policy** | Yêu cầu raw private key từ HSM | API từ chối; kiểm tra key class |
| **Không ghi inventory** | Simulate lỗi DB sau khi tạo key | Có quarantine/reconciliation; không để orphan key bị dùng |
| **Retry trùng request** | Gửi lại cùng request ID | Không tạo key ngoài dự kiến |
| **Sau compromise** | Request dùng lại key material bị lộ | Từ chối hoặc đưa vào incident workflow |

**Một phép thử “hai khóa mới khác nhau” không chứng minh RNG an toàn.** Cần đánh giá nguồn entropy/provider và trạng thái vận hành theo tiêu chuẩn áp dụng. Không cố export raw private key khỏi HSM chỉ để so sánh và chứng minh rằng “nó thực sự ngẫu nhiên”.

### 11.1. Các phép kiểm sau generation

Ở mức API và đặc tả phù hợp, có thể xác minh **algorithm, key size, curve, key type, provider key reference, permitted operations, non-exportability** và trạng thái. Một số provider hỗ trợ **self-test, attestation, key check value** hoặc bằng chứng riêng; chỉ dùng khi phù hợp và không làm lộ bí mật. **Đừng băm trực tiếp raw key rồi đưa hash vào log công khai** chỉ để làm fingerprint nếu không có lý do/đánh giá cụ thể; một số key class có nguy cơ bị dùng sai hoặc lộ metadata nhạy cảm.

### 11.2. Failure handling

Khi key generation đã thành công trong KMS nhưng cập nhật inventory thất bại:

1. Ghi một **operation ID** đủ truy vết trước khi gọi provider.
2. Phát hiện đối tượng khóa đã tồn tại khi retry và xử lý idempotency.
3. Giữ khóa mới ở trạng thái **quarantine/pre-active**, không cho dùng ngay.
4. Reconcile metadata, owner và policy; chỉ activate sau khi dữ liệu quản trị nhất quán.
5. Nếu hủy đối tượng lỗi, làm theo quy trình cho phép và kiểm tra **không còn dữ liệu phụ thuộc**.

Không tự import key từ một thư mục tạm không tin cậy để “chữa nhanh” lỗi generation và không bypass audit.

## 12. Vòng đời khóa bắt đầu từ generation policy

Khóa được sinh chỉ là **điểm bắt đầu** của một chuỗi trách nhiệm:

~~~mermaid
sequenceDiagram
    participant Owner as Service owner
    participant Policy as Policy + IAM
    participant KMS as KMS/HSM
    participant Inv as Key inventory
    participant App as Data / signing service
    Owner->>Policy: Xin tạo key theo purpose và scope
    Policy->>Policy: Algorithm, strength, location, approval
    Policy-->>Owner: Approve hoặc Deny
    Policy->>KMS: Generate theo profile được duyệt
    KMS-->>Inv: Key reference + metadata
    Inv->>Inv: Register key version ở PRE_ACTIVE
    Inv->>App: Activation/policy event được xác thực
    App->>KMS: Encrypt/Wrap/Sign khi quyền, state và time đạt
    KMS-->>App: Ciphertext / wrapped key / signature
    App->>Inv: Audit key ID/version và operation result
    Inv->>Inv: Rotation / retire / revoke / destroy theo policy
~~~

Sơ đồ minh họa control flow; KMS thường không chủ động gửi dữ liệu thẳng tới inventory nếu không có integration. Điều quan trọng là mỗi bước phải có **chủ thể chịu trách nhiệm, điểm thực thi quyền, trạng thái và bằng chứng**.

### 12.1. Activation và cryptoperiod

Chính sách nên chỉ rõ:

- `createdAt`: lúc vật liệu được sinh.
- `activationAt`: **thời điểm sớm nhất được phép dùng** cho mục đích đã quy định.
- `newUseUntil`: mốc chấm dứt **tạo bảo vệ mới**.
- `oldUseUntil` hoặc chính sách retention: khả năng decrypt/unwrap hoặc verify dữ liệu cũ khi cần.
- `rotationTrigger`: tuổi khóa, hạn mức, rủi ro, phát hiện compromise hoặc thay yêu cầu thuật toán.

Một key có thể Active cho `DECRYPT_OLD` nhưng **không được `ENCRYPT_NEW`** nếu đã nghỉ hưu theo policy. Tuy nhiên, trạng thái `Disabled` trong một số KMS sẽ chặn tất cả API; không giả định mọi KMS hỗ trợ decrypt-only. Phải thiết kế trạng thái lifecycle ứng dụng và quyền thực thi phù hợp.

### 12.2. Rotation và key generation

**Rotation thật sự đòi hỏi vật liệu khóa mới**, không chỉ sửa alias hoặc key ID. Với KEK, có thể **rewrap DEK** dưới KEK mới nếu DEK không bị lộ. Với DEK bị compromise, có thể cần **DEK mới và re-encrypt** dữ liệu. Việc sinh key mới phải lặp lại preflight, approval và audit như ban đầu, kể cả rotation tự động.

### 12.3. Destruction và backup

Key policy cần quy định lúc nào được hủy, khả năng sao lưu/khôi phục và cách xử lý dữ liệu phụ thuộc. Xóa KEK trong HSM trước khi rewrap mọi DEK có thể khiến backup không thể đọc. Ngược lại, giữ vô hạn mọi private key trong mọi bản sao cũng tăng diện tấn công.

## 13. Audit, governance và separation of duties

### Những trường audit có giá trị

| Trường | Ý nghĩa |
| --- | --- |
| `eventType` | `KEY_GENERATION_REQUESTED`, `APPROVED`, `DENIED`, `GENERATED`... |
| `requestId` / `operationId` | Liên kết request, retry và API provider |
| `actor` / `workloadIdentity` | Ai yêu cầu/ai phê duyệt |
| `policyId` / `policyRevision` | Quy tắc được dùng để quyết định |
| `keyId` / `version` / `providerRef` | Vật liệu nào được sinh và đăng ký |
| `algorithm` / `purpose` / `keyClass` | Thuật toán và phạm vi |
| `generationLocation` / `exportPolicy` | Ranh giới bảo vệ đã thực thi |
| `createdAt` / `activationAt` | Thời điểm tạo và hiệu lực dự kiến |
| `outcome` / `reasonCode` | Thành công, từ chối, lỗi, cần xử lý |

Không ghi **raw secret key, private key, DEK, KEK, plaintext, mật khẩu hoặc token** vào audit; hạn chế cả bản key được encode trong Base64, vì Base64 **không mã hóa**. Audit phải được kiểm soát truy cập, giữ toàn vẹn và retention theo phân loại dữ liệu.

### Separation of duties

Những người/chương trình có thể được tách vai:

1. **Key policy owner:** phê duyệt thuật toán, key class, cryptoperiod.
2. **Key operator:** vận hành HSM/KMS theo quyền giới hạn.
3. **Application principal:** chỉ sử dụng khóa để mã hóa/ký theo nghiệp vụ.
4. **Security auditor:** đọc metadata/audit, không mặc nhiên có quyền export/Sign/Decrypt.
5. **Incident responder:** có đường revoke khẩn cấp được kiểm soát và giám sát.

**Dual control / two-person approval** có ý nghĩa với các thao tác nhạy cảm, nhưng không nên áp dụng máy móc tới mọi khóa phiên sinh tự động. Mức kiểm soát phải phù hợp loại khóa và mô hình đe dọa.

## 14. Tình huống thực tế: nền tảng thanh toán đa tenant

Một nền tảng quản lý thanh toán có các yêu cầu:

- Mỗi tenant có dữ liệu giao dịch được mã hóa bằng **DEK**.
- KEK bảo vệ DEK nằm trong KMS/HSM theo chính sách.
- Lệnh chi trả được ký bằng private signing key do HSM quản lý.
- Nhiều service thuộc môi trường staging và production; toàn bộ thao tác cần audit.

### Thiết kế ban đầu có vấn đề

Nhóm phát triển tự sinh một AES key bằng `Random`, lưu trong biến môi trường dùng chung cho mọi tenant, dùng cùng key cho dữ liệu mới vô hạn và cho phép tất cả service gọi giải mã. Sau đó, khi cần ký giao dịch, họ tạo RSA key cục bộ và đưa PEM private key vào CI artifact.

Sai lầm không chỉ ở thuật toán hoặc cỡ khóa: **không có generation policy, purpose separation, tenant isolation, non-extractability, lifecycle và least privilege**.

### Thiết kế được kiểm soát

**Giai đoạn 1 — Chính sách:**

1. Phê duyệt profile `customer-data-dek`: AES-256 cho AEAD, DEK ngẫu nhiên theo tenant/đối tượng hoặc phạm vi có giới hạn, không dùng lại nonce dưới cùng key.
2. Phê duyệt profile `billing-kek`: khóa wrapping do KMS/HSM bảo vệ, chỉ những workload được chỉ định mới có quyền wrap/unwrap.
3. Phê duyệt profile `payment-signing`: private key ký chỉ được sinh trong vùng HSM được phép, không xuất và chỉ service thanh toán có quyền `Sign` cho thao tác đã duyệt.
4. Định nghĩa `owner`, `environment`, `tenant`, `activationAt`, cryptoperiod, inventory và audit cho mỗi class.

**Giai đoạn 2 — Sinh khóa:**

1. Workload gửi request có identity xác thực và idempotency key.
2. Policy engine từ chối yêu cầu sai môi trường, purpose, thuật toán hoặc vùng sinh.
3. KMS/HSM tạo key trong vùng bảo vệ được duyệt; trả về key reference và thuộc tính hỗ trợ xác minh.
4. Inventory đăng ký ID/version, owner, policy revision; khóa không được tự động sử dụng nếu chưa Active theo chính sách.

**Giai đoạn 3 — Sử dụng:**

1. Data service nhận request, kiểm tra quyền của người dùng với tenant và bản ghi.
2. Data service lấy/sinh DEK đúng profile, mã hóa AEAD với nonce/AAD phù hợp, lưu ciphertext và wrapped DEK cùng metadata.
3. Signing service kiểm tra phê duyệt lệnh chi trả, rồi gọi HSM ký; verifier phân phối public key đã xác thực.
4. Audit ghi key ID/version, policy revision, principal và kết quả, **không ghi plaintext hoặc private key**.

**Giai đoạn 4 — Rotation và sự cố:**

- Đến hạn thay KEK, sinh KEK mới theo cùng generation policy; chuyển primary, rewrap DEK và kiểm tra backup trước khi retire.
- Khi signing private key bị nghi lộ, chặn quyền `Sign`, thu hồi trust/cert thích hợp, tạo key mới và kiểm tra giao dịch ký trong khoảng ảnh hưởng.
- Khi một DEK đã lộ, chỉ đổi KEK không đủ; đánh giá thay DEK và **re-encrypt** dữ liệu.
- Khi staging bị lộ, phạm vi ảnh hưởng được giới hạn bởi **key separation và environment isolation**, thay vì một root key dùng cho mọi môi trường.

**Điểm rút ra:** policy generation được thực thi **trước khi tạo khóa** giúp chặn sai lầm có tính hệ thống mà rotation/incident response về sau khó khắc phục triệt để.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tạo khóa AES bằng `Math.random()` hoặc `Random` | Thiếu bảo đảm khó dự đoán | CSPRNG/`KeyGenerator` hoặc KMS |
| Tin mảng 32 byte luôn có 256 bit entropy | Đánh giá sai độ mạnh nguồn | Đánh giá entropy source và provider |
| Chỉ lưu `algorithm=AES` | Không kiểm soát size/mode/purpose | Profile có thuật toán, size, usage, AEAD policy |
| Tạo private signing key trong JVM dù policy yêu cầu HSM | Khóa từng ở vùng có thể xuất/dump | Sinh trực tiếp trong approved boundary |
| Dùng một key cho AES, HMAC và ký JWT | Cross-purpose exposure | Tách key theo mục đích |
| Một KEK dùng chung staging/production | Sự cố môi trường yếu ảnh hưởng dữ liệu thật | Environment/tenant isolation |
| Lưu raw key trong Git, config, log hoặc CI artifact | Rò rỉ key material | KMS/HSM/secret store, cấm export/log |
| Tin `exportable=false` trong JSON là bảo vệ thật | Provider có thể vẫn cho xuất raw key | Kiểm chứng thuộc tính tại KMS/HSM |
| Sinh key thành công rồi bỏ qua inventory | Không quản lý cryptoperiod/rotation/backup | Mandatory key registry và audit |
| Client tự chọn thuật toán/provider tùy ý | Policy bypass, downgrade | Allowlist profile với default deny |
| Đổi alias nhưng không sinh vật liệu mới khi compromised | Attacker vẫn có raw key | Rotation thực và xử lý dữ liệu phụ thuộc |
| Dùng random nonce mà không có usage limit | Collision (key, nonce) ở quy mô lớn | Nonce strategy/limit/rotation |
| Không có idempotency khi retry `CreateKey` | Orphan keys, quota/cost, khó audit | Request ID, reconciliation và quarantine |
| Xóa key cũ ngay sau khi tạo key mới | Mất khả năng giải mã backup/ciphertext | Recipient period, rewrap và restore test |
| Chỉ kiểm tra quyền lúc generation | Lạm dụng `Decrypt/Sign` sau này | Enforce IAM/state/purpose tại mỗi thao tác |
| HSM có key non-exportable nên coi mọi `Sign` là an toàn | Attacker có quyền API có thể ký giả | Authorization nghiệp vụ và audit thao tác |
| Fallback sang RNG yếu khi KMS lỗi | Bypass bảo mật khó phát hiện | Fail closed và xử lý lỗi theo chính sách |

## 16. Checklist khi đưa generation policy vào production

- [ ] Policy có owner, version, approval, **default deny** và danh sách profile được phép?
- [ ] Đã xác định rõ **key class, thuật toán, key length/curve/parameters và purpose**?
- [ ] Đã tách DEK, KEK, HMAC, PSK, private signing key và key agreement theo ranh giới bảo mật?
- [ ] CSPRNG/DRBG, nguồn entropy và provider được phê duyệt, không dùng PRNG không mật mã?
- [ ] Khóa yêu cầu non-extractable được sinh **trong** approved HSM/KMS, không phải sinh ở JVM rồi import?
- [ ] Mọi yêu cầu generation có workload identity xác thực, tenant/environment và scope chính xác?
- [ ] IAM phân tách quyền `CreateKey`, `Sign`, `Encrypt`, `Decrypt`, `Wrap`, `Unwrap`, `Delete`?
- [ ] Có quota, rate limit, idempotency, retry và xử lý orphan key?
- [ ] Key inventory ghi `keyId/version`, provider reference, owner, state, `createdAt`, `activationAt`, policy revision?
- [ ] Trạng thái **PRE_ACTIVE/ACTIVE** được enforce cùng cryptoperiod, không kích hoạt chỉ vì sinh thành công?
- [ ] Với AEAD có kiểm soát **nonce uniqueness dưới cùng key**, usage limits và rotation?
- [ ] Với signing key có public key distribution, chứng thư/trust binding và quy trình revoke?
- [ ] Với DEK/KEK có payload version, wrapped DEK, backup và kế hoạch rewrap/re-encrypt?
- [ ] Không in raw key, private key, password, PSK, traffic secret hoặc plaintext vào log/trace/CI?
- [ ] Có negative tests cho sai algorithm, size, environment, tenant, purpose, location, export và approval?
- [ ] Có audit và giám sát key generation theo principal, profile, key reference, kết quả, lỗi và exception?
- [ ] Đã thử xử lý KMS/HSM unavailable, inventory write failure, rollback và incident compromise?
- [ ] Chính sách tuân thủ/độ mạnh được xem xét lại định kỳ, sẵn sàng chuyển thuật toán/định dạng khi cần?

## 17. Câu hỏi tự kiểm tra

**1. Key generation policy khác key usage policy ở điểm nào?**  
Generation policy quyết định **điều kiện và cách tạo key material**, còn usage policy quyết định **ai được dùng key cho thao tác nào** sau khi tạo. Chúng phải liên kết qua key ID/version và IAM.

**2. Vì sao một AES-256 key sinh từ `Math.random()` chưa chắc mạnh?**  
Vì độ dài 256 bit không bảo đảm có 256 bit entropy. Nếu bộ sinh/seed có thể dự đoán, khóa vẫn yếu.

**3. Private key ký sinh trong Java rồi import vào HSM có thỏa `generated inside HSM` không?**  
Không. Vật liệu khóa đã tồn tại ngoài ranh giới bảo vệ; việc import sau đó không thay đổi lịch sử nguồn sinh.

**4. Vì sao non-extractable chưa đủ chống giả mạo chữ ký?**  
Vì một principal có quyền `Sign` trên HSM có thể lạm dụng API dù không biết byte private key. Cần IAM và authorization nghiệp vụ.

**5. Có thể dùng cùng khóa AES làm HMAC key để tiết kiệm key inventory không?**  
Không nên. Key separation theo purpose giúp giảm rủi ro cross-protocol misuse và phạm vi sự cố.

**6. KMS sinh KEK mới có tự khiến ciphertext cũ giải mã bằng KEK mới không?**  
Không. Wrapped DEK cũ có thể vẫn cần KEK cũ, trừ khi đã rewrap hoặc dùng cơ chế versioning của provider phù hợp.

**7. Khi key generation API thành công nhưng ghi inventory thất bại, nên cho dùng key ngay không?**  
Không. Cần quarantine/pre-active, reconciliation, idempotency và audit trước khi activation.

**8. Policy `exportable=false` trong JSON có chứng minh khóa không xuất được không?**  
Không. Thuộc tính phải được **provider/HSM/KMS thực thi và kiểm chứng**; metadata chỉ là tuyên bố.

**9. Vì sao sinh khóa tốt không thay quản lý nonce?**  
Vì AES-GCM/ChaCha20-Poly1305 vẫn có thể mất bảo mật nếu tái sử dụng cùng cặp (key, nonce). Khóa mạnh và nonce đúng là hai điều kiện độc lập.

**10. Khi một key đã bị lộ, có thể giữ nguyên material rồi đổi key ID/version không?**  
Không. Đổi tên không khiến attacker mất bản sao khóa. Cần vật liệu mới và đánh giá rewrap/re-encrypt, chứng thư và các dữ liệu phụ thuộc.

## Ghi nhớ

**Key generation policy là hàng rào đầu tiên trong vòng đời quản lý khóa:** quy định **ai được tạo khóa, loại khóa nào, bằng thuật toán/độ mạnh/nguồn entropy nào, ở vùng bảo vệ nào và được dùng cho mục đích gì**. Một triển khai an toàn cần **default deny, identity/IAM, profile thuật toán, CSPRNG, KMS/HSM khi phù hợp, non-extractability được thực thi, tách khóa theo purpose, kiểm toán và key inventory**. Sau generation, khóa vẫn cần **activation, cryptoperiod, nonce discipline, rotation, revoke, backup và destruction** theo chính sách. Đặc biệt, **DEK/KEK và envelope encryption, HMAC, chữ ký số, thỏa thuận khóa, password KDF và phân quyền nghiệp vụ** có yêu cầu khác nhau; đừng để một API tạo khóa thành công che khuất những điều kiện bảo vệ bắt buộc của cả hệ thống.

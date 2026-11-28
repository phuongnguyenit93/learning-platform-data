# Key encryption key

> **Chương:** Envelope encryption  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Key encryption key (KEK) là gì?

**Key encryption key (KEK)** là **khóa được sử dụng để bảo vệ một khóa mật mã khác**, thường bằng cơ chế **key wrapping** hoặc một phương thức mã hóa khóa đã được phê duyệt. Trong **envelope encryption**, KEK bảo vệ **data encryption key (DEK)**, còn DEK trực tiếp mã hóa dữ liệu nghiệp vụ.

Giả sử nền tảng hóa đơn cần mã hóa 10 triệu tài liệu. Thay vì gửi từng tài liệu tới HSM để mã hóa bằng một khóa gốc dùng lâu dài, hệ thống có thể:

1. Sinh một **DEK** ngẫu nhiên phù hợp cho một tài liệu hoặc một phạm vi dữ liệu được giới hạn.
2. Dùng DEK mã hóa tài liệu bằng thuật toán **AEAD** như AES-GCM.
3. Dùng **KEK trong KMS/HSM** để wrap DEK.
4. Lưu **ciphertext + wrapped DEK + metadata**, không lưu raw KEK và không lưu raw DEK cùng bản mã ở trạng thái nghỉ.
5. Khi đọc, kiểm tra quyền truy cập dữ liệu, unwrap đúng DEK bằng KEK phù hợp, rồi xác minh AEAD tag và giải mã.

KEK là một mắt xích quan trọng trong **key hierarchy** (hệ phân cấp khóa): nó giúp giảm nơi phải quản lý khóa cấp cao và cho phép thay lớp bảo vệ DEK theo kế hoạch. Tuy nhiên, KEK **không thay thế authorization**, **không tự tạo nonce an toàn** và **không khiến dữ liệu đã lộ lấy lại tính bí mật**.

**Phân biệt cốt lõi:** KEK là **vai trò của khóa**; một khóa AES chỉ trở thành KEK khi nó được cấp mục đích và quyền để bọc/bảo vệ khóa khác. Việc đặt tên `master-key` hay `root-key` không tự chứng minh khóa đó có security boundary hoặc key usage thích hợp.

### Mục tiêu học tập

Sau bài này, bạn sẽ hiểu được kiến trúc DEK–KEK, thuật toán key wrapping, cách đặt KEK trong KMS/HSM, metadata key ID/version và encryption context, vòng đời khóa từ generation đến destruction, phân quyền và kiểm toán, sự khác biệt giữa **rewrap** và **re-encrypt**, cùng ví dụ **Java 17** minh họa AES Key Wrap kết hợp AES-GCM.

## 2. KEK nằm ở đâu trong envelope encryption?

~~~mermaid
flowchart TB
    Owner[Key owner + key generation / usage policy] --> KMS
    subgraph KMS["KMS / HSM: vùng giữ hoặc thực thi KEK"]
        KEK[KEK v3: Wrap / Unwrap DEK]
    end
    Data[Plaintext thuộc tenant A] --> AEAD[AEAD Encrypt bằng DEK]
    RNG[CSPRNG / GenerateDataKey] --> DEK[DEK ngẫu nhiên]
    DEK --> AEAD
    DEK --> Wrap[Key wrap operation]
    KEK --> Wrap
    Wrap --> Wrapped[Wrapped DEK]
    AEAD --> CT[Ciphertext + authentication tag + nonce]
    Wrapped --> Store[(Storage)]
    CT --> Store
    Context[Key ID / version / algorithm / tenant / AAD] --> Store
~~~

Sơ đồ diễn giải **mối quan hệ logic**, không cam kết mọi KMS có API sinh/unwrap trả raw DEK hoặc mọi phép wrap đều thực hiện trong phần cứng. Có kiến trúc mà HSM xử lý toàn bộ DEK, có kiến trúc mà plaintext DEK tồn tại tạm thời trong **trusted application memory**. Phải kiểm tra API và vùng bảo vệ thực tế.

### 2.1. Vì sao dùng hai tầng khóa?

**Tách nhiệm vụ:** DEK chuyên mã hóa dữ liệu, KEK chuyên bảo vệ khóa. Ứng dụng có thể dùng AEAD hiệu năng cao cho dữ liệu lớn mà không yêu cầu KMS/HSM thực hiện từng phép mã hóa bản ghi.

**Tập trung kiểm soát:** KEK có thể nằm trong KMS/HSM với quyền `Wrap/Unwrap`, audit, rotation, quota và chính sách hủy riêng. Quyền đọc dữ liệu vẫn phải được ứng dụng kiểm soát.

**Thay lớp bảo vệ:** khi thay KEK theo kế hoạch mà DEK không bị lộ, có thể **rewrap** DEK dưới KEK mới mà không phải mã hóa lại toàn bộ nội dung.

**Giới hạn phạm vi:** hệ thống có thể sinh DEK riêng cho mỗi đối tượng, tenant hoặc nhóm bản ghi. Nếu một DEK lộ, hậu quả được giới hạn bởi dữ liệu thực sự phụ thuộc DEK đó, giả sử không còn đường tấn công khác.

**Điểm cần cảnh giác:** một KEK dùng chung cho quá nhiều DEK/tenant trở thành mục tiêu có mức ảnh hưởng lớn. Key hierarchy phải được thiết kế có **phạm vi, quyền và khả năng khôi phục** phù hợp.

## 3. KEK, DEK và các loại khóa thường gặp

| Khái niệm | Chức năng chính | Bảo vệ đối tượng nào? | Cần lưu ý |
| --- | --- | --- | --- |
| **DEK (Data Encryption Key)** | Mã hóa/giải mã dữ liệu | Plaintext/ciphertext nghiệp vụ | Nonce uniqueness, AEAD tag, thời gian sống |
| **KEK (Key Encryption Key)** | Wrap/unwrap hoặc encrypt khóa khác | DEK, key object được phép | Key usage, IAM, key version, vùng bảo vệ |
| **Root/master key** | Khóa ở tầng cao của hierarchy | KEK hoặc khóa dẫn xuất, tùy thiết kế | Tác động rộng, quorum, HSM, recovery |
| **Wrapping key** | Khóa dùng thuật toán wrapping | Khóa được wrap | Thường chính là một dạng KEK |
| **Transport public key** | Bảo vệ khóa khi truyền tới bên nhận | DEK hoặc keying material | Private key tương ứng là đường unwrap/decrypt |
| **HMAC key** | Xác thực/tạo MAC | Thông điệp | Không tự dùng làm KEK nếu profile không cho phép |
| **Private signing key** | Tạo chữ ký số | Digest/thông điệp theo scheme | Không thay thế key wrapping hoặc DEK |
| **Password-derived key** | Dẫn xuất từ password/passphrase | Có thể bảo vệ một DEK/KEK cấp thấp | Entropy password thấp, cần KDF và salt phù hợp |

### 3.1. KEK không nhất thiết là “khóa mạnh nhất”

KEK phải có **độ mạnh phù hợp** với DEK, thời gian bảo vệ và cơ chế wrapping. Nhưng tên gọi không cho biết cỡ khóa, độ mạnh hay khả năng chống tấn công. Ví dụ, một KEK AES-128 bảo vệ DEK AES-256 có thể làm **mức an toàn tổng thể bị giới hạn bởi lớp KEK**, tùy threat model và thuật toán.

Với các khóa cần bí mật dài hạn, không nên chỉ ghi `keySize=256`; phải kiểm tra **algorithm, mode/key wrap mechanism, key origin, protection boundary, quota và usage period**.

### 3.2. Key hierarchy nhiều tầng

Có thể có:

~~~text
Root key / HSM root of trust
    |
    +-- KEK cấp tổ chức (hoặc master wrapping key)
         |
         +-- KEK theo tenant / service / purpose
              |
              +-- Wrapped DEK #1 -> ciphertext record #1
              +-- Wrapped DEK #2 -> ciphertext record #2
              +-- Wrapped DEK #3 -> ciphertext record #3
~~~

Đây là **một cấu trúc minh họa**, không phải quy tắc mọi KMS phải có ba cấp. Một managed KMS có thể che phần key hierarchy bên trong; ứng dụng chỉ thấy **logical key ID, version và các API được phép**.

**Mỗi cấp hierarchy làm tăng nhu cầu quản lý lifecycle và phụ thuộc.** Hủy key cấp cao khi key cấp dưới còn được bọc dưới nó có thể làm mất khả năng phục hồi hàng loạt dữ liệu.

## 4. Đặc tính mật mã cần có ở một KEK

Một KEK chỉ có ích khi **phương pháp bảo vệ DEK an toàn**. Không nên dùng “mã hóa bất kỳ” rồi mặc định đó là key wrapping đúng chuẩn.

### 4.1. Confidentiality và integrity của wrapped key

**Confidentiality:** người không có quyền dùng KEK không thể dễ dàng khôi phục DEK từ wrapped DEK.

**Integrity:** nếu bản wrapped key bị sửa, unwrap phải **phát hiện lỗi**, thay vì trả ra một giá trị khóa tùy ý mà ứng dụng sử dụng mà không biết.

**Binding/ngữ cảnh:** phải biết DEK được bảo vệ cho **tenant nào, purpose nào, key ID/version nào và thuộc record nào**, để không dùng một wrapped DEK hợp lệ vào ngữ cảnh trái phép.

**Authorization:** dù ciphertext key blob hợp lệ, KMS/HSM có thể từ chối unwrap nếu principal không có quyền hoặc tenant/context không khớp policy.

**Không nên coi integrity check nội tại của AES Key Wrap là cơ chế tự xác thực toàn bộ metadata nghiệp vụ.** Một wrapped DEK hợp lệ vẫn có thể bị copy sang record hoặc tenant khác nếu ứng dụng không thiết kế binding và quyền phù hợp.

### 4.2. Key usage và key separation

KEK nên được tạo với purpose **`WRAP/UNWRAP` hoặc equivalent**. Không dùng một vật liệu bí mật vừa làm DEK AES-GCM cho dữ liệu, vừa làm HMAC key, vừa làm KEK trừ khi có thiết kế chuẩn và chính sách cho phép rõ ràng; **key separation** giảm nguy cơ cross-protocol misuse.

Nếu dẫn xuất các khóa khác nhau từ một root secret có entropy cao, dùng KDF phù hợp như **HKDF với context separation**; không tự ghép `rootKey + tenantId` rồi băm và gọi đó là hierarchy an toàn.

### 4.3. Nonce không đồng nghĩa KEK

Trong AES-GCM, **nonce/IV không phải khóa**; nó thường được lưu cùng ciphertext nhưng cần **không trùng dưới cùng một DEK**. Với **AES-KW theo RFC 3394**, cơ chế có cách bảo vệ integrity riêng và **không sử dụng nonce ngẫu nhiên cho mỗi lần wrap** theo API cơ bản. Hai lớp có yêu cầu khác nhau và không được trộn lẫn.

## 5. Các cơ chế dùng KEK để bọc khóa

| Cơ chế | Sử dụng khi | Điều phải kiểm tra |
| --- | --- | --- |
| **AES Key Wrap (AES-KW, RFC 3394)** | Bọc khóa với dữ liệu đầu vào phù hợp kích thước | Kích thước đầu vào, kiểm tra integrity unwrap, provider hỗ trợ |
| **AES Key Wrap with Padding (AES-KWP, RFC 5649)** | Dữ liệu cần wrap không đáp ứng ràng buộc kích thước AES-KW cơ bản | Provider/format, padding và integrity |
| **AEAD wrapping bằng AES-GCM** | Cần xác thực ciphertext và AAD tùy thiết kế | Nonce uniqueness, tag, context binding và key usage |
| **RSA-OAEP key transport/wrapping** | Bên gửi dùng public key để bảo vệ một khóa cho bên nhận | Hash/MGF, key length, private key protection, giới hạn kích thước |
| **KMS encrypt/wrap API** | Muốn KEK được quản lý trong KMS/HSM | Semantics provider, ciphertext blob, encryption context, IAM |
| **HSM native key object wrapping** | Di chuyển/backup key object theo cơ chế token đã duyệt | Policy export, template, key attributes, wrapped transfer |

**Không chọn AES-ECB hoặc AES-CBC không có kiểm soát toàn vẹn để “mã hóa DEK” theo cách tự chế.** Không XOR DEK với một key dài hạn rồi coi đó là wrapping. Định dạng wrapped key phải có version thuật toán và cơ chế kiểm tra lỗi rõ.

### 5.1. AES-KW theo RFC 3394

AES-KW là cơ chế chuyên dụng để bọc **keying material**. Dạng cơ bản yêu cầu dữ liệu khóa được wrap có kích thước phù hợp (bội số 64 bit, tối thiểu 128 bit); các DEK AES-128/AES-256 đáp ứng điều kiện này. Nó có cơ chế kiểm tra integrity của dữ liệu được wrap, nhưng **không có AAD cho tenant/record theo cách AES-GCM hỗ trợ**.

**Ví dụ:** một KEK AES-256 được dùng với AES-KW để wrap một DEK AES-256, sau đó lưu `wrappedDek` cùng `kekVersion`. Khi unwrap, nếu dữ liệu đã bị sửa, provider phải báo lỗi xác minh/integrity theo cơ chế đó.

**Không nên bọc một payload dữ liệu tùy ý bằng AES-KW rồi dùng như AEAD tổng quát**. AES-KW thiết kế cho key material với yêu cầu kích thước/format cụ thể.

### 5.2. AES-KWP và đầu vào kích thước bất kỳ

AES-KWP có padding và quy tắc xác minh dành cho dữ liệu có độ dài không đáp ứng dạng AES-KW cơ bản. Không tự thêm byte 0 vào DEK rồi wrap bằng AES-KW nếu chưa có format chuẩn và quy tắc xác minh chiều dài; dùng cơ chế đã được phê duyệt.

### 5.3. AES-GCM để bảo vệ key material

Nếu dùng AEAD để mã hóa DEK, bên cung cấp phải bảo đảm **nonce không tái sử dụng với cùng KEK**. Có thể đưa **key ID/version, purpose, tenant và format version** vào AAD, với encoding ổn định và không mơ hồ.

**Không đưa raw KEK vào AAD, log hoặc metadata.** AAD được xác thực nhưng **không tự được mã hóa/bí mật**; chỉ dùng dữ liệu metadata cần thiết, không chứa secret.

### 5.4. Asymmetric wrapping

Một public key RSA-OAEP cũng có thể dùng để bảo vệ DEK cho người giữ private key tương ứng. Tùy thuật ngữ, public key này đóng vai trò **key wrapping/transport key**; private key phục vụ unwrap/decrypt. Với cơ chế bất đối xứng, key hierarchy, lifecycle và rủi ro compromise cần phân biệt **public key được phân phối rộng** với **private key phải bảo vệ nghiêm ngặt**.

**RSA-OAEP không phải một dạng AES-KW.** Việc chọn RSA-OAEP, hybrid KEM/DEM hoặc cơ chế KMS hỗ trợ cần bám vào chuẩn giao thức và khả năng provider; không tự thiết kế key transport chỉ từ phép RSA textbook.

## 6. Tạo KEK an toàn

Key generation policy phải xác định **algorithm, strength, generation boundary, export policy, key usage, owner và cryptoperiod** trước khi sinh vật liệu KEK.

### 6.1. Sinh trong vùng bảo vệ phù hợp

Đối với KEK dài hạn hoặc có phạm vi rộng, thường ưu tiên **KMS/HSM** để quản lý key material và giới hạn quyền `Wrap/Unwrap`. Nếu chính sách yêu cầu KEK **non-extractable**, nó nên được sinh trong boundary đã phê duyệt và thuộc tính export được **provider thực thi**.

**Một KEK sinh trong JVM rồi import vào HSM không có cùng provenance với KEK được sinh bên trong HSM.** Key có thể từng nằm trong heap, dump, file, VM snapshot hoặc bản sao khác trước khi import.

### 6.2. Nguồn entropy

- Dùng **CSPRNG/DRBG** được phê duyệt hoặc generator của KMS/HSM theo khả năng hỗ trợ.
- Không dùng `Math.random()`, `java.util.Random`, timestamp, PID hoặc username để tạo secret key.
- Không xem “32 byte” là tương đương “256 bit entropy” nếu nguồn có thể đoán.
- Không tự fallback sang RNG yếu khi provider/HSM unavailable.
- Nếu có yêu cầu tuân thủ như FIPS, đánh giá **module, version, mode và phạm vi operation được chứng nhận**, không chỉ tên provider.

### 6.3. Metadata lúc tạo

Nên lưu **key ID/version, owner, tenant scope, algorithm/size, purpose, provider key reference, origin, `createdAt`, `activationAt`, `policyRevision`, approvalRef và audit evidence**. Không lưu **raw KEK** trong inventory, YAML, Git, log hoặc ticket.

### 6.4. Không dùng chung KEK vô hạn

Một KEK cho mọi tenant, môi trường và mục đích làm tăng **blast radius**. Các quyết định tách KEK theo tenant, service, region, data classification hoặc purpose nên dựa trên threat model, quota, chi phí và khả năng recovery. Không có một “số DEK tối đa trên mỗi KEK” áp dụng phổ quát cho mọi KMS/cipher; cần xem ràng buộc thuật toán, hạn mức provider và cryptoperiod.

## 7. Quy trình mã hóa bằng KEK và DEK

Một quy trình thực tế thường gồm ba ranh giới: **authorization**, **key operations** và **data encryption**.

~~~mermaid
sequenceDiagram
    participant Client as Caller
    participant App as Data service
    participant Auth as Tenant/IAM policy
    participant KMS as KMS/HSM với KEK v3
    participant DB as Data store
    Client->>App: Yêu cầu lưu dữ liệu tenant A
    App->>Auth: Kiểm tra quyền ghi record
    Auth-->>App: Allow/deny + context đáng tin
    App->>KMS: GenerateDataKey hoặc Wrap(DEK) theo policy
    KMS-->>App: Wrapped DEK + DEK tạm thời nếu API hỗ trợ
    App->>App: AEAD Encrypt bằng DEK, nonce và AAD
    App->>DB: Ciphertext + tag + nonce + wrapped DEK
    App->>DB: KEK keyId/version + format + context
    App-->>Client: Record reference, không trả raw key
~~~

**Bước 1 — Xác thực và phân quyền.** Caller chỉ được ghi dữ liệu của tenant/resource phù hợp. Không cho client gửi `tenantId` giả rồi chọn KEK của tenant khác.

**Bước 2 — Lấy/sinh DEK.** DEK phải có entropy phù hợp, key length đúng profile; có thể do application CSPRNG tạo hoặc KMS cung cấp theo API. Khi provider trả plaintext DEK, nó chỉ nên sống tạm thời trong bộ nhớ đáng tin.

**Bước 3 — Mã hóa dữ liệu bằng AEAD.** Dùng nonce/IV phù hợp, bảo đảm **cặp (DEK, nonce) không trùng** trong AES-GCM/ChaCha20-Poly1305 và kiểm tra tag ở chiều giải mã. Gắn AAD với ngữ cảnh dữ liệu nếu kiến trúc yêu cầu.

**Bước 4 — Wrap DEK bằng KEK.** Gọi đúng key reference/version hoặc alias được policy cho phép. Nếu KMS hỗ trợ **encryption context**, có thể ràng buộc context phù hợp theo semantics của nó.

**Bước 5 — Lưu.** Lưu ciphertext, tag, nonce, wrapped DEK, algorithm/format version, KEK key reference/version và metadata cần cho recovery. **Không lưu raw DEK hoặc KEK ở trạng thái nghỉ bên cạnh ciphertext**.

**Bước 6 — Audit.** Ghi `operationId`, principal, key reference/version, purpose, tenant, kết quả và policy revision; không ghi plaintext, DEK, KEK hoặc credentials.

### Thứ tự thao tác có thể thay đổi

Một số KMS hỗ trợ **GenerateDataKey** và trả cả wrapped DEK lẫn bản rõ tạm thời. Nếu ứng dụng tự sinh DEK, nó có thể gọi **WrapKey/Encrypt** để nhận wrapped DEK. Mỗi đường khác nhau về **nơi sinh key material, trách nhiệm entropy, quota và vùng dữ liệu rõ**, nên không giả định mọi provider có API và semantics giống nhau.

## 8. Quy trình giải mã và bảo vệ đường Unwrap

Giải mã gồm hai việc khác nhau: **được phép truy cập dữ liệu** và **có thể unwrap DEK**. Một ứng dụng sai có thể vô tình biến KMS/HSM thành một **decrypt oracle** nếu nó unwrap bất kỳ wrapped DEK nào do caller cung cấp.

~~~mermaid
sequenceDiagram
    participant Client as Caller
    participant App as Data service
    participant Policy as Resource + tenant policy
    participant Store as Storage
    participant KMS as KMS/HSM
    Client->>App: Đọc record X của tenant A
    App->>Policy: Kiểm tra quyền đọc X
    Policy-->>App: Allow/deny
    App->>Store: Lấy ciphertext + wrapped DEK + metadata
    Store-->>App: Record + KEK version + nonce + tag
    App->>App: Kiểm tra format và context đáng tin
    App->>KMS: Unwrap với key/version và policy context
    KMS-->>App: DEK tạm thời hoặc operation result
    App->>App: AEAD Decrypt + verify tag/AAD
    App-->>Client: Plaintext nếu toàn bộ kiểm tra đạt
~~~

### Quy tắc quan trọng

1. **Authorization trước Unwrap:** xác minh user/workload có quyền với **record thật**, không dựa vào `keyId` do client gửi.
2. **Đúng version:** ciphertext cũ phải tham chiếu KEK version đã bảo vệ DEK, hoặc dùng blob/format mà provider có thể định tuyến an toàn.
3. **Validate metadata:** algorithm identifier, length, nonce, tag, key reference, tenant và record context phải hợp lệ.
4. **Kiểm tra AEAD tag:** mọi lỗi xác thực phải từ chối trả plaintext; không dùng chế độ decrypt không xác thực.
5. **Không lộ key/plaintext trong lỗi:** không echo wrapped key, raw DEK, KEK, PIN hay stack trace nhạy cảm cho client.
6. **Không dùng key đã revoke:** trạng thái trong KMS/HSM và policy ứng dụng phải được kiểm tra gần lúc dùng, tránh stale cache/TOCTOU.

**Nếu một bên có raw KEK và bản wrapped DEK, KMS IAM không còn ngăn họ unwrap ngoại tuyến.** Vì vậy KEK phải được bảo vệ ở tầng vật liệu, không chỉ ở tầng API.

## 9. Metadata ciphertext và binding đúng ngữ cảnh

Một bản ghi envelope encryption cần **đủ thông tin để giải mã sau này** nhưng không tiết lộ secret. Ví dụ JSON minh họa:

~~~json
{
  "formatVersion": 2,
  "tenantId": "tenant-42",
  "recordId": "invoice-0081",
  "dataAlgorithm": "AES-256-GCM",
  "dataKeyScope": "PER_RECORD",
  "dekMaterial": "NOT_STORED_IN_PLAINTEXT",
  "nonceB64": "<base64-of-12-byte-nonce>",
  "ciphertextAndTagB64": "<base64-of-aead-output>",
  "wrappingAlgorithm": "KMS_PROVIDER_BLOB",
  "kekKeyId": "billing-kek",
  "kekVersion": "v3",
  "wrappedDekB64": "<base64-of-wrapped-dek>",
  "contextVersion": 1,
  "aadFields": ["tenantId", "recordId", "formatVersion"]
}
~~~

**Không tự dùng cấu trúc trên làm định dạng production.** Đây là schema khái niệm; `KMS_PROVIDER_BLOB` là giá trị mô tả, không phải tên thuật toán chuẩn. Các chuỗi trong dấu `<...>` là placeholder, không phải byte ciphertext hợp lệ.

### 9.1. AAD là gì?

**AAD (Additional Authenticated Data)** là dữ liệu được xác thực cùng bản mã trong AEAD nhưng **không nhất thiết được mã hóa**. Có thể sử dụng **tenant ID, record ID, format version và purpose** để ràng buộc ciphertext với ngữ cảnh.

Ví dụ, nếu `tenantId` nằm trong AAD, việc đổi metadata từ tenant A sang tenant B nhưng giữ nguyên ciphertext/tag sẽ khiến xác thực AEAD thất bại **nếu ứng dụng xây dựng AAD một cách nhất quán và lấy nguồn danh tính đáng tin**.

### 9.2. Canonical serialization

Không tự nối `tenantId + recordId` nếu các trường có thể tạo chuỗi nhập nhằng. Có thể dùng:

- Định dạng nhị phân **length-prefixed**.
- Schema version cố định, encoding UTF-8 nhất quán.
- Canonical encoding có quy tắc rõ cho thứ tự trường, `null`, Unicode và số.
- AAD được tái lập chính xác giữa mã hóa và giải mã.

**AAD không thay authorization.** Một client không có quyền tenant B vẫn có thể gửi metadata hoàn chỉnh của B; ứng dụng phải kiểm tra **principal → tenant/resource** độc lập.

### 9.3. Binding ở lớp KEK

AES-KW cơ bản không hỗ trợ AAD kiểu AEAD; không tự suy rằng `wrappedDek` được gắn chặt với tenant. Nếu cần binding ngay tại **KMS wrap/unwrap**, dùng **encryption context/authenticated metadata** khi nhà cung cấp hỗ trợ và **enforce cùng context** ở chiều giải mã, hoặc chọn định dạng/protocol wrapping phù hợp.

Đồng thời, ciphertext dữ liệu cần AEAD tag/AAD riêng; không nên tin rằng chỉ xác thực wrapped DEK là đủ bảo vệ toàn bộ bản ghi.

## 10. Java 17: AES Key Wrap cho DEK và AES-GCM cho dữ liệu

Ví dụ này minh họa **hai lớp mật mã** bằng JCA/JCE của Java 17:

- `AESWrap` (AES-KW, theo cách provider hỗ trợ) dùng **KEK AES-256** để wrap/unwrap **DEK AES-256**.
- `AES/GCM/NoPadding` dùng **DEK** để mã hóa một thông điệp với nonce ngẫu nhiên 96 bit và authentication tag 128 bit.
- **AAD** gắn ciphertext với tenant/record và format version.
- Không in raw key/plaintext ra log; kiểm thử kiểm tra bản mã bị sửa phải từ chối giải mã.

**Chỉ dùng cho học tập/thử nghiệm cục bộ.** KEK được sinh ngay trong JVM để minh họa API, **không đáp ứng yêu cầu KEK production phải ở KMS/HSM và không xuất được**. Ở production phải thay lớp wrapping bằng provider/KMS đã được phê duyệt, IAM, key version, audit và kiểm soát nonce ở quy mô thực.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class EnvelopeKekDemo {
    static final SecureRandom RNG = new SecureRandom();
    static final int GCM_TAG_BITS = 128;
    static final int NONCE_BYTES = 12;

    record Payload(
            String kekVersion,
            byte[] wrappedDek,
            byte[] nonce,
            byte[] ciphertextAndTag) {}

    static SecretKey newAes256Key() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static byte[] aadFor(String tenantId, String recordId) {
        // Ví dụ cố định. Production: encode length-prefixed/canonical,
        // không cho untrusted input tạo ký tự phân cách nhập nhằng.
        String context = "format=1\\ntenant=" + tenantId
                + "\\nrecord=" + recordId;
        return context.getBytes(StandardCharsets.UTF_8);
    }

    static Payload encrypt(
            byte[] plaintext, SecretKey kek, String kekVersion,
            String tenantId, String recordId) throws Exception {
        SecretKey dek = newAes256Key();

        // AES-KW dành cho keying material.
        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.WRAP_MODE, kek);
        byte[] wrappedDek = wrapper.wrap(dek);

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, nonce));
        cipher.updateAAD(aadFor(tenantId, recordId));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        // Không ghi raw DEK/KEK vào payload.
        return new Payload(
                kekVersion, wrappedDek, nonce, ciphertextAndTag);
    }

    static byte[] decrypt(
            Payload payload, SecretKey kek, String expectedKekVersion,
            String tenantId, String recordId) throws Exception {
        if (payload == null || kek == null || expectedKekVersion == null
                || !expectedKekVersion.equals(payload.kekVersion())
                || payload.nonce() == null
                || payload.nonce().length != NONCE_BYTES
                || payload.wrappedDek() == null
                || payload.wrappedDek().length == 0
                || payload.ciphertextAndTag() == null
                || payload.ciphertextAndTag().length < 16) {
            throw new IllegalArgumentException("Invalid envelope metadata");
        }

        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.UNWRAP_MODE, kek);
        SecretKey dek = (SecretKey) wrapper.unwrap(
                payload.wrappedDek(), "AES", Cipher.SECRET_KEY);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, payload.nonce()));
        cipher.updateAAD(aadFor(tenantId, recordId));
        return cipher.doFinal(payload.ciphertextAndTag());
    }

    public static void main(String[] args) throws Exception {
        SecretKey kek = newAes256Key(); // DEMO ONLY: production dùng KMS
        byte[] data = "Invoice record for tenant-42"
                .getBytes(StandardCharsets.UTF_8);
        Payload payload = encrypt(
                data, kek, "kek-v3", "tenant-42", "invoice-0081");

        byte[] recovered = decrypt(
                payload, kek, "kek-v3", "tenant-42", "invoice-0081");
        if (!Arrays.equals(data, recovered)) {
            throw new AssertionError("Decrypt mismatch");
        }

        // Sửa ngữ cảnh record, giữ nguyên blob -> AEAD từ chối.
        boolean contextRejected = false;
        try {
            decrypt(
                    payload, kek, "kek-v3",
                    "tenant-42", "another-record");
        } catch (AEADBadTagException expected) {
            contextRejected = true;
        }
        if (!contextRejected) {
            throw new AssertionError("AAD tampering was accepted");
        }

        // Không in raw key, DEK, plaintext, ciphertext hay PIN.
        System.out.println("KEK wrapping + AEAD verification: PASS");
        System.out.println("Wrapped DEK bytes: "
                + payload.wrappedDek().length);
    }
}
~~~

### 10.1. Kết quả và điều kiện tương thích

**`Cipher.getInstance("AESWrap")`** là tên transformation được các provider JCA phổ biến hỗ trợ, nhưng không nên giả định **mọi HSM/JDK/provider** hỗ trợ giống nhau. Kiểm tra thuật toán, key sizes, cơ chế wrapping và điều kiện integrity trong môi trường triển khai. Nếu provider không hỗ trợ, **không fallback ngầm sang AES/ECB**.

**`Cipher.WRAP_MODE`** khác **`ENCRYPT_MODE`**: wrap key trả về dạng mã hóa của đối tượng khóa phù hợp; unwrap trả `Key` theo algorithm/type đã chỉ định. Nếu wrapped blob đã bị sửa, lỗi xác minh integrity có thể được provider báo qua ngoại lệ phù hợp.

**`GCMParameterSpec(128, nonce)`** yêu cầu tag 128 bit, nonce 12 byte. Trong demo nonce được sinh ngẫu nhiên mỗi lần mã hóa với **DEK mới**. Production cần chiến lược nonce và giới hạn lượng bản mã dưới cùng DEK, nhất là khi ứng dụng có nhiều node hoặc phục hồi VM snapshot.

**Demo chỉ dùng dữ liệu tenant/record cố định**. Nếu xây AAD với input tùy ý, cần canonical encoding thay cho nối chuỗi với ký tự `\\n`; nếu không, giá trị chứa newline có thể tạo nhập nhằng.

### 10.2. Những gì đoạn code chưa giải quyết

1. **Không có KMS/HSM hoặc non-extractability:** KEK được tạo trong JVM và có thể bị lấy nếu tiến trình bị chiếm.
2. **Không có IAM, tenant authorization:** `tenantId` chỉ là chuỗi, không chứng minh caller có quyền với bản ghi.
3. **Không có persistent storage, backup và key inventory:** `kekVersion` không phải key reference có chứng nhận từ provider.
4. **Không có bộ kiểm tra đầu vào có giới hạn tài nguyên đầy đủ:** production phải áp size limits cho blob, nonce, AAD và metadata.
5. **Không giải quyết zeroization đầy đủ:** `SecretKey` và provider có thể giữ key bytes trong memory; Java không đảm bảo xóa mọi bản sao. Với production, hạn chế thời gian sống và dùng KMS/HSM phù hợp.
6. **Không mô phỏng key compromise/rotation:** rewrap, re-encrypt và revoke là quy trình riêng.
7. **`Payload` chứa mảng byte mutable:** record demo chưa có defensive copying; production phải kiểm soát mutation, kích thước dữ liệu và cách serialize/deserialize an toàn.

**Bài học quan trọng:** chỉ cần một ứng dụng có raw KEK trong RAM để thực hiện unwrap, bạn đã mở rộng vùng lộ KEK. Mô hình production thường đặt **KEK ngoài application process**, rồi cho ứng dụng nhận **DEK ngắn hạn** khi kiến trúc yêu cầu.

## 11. KEK trong KMS/HSM: chìa khóa nằm ở đâu?

Trong hệ thống production, một **KEK dài hạn** thường phù hợp để quản lý bằng **KMS hoặc HSM** bởi nó có thể bảo vệ nhiều DEK. Tuy nhiên, từ “KMS-backed” hay “HSM-backed” không tự mô tả mọi đường dữ liệu và quyền.

### 11.1. Mô hình phổ biến

| Thiết kế | KEK được giữ ở đâu? | DEK ở đâu khi mã hóa? | Điều cần kiểm tra |
| --- | --- | --- | --- |
| **Managed KMS wrapping key** | Trong dịch vụ/provider theo key class | Có thể có DEK bản rõ tạm ở ứng dụng | IAM, encryption context, key state, quota, provenance |
| **HSM key object wrapping** | Trong HSM token/partition | Có thể ở HSM hoặc application tùy workflow | PKCS#11 attributes, non-extractability, backup |
| **Local software KEK** | Trong process/secret store/file | Trong cùng process hoặc service | Threat model host, key export, memory/dump, rotation |
| **Derived KEK từ root secret** | Tùy nơi giữ root và KDF | DEK ở nơi được thiết kế | Context separation, root compromise, key version |
| **Asymmetric key transport** | Private unwrap key trong KMS/HSM hoặc recipient | Public wrap key có thể phân phối | Public-key binding, private key usage, OAEP params |

### 11.2. Non-extractable không chặn API misuse

Một KEK không thể xuất raw bytes vẫn có thể bị **lạm dụng qua API `Unwrap/Decrypt`** nếu attacker chiếm principal hợp lệ. Khi đó attacker có thể lấy nhiều DEK theo thời gian, mặc dù không bao giờ thấy KEK.

Do đó cần **IAM least privilege, tenant/resource authorization, chỉ dùng operations cần thiết, rate limiting, monitoring và khả năng revoke credential nhanh**. Phải phân biệt sự cố **raw KEK bị lộ** với sự cố **KMS API bị lạm dụng**; chúng có thể dẫn tới cùng việc lộ dữ liệu nhưng biện pháp khắc phục khác.

### 11.3. KEK import và BYOK

Một KEK sinh ở môi trường ngoài rồi import vào KMS là **imported key**, không phải **generated inside KMS/HSM**, dù sau đó được lưu trong vùng được quản lý. Cần ghi **origin, key type, wrapping/import protocol, bản sao nguồn, export policy và audit evidence**.

Nếu chính sách đòi hỏi KEK được sinh bên trong HSM và không xuất được, một key từng ở file PEM/hex hoặc RAM application không thỏa điều kiện nguồn sinh chỉ bằng việc import sau đó.

## 12. Key inventory cho KEK và wrapped DEK

**Một KEK không có key inventory đáng tin** sẽ khiến rotation, recovery và revocation trở thành thao tác đoán. Inventory nên phân biệt **logical KEK** với **mỗi version key material**.

### 12.1. Trường nên lưu

| Nhóm | Ví dụ | Mục đích |
| --- | --- | --- |
| Định danh | `keyId`, `keyVersion`, `alias` | Đúng key material khi wrap/unwrap |
| Phạm vi | `ownerTeam`, `tenantScope`, `environment` | Giảm cross-tenant misuse |
| Thuật toán | `algorithm`, `wrappingMechanism`, `keyUsage` | Không dùng KEK sai purpose |
| Nơi giữ | `providerKeyRef`, `generationBoundary`, `exportPolicy` | Xác minh KMS/HSM controls |
| Thời gian | `createdAt`, `activationAt`, `newUseUntil`, `oldUseUntil` | Quản lý cryptoperiod |
| State | `lifecycleState`, `primaryForNewUse`, `revokedAt` | Ngừng dùng mới và phản ứng sự cố |
| Governance | `policyRevision`, `approvalRef`, `custodian` | Truy vết quyết định |
| Phụ thuộc | `wrappedDekCount`, `dependentServices`, `backupRefs` | Rewrap, restore, destroy |
| Audit | `lastUsedAt`, `operationId`, `providerAuditRef` | Điều tra và phát hiện sai lệch |

### 12.2. Ví dụ record quản trị KEK

~~~json
{
  "keyId": "billing-kek",
  "keyVersion": "v3",
  "keyClass": "KEY_ENCRYPTION_KEY",
  "algorithm": "AES-256",
  "wrappingPurpose": ["WRAP", "UNWRAP"],
  "ownerTeam": "billing-security",
  "tenantScope": "production/billing",
  "providerKeyRef": "kms://example/billing-kek/v3",
  "generationBoundary": "MANAGED_KMS_HSM",
  "exportPolicy": "NON_EXTRACTABLE",
  "lifecycleState": "PRE_ACTIVE",
  "primaryForNewUse": false,
  "createdAt": "2026-11-28T08:00:00Z",
  "activationAt": "2026-12-01T00:00:00Z",
  "newUseUntil": "2027-03-01T00:00:00Z",
  "oldUseUntil": "2027-09-01T00:00:00Z",
  "policyRevision": 18,
  "approvalRef": "KEY-ROTATION-281",
  "providerAuditRef": "kms-operation-1027"
}
~~~

Ví dụ là **schema minh họa**, không phải API của nhà cung cấp cụ thể. `kms://...` là placeholder. Những thuộc tính như `MANAGED_KMS_HSM` hay `NON_EXTRACTABLE` chỉ nên ghi là **đã xác minh** nếu có bằng chứng về provider và đúng key class/operation.

**Mốc thời gian nhất quán:** `activationAt` ở tương lai so với `createdAt`, do đó record mẫu là **`PRE_ACTIVE`** và chưa phải primary. Một khóa được tạo không tự được phép wrap dữ liệu mới.

## 13. Cryptoperiod: KEK được phép wrap và unwrap đến khi nào?

Khóa có thể **hết thời hạn tạo bảo vệ mới** nhưng vẫn cần được dùng để mở dữ liệu cũ. Đây là lý do phân biệt:

- **Originator-usage period:** khoảng KEK được phép **Wrap/Encrypt DEK mới**.
- **Recipient-usage period:** khoảng được phép **Unwrap/Decrypt DEK đã tồn tại**, theo policy.

~~~text
Time UTC -------------------------------------------------------------------->

Created       Activation          Stop new Wrap          Stop old Unwrap
   |              |                     |                        |
   v              v                     v                        v
 Pre-active    ACTIVE: WRAP NEW     RETIRED: UNWRAP OLD        CLOSED
               + UNWRAP OLD        (chỉ nếu policy cho phép)
                  |<-- new-use -->|<----- old-use extension ----->|
~~~

### 13.1. Ranh giới thời gian

Một quy ước nhất quán là khoảng nửa mở:

\[
\text{wrapNewAllowed} \iff activationAt \le now < newUseUntil
\]

\[
\text{unwrapOldAllowed} \iff activationAt \le now < oldUseUntil
\]

Nhưng hai điều kiện trên **chưa đủ**; phải thêm **state, permission, purpose, tenant, policy revision và trạng thái compromise/revocation**. Tại đúng `newUseUntil`, không được tiếp tục wrap DEK mới bằng version đó.

**Không giả định KMS có chế độ “disabled nhưng vẫn unwrap old”.** Một số provider chặn **mọi operation** khi key bị disabled. Cần thiết kế key lifecycle và kế hoạch migration dựa trên API thực tế.

### 13.2. KEK rotation và key version

Một logical key như `billing-kek` có thể có `v2` và `v3`. Version `v3` được chọn cho wrap mới, còn `v2` được phép unwrap DEK cũ trong giai đoạn di chuyển. **Alias `current`** có thể trỏ tới `v3`, nhưng wrapped DEK cũ phải tham chiếu version đúng hoặc ciphertext blob chứa metadata để provider định tuyến an toàn.

**Đổi alias không đồng nghĩa đổi key material.** Rotation cần vật liệu khóa mới, policy mới nếu cần và kiểm tra backup; khi compromise, có thể cần hành động mạnh hơn.

## 14. Rotation KEK: rewrap khác re-encrypt

### 14.1. Rotation bình thường

Khi KEK sắp hết **originator-usage period** mà không có dấu hiệu key material bị lộ:

1. Tạo **KEK mới** bằng CSPRNG/KMS/HSM đúng policy, có key ID/version riêng.
2. Đăng ký vào inventory và kiểm tra algorithm, owner, purpose, IAM, backup/DR.
3. Kích hoạt KEK mới, chuyển **primary for new wrap**.
4. Ngừng dùng KEK cũ cho **wrap DEK mới**, nhưng giữ phương án unwrap dữ liệu cũ theo policy.
5. **Rewrap** wrapped DEK cũ sang KEK mới qua kênh tin cậy.
6. Cập nhật key version/reference và kiểm tra consistency của payload, database, backup.
7. Kiểm tra restore, đóng quyền cũ rồi hủy KEK cũ khi hết phụ thuộc theo retention.

### 14.2. Rewrap là gì?

**Rewrap** thay lớp bảo vệ KEK của cùng DEK:

~~~text
Trước:
  ciphertext = AEAD_Encrypt(DEK_v1, data)
  wrappedDek = Wrap(KEK_v2, DEK_v1)

Sau:
  ciphertext = AEAD_Encrypt(DEK_v1, data)  # giữ nguyên
  wrappedDek = Wrap(KEK_v3, DEK_v1)       # lớp bọc mới
~~~

Điều này có thể tránh mã hóa lại hàng terabyte dữ liệu khi **DEK vẫn được tin cậy**. Tuy nhiên, ứng dụng vẫn cần kiểm tra transaction, auth, tính toàn vẹn và bảo đảm không mất wrapped DEK do migration lỗi.

### 14.3. Re-encrypt là gì?

**Re-encrypt** thay **DEK** và tạo ciphertext mới:

~~~text
Trước:
  ciphertext_v1 = AEAD_Encrypt(DEK_v1, data, nonce_v1)

Sau:
  DEK_v2 <- CSPRNG/KMS
  ciphertext_v2 = AEAD_Encrypt(DEK_v2, data, nonce_v2)
  wrappedDek_v2 = Wrap(KEK_v3, DEK_v2)
~~~

Khi **DEK bị lộ hoặc nghi yếu**, rewrap cùng DEK không giải quyết vấn đề bí mật. Phải đánh giá DEK mới và re-encrypt dữ liệu có liên quan. Dữ liệu mà attacker đã đọc trước đó **không thể lấy lại tính bí mật** chỉ bằng rotation.

### 14.4. Sơ đồ migration có kiểm soát

~~~mermaid
flowchart TD
    A[KEK cũ sắp hết new-use period] --> B[Key owner duyệt kế hoạch rotation]
    B --> C[Sinh KEK mới trong KMS/HSM]
    C --> D[Kích hoạt primary mới cho Wrap]
    D --> E[Liệt kê wrapped DEK + backups]
    E --> F{Có bằng chứng DEK/KEK compromise?}
    F -->|Không| G[Rewrap DEK dưới KEK mới]
    F -->|Có / chưa loại trừ rủi ro| H[Đánh giá thay DEK + re-encrypt]
    G --> I[Update key version / kiểm thử decrypt]
    H --> I
    I --> J[Kiểm tra restore, tenant scope, audit]
    J --> K{Còn phụ thuộc KEK cũ?}
    K -->|Có| E
    K -->|Không| L[Retire/Destroy theo retention]
~~~

**Cẩn trọng với API re-encrypt của KMS:** có provider hỗ trợ rewrap từ ciphertext blob cũ sang blob mới **không đưa plaintext DEK ra ngoài provider**, có provider không có thao tác đó. Không gắn điều này thành giả định chung của mọi hệ thống.

## 15. Khi KEK bị lộ: hiểu đúng phạm vi sự cố

Đây là một trong những điểm quan trọng nhất của quản lý khóa. Một KEK bị compromise có thể gây rủi ro với **tất cả DEK được bọc bằng nó** mà attacker có thể thu thập, nhưng mức thiệt hại thực tế phụ thuộc vào **bản sao wrapped DEK, quyền API, dữ liệu mã hóa và thời điểm lộ**.

### 15.1. Các kịch bản khác nhau

| Kịch bản | Attacker có gì? | Hệ quả cần đánh giá | Hành động thường xem xét |
| --- | --- | --- | --- |
| **Lộ raw KEK** | Byte KEK và có thể wrapped DEK | Có thể unwrap ngoại tuyến những blob thu thập được | Containment, thay KEK; đánh giá DEK mới/re-encrypt |
| **Lộ KEK + wrapped DEK cũ** | KEK và các bản wrapped DEK trước migration | Rewrap bản hiện tại **không thu hồi** bản sao cũ | Đánh giá dữ liệu/ciphertext đã thu thập, thay DEK khi cần |
| **KMS API bị lạm dụng** | Credential gọi `Unwrap`, không nhất thiết raw KEK | Có thể lấy DEK qua API theo quyền tại thời điểm tấn công | Revoke credential, khóa quyền, tra audit, đánh giá DEK đã bị trả |
| **DEK bị lộ** | Raw DEK cho một tập ciphertext | Có thể giải mã dữ liệu dưới DEK đó | Thay DEK và re-encrypt, xử lý dữ liệu đã lộ |
| **Wrapped DEK bị sửa** | Quyền sửa blob hoặc metadata | Unwrap/tag có thể lỗi; có nguy cơ DoS hoặc confusion | Integrity validation, AAD/context binding, auth |
| **Một tenant bị chiếm** | Quyền hoặc data của tenant đó | Có thể lan sang tenant khác nếu KEK/IAM dùng chung sai | Tenant isolation, policy/role review, cân nhắc KEK per tenant |

### 15.2. Vì sao rewrap không xóa bản sao của attacker?

Giả sử attacker có:

~~~text
oldKEK = KEK_v2
oldWrappedDEK = Wrap(KEK_v2, DEK_A)
oldCiphertext = AEAD_Encrypt(DEK_A, message)
~~~

Sau sự cố, ứng dụng tạo `KEK_v3` và lưu `Wrap(KEK_v3, DEK_A)`. **Bản `oldWrappedDEK` mà attacker đã lấy vẫn tồn tại trong tay họ**. Nếu họ có `KEK_v2`, họ vẫn khôi phục `DEK_A` và giải mã `oldCiphertext`. Không có API revoke metadata nào khiến đối thủ quên những byte này.

Do đó, khi KEK bị lộ cùng bản wrapped DEK, cần **đánh giá DEK và dữ liệu có thể đã mất bí mật**; khi rủi ro yêu cầu, thay DEK, re-encrypt và xác minh bản sao/backup. **Rotation không xóa dữ liệu đã bị sao chép/đọc trước đó**.

### 15.3. Quy trình containment

1. Xác định **key ID/version**, owner, tenant/service và nơi key material từng tồn tại.
2. Chặn quyền `Wrap/Unwrap` nguy hiểm, thu hồi principal/session bị chiếm và cô lập đường API.
3. Phân biệt **raw KEK export** với **API misuse** và **chỉ lộ metadata/ciphertext blob**.
4. Tra KMS/HSM audit: operation, principal, key version, ciphertext context, thời điểm.
5. Tạo KEK/DEK mới theo mức độ cần thiết, không dùng lại material bị lộ dưới alias khác.
6. Đánh giá ciphertext, wrapped DEK, backup và các bản sao attacker có thể đã thu thập.
7. Thực hiện migration, negative tests, theo dõi stale cache và kết thúc sự cố có bằng chứng.

**Không xóa vĩnh viễn KEK cũ trước khi xác định dữ liệu hợp lệ còn phụ thuộc**, trừ khi tổ chức chủ động chấp nhận crypto-erasure theo quy trình và mô hình rủi ro phù hợp.

## 16. IAM, Key owner và separation of duties

KEK cấp cao là một tài nguyên nhạy cảm, nên **quyền sử dụng** và **quyền quản trị** phải được tách.

| Vai trò | Quyền/việc nên có | Không nên mặc nhiên có |
| --- | --- | --- |
| **Key owner** | Định nghĩa purpose, key policy, cryptoperiod, rotation/revoke | Raw KEK, mọi quyền unwrap/delete |
| **KMS/HSM custodian** | Tạo/backup/rotate theo approval | Quyền đọc dữ liệu tenant hoặc ký giao dịch nghiệp vụ |
| **Data service** | Wrap/unwrap được giới hạn theo workload, tenant và purpose | Export KEK, thay root key policy |
| **Security approver** | Đánh giá risk, approval nhạy cảm, incident handling | Tự xóa audit hoặc bypass IAM |
| **Data owner** | Retention, data classification, quyền truy cập dữ liệu | Điều khiển private/secret key ngoài policy |
| **Auditor** | Đọc log/metadata và đối chiếu compliance | Decrypt/Unwrap dữ liệu không cần thiết |

### 16.1. IAM tại KMS/HSM khác quyền truy cập dữ liệu

Một application principal có quyền `Unwrap` vẫn **không được giải mã mọi ciphertext** nếu không có quyền nghiệp vụ đối với record. KMS có thể không biết hệ thống phân quyền của ứng dụng. Phải áp **least privilege, authorization theo tenant/resource và key usage** ở cả hai lớp.

### 16.2. Quorum approval

Những hành động như **export/import KEK gốc, thay policy cho phép key extraction, khôi phục root material hoặc hủy KEK đang bảo vệ dữ liệu quan trọng** có thể cần **M-of-N approval**, ví dụ Key owner và Security cùng đồng ý, kèm xác nhận backup/retention.

**Quorum không phải chỉ hai click trong UI**. KMS/HSM hoặc execution broker phải **chặn operation thực tế** khi thiếu approval, và bảo vệ cả quyền sửa threshold/approver list. Đối với **containment khẩn cấp**, có thể có đường revoke/disable được ủy quyền riêng để không chờ quorum phá hủy dữ liệu.

### 16.3. Break-glass và thời gian phản ứng

Nếu attacker đang gọi `Unwrap` trái phép, runbook cần cho phép chặn principal hoặc đường API **ngay**, ghi audit và hậu kiểm. Việc **destroy root KEK** thường là quyết định khác: có thể gây mất dữ liệu nên cần dependency preflight và phê duyệt thích hợp.

## 17. Backup, high availability và crypto-erasure

KEK vừa phải được bảo vệ khỏi lộ, vừa phải **không bị mất ngoài ý muốn** nếu dữ liệu/backup còn cần nó.

### 17.1. Backup KEK an toàn

Một HSM/KMS có thể hỗ trợ **replication, backup, secure transfer hoặc disaster recovery** theo tính năng provider. Không mặc định key non-extractable đồng nghĩa “không backup được”; cũng không dùng việc có backup để suy ra raw KEK có thể được export.

Cần kiểm tra:

- Hình thức backup có **protected/wrapped key material** theo cơ chế chính thức không?
- Ai giữ **recovery credentials/root of trust** và có dual control khi cần?
- Backup/restore có giữ **key version, attributes, permissions và audit traceability** không?
- Bản copy có nằm trong vùng dữ liệu/region được chấp thuận và tuân thủ retention?
- Có **restore rehearsal** để chứng minh ciphertext cũ còn decrypt được không?

### 17.2. Availability và hiệu năng

Nếu mọi request decrypt phải gọi KMS để unwrap DEK, hệ thống chịu **latency, quota, network và availability** của KMS. Có thể cân nhắc **DEK caching** ngắn hạn trong trusted memory nếu threat model cho phép, nhưng caching tăng thời gian DEK tồn tại ở application, kéo dài ảnh hưởng khi memory bị lộ và làm khó revocation ngay lập tức.

Không có cấu hình cache “an toàn tuyệt đối” cho mọi môi trường. Chọn TTL, scope, zeroization best-effort, metrics và key version theo chính sách.

### 17.3. Crypto-erasure là gì?

**Cryptographic erasure** là làm mất khả năng giải mã dữ liệu bằng cách loại bỏ khóa cần thiết, **với giả định không còn bản sao khóa có thể khôi phục và dữ liệu đã được bảo vệ đúng thiết kế**.

Hủy KEK có thể khiến các wrapped DEK không thể mở, nhưng không thể đảm bảo crypto-erasure nếu:

- KEK hoặc DEK đã có bản copy trong backup, RAM dump hoặc attacker.
- Có phiên bản DEK khác còn ở dạng rõ.
- Dữ liệu được mã hóa bằng một key/version khác vẫn tồn tại.
- HSM/KMS chỉ bị `Disabled` chứ key material chưa bị hủy.

**Đừng nhầm revoke, disable, retire và destroy**. Mỗi thao tác có semantics khác nhau và rủi ro recovery khác nhau.

## 18. Monitoring và audit cho KEK

Một lớp KEK được quản lý tốt cần biết **ai đang wrap/unwrap, dùng đúng version không, còn dữ liệu phụ thuộc không và có thao tác bất thường không**.

### 18.1. Audit event minh họa

~~~json
{
  "eventType": "KEK_UNWRAP",
  "keyId": "billing-kek",
  "keyVersion": "v3",
  "principal": "billing-data-service",
  "tenantScope": "production/billing",
  "resourceRef": "invoice-0081",
  "operationId": "unwrap-20261128-001",
  "policyRevision": 18,
  "providerKeyRef": "kms://example/billing-kek/v3",
  "result": "SUCCESS",
  "recordedAt": "2026-11-28T10:00:00Z"
}
~~~

Đây là event minh họa, không phải log chuẩn của một cloud provider. Không ghi raw KEK/DEK, plaintext, password, token hoặc bản wrapped DEK khi không cần thiết. Cả key ID, tenant metadata và access pattern cũng có thể nhạy cảm, cần phân quyền đọc audit.

### 18.2. Các cảnh báo hữu ích

| Chỉ số | Tại sao theo dõi? |
| --- | --- |
| **Unwrap volume spike** | Có thể bị lạm dụng API hoặc xuất lượng lớn DEK |
| **Unexpected principal** | Workload không được cấp quyền nhưng gọi KMS |
| **Cross-tenant key usage** | Dùng KEK không đúng scope dữ liệu |
| **Old KEK used for new wrap** | Node chưa chuyển primary hoặc policy cache stale |
| **Revoked KEK accessed** | Có đường bypass / quyền chưa đồng bộ |
| **Key version mismatch** | Wrapped DEK trỏ sai key version |
| **Wrapping integrity failure** | Blob lỗi, bị sửa hoặc key/context không đúng |
| **KMS throttling/latency** | Ảnh hưởng availability, có thể kích hoạt retry storm |
| **Rewrap backlog** | Còn nhiều DEK/backup phụ thuộc KEK cũ |
| **Missing provider audit** | Khó đối chiếu người và key thực thi |
| **Backup restore failure** | Rủi ro mất dữ liệu khi retire/destroy |
| **Policy revision drift** | IAM/alias/key state không nhất quán giữa node |

### 18.3. Kiểm thử quyền bị từ chối

Nên có negative tests bằng tài khoản và key thử nghiệm:

- Principal không có `Unwrap` phải bị KMS/HSM từ chối.
- Tenant A không đọc được record thuộc tenant B dù cùng dịch vụ backend.
- Key version bị retire không còn được **wrap dữ liệu mới**.
- Key revoked/disabled không được xử lý trái policy.
- Wrapped DEK bị sửa hoặc AEAD tag sai phải từ chối, không trả plaintext.
- Đường API bypass approval/quorum phải bị chặn.
- KMS unavailable không được fallback sang KEK raw trong file để “chữa cháy”.
- Alias `current` không khiến bản ghi cũ unwrap sai version.

## 19. Tình huống thực tế: thay KEK của hệ thống lưu trữ đa tenant

Một công ty SaaS lưu chứng từ của hàng nghìn tenant. Mỗi chứng từ được mã hóa bằng **DEK riêng**, các DEK được bọc bởi **KEK theo tenant** trong KMS. Một số tenant có lịch sử dữ liệu 7 năm và backup lưu ở vùng khác.

### Giai đoạn A — Trạng thái hiện tại

Key inventory ghi:

~~~text
tenant-A / billing-kek / v2
  state: ACTIVE
  role: WRAP_NEW + UNWRAP_OLD
  wrapped DEKs: 2,400,000
  backups: region-1, region-2
  owner: billing-security

tenant-B / billing-kek / v4
  state: ACTIVE
  role: WRAP_NEW + UNWRAP_OLD
  wrapped DEKs: 900,000
  backups: region-2
~~~

Hai dòng chỉ minh họa số lượng và phạm vi. **Một logical key alias giống nhau giữa tenant không được coi là cùng vật liệu** nếu key references tách biệt.

### Giai đoạn B — Rotation bình thường tenant A

Owner chuẩn bị KEK `v3` cho tenant A trong KMS và bảo đảm **key generation, IAM, rotation approval, activation time, provider reference, backup recovery** đúng policy. Khi `v3` Active, dữ liệu mới được wrap dưới `v3`; `v2` không còn là primary cho wrap mới.

Một job **rewrap** các DEK cũ từ `v2` sang `v3`, kiểm tra trạng thái từng record bằng transaction/version. Nếu worker xử lý lại một job sau timeout, nó phải nhận biết **blob đã được rewrap** thay vì bọc lặp vô hạn hoặc ghi đè metadata sai.

### Giai đoạn C — Backup và dữ liệu đã mã hóa

Không chỉ quét database chính. Những backup và snapshot còn chứa wrapped DEK dưới `v2` cần được di chuyển hoặc bảo đảm policy cho phép phục hồi, theo retention. Sau migration, thực hiện **restore rehearsal**, kiểm tra record bất kỳ của tenant A và xác nhận blob/AAD đúng.

Chỉ khi không còn phụ thuộc hoặc có quyết định crypto-erasure hợp lệ mới retire/destroy `v2` theo quy trình. Không xóa KEK chỉ vì tỷ lệ rewrap ở database chính báo `100%`.

### Giai đoạn D — Sự cố giả định

Sau này phát hiện principal có quyền unwrap tenant A bị chiếm trong một giờ. Security chặn credential/session, tra KMS audit xem **những DEK nào đã được unwrap hoặc có nguy cơ bị lộ**. Nếu attacker chỉ có quyền API nhưng chưa lấy raw KEK, rủi ro có thể tập trung vào những DEK bị truy xuất; nếu đã có **raw KEK cùng wrapped DEK**, phạm vi có thể rộng hơn.

Tổ chức quyết định nơi nào cần **thay DEK và re-encrypt**, nơi nào chỉ cần quyền/KEK rotation, đồng thời đánh giá dữ liệu đã bị lấy. **Đừng tuyên bố “đã rewrap nên dữ liệu không còn lộ”**.

### Giai đoạn E — Audit và cải tiến

Owner theo dõi **KEK version, thời điểm kích hoạt, rewrap backlog, lỗi restore, IAM drift và anomalous unwrap**. Đội vận hành cập nhật playbook để phân biệt compromise vật liệu KEK và compromise principal KMS.

**Bài học:** KEK tạo ra một tầng quản trị mạnh, nhưng khả năng bảo mật thật phụ thuộc vào **metadata đáng tin, phân quyền chặt, key separation, migration có kiểm chứng và xử lý sự cố không nhầm rewrap với re-encrypt**.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng một khóa AES vừa làm DEK vừa làm KEK cho mọi dữ liệu | Tăng phạm vi lộ, sai purpose | Tách KEK và DEK theo policy |
| Sinh KEK bằng `Random` hoặc timestamp | Khóa dễ đoán | CSPRNG/KMS/HSM |
| Hard-code KEK trong Git hoặc config | Attacker lấy key material | KMS/HSM, secret handling và IAM |
| Dùng AES-ECB để bọc DEK | Thiếu bảo vệ phù hợp và integrity | AES-KW/KWP hoặc KMS wrapping chuẩn |
| Dùng AES-GCM để wrap mà tái sử dụng nonce với cùng KEK | Có thể phá bảo mật | Nonce strategy/limits hoặc wrapping mechanism chuẩn |
| Coi AES-KW tự bind tenant/record | Blob bị dùng lại sai context | Authorization + context/AAD binding phù hợp |
| Cho client gửi `keyId` rồi unwrap tùy ý | KMS biến thành decrypt oracle | Authorization resource, tenant và allowed key mapping |
| Đổi alias `current` nhưng không lưu version | Không unwrap được bản ghi cũ | Key ID/version ổn định trên payload |
| Sinh KEK mới nhưng giữ nguyên vật liệu bị lộ | Compromise tiếp diễn | Key material mới và incident response |
| Rewrap DEK đã lộ mà không re-encrypt | Attacker vẫn có DEK | Thay DEK và ciphertext khi cần |
| Lộ KEK + wrapped DEK cũ rồi chỉ rewrap bản mới | Attacker giữ bản old wrapped key | Đánh giá dữ liệu đã lộ và thay DEK |
| Hủy KEK trước khi kiểm tra backup | Mất khả năng giải mã | Dependency inventory và restore test |
| Coi HSM non-extractable là không thể bị lạm dụng | Attacker gọi `Unwrap` qua API | IAM, quotas, application auth và audit |
| Tin mọi KMS disabled đều còn unwrap được dữ liệu cũ | Phục hồi thất bại | Kiểm tra semantics provider và retention |
| Log raw DEK/KEK hoặc plaintext làm evidence | Mở rộng sự cố lộ secret | Chỉ log metadata và key reference |
| Không kiểm tra AEAD tag | Trả plaintext bị sửa/giả | AEAD decrypt phải verify trước khi dùng |
| Không kiểm soát nonce dưới cùng DEK | AEAD có nguy cơ bị phá | Nonce uniqueness và usage limits |
| Sai tenant AAD hoặc metadata không canonical | Confusion hoặc xác thực sai | Format/version/canonical encoding |
| HSM timeout thì dùng KEK fallback trong process | Hạ cấp bảo mật | Fail-closed/DR đã phê duyệt |
| Coi mọi lỗi unwrap như key not found rồi thử key khác tùy ý | Confusion, oracle và tăng phạm vi lỗi | Error handling có kiểm soát, đúng key reference |

## 21. Checklist triển khai Key encryption key

- [ ] Đã xác định **KEK là wrapping key**, khác DEK dữ liệu và private signing key?
- [ ] KEK có **owner, tenant scope, purpose, generation policy, key version và cryptoperiod**?
- [ ] KEK được sinh bằng **CSPRNG** hoặc KMS/HSM, đúng exportability/security boundary?
- [ ] Có dùng **AES-KW/AES-KWP, approved AEAD wrap hoặc provider KMS wrap API**, không tự chế ECB/XOR?
- [ ] Nếu dùng AEAD để wrap, nonce uniqueness và AAD format được quản lý chặt?
- [ ] Nếu dùng AES-KW, đã hiểu **không có AAD tenant/record** theo cơ chế cơ bản?
- [ ] DEK đủ entropy, được tách theo purpose/tenant/object hoặc phạm vi được duyệt?
- [ ] AES-GCM/ChaCha20-Poly1305 mã hóa dữ liệu có **nonce, tag và usage limits** đúng?
- [ ] Encryption/decryption có kiểm tra **tenant/resource authorization** ngoài KMS IAM?
- [ ] Ciphertext lưu đúng **algorithm version, KEK key ID/version, wrapped DEK, nonce/tag và context**?
- [ ] AAD được xây từ **nguồn metadata đáng tin** và serialization nhất quán?
- [ ] KEK không xuất raw bytes vào file, environment, crash dump, log hoặc ticket?
- [ ] IAM tách `Wrap/Unwrap`, admin policy, delete và key generation theo least privilege?
- [ ] Hành động root KEK export/delete/recovery có quorum approval/SoD theo risk tier khi cần?
- [ ] Có kế hoạch **activation, rotate, retired/decrypt-old, revoke và destroy** theo API thực tế?
- [ ] Rotation phân biệt **rewrap DEK** và **DEK mới + re-encrypt**?
- [ ] Trước khi destroy đã kiểm kê **wrapped DEK, ciphertext, backup, snapshot và restore dependency**?
- [ ] Có runbook cho **raw KEK compromise**, **API abuse** và **DEK compromise** riêng?
- [ ] Có audit actual key ID/version, principal, operation, tenant, result mà không ghi secret?
- [ ] Đã test **wrong tenant, wrong key version, tampered wrapped DEK, wrong AAD, revoked key, no fallback**?
- [ ] Có HA/DR, backup/restore rehearsal, rate limit và alert khi unwrap tăng đột biến?
- [ ] Đã phân biệt **Disable, Retire, Revoke, Destroy và Crypto-erasure** trong chính sách?

## 22. Câu hỏi tự kiểm tra

**1. KEK khác DEK ở điểm nào?**  
DEK mã hóa dữ liệu nghiệp vụ; KEK được dùng để bảo vệ DEK hoặc keying material khác. Hai loại nên có key usage và vòng đời riêng.

**2. Vì sao envelope encryption thường dùng DEK riêng rồi wrap bằng KEK?**  
Nó tách bulk encryption khỏi quản trị khóa cấp cao, cho phép kiểm soát KEK trong KMS/HSM và hỗ trợ rotation lớp bọc khi DEK vẫn được tin cậy.

**3. AES-KW có tự xác thực tenant/record ID không?**  
Không. AES-KW cơ bản có kiểm tra integrity của wrapped key nhưng không có AAD ngữ cảnh như AEAD. Cần context/authorization ở tầng phù hợp.

**4. Khi nào nên dùng AES-KWP thay AES-KW?**  
Khi keying material cần wrap không đáp ứng yêu cầu kích thước của AES-KW dạng cơ bản và provider hỗ trợ cơ chế có padding phù hợp.

**5. Dữ liệu đã mã hóa bằng DEK cần kiểm tra gì ở chiều decrypt?**  
Quyền đọc resource/tenant, key/version, định dạng, AAD/nonce và **authentication tag** của AEAD trước khi trả plaintext.

**6. KEK bị lộ thì chỉ tạo KEK mới và rewrap DEK có đủ không?**  
Không mặc nhiên. Nếu attacker có KEK cũ và wrapped DEK cũ, họ có thể vẫn khôi phục DEK. Cần đánh giá DEK mới/re-encrypt và dữ liệu đã có thể bị lấy.

**7. Khi DEK bị lộ nhưng KEK vẫn an toàn, hành động phù hợp là gì?**  
Đánh giá thay DEK và re-encrypt dữ liệu liên quan. Chỉ rewrap cùng DEK không làm DEK bí mật trở lại.

**8. Một KEK non-extractable trong HSM có chắc chắn không bị lạm dụng?**  
Không. Attacker có thể chiếm credential được phép gọi `Unwrap` và lấy DEK qua API. Cần IAM và authorization nghiệp vụ.

**9. Có nên xóa KEK cũ ngay sau khi chuyển alias sang key mới không?**  
Không. Backup/ciphertext có thể còn wrapped DEK dưới version cũ; phải kiểm tra dependency, rewrap và restore theo retention.

**10. AAD có thay việc kiểm tra quyền truy cập tenant không?**  
Không. AAD xác thực ngữ cảnh của ciphertext nhưng không chứng minh caller có quyền đọc dữ liệu.

**11. Vì sao không nên sinh KEK trong JVM cho hệ thống yêu cầu HSM?**  
Key material đã tồn tại trong process/heap và có thể bị lấy qua dump hoặc host compromise. Non-extractability phải được thực thi trong boundary được duyệt.

**12. Nếu KMS gặp lỗi, có thể dùng KEK dạng hex lưu sẵn trong biến môi trường để duy trì dịch vụ không?**  
Không được tự ý fallback như vậy. Phải dùng chiến lược fail-safe, HA hoặc DR đã được phê duyệt, không hạ cấp bảo mật.

## Ghi nhớ

**Key encryption key (KEK) là khóa chuyên bảo vệ các khóa khác, đặc biệt là DEK trong envelope encryption.** KEK cho phép tách **mã hóa dữ liệu bằng DEK** khỏi **quản trị key material và quyền Wrap/Unwrap trong KMS/HSM**. Thiết kế đúng cần cơ chế wrapping an toàn như **AES-KW/KWP, AEAD wrapping hoặc KMS provider API phù hợp**, cùng **key ID/version, metadata đã xác thực, tenant authorization, nonce discipline và audit**. Trong toàn bộ **key lifecycle**, phải quản lý **generation, activation, cryptoperiod, rotation, revocation và destruction**; khi rotation phân biệt **rewrap** với **re-encrypt**, và khi compromise không quên rằng **attacker có thể giữ KEK/DEK/wrapped DEK cũ**. Kết hợp **Key owner, separation of duties, quorum approval, backup/DR, key inventory và incident response** giúp KEK trở thành tầng bảo vệ có thể kiểm chứng — thay vì một bí mật cấp cao mà không ai biết cách thay thế hoặc thu hồi.

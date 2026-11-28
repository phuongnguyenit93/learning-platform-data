# Read với key cũ: Đọc dữ liệu lịch sử an toàn sau khi rotation

Giả sử **Customer Data Service** mã hóa hồ sơ bằng AES-256-GCM. Tháng trước, service dùng **DEK-v3**; tháng này, theo chính sách rotation, toàn bộ dữ liệu mới được mã hóa bằng **DEK-v4**. Người dùng vẫn có quyền đọc một hồ sơ được tạo tháng trước. Nếu ứng dụng chỉ biết alias **current-key → v4** rồi cố giải mã ciphertext của v3 bằng v4, thao tác sẽ thất bại. Nếu nhóm vận hành xóa v3 ngay sau rotation, hồ sơ cũ có thể **mất khả năng khôi phục vĩnh viễn**.

Giải pháp không phải **tiếp tục dùng v3 để mã hóa mới mãi mãi**. Ta cần tách hai quyền:

- **Write/Encrypt mới:** chỉ key version đang được phê duyệt và còn trong **originator-usage cryptoperiod**.
- **Read/Decrypt lịch sử:** key version thực sự bảo vệ dữ liệu cũ, còn được phép sử dụng trong **recipient-usage period** và theo chính sách truy cập.

Đây là ý nghĩa của **Read với key cũ** trong chương **Cryptoperiod và rotation**: hệ thống **chuyển sang khóa mới cho dữ liệu mới** nhưng vẫn có **đường đọc được kiểm soát, có giới hạn và có thể kiểm toán** cho bản mã hợp lệ được tạo dưới khóa cũ.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, kiến thức này nối trực tiếp vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy** với **AES-GCM, KEK/DEK, envelope encryption, KMS/HSM, IAM, chữ ký số, audit và backup/DR**. Vấn đề quan trọng nhất là cân bằng giữa **khả năng truy cập dữ liệu hợp lệ** và **không tiếp tục tạo thêm dữ liệu phụ thuộc khóa đã hết thời hạn dùng mới**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **rotation không đồng nghĩa xóa khóa cũ**, và phân biệt **Encrypt bằng key mới** với **Decrypt bằng key version lịch sử**.
2. Phân biệt **cryptoperiod dùng để bảo vệ dữ liệu mới** và **thời hạn dùng khóa để xử lý dữ liệu lịch sử**, không nhầm với retention của ciphertext.
3. Thiết kế **single-write / multi-read** (còn gọi dual-read khi có hai phiên bản), cùng **immutable key ID/version** trong envelope.
4. Phân biệt **read-only old key**, **retired key**, **disabled/suspended key**, **compromised key** và **destroyed key**, tránh biến read-only thành quyền mở dữ liệu không giới hạn.
5. Thiết kế đường đọc cho **DEK rotation, KEK rotation, rewrap và re-encrypt**, bao gồm AAD, nonce, authentication tag và encryption context.
6. Hiểu hành vi của **KMS/HSM** khi key alias hoặc key material rotation thay đổi, cùng các giới hạn về provider-defined key versions.
7. Quản lý **IAM, tenant/resource authorization, key caching, audit, retention, restore và migration** đối với dữ liệu được mã hóa từ lâu.
8. Chạy ví dụ **Java 17** cho phép đọc ciphertext cũ bằng đúng khóa v1, ghi mới bằng v2, từ chối ghi bằng v1 và từ chối dữ liệu bị sửa/khác tenant.

## 2. Bài toán: Tại sao đọc bằng key cũ là cần thiết?

### 2.1. Một timeline thực tế

~~~text
Ngày 01:
  DEK-v1 ACTIVE
  Record A được Encrypt bằng DEK-v1

Ngày 30 (rotation):
  DEK-v2 ACTIVE cho Encrypt mới
  DEK-v1 READ_ONLY cho Decrypt record lịch sử
  Record B được Encrypt bằng DEK-v2

Ngày 45:
  Đọc Record A -> resolve DEK-v1 -> Decrypt + verify tag
  Đọc Record B -> resolve DEK-v2 -> Decrypt + verify tag
  Ghi Record C -> chỉ DEK-v2

Ngày 90 (sau migration nếu có):
  Record A đã được re-encrypt sang DEK-v2
  Không còn dữ liệu/backup cần DEK-v1? Cần kiểm chứng.
  Chỉ khi retention, backup và policy cho phép mới xem xét destroy v1.
~~~

Mốc thời gian trên **chỉ là minh họa**, không phải lời khuyên bắt buộc xoay khóa sau 30 hay 90 ngày. **Cryptoperiod** phải được xác định từ thuật toán, số lần sử dụng, độ nhạy dữ liệu, môi trường vận hành, yêu cầu pháp lý và chính sách tổ chức.

### 2.2. Ba dữ kiện quyết định khóa cần dùng

Để mở một bản mã lịch sử, ứng dụng cần biết:

1. **Ciphertext được tạo dưới material nào?** Key ID/version (hoặc provider ciphertext blob có đủ thông tin tương ứng).
2. **Material đó có còn khả dụng và được phép Decrypt không?** Key state, cryptoperiod, IAM/grant và retention.
3. **Context giải mã có còn khớp không?** Algorithm, nonce/IV, authentication tag, AAD/encryption context, format version và phạm vi tenant/record.

Nếu thiếu bất kỳ nhóm dữ kiện nào, thao tác đọc có thể thất bại. **Một chuỗi alias hiện tại** không đủ để thay thế toàn bộ metadata lịch sử.

### 2.3. Điều gì xảy ra nếu chỉ lưu current key?

~~~mermaid
flowchart TD
    D["Đọc record lịch sử"] --> M["Load ciphertext + metadata"]
    M --> Q{"Có immutable keyRef/version?"}
    Q -->|"Có"| R["Resolve đúng historical key material"]
    Q -->|"Không"| A["Chỉ có alias current-key"]
    A --> X["Alias đã trỏ sang key version mới"]
    X --> F["Authentication failure / mất khả năng giải mã"]
    R --> P{"Key được phép historical Decrypt?"}
    P -->|"Không"| N["DENY / incident / recovery workflow"]
    P -->|"Có"| V["AEAD verify + Decrypt đúng context"]
    V --> O["Trả plaintext cho caller đã được phân quyền"]
~~~

**Không “thử tất cả khóa”** để bù cho metadata thiếu: việc đó gây chi phí lớn, biến dịch vụ thành **key enumeration/decryption oracle**, và khó audit. Hệ thống nên có **key reference được xác định từ dữ liệu đã lưu**, với chính sách migration riêng cho bản ghi legacy không có version.

## 3. Cryptoperiod: Write period khác Read period

### 3.1. Originator-usage và recipient-usage

Trong quản lý khóa, cần phân biệt hai góc nhìn:

- **Originator-usage period:** khoảng thời gian khóa được dùng để **tạo bảo vệ mật mã mới** (ví dụ Encrypt dữ liệu mới, Generate MAC mới hoặc Sign nội dung mới).
- **Recipient-usage period:** khoảng thời gian khóa/đối tượng liên quan được dùng để **xử lý thông tin đã được bảo vệ trước đó** (ví dụ Decrypt bản mã cũ, Verify MAC/chữ ký lịch sử), tùy thiết kế thuật toán và trust policy.

Các khoảng thời gian này có thể **khác nhau**, đặc biệt khi doanh nghiệp lưu archive lâu hơn chu kỳ rotation. Đối với public-key signatures, **public verification key và trust evidence** có thể cần được duy trì sau thời gian **private key được phép ký mới**.

### 3.2. Cryptoperiod không đồng nghĩa retention

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| **New-use cryptoperiod** | Khóa được phép Encrypt/Sign mới đến khi nào? | DEK-v1 ngừng Encrypt sau khi v2 Active |
| **Historical-use period** | Được phép Decrypt/Verify dữ liệu cũ đến khi nào? | Đọc record cũ khi còn retention |
| **Data retention** | Ciphertext/record cần tồn tại bao lâu? | Hóa đơn lưu theo chính sách doanh nghiệp |
| **Key retention** | Material/backup nào cần được giữ để mở dữ liệu? | Giữ DEK/KEK version liên quan archive |
| **IAM grant/session TTL** | Principal có quyền sử dụng khóa trong bao lâu? | Service token ngắn hạn |
| **Cache/lease TTL** | Plaintext DEK tạm còn sống trong memory bao lâu? | Lease trong một request/batch |
| **Provider deletion waiting period** | Khi nào lệnh destroy thực sự có hiệu lực? | Theo lifecycle của provider |

**Không thể quyết định ngày hủy khóa chỉ từ ngày hết hạn Encrypt mới.** Phải kiểm tra cả ciphertext đang tồn tại, EDK, backup, legal hold, nhu cầu Verify, key escrow và mọi đường khôi phục.

### 3.3. Trạng thái khóa: Mô hình khái niệm

~~~mermaid
stateDiagram-v2
    [*] --> PRE_ACTIVE: Generate/import key
    PRE_ACTIVE --> ACTIVE: Approve, provision
    ACTIVE --> READ_ONLY: Rotate new-use key
    ACTIVE --> SUSPENDED: Pause/key incident
    READ_ONLY --> SUSPENDED: Risk review
    SUSPENDED --> READ_ONLY: Approved historical use
    SUSPENDED --> COMPROMISED: Confirm material exposure
    READ_ONLY --> DESTROYED: Dependencies cleared
    COMPROMISED --> DESTROYED: Remediation + retention review
    DESTROYED --> [*]
~~~

**Đây không phải bảng trạng thái của một KMS cụ thể.** Một số provider không có native state **READ_ONLY** trên từng key version. Ứng dụng có thể phải thực thi **không Encrypt mới** ở policy/gateway, trong khi provider chỉ có khái niệm enabled/disabled hoặc IAM permissions khác. Khi đã **COMPROMISED**, không đơn giản “cho đọc vì dữ liệu cũ còn cần”: cần incident response, đánh giá exposure và đường khôi phục an toàn.

### 3.4. Ma trận cho phép thao tác

| Key state logic | Encrypt/Sign/Wrap mới | Decrypt/Verify/Unwrap lịch sử | Ghi chú |
|---|---|---|---|
| **PRE_ACTIVE** | Không | Không, trừ test có kiểm soát | Chưa phê duyệt |
| **ACTIVE** | Cho phép nếu đúng purpose, IAM và cryptoperiod | Cho phép nếu đúng quyền | Không có nghĩa mọi principal đều được dùng |
| **READ_ONLY / RETIRED** | **Không** | **Có thể**, theo retention và policy | Cần immutable keyRef/version |
| **SUSPENDED / DISABLED** | Không | Thường bị chặn hoặc rất hạn chế tùy provider/incident | Không bypass vì availability |
| **COMPROMISED** | Không | Theo incident/trust policy, không tự cho phép | Có thể cần rotate/re-encrypt |
| **DESTROYED** | Không | Không bằng material đã hủy | Backup/escrow có thể vẫn tồn tại |

Điều quan trọng là **mỗi service không được suy quyền từ trạng thái một mình**. Historical Decrypt còn cần đúng **principal, tenant, record ownership, key purpose và key version**.

## 4. Kiến trúc single-write / multi-read

### 4.1. Chỉ một write key, nhiều historical read keys

~~~mermaid
flowchart TD
    W["New write / Encrypt request"] --> AW["Resolve ACTIVE write-key version"]
    AW --> WV["Validate IAM, purpose, tenant, cryptoperiod"]
    WV --> ENC["Encrypt AES-GCM, nonce mới, content AAD"]
    ENC --> P[("Persist ciphertext + immutable keyRef/version")]
    R["Read existing record"] --> LOAD[("Load ciphertext + keyRef/version")]
    LOAD --> KR["Resolve historical key from trusted registry"]
    KR --> AUTH["Authorize principal, tenant, record, historical-use state"]
    AUTH --> DEC["AEAD Verify + Decrypt"]
    DEC --> OUT["Return plaintext by business policy"]
~~~

Một vòng rotation hai phiên bản có thể diễn ra như sau:

~~~text
writeKey = DEK-v4       // chỉ Encrypt mới
readKeys = {DEK-v3, DEK-v4}  // Decrypt đúng version của record

Encrypt(newData):
    version = writeKey.version
    Encrypt(newData, writeKey, uniqueNonce, AAD)
    Persist(version, nonce, ciphertext/tag)

Decrypt(existingRecord):
    version = existingRecord.keyVersion
    key = ResolveTrustedKey(version)
    CheckHistoricalUse(key, principal, tenant, record)
    AEAD_Decrypt(key, nonce, ciphertext/tag, AAD)
~~~

**“Multi-read” không có nghĩa một request thử lần lượt v3, v4, v5.** Nó có nghĩa hệ thống có **khả năng giải mã dữ liệu thuộc nhiều phiên bản**, còn **mỗi record chỉ chọn đúng key version được ghi nhận**.

### 4.2. Write path và read path nên tách quyền

| Principal | Quyền mới thường cần | Quyền không cấp mặc định |
|---|---|---|
| **Customer Data Writer** | Encrypt/GenerateDataKey/Wrap dưới active key theo tenant | Unwrap toàn bộ EDK lịch sử |
| **Customer Data Reader** | Decrypt/Unwrap key versions hợp lệ cho record được phép | Encrypt mới bằng key retired |
| **Migration worker** | Historical Decrypt + new Encrypt/Rewrap theo approved job | Arbitrary cross-tenant Decrypt, Export root key |
| **Key administrator** | Rotate/UpdatePolicy/Disable theo approval | Đọc plaintext nghiệp vụ chỉ vì quản lý key |
| **Independent auditor** | Xem key ID/version, usage, state, policy revisions | Raw DEK/KEK, Sign/Decrypt |

**Tách quyền giữa writer và reader** giảm blast radius và làm audit rõ. Trong ứng dụng nhỏ, cùng service có thể vừa read vừa write, nhưng service vẫn phải **chặn operation bằng key retired** tại điểm gọi.

### 4.3. Đọc theo immutable key reference

Một record mã hóa cần tối thiểu:

~~~json
{
  "envelopeVersion": 1,
  "tenantId": "tenant-42",
  "recordId": "invoice-2026-001",
  "contentAlgorithm": "AES-256-GCM",
  "contentKeyRef": {
    "keyId": "tenant-42-invoice-dek",
    "keyVersion": 3
  },
  "contentNonce": "<BASE64_12_BYTES>",
  "ciphertextWithTag": "<BASE64_CIPHERTEXT_AND_TAG>",
  "contentAadSchema": "invoice-v1"
}
~~~

**Đây chỉ là ví dụ schema**. Một envelope thực tế dùng KMS có thể lưu **wrapped DEK, KEK resource/version, KMS ciphertext blob, wrapping algorithm/context** chứ không lưu plaintext DEK hoặc tên version theo cùng định dạng. Nội dung trong dấu góc là placeholder, không phải dữ liệu thật; **Base64 không phải mã hóa**.

Key version phải là **version thực sự gắn với material đã dùng**, không phải alias **current-key** tại thời điểm đọc. Nếu provider tự xử lý material version trong ciphertext blob, nên dùng **provider-defined reference/blob** chứ không tự suy version từ tên alias.

### 4.4. Metadata từ storage là dữ liệu chưa tin

Không làm thế này:

~~~text
record.keyVersion = 2  // caller sửa
service:
    fetch key material v2
    decrypt hoặc trả dữ liệu
~~~

Trước khi gọi KMS/JCA, cần:

1. **Xác thực caller** và quyền read đối với record/tenant theo nguồn tin cậy.
2. **Kiểm tra schema/size/algorithm allowlist**, key ID, version và key purpose.
3. **Resolve từ trusted key registry** và kiểm tra tenant/purpose/owner/state, không dựa riêng vào field do client gửi.
4. **Ràng buộc AAD/encryption context** với record, tenant, key ID/version phù hợp.
5. **Verify authentication tag** trước khi sử dụng plaintext; không phát tán chi tiết key enumeration qua lỗi.

**AEAD tag không thay thế IAM**: nếu role có quyền Unwrap dữ liệu của tenant khác, kiểm tra tag thành công vẫn không chứng minh user có quyền đọc.

## 5. Read với key cũ trong envelope encryption: Phải phân biệt DEK và KEK

Trong envelope encryption, có ít nhất **hai lớp khóa**:

- **DEK (Data Encryption Key)** trực tiếp bảo vệ payload.
- **KEK (Key Encryption Key)** dùng Wrap/Encrypt DEK. KMS/HSM thường quản lý KEK và có thể giữ KEK non-exportable.

Nếu dữ liệu được mã hóa nhiều năm, một record có thể có **DEK version/identifier riêng** và **KEK version riêng**. Read cũ cần biết **khóa nào dùng cho lớp nào**.

### 5.1. Dòng dữ liệu khi ghi một record

~~~mermaid
sequenceDiagram
    participant App as Customer Data Writer
    participant KMS as KMS/HSM giữ KEK
    participant DB as Encrypted storage
    App->>App: Xác thực tenant và Write authorization
    App->>KMS: GenerateDataKey / Wrap đúng KEK hiện tại
    KMS-->>App: DEK tạm trong RAM + encrypted DEK (theo API)
    App->>App: AES-GCM Encrypt bằng DEK, unique nonce + content AAD
    App->>DB: Content ciphertext/tag, EDK, key references/versions
    App->>App: Cleanup plaintext DEK best effort
~~~

Một số KMS cho ứng dụng nhận plaintext DEK tạm để mã hóa local; provider khác có API Wrap/Unwrap hoặc crypto service giữ key handle. **Không có API chung** bắt buộc mọi KMS trả DEK theo cùng cách.

### 5.2. Đọc dữ liệu cũ sau rotation KEK

~~~text
Record A:
    Content = AES-GCM(DEK-A, payload-A, nonce-A, aad-A)
    EDK-A-v3 = Wrap(KEK-v3, DEK-A, wrapContext-A)

Sau rotation:
    KEK-v4 ACTIVE cho EDK mới
    KEK-v3 historical Unwrap nếu được phép

Read Record A:
    Load EDK-A-v3 + KEK-v3 reference + context
    Authorized Unwrap(KEK-v3, EDK-A-v3)
    -> DEK-A plaintext tạm (nếu API trả)
    -> AES-GCM Decrypt(payload-A, DEK-A, nonce-A, aad-A)
~~~

Lưu ý:

1. **Rotation KEK không tự đổi DEK**. Nếu vẫn có EDK dưới KEK-v3, cần **Unwrap bằng đúng key version/provider ciphertext blob**.
2. **KEK mới không nhất thiết mở được EDK cũ**; chỉ khi provider có cơ chế version handling đúng contract hoặc EDK đã được rewrap.
3. KMS **non-exportable KEK** không có nghĩa plaintext DEK chưa từng tồn tại trong JVM.
4. **KMS encryption context** có thể là AAD hoặc input của policy; phải lưu/tái tạo đúng, không coi context có thể thay tùy ý.
5. **Provider key rotation** có thể giữ các material versions cũ dưới một logical key ID. Không được suy rằng API luôn có parameter version tường minh; tuân thủ **ciphertext blob/key version semantics** của chính provider.

### 5.3. Rewrap EDK: Giảm phụ thuộc vào KEK cũ

**Rewrap** nghĩa là chuyển lớp bảo vệ của **cùng một DEK**:

~~~text
DEK-A = Unwrap(KEK-v3, EDK-A-v3, context-v3)
EDK-A-v4 = Wrap(KEK-v4, DEK-A, context-v4)

Content ciphertext không đổi
Content DEK không đổi
Wrapped DEK + KEK reference/wrap metadata thay đổi
~~~

Nếu provider hỗ trợ **server-side re-encryption/rewrap**, ưu tiên đánh giá phương án **không xuất raw DEK sang application**. Một số provider chỉ hỗ trợ chuyển **blob do chính provider sinh**; không tự giả định API chuyển được mọi AES-KW/AES-GCM-wrapped DEK.

Rewrap cần:

- Kiểm tra **key state/purpose/tenant/IAM** của KEK cũ và mới.
- Dùng **đúng wrap algorithm, wrapping AAD/context và provider reference**.
- Sinh **wrap nonce mới** khi cơ chế AEAD yêu cầu, nhất là AES-GCM với KEK mới.
- Ghi EDK mới và KEK reference **nguyên tử** cùng metadata liên quan.
- Xác minh khả năng đọc trước khi dừng quyền với KEK cũ.
- Đối soát EDK trong **primary DB, backups, archives, replicas và delayed queues**.

**Rewrap không phải re-encrypt content**. Nếu **DEK đã lộ**, đổi KEK không làm attacker quên DEK.

### 5.4. Read cũ sau rotation DEK

Nếu data encryption thực sự thay từ **DEK-v3** sang **DEK-v4**, ciphertext của v3 **không thể mở chỉ bằng v4**. Có các chiến lược:

| Chiến lược | Cách đọc ciphertext cũ | Ưu điểm | Rủi ro/chi phí |
|---|---|---|---|
| **Lazy re-encrypt** | Mở bằng DEK-v3 theo metadata, tùy policy mã hóa lại bằng v4 khi đọc/ghi | Chia nhỏ migration, giảm batch lớn | Cần CAS, write-amplification, backup cũ |
| **Batch/background re-encrypt** | Worker đọc bằng v3 và ghi ciphertext mới bằng v4; sau đó read v4 | Có tiến độ đo được, thu hẹp dependency cũ | Tải hệ thống, plaintext transit, retries và transaction |
| **Giữ read-only v3 đến hết retention** | Record cũ tiếp tục Decrypt bằng v3 | Ít thay đổi dữ liệu | Kéo dài exposure của key v3 và gánh nặng DR |

**Không nhất thiết re-encrypt tất cả dữ liệu sau mỗi KEK rotation**; nhưng khi chính **DEK cần thay**, việc rewrap cùng DEK không đáp ứng mục tiêu đó. Tùy dữ liệu, cryptoperiod và threat model, tổ chức có thể chọn giữ key cũ read-only hoặc re-encrypt theo lộ trình.

### 5.5. Content AAD và wrapping metadata không nên trộn bừa

Nếu content ciphertext giữ nguyên khi rewrap, **content AAD cũng phải giữ nguyên** theo cách ciphertext/tag được tạo:

~~~text
contentAAD = encode(
    formatVersion,
    tenantId,
    recordId,
    contentAlgorithm,
    contentDekRef
)

wrapContext = encode(
    tenantId,
    recordId,
    kekRef/version,
    wrappedDekPurpose
)
~~~

Nếu **KEK-v3** nằm trong **content AAD** rồi migration sửa thành **KEK-v4**, xác minh GCM tag của ciphertext cũ có thể thất bại. Phải xác định **metadata nào gắn với payload bất biến** và **metadata nào gắn với EDK có thể rewrap**.

**AAD là dữ liệu được xác thực, không nhất thiết được giữ bí mật**, và không phải bằng chứng user có quyền. Một attacker thay tenant/record để chọn key trước khi authorization vẫn là rủi ro dù AES-GCM sau đó báo tag lỗi.

## 6. Quy trình đọc record cũ an toàn từ đầu tới cuối

### 6.1. Sơ đồ tuần tự

~~~mermaid
sequenceDiagram
    participant U as Caller
    participant API as Data API
    participant DB as Storage
    participant REG as Key Registry/Policy
    participant KMS as KMS/HSM
    participant LOG as Secure Audit
    U->>API: Read recordId thuộc tenant
    API->>API: Verify identity và resource authorization
    API->>DB: Load envelope theo recordId đã được kiểm tra
    DB-->>API: Ciphertext, nonce/tag, EDK, keyRef/version, formats
    API->>API: Validate structure/size/algorithm allowlist
    API->>REG: Resolve immutable key reference + state/purpose/tenant
    REG-->>API: Historical-use policy + provider key
    alt Historical key không được phép
        API->>LOG: Denied, metadata-only
        API-->>U: Controlled denial
    else Đúng quyền và state
        API->>KMS: Unwrap đúng EDK/context (nếu cần)
        KMS-->>API: DEK hoặc authorized crypto result
        API->>API: AEAD Verify tag + Decrypt content
        API->>LOG: keyRef/version, principal, operation, outcome
        API-->>U: Plaintext đã được phân quyền
        API->>API: Cleanup DEK best effort
    end
~~~

### 6.2. Thuật toán read path ở mức kiến trúc

~~~text
ReadEncryptedRecord(authenticatedCaller, recordId):
    1. Load trusted resource ownership -> authorize read.
    2. Load encrypted envelope -> parse with size bounds.
    3. Compare envelope tenant/record to trusted ownership.
    4. Validate contentAlgorithm/format/schema allowlist.
    5. Resolve exact keyRef/version -> trusted registry/provider.
    6. Check:
           purpose == CONTENT_ENCRYPTION
           keyState permits historical Decrypt
           authenticatedCaller/workload has Decrypt/Unwrap scope
           recordKey metadata belongs to tenant/environment
    7. Unwrap encrypted DEK if using envelope encryption.
    8. Rebuild exact content AAD; verify AEAD tag and decrypt.
    9. Optionally migrate via CAS to new DEK/KEK by approved job.
   10. Cleanup plaintext DEK, audit result (no raw key/plaintext).
~~~

### 6.3. Không biến metadata thiếu thành việc dò khóa

Một hệ thống legacy có thể chỉ lưu:

~~~text
record.createdAt = 2024-06-10
record.ciphertext = ...
~~~

Không nên đoán key version từ createdAt rồi tự thử nhiều keys trong request production. Nếu **key assignment có hiệu lực theo mốc thời gian**, mapping cần được kiểm chứng bằng **change-controlled migration records, inventory, provider logs hoặc metadata lịch sử đáng tin**.

Đường xử lý legacy nên:

1. Đặt bản ghi vào **quarantine/migration queue** khi thiếu keyRef, không thử vô hạn trong API.
2. Phê duyệt rule mapping old format → key reference với evidence.
3. Đọc trong worker được giới hạn permissions, **không xuất plaintext ra log**.
4. Re-encrypt hoặc bổ sung metadata đã xác thực, lưu envelope revision mới.
5. Đối soát số records còn thiếu keyRef và báo cáo audit.

### 6.4. Phân biệt lỗi để xử lý nhưng không lộ thông tin cho caller

| Lỗi nội bộ | Hành vi đối ngoại | Điều tra/audit nội bộ |
|---|---|---|
| No permission/tenant mismatch | Denied, không trả plaintext | caller, resource ref, policy decision |
| Unknown key version | Controlled failure | key ID/version, migration/registry mismatch |
| Key disabled/suspended | Denied/unavailable theo policy | state, provider outcome, incident ID |
| KMS timeout/region outage | Bounded retry/DR/fail closed | latency, provider request ID, affected dependencies |
| AEADBadTagException | Invalid encrypted record, không trả dữ liệu | integrity category, keyRef, schema, request ID |
| Missing/wrong AAD encoding | Controlled data/format error | format version, canonicalization discrepancy |
| Key material destroyed | Recovery failure, không tự fallback | backup/restore policy, key lifecycle records |

**Một lỗi AEAD tag không chứng minh dữ liệu bị attacker sửa**; sai key version, nonce, context, storage corruption hay bug migration cũng có thể gây ra. Tuy nhiên không trả thông tin như **“key v3 tồn tại và tag đúng nhưng tenant sai”** cho client không đáng tin, vì có thể trở thành key-enumeration oracle.

## 7. Key state và IAM: Read-only phải được thực thi ở đâu?

### 7.1. Có ít nhất ba tầng kiểm soát

| Tầng | Chặn điều gì? | Giới hạn |
|---|---|---|
| **Application/key registry** | Không Encrypt bằng v1, chọn đúng v1 cho historical read, kiểm tra record | Có thể bị bypass nếu workload có quyền gọi provider trực tiếp |
| **KMS/HSM IAM/usage constraints** | Principal/action/key scope, non-exportability, key state do provider enforce | Có thể không hiểu record ownership hoặc read-only per key version |
| **Business authorization** | User nào được xem record thuộc tenant nào | Không tự chặn key reuse nếu KMS/API không tách purpose |

**READ_ONLY** thường là **policy logic**, không phải bảo đảm mà mọi provider tự hỗ trợ cho từng material version. Nếu KMS tự rotate key material dưới cùng logical key ID, operation **Encrypt** trên logical key có thể tự dùng current material; **Decrypt** đọc cũ dựa trên ciphertext blob. Phải đọc provider contract để biết chính xác cơ chế.

### 7.2. Không trao “historical decrypt all” khi không cần

Một **data reader** có quyền mở dữ liệu cũ nên:

- Chỉ được gọi **Decrypt/Unwrap** cho key family/tenant/record thuộc phạm vi.
- Không có quyền **ExportRawKEK**, **ManageKeyPolicy**, **DestroyKey** hoặc Sign.
- Có **resource authorization** trước KMS.
- Có **rate limits, audit và kiểm soát tải** để giảm lạm dụng như oracle.
- Không nhận token vô thời hạn hay giữ raw DEK trong cache không giới hạn.

Một migration worker cần nhiều quyền hơn reader bình thường nhưng nên dùng **temporary grants**, allowlist key versions/datasets, approvals và giám sát. **Admin có quyền đổi key state** không nên mặc nhiên có quyền đọc plaintext.

### 7.3. Khi khóa cũ bị compromise

Nếu **raw DEK-v1 đã lộ**, đối thủ có thể giải mã ciphertext đã mã hóa bằng v1 nếu họ có bản mã, dù hệ thống đã rotate sang v2. **Không nên tiếp tục cấp Read v1 như bình thường** chỉ vì archival requirement; phải mở quy trình incident:

1. Khoanh vùng **record/object/backup** dùng v1.
2. Đánh giá ai đã có v1 hoặc khả năng v1 xuất hiện trong dump/log/host.
3. **Dừng Encrypt mới bằng v1** (nếu chưa dừng).
4. Thu hồi quyền truy cập/credential liên quan, giới hạn Decrypt v1 theo approved recovery plan.
5. Cân nhắc **re-encrypt dưới v2/v3**, xóa/retire bản cũ theo chính sách.
6. Xác minh dữ liệu lịch sử và backups; ghi nhận sự cố cùng các giới hạn “không thu hồi được dữ liệu đã bị sao chép”.

Nếu **KEK-v1 bị lộ**, phạm vi có thể rộng hơn một DEK: nhiều EDK cũ có thể bị Unwrap. **Chỉ rewrap EDK sang KEK mới không sửa được khả năng DEK đã bị giải mã trước đó**. Cần đánh giá **DEK exposure** và re-encrypt theo risk.

**Nếu chỉ credential KMS bị lộ mà material KEK vẫn non-exportable**, phải điều tra **Unwrap/Decrypt API calls** đã diễn ra, không suy mặc định key bytes KEK đã bị lấy; nhưng cũng không coi sự cố vô hại.

### 7.4. Revocation và cache cũ

Disable KEK trong KMS có thể ngăn **Unwrap mới**, nhưng DEK đã được giải mã và cache trong JVM **vẫn có thể Encrypt/Decrypt offline** cho đến khi lifetime/cache invalidation hoặc workload bị dừng. Do vậy:

- Dùng **DEK leases, TTL, cache size và scope** rõ ràng.
- Không dùng cache key **current-key** nếu underlying material có thể thay version.
- Theo dõi effective-time của key state, IAM grant và session TTL.
- Xử lý **stale state** giữa instances/regions theo policy và revision.
- Biết rằng **Arrays.fill(byte[])** chỉ là cleanup best effort, không xóa mọi bản sao trong JCA/provider/native memory.

**Một KMS API trả “AccessDenied” không tự chứng minh mọi process đang giữ raw DEK đều đã ngừng sử dụng nó.**

## 8. Migration: Giữ old key để Read hay chuyển dữ liệu sang key mới?

Có ba mục tiêu có thể xung đột:

1. **Dữ liệu lịch sử phải còn đọc được** đúng thời hạn nghiệp vụ.
2. **Khóa cũ không được tạo thêm ciphertext** ngoài new-use cryptoperiod.
3. **Đường phụ thuộc vào khóa cũ cần giảm dần** nếu rủi ro, chi phí hoặc chính sách yêu cầu.

Một migration tốt có mục tiêu đo được: **bao nhiêu records đang dưới key v1, bao nhiêu đã sang v2, bao nhiêu lỗi, bao nhiêu bản sao/backup chưa chuyển và lúc nào mới được hủy key cũ**.

### 8.1. Ba giai đoạn an toàn

~~~mermaid
flowchart LR
    P1["Phase A: v1 ACTIVE"] --> P2["Phase B: v2 ACTIVE, v1 READ_ONLY"]
    P2 --> P3["Phase C: Migration / retention"]
    P3 --> C{"Còn dependency v1?"}
    C -->|"Có"| R["Giữ historical Read v1 theo policy"]
    C -->|"Không"| V["Verify restore, backups và legal hold"]
    V --> D["Retire/destroy v1 theo approval"]
    R --> P3
~~~

Trong **Phase B**, dữ liệu mới phải ghi bằng v2, dù một số readers còn đang sử dụng v1. Nếu writers vẫn Encrypt v1 sau mốc rotation, **số record phụ thuộc v1 có thể không bao giờ giảm**.

### 8.2. Lazy re-encrypt khi đọc

Luồng:

~~~text
Read record revision=10, DEK-v1
    |
    +-- Authorize + Decrypt bằng v1
    |      -> trả plaintext cho caller hợp lệ
    |
    +-- Nếu policy cho phép migration:
           Generate fresh nonce
           Encrypt plaintext bằng DEK-v2 + new AAD
           CAS update only if revision == 10
           Audit migration result
~~~

Ưu điểm là chỉ chuyển dữ liệu thực sự được đọc. Nhược điểm:

- Những record **ít truy cập** vẫn phụ thuộc v1 đến hết retention.
- Một read request có thể trở thành **write request**, nên cần rõ quyền và transaction boundary.
- Hai request đọc cùng lúc có thể đều cố re-encrypt; phải dùng **compare-and-swap** hoặc migration worker tách biệt.
- Nếu người dùng đọc record nhưng **không được phép sửa** thì business API không nên tự ghi mà không có migration policy.
- Lỗi migration không được làm hỏng record gốc hay trả plaintext cho principal trái quyền.

Đối với hệ thống nhạy cảm, có thể ưu tiên gửi migration vào **bounded queue** và để **worker được phê duyệt** xử lý, thay vì viết trực tiếp từ mỗi read.

### 8.3. Background migration và tính nguyên tử

Tình huống race:

~~~text
T0 Worker A đọc record revision 17, key v1
T1 API Writer B cập nhật record revision 18 bằng key v2
T2 Worker A mã hóa lại plaintext cũ từ revision 17
T3 Worker A ghi đè record revision 18

=> Mất cập nhật mới, dù cả ciphertext đều hợp lệ.
~~~

Giải pháp: **optimistic locking / compare-and-swap** theo revision/ETag, hoặc transaction phù hợp với DB.

~~~sql
-- Pseudo SQL minh họa, tên cột phụ thuộc schema thật.
UPDATE encrypted_record
SET
    envelope_blob = :new_envelope,
    revision = revision + 1
WHERE
    record_id = :record_id
    AND revision = :expected_revision
    AND key_version = :expected_old_key_version;
~~~

Nếu số hàng cập nhật bằng 0, record đã đổi; worker **không overwrite**, mà reload/đánh giá retry. **Không tái sử dụng AES-GCM nonce đã dùng trong lần Encrypt trước** khi retry một encryption mới dưới cùng key, và không xây một deduplication mechanism khiến encrypt trùng nonce với payload khác.

### 8.4. Migration không đồng nghĩa đổi metadata mà không đổi ciphertext

Sai:

~~~text
record.keyVersion = 1
record.ciphertext = AES-GCM(DEK-v1, plaintext)

UPDATE record SET keyVersion = 2;

Kết quả: AEAD decrypt bằng DEK-v2 thất bại.
~~~

Đúng khi thay DEK:

~~~text
plaintext = AEAD_Decrypt(DEK-v1, oldCiphertext, oldNonce, oldAAD)
newCiphertext = AEAD_Encrypt(DEK-v2, plaintext, newNonce, newAAD)
atomicPersist(newCiphertext, keyRef=v2, newNonce, newTag, newRevision)
~~~

**Khi thay KEK nhưng giữ DEK**, có thể chỉ rewrap EDK và cập nhật lớp wrapping nếu content AAD không đổi. Không trộn hai loại migration để tránh thất bại khó chẩn đoán.

### 8.5. Lập kế hoạch theo khối lượng và rủi ro

Đối với hàng triệu records:

- **Thống kê dependencies** theo key ID/version, tenant, data classification và retention.
- Chia **batch**, giới hạn throughput, KMS quotas và retry/backoff.
- Có **checkpoint**, idempotency key, envelope revision và audit.
- Không chuyển **plaintext hàng loạt** qua untrusted queue hoặc export CSV.
- Giữ đường **rollback** có kiểm soát: phục hồi record revision cùng key references, không khôi phục key đã destroy.
- Thử **representative samples** từ archive và backup, bao gồm versions lâu đời.
- Đo **tỷ lệ lỗi integrity, key unavailable, format mismatch** và nguyên nhân.

**Mục tiêu không chỉ là 100% record tại primary DB đã đổi**. Snapshot, backup, object replication, delayed events và external encrypted exports có thể còn phụ thuộc key cũ.

## 9. Backup, archive và khôi phục dữ liệu lịch sử

### 9.1. Những thành phần phải tồn tại cùng nhau

Để restore một ciphertext cũ, cần:

| Thành phần | Nếu thiếu có thể xảy ra |
|---|---|
| **Ciphertext + authentication tag** | Không có nội dung được bảo vệ hoặc không thể xác minh integrity |
| **Nonce/IV đúng thuật toán** | Không thể giải mã chính xác hoặc không thể verify AEAD tag |
| **Content keyRef/version** | Không biết material nào đã Encrypt |
| **Wrapped DEK (nếu dùng envelope)** | Mất đường khôi phục plaintext DEK |
| **KEK provider key ID/version/blob** | Không thể Unwrap EDK dưới đúng key |
| **AAD/encryption context schema** | Tag/MAC verification có thể thất bại |
| **Provider key material/backup và quyền Restore** | Có metadata nhưng không có material hợp lệ |
| **Tenant/record ownership metadata** | Không thể kiểm tra quyền và scope |
| **Format/algorithm version** | Không thể tái tạo đúng crypto operation |

**Backup chỉ có ciphertext không đủ** nếu khóa và metadata cần mở nó không được bảo toàn. Ngược lại, để raw KEK cạnh ciphertext trong backup sẽ phá ranh giới bảo mật.

### 9.2. KMS/HSM recovery có khác nhau giữa providers

Một KMS có thể hỗ trợ **automatic rotation** mà key material cũ vẫn được giữ nội bộ để Decrypt ciphertext blob. Một HSM có thể hỗ trợ **secure backup/replication** cho non-exportable key objects theo chính sách. Provider khác có thể yêu cầu **import material** hoặc không đảm bảo cùng key IDs khi restore sang region khác.

Vì vậy cần xác minh:

1. **Key ID/version** nào được giữ nguyên sau restore hoặc import?
2. **Material lịch sử** có thể dùng Decrypt/Unwrap trong môi trường DR không?
3. Có cần **ciphertext blob chứa key version** và provider context không?
4. **IAM/key policy** và trạng thái key có cho phép recovery sau sự cố không?
5. Backup có **recovery shares, quorum/approvals và data residency** phù hợp không?
6. Có **test restore** từ bản mã cũ, không chỉ test Encrypt mới?

**Không tự export raw KEK** sang file tạm chỉ để tạo DR path. Nếu cần backup material nhạy cảm, sử dụng quy trình provider-approved, bảo vệ split knowledge/dual control nếu policy yêu cầu.

### 9.3. Key cũ trong backup làm phức tạp crypto-erasure

Giả sử đã re-encrypt mọi record tại primary DB sang DEK-v2 rồi xóa DEK-v1 khỏi registry:

~~~text
Primary DB: tất cả ciphertext dùng DEK-v2
Backup tháng trước: vẫn có ciphertext dùng DEK-v1
External archive: có EDK dưới KEK-v1
DR image: chứa key material/credential lịch sử
~~~

Nếu legal hold/retention yêu cầu đọc backup cũ, **key v1 có thể vẫn cần được giữ**. Nếu mục tiêu là **crypto-erasure**, cần chứng minh tất cả đường truy cập material đã bị loại bỏ theo chính sách, không chỉ bỏ tham chiếu tại primary DB. Điều này có thể bao gồm các quyết định pháp lý/retention không do ứng dụng đơn phương đưa ra.

### 9.4. KMS outage và “read old key”

Nếu KMS không khả dụng:

- Không fallback sang **hardcoded KEK** hoặc một “emergency master key” không được kiểm soát.
- Có thể dùng **HA/multi-region approved KMS** hoặc DR theo provider contract.
- Nếu local **DEK cache còn lease hợp lệ**, read có thể được phép theo policy đã phê duyệt; **không kéo dài TTL vô hạn** khi outage.
- Nếu key cũ cần KMS Unwrap nhưng không có đường khôi phục, **fail closed** hoặc đưa vào queue với trạng thái rõ ràng; không thử decrypt bằng random/current key.
- Giới hạn retry, backoff, quotas và audit; một lỗi KMS không nên tạo storm trên historical key archive.

**Availability cần thiết, nhưng không biện minh cho bỏ IAM hoặc phá key boundary.** Mục tiêu RTO/RPO phải được cân bằng với security policy trước khi xảy ra outage.

## 10. Đọc “bằng key cũ” trong chữ ký số, MAC và JWT

**Historical use không chỉ có Decrypt.** Với một số primitive, việc xử lý dữ liệu cũ là **Verify** chứ không phải “giải mã”.

### 10.1. Private signing key ngừng Sign, public key vẫn Verify

Ví dụ:

~~~text
Tháng 1: private-sign-v3 Sign invoice-001
Tháng 2: private-sign-v4 ACTIVE
         private-sign-v3 không Sign mới
         public-verify-v3 có thể còn trong trust store để Verify lịch sử

Verify invoice-001:
    resolve issuer + trusted key ID v3
    verify signature bằng public key v3
    kiểm tra trạng thái tin cậy, thời điểm và chính sách
~~~

**Verify toán học thành công không đồng nghĩa chữ ký được tin cậy** khi private key đã compromise, certificate bị revoke hoặc thiếu timestamp/evidence cần thiết. Với chữ ký lưu dài hạn, có thể cần **certificate chain, trusted timestamp, revocation evidence và validation policy**.

Không giữ quyền **Sign bằng private key cũ** chỉ vì muốn tiếp tục Verify chữ ký cũ; public key đủ để Verify trong các scheme bất đối xứng phù hợp.

### 10.2. JWT/JWS: Chấp nhận token với kid cũ có giới hạn

Khi JWT signing key được rotate:

- Issuer ký token mới bằng private key mới.
- Verifier có thể giữ public key cũ trong **trusted JWKS/trust store** đủ để Verify những token chưa hết hạn theo policy.
- JWT header **kid** giúp chọn key, nhưng không được biến URL/keyId từ header thành nguồn tin cậy tùy ý.
- Phải kiểm tra **signature, algorithm allowlist, issuer, audience, expiry, token type, replay/session policy**.
- Khi key cũ bị compromise, cần xử lý trust/tokens ngay theo incident policy, không đợi grace period mặc định.

Không dùng “read old key” làm lý do chấp nhận **expired tokens vô thời hạn**. **Key rotation grace window** và **token validity** là hai điều kiện riêng.

### 10.3. HMAC: Verify bằng secret cũ không giống public-key verification

Với HMAC webhook, **sender và receiver cùng biết secret**:

~~~text
Sender đã chuyển sang HMAC-key-v2.
Receiver cho phép Verify bằng v1 và v2 trong migration window.
Sau khi window kết thúc: không chấp nhận v1.
~~~

Không nên giữ HMAC secret cũ vô thời hạn nếu tất cả bên liên quan đã chuyển. Mọi bên biết HMAC secret đều có thể **tạo MAC mới**, nên “verify only” bằng cùng raw secret cần policy nghiêm và **chống replay** bằng timestamp, nonce/message ID hoặc protocol semantics. Một verifier đang giữ raw HMAC secret v1 có **khả năng mật mã tạo tag v1**, dù application policy cấm.

### 10.4. Password hashing và pepper rotation là bài toán khác

Password hash là **một chiều**, không Decrypt bằng key cũ. Nếu có **pepper** (secret server-side) hoặc key material hỗ trợ bảo vệ password hash, kế hoạch chuyển version có thể yêu cầu:

- Nhận biết **hash algorithm/cost/salt/pepper version** theo policy.
- Verify login hợp lệ bằng đường cũ trong cửa sổ được phê duyệt.
- **Rehash** bằng tham số/pepper mới khi có plaintext password do user vừa xác thực thành công, hoặc kích hoạt reset credential khi cần.
- Không lưu plaintext password chỉ để thực hiện migration hàng loạt.

Không áp dụng máy móc mô hình AES Decrypt/Encrypt cho password hash; đây là primitive với lifecycle và threat model khác.

## 11. Java 17: Đọc với DEK-v1, ghi với DEK-v2 và migrate có revision

Ví dụ tự chạy dùng **JDK 17+**, không phụ thuộc SDK bên ngoài. Mục tiêu của nó là **phân biệt key state/cryptoperiod và key version của từng record**, không phải mô phỏng hoàn chỉnh KMS/HSM.

Các nguyên tắc được minh họa:

- Ban đầu **AES-256-GCM key v1** ở trạng thái ACTIVE, Encrypt record A.
- Rotation tạo **material v2 độc lập**, chuyển v1 sang READ_ONLY và v2 thành active write key.
- Record A còn mở được với **v1**, record B mới được Encrypt bằng **v2**.
- Cố Encrypt mới bằng v1 sẽ **bị từ chối**, dù key object v1 vẫn tồn tại để Decrypt.
- **Identity/tenant/record authorization** được kiểm tra trước crypto operation.
- Nonce 96 bit mới dùng với mỗi phép Encrypt; AAD encode có version, purpose, tenant, record và immutable keyRef.
- Ciphertext bị sửa khiến **AES-GCM tag verification thất bại**.
- Migration giải mã A bằng v1, mã hóa lại bằng v2 và chỉ persist bằng **compare-and-swap theo revision**, không đơn thuần sửa field version.
- Khi v1 bị SUSPENDED, request đọc ciphertext còn phụ thuộc v1 bị từ chối.

**Giới hạn quan trọng:** Đây là môi trường thử nghiệm **raw SecretKey sinh và giữ trong JVM**. Không có KMS/HSM non-exportable key, không có IdP/IAM thực, mọi principal trong demo là đối tượng tạo từ source code. **Không đưa class này vào production rồi coi metadata check là provider enforcement.**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class ReadWithOldKeyDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String PURPOSE = "CONTENT_ENCRYPTION";
    private static final String ALGORITHM = "AES-256-GCM";
    private static final int FORMAT_VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    enum State {
        ACTIVE, READ_ONLY, SUSPENDED
    }

    record KeyRef(String id, int version) {
        KeyRef {
            if (id == null || id.isBlank() || version < 1) {
                throw new IllegalArgumentException("Invalid key reference");
            }
        }
    }

    record KeyEntry(
            KeyRef ref,
            String tenant,
            String purpose,
            State state,
            SecretKey material) {
        KeyEntry {
            Objects.requireNonNull(ref);
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(purpose);
            Objects.requireNonNull(state);
            Objects.requireNonNull(material);
        }

        KeyEntry withState(State next) {
            return new KeyEntry(ref, tenant, purpose, next, material);
        }
    }

    static final class Registry {
        private final Map<KeyRef, KeyEntry> keys = new HashMap<>();
        private KeyRef activeWriteRef;

        synchronized void initialize(KeyEntry initial) {
            if (!keys.isEmpty() || initial.state() != State.ACTIVE) {
                throw new IllegalStateException("Invalid initialization");
            }
            keys.put(initial.ref(), initial);
            activeWriteRef = initial.ref();
        }

        synchronized void rotate(KeyEntry next) {
            KeyEntry current = keys.get(activeWriteRef);
            if (current == null || current.state() != State.ACTIVE
                    || next.state() != State.ACTIVE
                    || !next.ref().id().equals(current.ref().id())
                    || next.ref().version() <= current.ref().version()
                    || !next.tenant().equals(current.tenant())
                    || !next.purpose().equals(current.purpose())
                    || keys.containsKey(next.ref())) {
                throw new IllegalArgumentException("Invalid rotation");
            }
            keys.put(current.ref(), current.withState(State.READ_ONLY));
            keys.put(next.ref(), next);
            activeWriteRef = next.ref();
        }

        synchronized void suspend(KeyRef ref) {
            KeyEntry old = keys.get(ref);
            if (old == null) {
                throw new IllegalArgumentException("Unknown key");
            }
            keys.put(ref, old.withState(State.SUSPENDED));
        }

        synchronized KeyEntry get(KeyRef ref) {
            KeyEntry key = keys.get(ref);
            if (key == null) {
                throw new SecurityException("Unknown key reference");
            }
            return key;
        }

        synchronized KeyRef activeWriteRef() {
            return activeWriteRef;
        }
    }

    record Identity(
            String service,
            String tenant,
            boolean authenticated,
            Set<String> authorizedRecords) {
        Identity {
            Objects.requireNonNull(service);
            Objects.requireNonNull(tenant);
            authorizedRecords = Set.copyOf(authorizedRecords);
        }
    }

    record Envelope(
            int formatVersion,
            String algorithm,
            String tenant,
            String recordId,
            KeyRef keyRef,
            long revision,
            byte[] nonce,
            byte[] ciphertextWithTag) {
        Envelope {
            Objects.requireNonNull(algorithm);
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(recordId);
            Objects.requireNonNull(keyRef);
            nonce = Objects.requireNonNull(nonce).clone();
            ciphertextWithTag =
                    Objects.requireNonNull(ciphertextWithTag).clone();
        }

        @Override
        public byte[] nonce() {
            return nonce.clone();
        }

        @Override
        public byte[] ciphertextWithTag() {
            return ciphertextWithTag.clone();
        }
    }

    static final class Store {
        private final Map<String, Envelope> records = new HashMap<>();

        synchronized void insert(Envelope envelope) {
            if (records.putIfAbsent(
                    envelope.recordId(), envelope) != null) {
                throw new IllegalStateException("Record already exists");
            }
        }

        synchronized boolean compareAndSet(
                String recordId, long expectedRevision,
                Envelope replacement) {
            Envelope current = records.get(recordId);
            if (current == null || current.revision() != expectedRevision
                    || !current.recordId().equals(replacement.recordId())
                    || !current.tenant().equals(replacement.tenant())
                    || replacement.revision() != expectedRevision + 1) {
                return false;
            }
            records.put(recordId, replacement);
            return true;
        }

        synchronized Envelope load(String recordId) {
            return records.get(recordId);
        }
    }

    private static SecretKey newAesKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    private static void putString(
            DataOutputStream out, String field) throws Exception {
        byte[] encoded = field.getBytes(StandardCharsets.UTF_8);
        out.writeInt(encoded.length);
        out.write(encoded);
    }

    // AAD không nhập nhằng và gắn đúng material version.
    private static byte[] contentAad(
            String tenant, String recordId, KeyRef ref) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(FORMAT_VERSION);
            putString(out, PURPOSE);
            putString(out, ALGORITHM);
            putString(out, tenant);
            putString(out, recordId);
            putString(out, ref.id());
            out.writeInt(ref.version());
        }
        return bytes.toByteArray();
    }

    // Trong production: identity và quyền record phải đến từ IdP/
    // authorization layer đáng tin, không phải request body.
    private static void requireResource(
            Identity caller, String tenant, String recordId,
            boolean write) {
        if (caller == null || !caller.authenticated()
                || !caller.tenant().equals(tenant)
                || !caller.authorizedRecords().contains(recordId)) {
            throw new SecurityException("Resource access denied");
        }
        if (write
                && !Set.of("writer", "migration").contains(
                        caller.service())) {
            throw new SecurityException("Write not allowed");
        }
        if (!write
                && !Set.of("reader", "migration").contains(
                        caller.service())) {
            throw new SecurityException("Read not allowed");
        }
    }

    private static void requireKeyScope(
            KeyEntry key, String tenant) {
        if (!key.tenant().equals(tenant)
                || !PURPOSE.equals(key.purpose())) {
            throw new SecurityException("Key scope denied");
        }
    }

    // Public Write API chọn active version; không nhận arbitrary keyRef.
    static Envelope encryptNew(
            Registry registry, Identity caller, String recordId,
            byte[] plaintext) throws Exception {
        return encryptWithRef(registry, caller, recordId,
                plaintext, registry.activeWriteRef(), 1);
    }

    // Helper chỉ dùng nội bộ trong demo cho migration/negative test.
    private static Envelope encryptWithRef(
            Registry registry, Identity caller, String recordId,
            byte[] plaintext, KeyRef ref, long revision)
            throws Exception {
        Objects.requireNonNull(plaintext);
        requireResource(caller, caller.tenant(), recordId, true);
        KeyEntry key = registry.get(ref);
        requireKeyScope(key, caller.tenant());
        if (key.state() != State.ACTIVE
                || !ref.equals(registry.activeWriteRef())) {
            throw new SecurityException("Key not valid for new Encrypt");
        }

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key.material(),
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(contentAad(caller.tenant(), recordId, ref));
        byte[] ciphertext = cipher.doFinal(plaintext);
        return new Envelope(
                FORMAT_VERSION, ALGORITHM, caller.tenant(), recordId,
                ref, revision, nonce, ciphertext);
    }

    static byte[] readHistorical(
            Registry registry, Identity caller, String recordId,
            Envelope envelope) throws Exception {
        Objects.requireNonNull(envelope);
        requireResource(caller, envelope.tenant(), recordId, false);
        if (envelope.formatVersion() != FORMAT_VERSION
                || !ALGORITHM.equals(envelope.algorithm())
                || !recordId.equals(envelope.recordId())
                || envelope.revision() < 1
                || envelope.nonce().length != NONCE_BYTES
                || envelope.ciphertextWithTag().length < TAG_BITS / 8) {
            throw new SecurityException("Invalid envelope");
        }
        KeyEntry key = registry.get(envelope.keyRef());
        requireKeyScope(key, envelope.tenant());
        if (key.state() != State.ACTIVE
                && key.state() != State.READ_ONLY) {
            throw new SecurityException("Historical key not usable");
        }

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key.material(),
                new GCMParameterSpec(TAG_BITS, envelope.nonce()));
        cipher.updateAAD(contentAad(
                envelope.tenant(), envelope.recordId(),
                envelope.keyRef()));
        // doFinal xác minh authentication tag trước khi trả plaintext.
        return cipher.doFinal(envelope.ciphertextWithTag());
    }

    static Envelope migrateToCurrent(
            Registry registry, Identity migrationIdentity,
            String recordId, Envelope old) throws Exception {
        requireResource(
                migrationIdentity, old.tenant(), recordId, true);
        byte[] plaintext = readHistorical(
                registry, migrationIdentity, recordId, old);
        try {
            // Fresh nonce + current active key. Không chỉ đổi keyRef!
            return encryptWithRef(
                    registry, migrationIdentity, recordId, plaintext,
                    registry.activeWriteRef(), old.revision() + 1);
        } finally {
            Arrays.fill(plaintext, (byte) 0); // Best effort.
        }
    }

    public static void main(String[] args) throws Exception {
        Registry registry = new Registry();
        KeyRef v1 = new KeyRef("tenant-42-content-key", 1);
        KeyRef v2 = new KeyRef("tenant-42-content-key", 2);
        registry.initialize(new KeyEntry(
                v1, "tenant-42", PURPOSE, State.ACTIVE, newAesKey()));

        Identity writer = new Identity(
                "writer", "tenant-42", true,
                Set.of("invoice-A", "invoice-B"));
        Identity reader = new Identity(
                "reader", "tenant-42", true,
                Set.of("invoice-A", "invoice-B"));
        Identity migrator = new Identity(
                "migration", "tenant-42", true,
                Set.of("invoice-A"));
        Identity wrongTenant = new Identity(
                "reader", "tenant-OTHER", true,
                Set.of("invoice-A"));

        byte[] payload = "Example only; no customer data"
                .getBytes(StandardCharsets.UTF_8);
        Store store = new Store();
        try {
            Envelope old = encryptNew(
                    registry, writer, "invoice-A", payload);
            store.insert(old);

            // Rotation: v1 READ_ONLY; v2 ACTIVE.
            registry.rotate(new KeyEntry(
                    v2, "tenant-42", PURPOSE, State.ACTIVE, newAesKey()));
            Envelope newer = encryptNew(
                    registry, writer, "invoice-B", payload);
            store.insert(newer);

            System.out.println("New writes use v2: "
                    + (newer.keyRef().version() == 2));

            byte[] restoredOld = readHistorical(
                    registry, reader, "invoice-A", store.load("invoice-A"));
            try {
                System.out.println("Old v1 remains readable: "
                        + Arrays.equals(payload, restoredOld));
            } finally {
                Arrays.fill(restoredOld, (byte) 0);
            }

            try {
                encryptWithRef(
                        registry, writer, "invoice-A",
                        payload, v1, 2);
                throw new AssertionError("Old key used for Encrypt");
            } catch (SecurityException expected) {
                System.out.println("Old v1 cannot Encrypt: true");
            }

            try {
                readHistorical(registry, wrongTenant, "invoice-A", old);
                throw new AssertionError("Cross-tenant read allowed");
            } catch (SecurityException expected) {
                System.out.println("Cross-tenant read denied: true");
            }

            byte[] changed = old.ciphertextWithTag();
            changed[0] ^= 1;
            Envelope tampered = new Envelope(
                    old.formatVersion(), old.algorithm(), old.tenant(),
                    old.recordId(), old.keyRef(), old.revision(),
                    old.nonce(), changed);
            try {
                readHistorical(registry, reader, "invoice-A", tampered);
                throw new AssertionError("Tampered content accepted");
            } catch (AEADBadTagException expected) {
                System.out.println("Tampered ciphertext rejected: true");
            }

            Envelope migrated = migrateToCurrent(
                    registry, migrator, "invoice-A", old);
            boolean updated = store.compareAndSet(
                    "invoice-A", old.revision(), migrated);
            System.out.println("CAS migration committed: " + updated);
            System.out.println("Migrated uses v2: "
                    + (store.load("invoice-A").keyRef().version() == 2));

            // Retry dựa trên revision cũ bị từ chối.
            boolean staleUpdate = store.compareAndSet(
                    "invoice-A", old.revision(), migrated);
            System.out.println("Stale CAS rejected: " + !staleUpdate);

            registry.suspend(v1);
            try {
                readHistorical(registry, reader, "invoice-A", old);
                throw new AssertionError("Suspended key still usable");
            } catch (SecurityException expected) {
                System.out.println("Suspended v1 read denied: true");
            }

            byte[] migratedPlaintext = readHistorical(
                    registry, reader, "invoice-A",
                    store.load("invoice-A"));
            try {
                System.out.println("Migrated v2 decrypt succeeds: "
                        + Arrays.equals(payload, migratedPlaintext));
            } finally {
                Arrays.fill(migratedPlaintext, (byte) 0);
            }
        } finally {
            Arrays.fill(payload, (byte) 0);
        }
    }
}
~~~

Lưu thành **ReadWithOldKeyDemo.java** rồi chạy bằng JDK 17+:

~~~bash
javac ReadWithOldKeyDemo.java
java ReadWithOldKeyDemo
~~~

Kết quả logic mong đợi:

~~~text
New writes use v2: true
Old v1 remains readable: true
Old v1 cannot Encrypt: true
Cross-tenant read denied: true
Tampered ciphertext rejected: true
CAS migration committed: true
Migrated uses v2: true
Stale CAS rejected: true
Suspended v1 read denied: true
Migrated v2 decrypt succeeds: true
~~~

### 11.1. Vì sao Read không dùng current key?

Trong **readHistorical**, key được tra theo **envelope.keyRef()**; **không có đoạn nào tự thay v1 bằng v2**. Đó là lý do bản mã cũ vẫn đọc được sau rotation.

Trong **encryptNew**, hệ thống luôn chọn **registry.activeWriteRef()**, còn helper nội bộ kiểm tra **key.state == ACTIVE** và ref đúng active. Nhờ vậy **không tạo thêm ciphertext mới dưới v1** khi v1 đã READ_ONLY.

### 11.2. Vì sao AAD có key ID/version?

AAD encode **purpose, algorithm, tenant, record và immutable keyRef/version** nên việc thay các metadata này mà không tạo lại ciphertext/tag có thể gây authentication failure. Cùng lúc, **IAM/resource authorization** vẫn phải kiểm tra trước khi dùng key, vì AAD không chứng minh quyền của caller.

### 11.3. Vì sao phải CAS khi migration?

Nếu một writer vừa cập nhật invoice-A sau khi migration worker đọc revision cũ, worker không được ghi đè payload mới bằng plaintext cũ. **CAS theo revision** giúp từ chối update stale. Trong production, cần transaction/storage semantics thật, idempotent retry và kiểm tra các bản sao ở database/queue/backup.

### 11.4. Những giới hạn của Java demo

1. **Không có KMS/HSM**: AES keys được tạo/giữ trong JVM; key versions trong HashMap không phải provider versions thực.
2. **Không có IAM/IdP**: Identity chứa boolean authenticated và Set record IDs được tạo trong source; production phải dùng authenticated workload/user identity và resource authorization thực.
3. **Không có encrypted DEK/KEK**: demo chỉ mô phỏng trực tiếp data key rotation. Envelope encryption cần thêm wrapped DEK, KEK reference và context phù hợp.
4. **Không có hard cryptoperiod deadline**: State READ_ONLY được set lúc rotate nhưng một provider thực cần enforce originator usage period/IAM theo policy.
5. **Không có durable persistence**: Store HashMap mất khi process restart. Production cần database/backup với keyRef/version và transactional migration.
6. **Không có trust boundary chống RCE**: Một process kiểm soát registry có thể đọc SecretKey hoặc gọi JCA trực tiếp; cần provider enforcement hoặc crypto gateway.
7. **Nonce ngẫu nhiên 96 bit không bảo đảm tuyệt đối không trùng**: số lượng Encrypt trên một key và multi-replica strategy phải được đánh giá; demo chỉ có ít lời gọi.
8. **Key material không được zeroize tuyệt đối**: SecretKey/Cipher/provider có thể giữ bản sao; Arrays.fill chỉ cleanup payload byte[] mà code sở hữu.
9. **Không có kiểm soát ciphertext size/DoS hoàn chỉnh**: demo chỉ kiểm tra tối thiểu GCM tag/nonce, production cần bounds, quotas, schema validation.
10. **Không chống rollback bằng AEAD**: một envelope cũ hợp lệ có thể được replay; store revision có ý nghĩa khi được bảo vệ và so với nguồn tin cậy.
11. **Không có backup/DR, multi-region state propagation, policy revision và audit bền vững**.
12. **Không có test cryptographic assurance/provider compliance**: chỉ minh họa API JCA Java 17 và kiến trúc read-old/write-new.
13. **Không có điều tra compromise**: state SUSPENDED được demo đặt thủ công; trong thực tế decision phải dựa trên incident/approval/retention.
14. **Không có chống đồng thời tại KMS/key rotation**: Registry dùng synchronized trong cùng JVM, không bảo vệ nhiều replicas/regions.

**Điểm cốt lõi của ví dụ:** Quá trình rotation phải **giữ key mapping đúng cho dữ liệu cũ**, **ngừng tạo dữ liệu mới với key cũ** và **đổi thực sự ciphertext/material khi migrate**, chứ không chỉ thay tên hoặc số version.

## 12. Threat model: Sai lầm thường gặp khi đọc dữ liệu bằng khóa cũ

| Sai lầm / nguy cơ | Hậu quả | Hướng kiểm soát |
|---|---|---|
| **Chỉ dùng alias current-key để Decrypt** | Gọi nhầm material v2 trên ciphertext v1, authentication fail | Lưu đúng immutable keyRef/version hoặc provider ciphertext blob |
| **Xóa v1 ngay khi active v2** | Record/archive/backup v1 không thể đọc | Key dependency inventory, restore drill, retirement policy |
| **Để v1 tiếp tục Encrypt mới** | Dependency vào key cũ tăng, originator cryptoperiod bị phá | Single-write active-key policy, provider enforcement khi hỗ trợ |
| **Key cũ dùng cho mọi tenant** | Reader có thể Unwrap/Decrypt cross-tenant | Tenant-scoped key policy và resource authorization |
| **Tin keyVersion từ request body** | Attacker ép service chọn keys ngoài phạm vi | Resolve từ trusted stored envelope và authenticated record |
| **Thử mọi key khi Decrypt lỗi** | Key enumeration/oracle, DoS, audit mơ hồ | Deterministic key lookup, quarantine legacy data |
| **Chỉ sửa version field khi migrate** | Ciphertext/tag không khớp key material mới | Decrypt + fresh Encrypt hoặc đúng server-side rewrap |
| **Rewrap KEK và cho rằng DEK đã rotate** | DEK lộ vẫn giải mã được content | Phân biệt DEK/KEK; re-encrypt khi thay DEK |
| **Đưa KEK version vào content AAD rồi rewrap** | Authentication tag sai khi metadata KEK đổi | Tách content AAD và wrapping context |
| **Dùng lại GCM nonce sau restore/retry** | Có thể phá confidentiality và integrity | Unique nonce per key across replicas/restarts |
| **Migration overwrite record revision mới** | Mất cập nhật hợp lệ, không nhất quán | CAS/ETag/transaction và idempotency |
| **Giữ plaintext DEK v1 trong cache vô hạn** | Disable KMS không ngăn offline decrypt | TTL/lease/capacity, key state reconciliation |
| **KMS role Decrypt all để “hỗ trợ legacy”** | RCE hoặc confused deputy có thể đọc nhiều tenants | Purpose/key scope, IAM tối thiểu, audit |
| **Đổi signing key và xóa public key cũ** | Không Verify chữ ký hợp lệ trong retention | Historical trust/public-key retention theo protocol |
| **Giữ private signing key cũ để Verify** | Không cần thiết; tăng nguy cơ Sign trái phép | Verifier giữ public key, private Sign key retire |
| **Cho HMAC v1 Verify vô hạn** | Shared secret cũ vẫn có thể tạo MAC, replay risk | Grace window hữu hạn, anti-replay và rotation |
| **Chấp nhận JWT cũ vì kid còn trong JWKS** | Có thể chấp nhận token hết hạn/thu hồi | Verify issuer/audience/exp/trust và token policy |
| **Tái sử dụng key bị compromised do còn archive** | Tiếp tục exposure, trust sai | Incident-approved recovery và migration |
| **KMS revoke xong nghĩ mọi cached DEK đã chết** | DEK đã unwrap vẫn dùng offline | Workload controls, cache invalidation, session/lease policy |
| **Backup thiếu EDK hoặc key versions** | DR không thể mở dữ liệu lịch sử | Restore test kiểm tra đủ crypto metadata/material |
| **Legacy metadata mơ hồ được đoán từ createdAt** | Lỗi key resolution hoặc dùng sai key | Evidence-based mapping và controlled migration |
| **Log raw DEK/KEK khi debug lỗi tag** | Tạo bản copy secret ngoài kiểm soát | Log metadata only, secure diagnostic artifacts |
| **Xem AEAD tag là chống rollback** | Bản mã cũ hợp lệ được replay vào record mới | Trusted revision/anti-rollback policy |
| **Cho migration worker giữ quyền Decrypt v1 vô thời hạn** | Tăng rủi ro lạm dụng key lịch sử | Temporary grants, allowlisted batches, approvals |
| **Provider state/version được giả định sai** | Read cũ thất bại hoặc lộ quyền crypto mới | Kiểm tra provider semantics và negative tests |

### 12.1. Key-confusion từ metadata chưa tin cậy

~~~text
Caller muốn đọc record tenant-B.
Caller tự gửi:
    tenantId = tenant-B
    keyId = tenant-B-KEK
    keyVersion = 2

Service chỉ kiểm tra JWT workload identity của chính nó:
    KMS role cho Unwrap mọi KEK
    không kiểm tra caller có quyền record
    gọi KMS Unwrap trước khi resource authorization

=> Service có nguy cơ trở thành confused deputy.
~~~

**Giải pháp:** trước khi KMS Unwrap, xác thực **caller/record ownership**, sau đó resolve key version từ envelope/registry đáng tin, kiểm tra tenant/purpose và provider IAM. **Content AAD giúp phát hiện metadata không khớp với bản mã**, nhưng không thay thế authorization.

### 12.2. Key compromise không có rollback thần kỳ

Nếu attacker đã lấy **DEK-v1** và bản sao ciphertext-v1, việc doanh nghiệp:

1. Tạo DEK-v2;
2. Mã hóa lại primary DB bằng v2;
3. Xóa DEK-v1 khỏi production;

không làm attacker **mất khả năng đọc ciphertext-v1 đã sao chép**. Rotation/re-encryption giúp giới hạn **dữ liệu lưu mới và phạm vi tấn công tương lai**, không thể thu hồi toàn bộ thông tin đã lộ. Cần đánh giá exposure, thông báo/biện pháp ứng phó theo quy trình áp dụng.

## 13. Kiểm thử Read với key cũ và rotation

### 13.1. Test matrix

| Test case | Kết quả kỳ vọng | Mục tiêu kiểm tra |
|---|---|---|
| Encrypt record A bằng v1 trước rotation | Ciphertext có keyRef v1 | Material và metadata ban đầu |
| Rotate v1 → v2 | v1 historical read, v2 new write | Key state transition |
| Encrypt mới sau rotation | **Chỉ v2**, không v1 | Single-write policy |
| Decrypt record A cũ bằng v1 | **Thành công** với đúng quyền | Multi-read historical version |
| Decrypt record B mới bằng v2 | **Thành công** | Current key path |
| Cố Encrypt bằng v1 READ_ONLY | **DENY** | Không kéo dài originator cryptoperiod |
| Reader dùng v1 của tenant B | **DENY** | Tenant/IAM isolation |
| Caller biết key ID nhưng không có record permission | **DENY trước Unwrap** | Resource authorization |
| Đổi keyVersion trong envelope từ v1 sang v2 | **DENY/tag failure**, không trả plaintext | Immutable reference + AAD |
| Đổi nonce, ciphertext hoặc AAD | **AEAD authentication failure** | Integrity |
| Key v1 SUSPENDED | **DENY historical decrypt** theo policy | Key state |
| KMS key Disabled nhưng local DEK cache còn | Cache xử lý theo lease/invalidation policy | Revocation lag |
| Rewrap EDK từ KEK-v3 sang KEK-v4 | Vẫn Decrypt đúng content DEK, payload không đổi | KEK rotation |
| Re-encrypt record từ DEK-v1 sang DEK-v2 | Ciphertext/nonce/tag/keyRef mới, plaintext tương đương | DEK rotation |
| CAS migration gặp revision mới | **Không overwrite**, retry/reload | Concurrency |
| Worker retry sau timeout | Không lặp nonce nguy hiểm hoặc sửa nhầm record | Idempotency, nonce usage |
| Record legacy thiếu version | Quarantine/migration có kiểm soát | No arbitrary brute-force keys |
| Backup một tháng trước rotation | Restore đủ v1 material, EDK, metadata và quyền | DR |
| Signing key v1 retired | Không Sign mới, public key Verify lịch sử theo trust | Asymmetric lifecycle |
| HMAC secret v1 hết grace | Không Generate/Verify MAC v1 ngoài policy | Shared secret lifecycle |
| JWT v1 còn key nhưng token hết hạn | **DENY** | Token validity độc lập rotation |
| KMS outage trong read old record | Fail closed/approved DR/lease bounded | Availability vs security |
| Legacy key chính thức compromised | Incident path, không tự bật read | Risk response |

### 13.2. Negative tests quan trọng hơn một round-trip

Một test **Encrypt v1 → Decrypt v1** thành công chỉ chứng minh một đường cơ bản. Sau rotation, phải thử:

- **Từ chối Encrypt v1** ở application và **provider boundary nếu có khả năng enforce**.
- **Từ chối Unwrap/Decrypt** khi tenant, record, identity hoặc key purpose sai.
- **Từ chối old key đã Disabled/Suspended** theo trạng thái thực tế.
- **Tránh đổi key ID/version bằng untrusted payload**.
- **Bắt AEADBadTagException** mà không trả plaintext một phần.
- **Không chấp nhận stored ciphertext revision cũ** nếu business policy yêu cầu chống rollback.
- **Không lộ thông tin chi tiết về key existence** trong error message đối ngoại.

Nếu chỉ kiểm tra Java application policy mà KMS role còn cho phép caller **Decrypt old key trực tiếp**, RCE có thể bypass. Cần thử **direct API path** trong môi trường test và theo đúng provider contract.

### 13.3. Kiểm thử restore thay vì chỉ tin backup

Một bài DR drill nên có:

1. Một record v1 **chưa re-encrypt**.
2. Một record v1 **đã rewrap EDK** sang KEK mới.
3. Một record **đã re-encrypt DEK-v2**.
4. Một chữ ký cũ cần **public-key Verify**.
5. Một key **retired** với historical-use policy.
6. Một key **disabled** phải từ chối operations.
7. Một bản backup ở region/partition khác với access policy được phê duyệt.

Đo **RTO, key restore availability, integrity verification và ability to deny unauthorized callers**. Không xem việc backup tool trả “success” là bằng chứng historical Decrypt thực sự hoạt động.

## 14. Audit và monitoring khi nhiều key versions cùng tồn tại

### 14.1. Những thông tin nên có trong audit event

| Field | Vì sao cần |
|---|---|
| Principal/service identity | Ai đã thực hiện historical read |
| Tenant, resourceRef, requestId | Gắn operation với quyền dữ liệu |
| Key family và **immutable key version** | Chứng minh đang dùng v1/v2 đúng mục đích |
| Algorithm, key purpose, envelope format | Phát hiện key/algorithm confusion |
| Operation ENCRYPT/DECRYPT/WRAP/UNWRAP | Phân biệt new-use và historical-use |
| Key state/cryptoperiod decision | Tìm sử dụng key retired cho Encrypt mới |
| Policy revision và effectiveAt | Điều tra stale permissions |
| KMS provider request ID/outcome | Đối soát application với data plane |
| Migration revision/batch/checkpoint | Chống ghi đè dữ liệu và đo tiến độ |
| Reason/outcome của lỗi integrity | Phát hiện tampering hoặc lỗi format |

**Không ghi** raw DEK/KEK, HMAC secret, private key, plaintext record, KMS Decrypt response hoặc token. **Key ID** có thể tiết lộ topology/tenant; audit logs vẫn cần access controls và retention.

### 14.2. Chỉ số hữu ích

- **Tỷ lệ Encrypt mới sử dụng active key** — mục tiêu là không còn Encrypt dưới retired versions.
- **Số ciphertext/EDK còn phụ thuộc từng old key version** theo tenant, storage, backup.
- **Lượt historical Decrypt/Unwrap** theo principal, key version và resource scope.
- **Số migration CAS conflicts**, retries, failures và records chưa chuyển.
- **KMS Unwrap errors** và tỷ lệ AEAD authentication failures sau rotation.
- **Stale key-state cache age/propagation lag** giữa instances/regions.
- **Số grants vẫn cho phép Encrypt bằng retired key** hoặc Decrypt quá phạm vi.
- **Restore drill coverage** cho key versions đã nghỉ.
- **Số raw DEK leases sống** và lifetime vi phạm policy.
- **Key dependency count trước lệnh Destroy**, bao gồm archive/backup.
- **Số JWT/verifier cần old public keys** và HMAC consumers còn chấp nhận secret cũ.

Metric **không có old-key reads trong 30 ngày** không chứng minh đã an toàn để hủy. Dữ liệu archive có thể chỉ được đọc nhiều năm một lần hoặc đang chịu legal hold.

### 14.3. Ngăn “read-only” bị dùng làm lối đi vĩnh viễn

Từng old key nên có:

- **Owner và reason để tiếp tục historical use**.
- **Expected remaining dependencies** và giới hạn ngày review.
- **Allowed operations/principals** được kiểm tra.
- **Retention/legal constraints**.
- **Migration plan** nếu cần giảm rủi ro.
- **Backup/restore references** và audit evidence.
- **Incident flag** nếu key có dấu hiệu compromised hoặc tampering.

Một key được để trạng thái READ_ONLY vô thời hạn **không tự là lỗ hổng** nếu archive phải lưu dài hạn và policy bảo vệ tốt; nhưng thiếu owner, review, IAM scope hoặc khả năng restore là rủi ro vận hành lớn.

## 15. Case study: Customer Data Platform sau ba lần rotation

### 15.1. Bối cảnh

Một công ty lưu hồ sơ khách hàng, hóa đơn và bản sao lưu nhiều năm:

~~~text
2024: DEK-v1 cho một tập records
2025: DEK-v2 cho records mới
2026: DEK-v3 cho records mới

KEK:
  tenant-a-kek-v5 bảo vệ nhiều EDK cũ
  tenant-a-kek-v6 đang ACTIVE cho EDK mới

Storage:
  DB chính, object archive, nightly backup, DR replica

Service:
  Java Customer API, background migration worker, KMS/HSM
~~~

Mọi người thống nhất cần chuyển **write** sang DEK-v3. Tuy nhiên, một script migration chỉ đổi config **CURRENT_DEK_VERSION=3** rồi xóa DEK-v1 trong secret store. Các record cũ có ciphertext dưới v1 không thể Decrypt. Nhóm vận hành thử đổi key ID trong database sang v3, khiến GCM tag vẫn sai.

**Lỗi gốc** là coi rotation là **đổi config hiện tại**, bỏ qua **dependency của ciphertext lịch sử và key material**.

### 15.2. Thiết kế sửa lỗi

**Bước 1 — Inventory theo material/version.** Đếm mọi record có content DEK-v1/v2/v3 và mọi EDK dưới KEK-v5/v6. Phân loại cả archive, backup, replicas và legal hold.

**Bước 2 — New-use policy.** Chỉ DEK-v3 ở trạng thái ACTIVE được dùng Encrypt payload mới. v1/v2 được phép historical Decrypt theo principal/tenant/record policy, trừ key nào đã compromised/suspended.

**Bước 3 — Format metadata.** Mỗi envelope lưu format/algorithm, immutable content keyRef/version, nonce/tag, wrapping keyRef/blob và AAD schema. Không dùng alias current làm reference lịch sử.

**Bước 4 — Key resolver.** Crypto service nhận key ID/version từ envelope đã validate; registry và KMS xác định correct material và usage state. IAM/authorization chặn cross-tenant và read ngoài quyền.

**Bước 5 — Rewrap KEK cũ nếu cần.** EDK dưới KEK-v5 có thể được rewrap sang KEK-v6 theo provider contract mà không đổi DEK. Content ciphertext và content AAD giữ nguyên.

**Bước 6 — Re-encrypt DEK legacy nếu cần.** Worker đọc bằng v1/v2, mã hóa lại bằng v3 và nonce mới, cập nhật atomic envelope qua CAS. Ghi audit migration outcome, retry có giới hạn.

**Bước 7 — Validate.** Đọc thử đại diện các versions cũ và mới; test wrong-tenant, tampered ciphertext, disabled key, KMS outage và concurrent updates.

**Bước 8 — DR và retention.** Backup cũ cần KEK-v5/DEK-v1 không được bỏ trước khi restore test và dependency review. Record đã chuyển v3 tại DB chưa nói rằng backup cũ không cần v1.

**Bước 9 — Decommission.** Khi tất cả đường cần historical Decrypt đã chuyển, owner/security approvers xem xét Disable/Destroy v1/v2 theo policy và luật retention; giữ tombstone/audit cần thiết.

### 15.3. Một yêu cầu đọc đặc biệt

Giả sử kiểm toán viên có quyền xem **invoice-A năm 2024**, nhưng không có quyền trên các hóa đơn của tenant B. Read path đúng:

~~~text
Auditor identity -> role + tenant A + invoice-A read authorization
        |
        v
Load envelope(invoice-A) -> contentKeyRef DEK-v1
        |
        v
Check DEK-v1 historical usage state
        |
        v
KMS Unwrap EDK bằng đúng KEK reference và context
        |
        v
AES-GCM Decrypt bằng DEK-v1 + nonce + content AAD
        |
        v
Return invoice-A, audit purpose = AUTHORIZED_ARCHIVE_READ
~~~

**Đừng cấp cho auditor raw KEK hay private key** chỉ vì cần đọc một tài liệu. Nếu người dùng chỉ cần xem hóa đơn qua application, service có thể thực hiện crypto trong boundary và trả nội dung đã được kiểm soát theo quyền nghiệp vụ.

### 15.4. Điều gì nếu DEK-v1 bị xác nhận lộ?

Khi v1 **COMPROMISED**, doanh nghiệp không tiếp tục read-old bình thường rồi chỉ tăng audit. Phải:

1. Khóa phạm vi key v1, user/services/host và các records phụ thuộc.
2. Cô lập credential/process, kiểm tra log/dump/storage access theo incident procedure.
3. Xác định attacker có thể sở hữu ciphertext nào.
4. Ưu tiên migration sang material mới theo risk, nhưng không tuyên bố các bản mã attacker đã sao chép “được bảo vệ lại”.
5. Kiểm tra mọi KEK/EDK backup và provider key usage.
6. Điều chỉnh chính sách archive access/trust khi cần, với approval và documentation.

**Khác biệt trọng tâm:** v1 **RETIRED nhưng vẫn đáng tin** có thể được dùng để historical Decrypt. v1 **COMPROMISED** cần một luồng xử lý rủi ro riêng, không nên được coi là “read-only an toàn”.

## 16. Runbook vận hành Read với key cũ

### 16.1. Trước rotation

1. **Xác định phạm vi:** Key family, algorithm, owner, tenant, purpose, material version hiện tại và các producers/consumers.
2. **Phân biệt loại rotation:** DEK, KEK, signing key, HMAC, KDF root, certificate hay credential?
3. **Liệt kê dependencies:** ciphertext, EDK, backup, archives, snapshots, JWKS/verifiers và recipients nếu liên quan.
4. **Định nghĩa new-use cryptoperiod:** thời gian dừng Encrypt/Sign bằng material cũ.
5. **Định nghĩa historical-use policy:** principal nào vẫn cần Decrypt/Verify, đến khi nào và trạng thái nào được phép?
6. **Xác nhận provider semantics:** API Key ID/version, aliases, automatic rotation, ciphertext blob, grace period, deletion/restore behavior.
7. **Lập kế hoạch failure:** rollback không phá metadata, KMS outage, key-state propagation, migration concurrency.
8. **Bảo đảm backup/DR:** test restore record tiêu biểu bằng key cũ trước khi chuyển trạng thái.

### 16.2. Khi rotation

~~~text
T0: Create/activate new material vNext.
T1: Verify new key algorithm/purpose/IAM and positive tests.
T2: Switch new encryption/signing to vNext.
T3: Mark old material READ_ONLY under approved policy.
T4: Verify:
    - New Encrypt selects vNext
    - Old Decrypt still selects vOld
    - Old Encrypt denied
    - Wrong tenant/principal denied
    - KMS provider/audit decisions aligned
T5: Record effectiveAt, policy revision, key IDs and owner.
~~~

**T2 và T3 phải có consistency plan**. Trong hệ thống nhiều instances, một pod còn config cũ có thể tiếp tục Encrypt bằng vOld. Cần controlled rollout, desired-state reconciliation và provider-level restrictions nếu rủi ro yêu cầu.

### 16.3. Sau rotation

- Theo dõi **không còn Encrypt mới với old key** và số old-key Decrypt đang hợp lệ.
- Theo dõi **ciphertext/EDK dependency counts** tại primary, archive, backup.
- Quản trị **migration** theo batch, CAS, error handling và checkpoint.
- Giới hạn **cache TTL** của historical DEK; rà revoke/disable behavior.
- Theo dõi **KMS API denial, stale alias, unknown version, wrong AAD**.
- Thử **read/restore** các records cũ từ những môi trường cần vận hành.
- Chỉ khi phụ thuộc đã được giải quyết mới đề xuất Destroy với approval và evidence.

### 16.4. Trước khi destroy old key

Một phiếu duyệt Destroy nên có:

~~~text
keyRef/version:
keyOwner:
reason/approval/ticket:
cryptoperiod end:
new-use stopped evidence:
remaining primary ciphertext count:
remaining archive/backup/snapshot dependencies:
rewrap/re-encrypt migration result:
provider backup/escrow/replica checks:
DR restore drill result:
legal hold / retention decision:
planned destroy effective time:
rollback/recovery limitations:
independent reviewer:
~~~

**Không destroy chỉ vì lastUsedAt cũ hoặc EDK count tại primary DB bằng 0.** Backup lịch sử, external encrypted exports hoặc dữ liệu hiếm khi đọc vẫn có thể cần old key.

### 16.5. Ứng phó khi historical Decrypt đột ngột thất bại

Runbook ngắn:

1. **Không đổi current key để thử mò**. Tạm ngừng migration tự động trên tập dữ liệu bị ảnh hưởng.
2. Xác định **key ID/version, provider, tenant, record, algorithm, schema, state** từ nguồn được bảo vệ.
3. Đối chiếu **KMS audit, key inventory, policy revisions, key rotation events**.
4. Kiểm tra **EDK/wrap context, AAD canonicalization, nonce/tag** và ciphertext integrity.
5. Phân biệt **key not found/disabled**, **permission denied**, **KMS outage** và **AEAD tag failure**.
6. Chỉ dùng **approved restore/fallback route**, không import raw KEK vào JVM tùy tiện.
7. Kiểm tra representative old/new records để xác nhận sửa lỗi không phá các versions khác.
8. Ghi audit evidence và root cause; tuyệt đối không đính kèm raw key hoặc plaintext vào ticket.

## 17. Checklist triển khai Read với key cũ

1. **Cryptoperiod:** Có tách new Encrypt/Sign period khỏi historical Decrypt/Verify period?
2. **Owner:** Mỗi old key version còn có owner, mục đích sử dụng và lý do giữ lại?
3. **Key references:** Ciphertext lưu immutable key ID/version hoặc provider blob có đủ dữ kiện để chọn material cũ?
4. **Algorithms:** Format/algorithm/nonce/tag và AAD schema được lưu hoặc tái tạo chính xác?
5. **Purpose:** DEK chỉ Content Encrypt/Decrypt, KEK chỉ Wrap/Unwrap, signing key chỉ đúng Sign/Verify purpose?
6. **No key guessing:** Không thử hàng loạt old keys để tìm key mở được record không có metadata?
7. **Single-write:** Encrypt mới chỉ dùng current ACTIVE material, không dùng READ_ONLY key?
8. **Multi-read:** Decrypt các versions lịch sử chỉ khi state và policy cho phép, không mặc định mọi old key đều khả dụng?
9. **Provider behavior:** Đã xác minh automatic rotation, key version, alias, ciphertext blob và disabled-state semantics?
10. **IAM:** Principal có quyền Decrypt/Unwrap theo key family, tenant, environment và purpose; không Export/Destroy mặc định?
11. **Business authorization:** Caller có quyền với record trước khi gọi KMS?
12. **Metadata trust:** tenant, record ID, keyRef và state được xác minh từ nguồn tin cậy, không tin HTTP body/envelope tùy ý?
13. **AAD:** Content AAD ràng buộc context bất biến, không bị thay vô tình khi chỉ rewrap KEK?
14. **Nonce:** AES-GCM Encrypt mới dùng nonce unique với cùng DEK; nếu wrap bằng GCM, wrap nonce unique với KEK?
15. **Tag:** Decrypt luôn verify AEAD authentication tag trước khi trả plaintext?
16. **Key rotation:** Có phân biệt KEK rewrap với DEK re-encrypt và public-key verification sau Sign rotation?
17. **Migration:** Batch/lazy migration có revision/CAS, bounded retries, audit và rollback có kiểm soát?
18. **Atomicity:** Ciphertext + keyRef/version + nonce/tag + metadata luôn được ghi nhất quán?
19. **Old-key permissions:** READ_ONLY key không còn Encrypt mới; nếu provider thiếu native state, gateway/IAM có kế hoạch chặn bypass?
20. **Compromise:** Không giữ đọc bình thường bằng material đã bị lộ; có incident-approved recovery?
21. **Cache:** Plaintext DEK cũ có TTL/size/scope, tránh giữ vô hạn hoặc tiếp tục dùng sau revoke theo policy?
22. **Drift:** Key-state và policy events có revision/effective time, ngăn stale event re-enable permission?
23. **Backups:** Ciphertext lịch sử có EDK, KEK version/material, AAD và restore path hợp lệ?
24. **DR:** Đã thử mở record thật trong test/recovery environment với old version và correct authorization?
25. **Retention:** Đã đối chiếu primary DB, backup, archives, legal hold trước khi Destroy?
26. **Audit:** Log keyRef/version, principal, action, result và migration revision mà không ghi raw keys/plaintext?
27. **Monitoring:** Thấy số old-key reads, số records còn phụ thuộc, lỗi AEAD/KMS và tiến độ migration?
28. **Concurrency:** Re-encrypt không overwrite cập nhật mới, CAS conflict được xử lý rõ?
29. **Resilience:** KMS outage có bounded retry/approved DR, không hardcode fallback KEK?
30. **JWT/Sign:** Old public key có thể Verify theo trust/expiry; private key retired không được Sign mới?
31. **HMAC:** Shared secret cũ chỉ được Verify trong grace period phù hợp, có anti-replay và không chấp nhận vô hạn?
32. **Password hashes:** Nếu có pepper rotation, đã phân biệt Verify/Rehash với AES Decrypt và không lưu plaintext password?
33. **Destruction:** Có approval, dependent-key inventory, backup/escrow review và thử restore trước lệnh hủy?
34. **Negative tests:** Old Encrypt denied, cross-tenant denied, tamper rejected, disabled key denied, stale CAS rejected?
35. **Final acceptance:** Có bằng chứng vừa **đọc được ciphertext hợp lệ** vừa **chặn được quyền ngoài phạm vi** trong data plane?

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao DEK-v1 có thể vẫn cần sau khi DEK-v2 đã ACTIVE?

**Trả lời:** Vì ciphertext đã được mã hóa bằng v1 không thể tự giải mã bằng v2. Cần giữ v1 cho historical Decrypt theo policy hoặc re-encrypt dữ liệu cũ bằng v2 trước khi retire/destroy v1.

**Câu 2.** READ_ONLY cho old key có nghĩa gì?

**Trả lời:** Đây là trạng thái/policy logic **cấm tạo ciphertext mới** bằng old key nhưng **có thể cho phép historical Decrypt** đúng quyền. Không phải KMS/HSM nào cũng có native READ_ONLY theo từng material version.

**Câu 3.** Vì sao không chỉ dùng alias current-key khi đọc ciphertext?

**Trả lời:** Alias có thể đổi mục tiêu sau rotation. Bản mã lịch sử cần đúng immutable key reference/version hoặc provider ciphertext blob có khả năng chọn material đã dùng lúc Encrypt.

**Câu 4.** Cryptoperiod của new Encrypt và thời hạn retention của ciphertext có giống nhau không?

**Trả lời:** **Không.** Key có thể ngừng tạo ciphertext mới nhưng vẫn cần mở dữ liệu lưu nhiều năm. Phải quản lý new-use period, historical-use policy và data retention riêng.

**Câu 5.** Nếu KEK-v3 rotate sang KEK-v4, content ciphertext có bắt buộc phải re-encrypt không?

**Trả lời:** **Không nhất thiết.** Có thể rewrap cùng DEK bằng KEK mới, giữ content ciphertext nếu content AAD/format cho phép; phải cập nhật EDK và wrapping metadata nhất quán.

**Câu 6.** Rewrap DEK-v1 dưới KEK mới có đổi raw DEK-v1 không?

**Trả lời:** **Không.** Rewrap chỉ thay lớp bảo vệ DEK. Muốn thay DEK cho payload cũ, phải re-encrypt bằng DEK mới hoặc cơ chế tương đương được phê duyệt.

**Câu 7.** Nếu raw DEK-v1 bị lộ, chỉ chuyển mọi EDK sang KEK-v4 có đủ không?

**Trả lời:** **Không.** Attacker đã biết DEK-v1 vẫn có thể giải mã ciphertext tương ứng; cần đánh giá re-encrypt và phạm vi dữ liệu đã có thể bị sao chép.

**Câu 8.** Làm sao service biết key version nào dùng để Decrypt một record cũ?

**Trả lời:** Từ **immutable keyRef/version trong envelope được xác thực**, hoặc provider-defined ciphertext blob/reference, rồi resolve dưới trusted registry/KMS theo scope và state được phép.

**Câu 9.** Có nên thử mọi keys v1, v2, v3 khi AEADBadTagException xuất hiện không?

**Trả lời:** **Không nên.** Cần tìm nguyên nhân keyRef/AAD/nonce/tag/context, xử lý legacy metadata bằng migration đã được phê duyệt thay vì tạo key-enumeration oracle.

**Câu 10.** AAD có thể thay kiểm tra user có quyền đọc record không?

**Trả lời:** **Không.** AAD bảo vệ integrity của context dưới AEAD, nhưng user/tenant authorization phải được kiểm tra từ identity và quyền resource trước khi gọi KMS/Decrypt.

**Câu 11.** Khi KMS Disable KEK-v1, mọi plaintext DEK-v1 đã cache trong JVM có mất hiệu lực ngay không?

**Trả lời:** **Không.** Cache có thể còn raw DEK và Decrypt offline. Cần leases/TTL/invalidation, workload/session controls và xử lý key compromise riêng.

**Câu 12.** Tại sao migration phải dùng compare-and-swap?

**Trả lời:** Vì writer có thể cập nhật record sau khi migration worker đọc revision cũ. CAS giúp ngăn worker ghi đè ciphertext mới bằng plaintext cũ.

**Câu 13.** Khi retry migration bằng AES-GCM, có được lặp lại nonce với cùng key cho plaintext khác không?

**Trả lời:** **Không.** Nonce phải unique trong các lần Encrypt dùng cùng key. Với retry, cần thiết kế state/idempotency và nonce generation tránh reuse, kể cả nhiều replicas/restore.

**Câu 14.** Một record cũ có GCM tag hợp lệ có nghĩa đây là revision mới nhất không?

**Trả lời:** **Không.** AEAD không tự chống rollback; record revision/anti-replay policy phải được bảo vệ và kiểm tra ở tầng storage/business.

**Câu 15.** Nếu xóa DEK-v1 ở primary KMS nhưng một backup còn copy material, có chắc dữ liệu đã crypto-erase không?

**Trả lời:** **Không.** Cần xét tất cả backup/escrow/replicas/cached copies và khả năng mở EDK; chỉ bỏ metadata không đủ để chứng minh key destruction.

**Câu 16.** KMS có automatic rotation thì ứng dụng có luôn phải chỉ định material version khi Decrypt không?

**Trả lời:** **Không có quy tắc chung.** Một số provider lưu thông tin material version trong opaque ciphertext blob và tự chọn version phù hợp. Phải theo provider contract, không tự dựng version.

**Câu 17.** Khi signing key-v1 hết hạn Sign mới, verifier có thể cần v1 không?

**Trả lời:** **Có thể cần public verification key v1** và trust evidence để Verify chữ ký cũ. Không cần giữ private key có quyền Sign để thực hiện Verify.

**Câu 18.** JWT có kid cũ còn tồn tại trong JWKS thì token cũ hết hạn có được chấp nhận không?

**Trả lời:** **Không.** Phải kiểm tra token expiry, issuer, audience, signature, algorithm và session/trust policy. Giữ public key cũ không kéo dài hiệu lực token.

**Câu 19.** HMAC secret cũ ở trạng thái Verify-only trong ứng dụng có bảo đảm receiver không thể tạo tag mới không?

**Trả lời:** **Không về mặt mật mã** nếu receiver vẫn giữ raw secret. HMAC là shared-key MAC; cần giới hạn grants, thời gian chấp nhận, anti-replay và rotation thực.

**Câu 20.** Password hash cũ có thể “Decrypt bằng pepper v1 rồi Encrypt bằng pepper v2” không?

**Trả lời:** **Không.** Password hashing là một chiều. Cần Verify theo version và Rehash khi người dùng cung cấp password hợp lệ, hoặc reset nếu cần; không lưu plaintext password để migrate.

**Câu 21.** Vì sao key RETIRED và key COMPROMISED không nên được xem giống nhau?

**Trả lời:** Key RETIRED có thể hết thời hạn new-use nhưng vẫn đáng tin để historical Decrypt theo policy. COMPROMISED nghĩa material/trust có nguy cơ bị lộ hoặc lạm dụng, cần incident response và không tự cho historical use bình thường.

**Câu 22.** Nếu một admin có quyền quản lý KEK, người đó có mặc nhiên được đọc mọi record mã hóa dưới KEK không?

**Trả lời:** **Không nên.** Key administration, KMS Unwrap và business record authorization là các quyền tách biệt, cần least privilege, separation of duties và audit.

**Câu 23.** Làm sao biết đã an toàn để destroy một old key?

**Trả lời:** Phải chứng minh mọi ciphertext/EDK/backup/archive/recipient còn cần material đã được xử lý theo retention; có owner approval, key inventory dependency review và restore test. Chỉ đo lastUsedAt không đủ.

**Câu 24.** Vì sao old-key read cần được audit riêng?

**Trả lời:** Để phát hiện cross-tenant access, key usage sau cryptoperiod, lạm dụng historical Decrypt, migration failures và xác định old-key dependencies trước rotation/revocation/destroy.

## 19. Tổng kết

**Read với key cũ** là điều kiện thiết yếu để **rotation không phá dữ liệu lịch sử**. Thiết kế đúng không phải “vẫn cho mọi service dùng v1”, mà là **chỉ dùng key hiện tại cho thao tác bảo vệ dữ liệu mới**, đồng thời **đọc bản mã cũ bằng chính material/version đã tạo ra nó**, dưới quyền IAM và business authorization phù hợp.

Các điểm phải ghi nhớ:

- **Cryptoperiod có nhiều khía cạnh:** dừng Encrypt/Sign mới không đồng nghĩa hủy ngay key version cũ; retention và historical Decrypt/Verify cần quản trị riêng.
- **Key reference bất biến:** ciphertext/EDK cần đủ key ID/version, algorithm, nonce/tag, AAD/context và provider metadata để chọn đúng material.
- **DEK rotation khác KEK rotation:** rewrap EDK không thay DEK; thay DEK cũ cho data at rest cần re-encrypt.
- **Historical read có ranh giới:** only authorized principal, tenant, record, key purpose và state; disabled/compromised key không tự được ngoại lệ vì archive.
- **Migration phải nhất quán:** CAS/transaction, fresh nonce, audit và dependency counting để không phá cập nhật mới hoặc mất dữ liệu.
- **DR và crypto-erasure phải xét mọi bản sao:** primary DB, backup, archive, HSM recovery, local DEK cache và consumer trust.
- **Verify khác Decrypt:** public verification key của chữ ký, HMAC secret shared và JWT token validity có lifecycle riêng; không áp cùng một chính sách cho mọi primitive.

**Điểm cốt lõi:** Sau rotation, **Encrypt mới bằng key mới; Decrypt dữ liệu cũ bằng đúng key cũ nếu còn được phép; migrate có kiểm soát; chỉ hủy khi không còn phụ thuộc hợp lệ**. Kết hợp **immutable key versions, KMS/HSM, phân quyền, kiểm tra AEAD, audit và DR** giúp hệ thống vừa bảo vệ khóa vừa tiếp tục truy cập dữ liệu lịch sử an toàn.

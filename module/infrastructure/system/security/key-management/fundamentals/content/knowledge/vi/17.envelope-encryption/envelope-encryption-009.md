# Re-wrap DEK khi rotate KEK – Thay lớp bảo vệ khóa dữ liệu trong envelope encryption

**Re-wrap DEK khi rotate KEK** là quá trình **tháo lớp bọc hiện tại của Data Encryption Key (DEK) bằng Key Encryption Key (KEK) cũ, rồi bọc lại *chính DEK đó* bằng KEK mới**, với điều kiện bảo vệ và kiểm toán phù hợp. Trong trường hợp re-wrap thuần túy, **giá trị DEK không đổi** và **ciphertext của dữ liệu nghiệp vụ cũng không đổi**; chỉ **wrapped DEK và metadata liên quan đến lớp bọc** được cập nhật.

Đây là một kỹ thuật quan trọng trong chương **Envelope encryption** thuộc module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Nó kết nối vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy** của khóa với KMS/HSM, mật mã đối xứng, chữ ký số, quản lý version, kiểm soát truy cập, backup/DR và kiểm toán.

> **Phân biệt đầu tiên cần nhớ:** **Rotate KEK** là thay khóa bảo vệ DEK; **re-wrap DEK** là chuyển lớp bảo vệ DEK sang KEK mới; còn **rotate DEK và re-encrypt dữ liệu** là thay khóa thực sự mã hóa dữ liệu. Re-wrap không chữa được việc **bản thân DEK đã bị lộ**.

## 1. Tại sao có DEK, KEK và re-wrap?

Giả sử Billing Service mã hóa một triệu hóa đơn bằng AES-GCM. Mỗi hóa đơn hoặc nhóm dữ liệu được mã hóa bằng một **DEK**, còn DEK được mã hóa hoặc bọc bằng **KEK** do KMS/HSM quản lý.

Nếu mã hóa toàn bộ dữ liệu bằng một khóa duy nhất, việc đổi khóa có thể buộc hệ thống giải mã rồi mã hóa lại khối lượng dữ liệu lớn. **Envelope encryption** tách thành hai lớp:

- **DEK:** dùng cho mã hóa/giải mã dữ liệu; chẳng hạn khóa AES-256-GCM, thường chỉ tồn tại dạng rõ trong bộ nhớ ứng dụng khi cần.
- **KEK:** dùng để **wrap/unwrap DEK**; có thể là khóa đối xứng được bảo vệ trong KMS/HSM và không xuất dưới dạng rõ vào ứng dụng.
- **Wrapped DEK:** một biểu diễn DEK đã được bảo vệ bởi KEK, thường được lưu cùng ciphertext.
- **Metadata:** key reference, phiên bản/định dạng, encryption context, nonce/tag/AAD và owner/tenant liên quan.

Khi tổ chức phải chuyển **KEK v3 → KEK v4**, DEK cũ có thể vẫn là khóa thích hợp cho dữ liệu đang lưu. Re-wrap cho phép thay lớp bảo vệ của DEK mà không phải chạm vào ciphertext lớn.

### 1.1. Mô hình trước và sau re-wrap

~~~mermaid
flowchart LR
    K3["KEK v3: cũ"] --> W3["Wrapped DEK-A (dưới v3)"]
    W3 -. "Unwrap an toàn / re-wrap" .-> W4["Wrapped DEK-A (dưới v4)"]
    K4["KEK v4: mới"] --> W4
    DEK["DEK-A: không thay đổi"] --> DATA["AES-GCM ciphertext: không thay đổi"]
    W3 -. "Cùng một DEK-A" .-> DEK
    W4 -. "Cùng một DEK-A" .-> DEK
~~~

**Điều thay đổi:** blob của wrapped DEK, KEK reference/version, sự kiện rotation và có thể là encryption context phục vụ thao tác wrap.

**Điều không thay đổi trong re-wrap thuần túy:** bytes DEK, thuật toán dùng mã hóa dữ liệu, ciphertext, nonce và authentication tag của dữ liệu.

**Ngoại lệ quan trọng:** nếu ứng dụng đã đưa **KEK reference hoặc wrapped DEK cũ vào AAD của ciphertext**, thay metadata đó có thể khiến bước xác thực dữ liệu thất bại. Khi đó phải có thiết kế AAD/migration phù hợp; không được sửa field tùy ý rồi giả định ciphertext vẫn giải mã được.

## 2. Re-wrap, rotate KEK, rotate DEK và re-encrypt khác nhau thế nào?

| Hoạt động | Key material đổi? | Ciphertext dữ liệu đổi? | Tác động chính |
| --- | --- | --- | --- |
| **Rotate KEK** | KEK mới, DEK có thể giữ nguyên. | Không tự đổi. | Có khóa bọc mới cho thao tác tiếp theo. |
| **Re-wrap DEK** | Thay KEK bảo vệ; **DEK giữ nguyên**. | Thường **không**. | Cập nhật wrapped DEK và metadata lớp bọc. |
| **Rotate DEK** | **DEK mới**. | Dữ liệu cũ chưa tự đổi. | Cần quy định sử dụng DEK mới và dữ liệu cũ được đọc thế nào. |
| **Re-encrypt dữ liệu** | Có thể dùng DEK khác hoặc scheme mới. | **Có**, ciphertext/tag/nonce thường thay. | Chuyển dữ liệu sang khóa/chế độ/định dạng mới. |
| **Đổi alias KEK** | Chưa chắc đổi material hoặc DEK. | Không. | Đổi con trỏ cho các lần gọi mới; không chứng minh dữ liệu cũ đã được migrate. |
| **Provider-managed key material rotation** | Có thể thay các thế hệ KEK nội bộ. | Tùy dịch vụ, thường dữ liệu đã mã hóa không cần đổi. | Nhà cung cấp xử lý key versions lịch sử theo hợp đồng API. |

**Không có nghĩa mọi lần rotate KEK đều bắt buộc re-wrap.** Một số KMS hỗ trợ xoay vật liệu nội bộ trong cùng key object, vẫn đọc được encrypted data key cũ mà không cần ứng dụng cập nhật từng blob. Re-wrap thường cần khi **muốn ngừng phụ thuộc vào KEK object/version cũ**, chuyển sang KEK mới ở phạm vi khác hoặc đáp ứng mục tiêu vận hành/tuân thủ cụ thể.

### 2.1. Vì sao re-wrap không giải quyết DEK compromise?

Giả sử kẻ tấn công đã lấy **DEK-A rõ**. Khi re-wrap:

~~~text
Trước:   WrappedDEK-A-v3 = Wrap(KEK-v3, DEK-A)
Sau:     WrappedDEK-A-v4 = Wrap(KEK-v4, DEK-A)

Dữ liệu: Ciphertext-A = AES-GCM-Encrypt(DEK-A, plaintext, ...)
~~~

Nếu người tấn công đã biết **DEK-A**, việc thay `Wrap(KEK-v3, DEK-A)` bằng `Wrap(KEK-v4, DEK-A)` **không lấy lại tính bí mật** của ciphertext đã bảo vệ bởi DEK-A. Cần đánh giá **tạo DEK mới, re-encrypt dữ liệu còn cần giữ bí mật** và tác động của các bản dữ liệu hoặc backup có thể đã bị đọc.

Tương tự, nếu KEK v3 bị lộ, phải đánh giá **các wrapped DEK dưới v3 mà attacker có thể tiếp cận và giải bọc**, chứ không chỉ đổi KEK reference.

## 3. Hai cách thực hiện re-wrap và ranh giới tin cậy

Về mặt khái niệm, re-wrap gồm hai bước: **unwrap DEK** từ lớp bọc cũ và **wrap cùng DEK** dưới lớp bọc mới.

### 3.1. Phương án ưu tiên: re-wrap hoặc re-encrypt bên trong KMS/HSM

Nếu nhà cung cấp hỗ trợ thao tác phù hợp, ứng dụng hoặc migration worker gửi **wrapped DEK cũ**, source key/context và destination key/context tới KMS/HSM. Dịch vụ thực hiện chuyển lớp bảo vệ trong ranh giới tin cậy và trả **wrapped DEK mới**, không trả **DEK rõ** về ứng dụng.

~~~mermaid
sequenceDiagram
    participant W as Migration worker
    participant K as KMS/HSM
    participant D as Metadata store
    W->>D: Đọc wrapped DEK + KEK ref/version cũ
    W->>K: Rewrap(source, destination, blob, contexts)
    Note over K: Unwrap và wrap trong ranh giới nhà cung cấp
    K-->>W: Wrapped DEK mới + destination key ref
    W->>D: CAS update wrapped DEK + key ref/version
    D-->>W: Thành công hoặc conflict
    Note over W: Không cần nhận DEK rõ hoặc decrypt ciphertext
~~~

**Lợi ích:** giảm nguy cơ DEK xuất hiện ở application memory, crash dump, profiler hoặc log, đồng thời để KMS/HSM áp quyền và audit thao tác.

**Giới hạn:** không phải mọi KMS có API re-wrap trực tiếp; một số API chỉ hỗ trợ một tập nguồn/đích, loại khóa, encryption context, vùng hoặc tài khoản. Cần kiểm tra **hợp đồng API, điều kiện IAM và khả năng chuyển qua provider**, không tự giả định mọi dịch vụ có thể gọi `ReEncrypt` hay `Rewrap` giống nhau.

### 3.2. Phương án thay thế: unwrap rồi wrap trong tiến trình được kiểm soát

Nếu không có KMS-native re-wrap phù hợp, kiến trúc có thể cân nhắc một worker được phép:

1. Gọi KMS/HSM **unwrap/decrypt wrapped DEK** bằng KEK cũ.
2. Nhận **DEK rõ trong bộ nhớ tạm** thuộc ranh giới đã được phê duyệt.
3. Gọi cơ chế **wrap/encrypt key material** bằng KEK mới theo API được hỗ trợ.
4. Không lưu hoặc log DEK rõ; giảm thời gian giữ trong bộ nhớ và hạn chế quyền của worker.
5. Kiểm chứng và cập nhật metadata một cách nguyên tử.

**Rủi ro lớn hơn:** DEK đi qua runtime của worker; cần kiểm soát memory dumps, quyền máy, debug logging, transport, credential và zeroization trong phạm vi khả thi. Với khóa có yêu cầu **không rời HSM**, phương án này **không hợp lệ**, phải dùng secure HSM migration hoặc thiết kế lại phương án.

Không tự xây giao thức wrap dựa trên một chuỗi AES tùy ý. Sử dụng **thuật toán/API key wrapping được phê duyệt** (chẳng hạn cơ chế wrap của KMS/HSM) và hiểu đúng tính toàn vẹn của wrapped key.

### 3.3. Khi không thể re-wrap trực tiếp

Một số tình huống cần chiến lược khác:

- Chuyển từ **KMS A sang KMS B** không có đường secure re-wrap chung.
- KEK cũ **non-exportable**, provider không hỗ trợ cross-provider unwrap/wrap trong HSM.
- Loại key, kích thước hoặc thuật toán không được phép làm source/destination cho cùng API.
- Encryption context cũ không còn tái dựng được.
- KEK cũ đã bị disable/destroy nên không thể giải bọc các DEK còn phụ thuộc.
- Mô hình dữ liệu AAD gắn trực tiếp với wrapped DEK hoặc key reference cần thay.

Khi đó có thể phải dùng **hệ thống trung gian HSM được phê duyệt, secure import/export**, hoặc **re-encrypt dữ liệu dưới DEK mới** theo phương án phục hồi có thể thực thi. **Không được giả định “mất KEK cũ” có thể khắc phục bằng cách tạo KEK mới**; nếu không còn đường giải mã DEK thì bản mã có thể vĩnh viễn không đọc được.

## 4. Mô hình dữ liệu để re-wrap an toàn

Một bản ghi envelope có thể có cấu trúc khái niệm:

~~~yaml
schemaVersion: "invoice-envelope-v1"
tenantRef: "tenant-A"
objectRef: "invoice-123"
dekRef: "dek-invoice-123"
dataAlgorithm: "AES-256-GCM"
nonce: "<encoded-96-bit-nonce>"
ciphertextWithTag: "<encoded-ciphertext-and-authentication-tag>"
wrapping:
  kekRef: "kms://prod/billing/kek-v3"
  kekVersionRef: "v3"
  wrappedDek: "<encoded-wrapped-data-key>"
  wrapContextVersion: "billing-wrap-context-v1"
recordRevision: 41
~~~

Đây là **schema minh họa, không phải schema chuẩn của một KMS**. `wrappedDek` là ciphertext của **DEK**, không phải plaintext key. `kekVersionRef` có thể là version quản trị riêng nếu nhà cung cấp không công khai material version.

Khi chuyển sang v4, một bản ghi mới có thể chứa:

~~~yaml
wrapping:
  kekRef: "kms://prod/billing/kek-v4"
  kekVersionRef: "v4"
  wrappedDek: "<new-wrapped-dek-for-the-same-data-key>"
  wrapContextVersion: "billing-wrap-context-v1"
recordRevision: 42
~~~

**Không đổi `ciphertextWithTag` và `nonce` trong re-wrap thuần túy.** Nếu đổi, đó là một migration lớn hơn và cần làm rõ liệu DEK/ciphertext cũng đã thay.

### 4.1. Key reference, material version, alias và predecessor

| Khái niệm | Ví dụ | Đặc tính cần nhớ |
| --- | --- | --- |
| **Logical key family** | billing-invoice-kek | Tập hợp khóa cùng purpose/owner. |
| **Provider key object** | kms://prod/billing/kek-v4 | Đối tượng provider cấp. |
| **Material version** | v4 hoặc provider version ID | Thế hệ vật liệu khóa hoặc định danh logic được xác minh. |
| **Alias current** | billing-kek-current | Con trỏ có thể thay đổi, không phải lịch sử bất biến. |
| **Predecessor** | v4 có predecessor là v3 | Quan hệ phiên bản thay thế, không phải quan hệ wrap. |
| **WRAPS edge** | KEK v4 wraps DEK-A | Quan hệ bảo vệ một DEK cụ thể. |
| **ENCRYPTS edge** | DEK-A encrypts invoice-123 | Quan hệ giữa DEK và bản mã dữ liệu. |

**Predecessor của KEK v4 là KEK v3; predecessor của DEK-A không thay đổi vì chỉ re-wrap.** DEK-A không được sinh mới, nên không nên giả vờ tạo “DEK-A v2” nếu thực tế giá trị key vẫn như cũ.

### 4.2. Không chỉ lưu alias current

Nếu record cũ dùng KEK v3 nhưng application luôn gọi `billing-kek-current` đã trỏ tới v4, khả năng decrypt phụ thuộc hợp đồng của KMS. Một số provider tự nhận diện key từ encrypted blob; nơi khác yêu cầu đúng key object.

Vì vậy **phải lưu đúng reference/version hoặc provider encrypted blob có đủ thông tin được bảo đảm**, và quy trình đọc dữ liệu lịch sử phải được kiểm thử với **KEK cũ và mới**.

### 4.3. Ràng buộc metadata với dữ liệu

Để tránh thay một wrapped DEK sang record khác:

- AEAD của dữ liệu nên ràng buộc **tenant, object ID, purpose, format và DEK reference** vào AAD khi giao thức cho phép.
- KMS wrap context nên ràng buộc **tenant/object/purpose** theo khả năng provider.
- Lớp ứng dụng vẫn phải kiểm tra **authorization trước Decrypt/Unwrap**, không chỉ dựa vào ciphertext.
- Metadata nhạy cảm với ngữ cảnh cần **tính toàn vẹn** theo thiết kế, không tin các trường do client tự gửi.

**Quan trọng:** AAD của ciphertext nên dùng các định danh **ổn định qua KEK rotation**. Nếu AAD chứa `kekRef` hoặc byte `wrappedDek` hiện tại, re-wrap đổi các trường này có thể làm tag AES-GCM của dữ liệu **không còn hợp lệ**. Khi đó phải có phiên bản schema, migration AAD/re-encryption hoặc cơ chế liên kết khác được đánh giá.

## 5. Encryption context, AAD và key wrapping có gì khác?

Ba khái niệm có thể tương tác, nhưng không nên trộn:

| Thành phần | Được dùng ở đâu? | Vai trò |
| --- | --- | --- |
| **AES-GCM AAD của dữ liệu** | Khi mã hóa/giải mã ciphertext ứng dụng bằng DEK. | Xác thực ngữ cảnh của dữ liệu, không mã hóa AAD. |
| **Encryption context của KMS** | Khi gọi API KMS wrap/unwrap/re-encrypt, nếu có hỗ trợ. | Ràng buộc thao tác KMS với dữ liệu ngữ cảnh và policy. |
| **Key reference/version** | Ở registry, provider key object hoặc blob. | Chỉ ra KEK/DEK nào đang được dùng, phục vụ rotation và audit. |

Ví dụ:

~~~text
Data AEAD AAD (ổn định theo object):
  purpose = invoice-data-v1
  tenant  = A
  object  = invoice-123
  dekRef  = dek-invoice-123

KMS wrap context:
  purpose = invoice-dek-wrap-v1
  tenant  = A
  object  = invoice-123
  dekRef  = dek-invoice-123

Old KEK reference: kek-v3
New KEK reference: kek-v4
~~~

Trong trường hợp này, **AAD của dữ liệu không thay** và context khi re-wrap có thể được giữ nguyên nếu provider yêu cầu. **Một số KMS cho phép source context và destination context khác nhau**, nhưng phải kiểm tra API thật, tính tương thích và semantics.

**Đừng đặt PII/secret vào context chỉ để debug**: nhiều provider có thể đưa encryption context vào audit log. Context thường nên dùng giá trị định danh đã được phân loại, không dùng plaintext dữ liệu nghiệp vụ nhạy cảm.

### 5.1. Cơ chế xác thực dữ liệu vẫn phải được giữ nguyên

Khi đọc record sau re-wrap:

1. Kiểm tra principal có quyền với object/tenant.
2. Tra metadata và xác định wrapped DEK, KEK reference/context theo format.
3. KMS/HSM unwrap DEK bằng key còn được phép.
4. Ứng dụng dùng **DEK thực sự** và đúng AAD để **AES-GCM verify tag**.
5. Chỉ trả dữ liệu khi xác thực và quyền đều hợp lệ.

**KMS Unwrap thành công không chứng minh người dùng cuối có quyền đọc invoice**. IAM kiểm soát workload gọi KMS; quyền dữ liệu là trách nhiệm kết hợp của ứng dụng và data owner.

## 6. Quy trình rotate KEK và re-wrap DEK an toàn

Một **rotation runbook** nên tách **chuẩn bị, chuyển ghi mới, migration dữ liệu cũ, đối soát, retire và destroy**.

~~~mermaid
flowchart TD
    PLAN["Lập kế hoạch: scope, owner, inventory, risk"] --> PREP["Tạo KEK v4 trong KMS, policy/backup/DR"]
    PREP --> READY["Kiểm tra API, quyền, region, consumer readiness"]
    READY --> SWITCH["Chuyển new writes sang KEK v4"]
    SWITCH --> DUAL["Duy trì read bằng v3/v4 theo policy"]
    DUAL --> REWRAP["Re-wrap DEK cũ qua KMS/HSM được duyệt"]
    REWRAP --> CAS["CAS cập nhật wrapped DEK + version atomically"]
    CAS --> RECON["Đối soát DB, archive, snapshot và failures"]
    RECON --> DECIDE{"Còn dependency hợp lệ vào KEK v3?"}
    DECIDE -->|Có| DUAL
    DECIDE -->|Không| RETIRE["Retire/disable theo phê duyệt"]
    RETIRE --> DESTROY["Destroy khi đủ điều kiện retention/recovery"]
~~~

### 6.1. Giai đoạn A – Chuẩn bị

1. Xác định **KEK family/owner**, key IDs, versions, tenant/environment và **lý do rotation**.
2. Truy vấn **key inventory**: wrapped DEK nào, ciphertext/backup nào, consumer và archive nào còn phụ thuộc KEK cũ.
3. Tạo **KEK mới từ nguồn ngẫu nhiên mật mã được phê duyệt** trong KMS/HSM và ghi version/predecessor.
4. Áp quyền cho migration worker: **source unwrap/re-encrypt-from** và **destination wrap/re-encrypt-to** theo API provider; tránh quyền admin, export hoặc delete.
5. Xác minh phương án **backup/recovery**, restore test và trạng thái KMS mới.
6. Kiểm tra tương thích **encryption context, schema, AAD và SDK** với data path cũ/mới.
7. Đặt các **metrics và audit events** đo tiến độ, lỗi, tỷ lệ thành công và thao tác nhạy cảm.

**Không tắt/xóa KEK cũ trước khi bắt đầu migration**, trừ khi một phương án xử lý sự cố được phê duyệt yêu cầu cô lập khẩn cấp và đã cân nhắc việc mất khả năng đọc dữ liệu.

### 6.2. Giai đoạn B – Chuyển new writes

Sau khi KEK v4 sẵn sàng, đưa các thao tác **wrap DEK mới** sang v4. Dữ liệu mới không nên tiếp tục phụ thuộc v3 vì một ứng dụng chưa cập nhật cấu hình.

Trong giai đoạn này:

- **Single-write (v4):** ghi mới dùng KEK v4.
- **Multi-version read:** đọc bản cũ dùng v3 và bản mới dùng v4 theo key reference/format được xác thực.
- **Metrics:** giám sát xem còn dịch vụ nào tạo wrapped DEK dưới v3.
- **Consumer readiness:** mọi reader/restore path cần hiểu format và key reference mới.

**Chuyển alias current không có nghĩa những DEK cũ đã được re-wrap**. Re-wrap backlog là công việc riêng.

### 6.3. Giai đoạn C – Re-wrap theo batch có kiểm soát

Với mỗi bản ghi thuộc v3:

1. Đọc bản ghi cùng **revision** và key reference, wrap context, tenant/object mapping được xác thực.
2. Bảo đảm caller/migration worker được phép xử lý object/key family tương ứng.
3. Gọi **KMS/HSM re-wrap** theo source v3 và destination v4, giữ DEK không đổi.
4. Kiểm tra **response destination key identity**, định dạng blob, trạng thái và độ dài phù hợp; không log blob hoặc DEK.
5. Cập nhật **wrapped DEK + KEK reference/version + record revision** trong một thay đổi nguyên tử.
6. Nếu có tranh chấp phiên bản, **không ghi đè** record vừa được thay đổi bởi worker khác; đọc lại và xử lý idempotent.
7. Ghi audit result/record ref đã phân loại, không ghi secret; theo dõi các bản ghi lỗi để retry.

Đối với rất nhiều bản ghi, dùng **batch có giới hạn tốc độ/concurrency**, checkpoint bền vững, backoff và retry có kiểm soát theo đặc tính API KMS. Không tăng song song vô hạn chỉ để kết thúc nhanh, vì KMS có quota, chi phí và độ trễ.

### 6.4. Giai đoạn D – Đối soát và retire

Không chỉ dựa vào tiến trình báo “100% completed”. Cần đối soát:

- **DB live:** còn wrapped DEK nào chỉ dưới v3?
- **Snapshot và backup:** có bản lưu cũ cần v3 để khôi phục?
- **Archive/cold storage:** có record cũ không nằm trong bảng đang chạy?
- **Queues, caches, replica:** có consumer nào giữ phiên bản cũ?
- **Current write paths:** còn service nào tạo wrapped DEK mới dưới v3?
- **DR drills:** restore một bản sao lịch sử bằng key/format đúng có thành công?
- **Policy/retention:** dữ liệu phải giữ bao lâu; có legal hold hoặc ngoại lệ không?
- **Audit:** điều gì chưa đối soát, ai đã phê duyệt retire/disable/destroy?

**Retire/disable** là trạng thái vận hành, còn **destroy** là mất khả năng phục hồi vật liệu khóa theo cơ chế provider. Chỉ tiến tới destruction khi quyền, phụ thuộc và backup thực sự cho phép.

## 7. Idempotency, optimistic concurrency và cập nhật atomically

Migration có thể chạy đồng thời với hệ thống đang đọc/ghi. Một tác vụ re-wrap có thể bị retry do timeout **sau khi KMS đã thực hiện phép toán** hoặc sau khi DB đã ghi thành công. Phải thiết kế để **retry không làm hỏng record**.

### 7.1. Tại sao cần compare-and-swap (CAS)?

Giả sử hai migration workers cùng thấy:

~~~text
recordId = invoice-123
kekRef = kek-v3
revision = 41
wrappedDek = W3
~~~

Worker A re-wrap ra `W4a`, worker B re-wrap ra `W4b`. Dù cả hai blob có thể bọc cùng DEK, chúng không nhất thiết byte-for-byte giống nhau vì cơ chế wrap có thể dùng randomness.

Nếu worker B ghi đè không điều kiện lên kết quả của A, audit và metadata dễ lệch; tệ hơn, nếu đồng thời application đang **re-encrypt dữ liệu bằng DEK mới**, ghi đè có thể khiến ciphertext và wrapped DEK **không còn thuộc cùng DEK**.

Giải pháp: chỉ cập nhật khi **revision hiện tại vẫn bằng 41** và **source KEK vẫn là v3**. Nếu CAS thất bại, bỏ kết quả không còn phù hợp và đọc lại record trước khi quyết định tiếp.

### 7.2. Ví dụ cập nhật điều kiện trong database

~~~sql
-- Chỉ minh họa SQL; tham số được bind, không string-concatenate.
UPDATE encrypted_object
SET wrapped_dek = :new_wrapped_dek,
    kek_ref = :new_kek_ref,
    kek_version = :new_kek_version,
    revision = revision + 1,
    rewrapped_at = :now
WHERE id = :record_id
  AND tenant_ref = :trusted_tenant_ref
  AND revision = :expected_revision
  AND kek_ref = :expected_old_kek_ref;
~~~

**Chỉ coi thao tác hoàn thành nếu số hàng cập nhật đúng bằng 1.** Khi bằng 0, có thể record đã được migrate bởi worker khác, key reference không còn là source hoặc object đã đổi; phải tra lại metadata và xử lý theo chính sách, **không retry mù**.

**Không cập nhật wrapped DEK và KEK reference bằng hai transaction riêng**: khoảng trống ở giữa có thể khiến reader dùng sai KEK để unwrap.

### 7.3. Không thể giao dịch nguyên tử cả KMS và database

KMS re-wrap và DB CAS thường là hai hệ thống khác nhau, không có một distributed transaction chung. Nếu KMS đã re-wrap thành công nhưng DB ghi thất bại, worker có thể **bỏ blob mới và thử lại theo source cũ**, miễn là KMS operation/retry policy cho phép và KEK cũ vẫn hợp lệ.

Hãy ghi **migration request/job ID**, checkpoint, attempts và outcome; dùng retry backoff cho lỗi tạm, phân biệt lỗi **AccessDenied, context mismatch, key disabled, invalid ciphertext, quota và DB conflict**.

**Không coi mọi error là retryable.** Một ciphertext bị sửa hoặc thiếu context không nên được thử vô hạn với nhiều key khác nhau; cần cách ly bản ghi và điều tra.

## 8. Java 17: coordinator thực hiện re-wrap bằng KMS và CAS metadata

Ví dụ sau diễn đạt **đường điều phối an toàn** cho re-wrap. Nó **không tự bọc khóa và không nhận plaintext DEK**. Adapter `KmsRewrapper` chỉ cung cấp `rewrap()` được nhà cung cấp hỗ trợ; nếu provider không có thao tác này, kiến trúc phải chọn phương án khác đã được đánh giá, **không giả vờ có API**.

`EnvelopeStore` chịu trách nhiệm truy cập DB và **CAS nguyên tử**. KMS adapter, store và quyền người dùng đều là **interface**, cần triển khai bằng hệ thống đáng tin trong production.

~~~java
import java.util.Map;
import java.util.Objects;

public final class RewrapDekCoordinator {
    enum Result {
        MIGRATED, ALREADY_TARGET, SOURCE_MISMATCH, CONFLICT
    }

    // Metadata của một object; ciphertext và DEK không đổi.
    // Byte arrays cần defensive copy trong production.
    record EnvelopeRecord(
            String recordId,
            String tenantRef,
            String objectRef,
            String dekRef,
            String kekRef,
            String wrapContextVersion,
            byte[] wrappedDek,
            long revision) {}

    record WrappedKeyResult(
            String destinationKekRef,
            byte[] wrappedDek) {}

    interface KmsRewrapper {
        // Provider thực hiện unwrap+wrap trong trust boundary
        // và KHÔNG trả DEK rõ cho worker.
        WrappedKeyResult rewrap(
                String sourceKekRef,
                String destinationKekRef,
                byte[] oldWrappedDek,
                Map<String, String> sourceContext,
                Map<String, String> destinationContext) throws Exception;
    }

    interface EnvelopeStore {
        EnvelopeRecord load(String recordId);

        // CAS bền vững: update wrappedDek, kekRef, revision atomically
        // nếu ID/tenant, old revision và old KEK vẫn khớp.
        // Không thay ciphertext, nonce, authentication tag hoặc DEK.
        boolean compareAndSwapWrap(
                EnvelopeRecord observed,
                String newKekRef,
                byte[] newWrappedDek);
    }

    interface Authorization {
        // Dùng workload identity/actor đã xác thực, không tin
        // tenantRef/keyRef do caller tùy ý chọn.
        void requireRewrapPermission(
                String actorRef, String tenantRef,
                String sourceKekRef, String targetKekRef);
    }

    private final KmsRewrapper kms;
    private final EnvelopeStore store;
    private final Authorization authorization;
    private final String sourceKekRef;
    private final String targetKekRef;

    // Các ref này phải được cấu hình/registry phê duyệt từ server.
    public RewrapDekCoordinator(
            KmsRewrapper kms, EnvelopeStore store,
            Authorization authorization,
            String sourceKekRef, String targetKekRef) {
        this.kms = Objects.requireNonNull(kms);
        this.store = Objects.requireNonNull(store);
        this.authorization = Objects.requireNonNull(authorization);
        if (sourceKekRef == null || sourceKekRef.isBlank()
                || targetKekRef == null || targetKekRef.isBlank()
                || sourceKekRef.equals(targetKekRef)) {
            throw new IllegalArgumentException("Invalid KEK migration pair");
        }
        this.sourceKekRef = sourceKekRef;
        this.targetKekRef = targetKekRef;
    }

    private static Map<String, String> wrapContext(EnvelopeRecord r) {
        // Bám theo schema KMS context đã dùng khi wrap lần đầu.
        // Những trường này cần đủ ổn định và được xác thực.
        return Map.of(
                "purpose", "billing-dek-wrap-v1",
                "tenant", r.tenantRef(),
                "object", r.objectRef(),
                "dekRef", r.dekRef());
    }

    public Result migrateOne(String actorRef, String trustedRecordId)
            throws Exception {
        EnvelopeRecord row = store.load(trustedRecordId);
        if (row == null) {
            throw new IllegalArgumentException("Unknown record");
        }

        authorization.requireRewrapPermission(
                actorRef, row.tenantRef(), sourceKekRef, targetKekRef);

        if (targetKekRef.equals(row.kekRef())) {
            return Result.ALREADY_TARGET; // Retry an toàn.
        }
        if (!sourceKekRef.equals(row.kekRef())) {
            return Result.SOURCE_MISMATCH; // Không thử mọi KEK.
        }
        if (row.wrappedDek() == null || row.wrappedDek().length == 0
                || row.tenantRef() == null || row.tenantRef().isBlank()
                || row.objectRef() == null || row.objectRef().isBlank()
                || row.dekRef() == null || row.dekRef().isBlank()
                || !"billing-wrap-context-v1".equals(
                        row.wrapContextVersion())) {
            throw new SecurityException("Invalid envelope metadata");
        }

        Map<String, String> context = wrapContext(row);
        WrappedKeyResult result = kms.rewrap(
                sourceKekRef, targetKekRef,
                row.wrappedDek().clone(),
                context, context);

        if (result == null
                || !targetKekRef.equals(result.destinationKekRef())
                || result.wrappedDek() == null
                || result.wrappedDek().length == 0) {
            throw new SecurityException("Invalid KMS rewrap result");
        }

        // Store implementation phải clone/check các byte arrays
        // và bảo đảm CAS thật ở database, không phải check-then-put.
        boolean changed = store.compareAndSwapWrap(
                row, targetKekRef, result.wrappedDek().clone());

        return changed ? Result.MIGRATED : Result.CONFLICT;
    }

    // Không gọi main với giả KMS/khóa cố định; adapter thực chỉ được
    // triển khai bằng SDK KMS/HSM đã được phê duyệt và kiểm thử.
}
~~~

### 8.1. Ví dụ trên bảo vệ những gì?

1. **Không đụng plaintext DEK:** worker chuyển **wrapped DEK** qua KMS, không tự mã hóa dữ liệu.
2. **Source/target KEK cố định theo kế hoạch:** không lấy arbitrary key ID từ payload của client.
3. **Authorization trước KMS:** xác minh actor có quyền re-wrap theo tenant/source/destination; KMS IAM phải kiểm tra độc lập.
4. **Context ổn định:** sử dụng `tenantRef`, `objectRef`, `dekRef`, `purpose` theo format đã xác định.
5. **Không thử nhiều key để đoán:** chỉ chấp nhận bản ghi có source KEK đúng; các record khác được bỏ qua hoặc đưa vào quy trình khác.
6. **Kiểm tra kết quả provider:** chỉ chấp nhận destination key reference mong muốn.
7. **CAS bảo vệ tính nhất quán:** nếu metadata đổi giữa lúc KMS re-wrap và DB ghi, không ghi đè mù.
8. **Idempotency:** record đã ở target KEK được coi là không cần migration lại.
9. **Không sửa ciphertext:** interface Store chỉ có thao tác cập nhật wrap và revision.

### 8.2. Những điểm còn thiếu trước production

- **KMS adapter thật:** quyền source/destination, provider encryption context semantics, API quota, retries và kiểm tra response; không nhà cung cấp nào bị giả định có cùng `rewrap()`.
- **Store thật:** schema, locking/CAS, transaction, immutable/copy-safe byte arrays, audit/event history, backup/restore và record ownership.
- **Kết nối với dữ liệu:** code không chứa ciphertext/tag để tránh nhầm thao tác re-wrap với re-encrypt; Store phải bảo đảm **DEK và ciphertext không thay**.
- **Kiểm tra key material/version:** `targetKekRef` là reference giả định có thẩm quyền; nếu provider trả version/other metadata cần xác minh thêm.
- **Sự cố và lỗi:** retry/backoff, dead-letter queue, classification, target key disabled, context mismatch, KMS outage và rollback.
- **Thử nghiệm đọc dữ liệu:** unit test hoặc kiểm tra KMS re-wrap chưa chứng minh dữ liệu thật giải mã được; cần decrypt/AEAD verify bằng mẫu được phép.
- **Giám sát:** progress metrics, principal/operation audit, alert bất thường mà không log DEK, KEK, raw wrapped DEK hoặc plaintext.
- **Security properties của wrap:** adapter phải bảo đảm rewrap **giữ nguyên DEK**; nếu trả về khóa dữ liệu mới thì đó là thao tác khác, không phù hợp với giả định code.
- **Multi-tenant:** `recordId` tra cứu phải được gắn với quyền và tenant đã xác thực; không tin metadata được client sửa.

**Lưu ý bảo mật:** Các Java `record` chứa `byte[]` **không tự tạo deep immutability**. Triển khai thực cần clone ở điểm nhận/trả để tránh thay dữ liệu giữa kiểm tra và lưu; những byte đó là wrapped key, không nên ghi log.

## 9. Cách tổ chức migration trên tập dữ liệu lớn

Re-wrap có thể liên quan tới **hàng triệu wrapped DEK**; mỗi KMS call có độ trễ, quota, chi phí và chính sách truy cập riêng.

### 9.1. Tách inventory, coordinator và workers

~~~mermaid
flowchart LR
    INV["Key inventory: old key dependencies"] --> PLAN["Migration plan: source/target KEK, scope"]
    PLAN --> QUEUE["Job queue + checkpoint"]
    QUEUE --> W1["Worker A"]
    QUEUE --> W2["Worker B"]
    W1 --> KMS["KMS/HSM rewrap"]
    W2 --> KMS
    KMS --> CAS["CAS metadata update"]
    CAS --> METRICS["Progress, errors, audit"]
    METRICS --> RECON["Reconciliation và release old KEK"]
~~~

**Một số nguyên tắc vận hành:**

- **Partition work** theo tenant/key family/record ranges để dễ theo dõi.
- **Giới hạn concurrency** để không phá quota KMS hay làm giảm khả năng giải mã của hệ thống online.
- **Checkpoint bền vững** để worker có thể tiếp tục sau restart.
- **Idempotency theo record/source/target key**; cùng job chạy lại không làm hỏng dữ liệu.
- **Backoff cho lỗi tạm**; đưa lỗi crypto/context/permission vào luồng xử lý riêng.
- **Metrics còn tồn đọng** theo source KEK/version và backup category, không chỉ tổng số tasks đã chạy.
- **Audit theo sự kiện** với owner, actor, reason/approvalRef, source/target key refs và kết quả.
- **Canary** một lượng dữ liệu nhỏ và kiểm tra read path trước khi mở rộng.

Không log nguyên wrapped DEK hoặc plaintext vào error queue để “dễ retry”. Queue chỉ cần **record reference, migration plan ID và metadata đã phân loại**; worker đọc blob từ storage được kiểm soát.

### 9.2. Trạng thái và kết quả cần phân biệt

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| **MIGRATED** | CAS ghi wrapped DEK mới thành công. | Ghi audit, tăng counter, tiếp tục. |
| **ALREADY_TARGET** | Bản ghi đã dùng KEK mới. | Idempotent success; không gọi KMS lần nữa. |
| **CONFLICT** | Record đổi giữa read và CAS. | Đọc lại, kiểm tra lineage rồi quyết định retry. |
| **SOURCE_MISMATCH** | Không thuộc KEK nguồn của kế hoạch. | Không thử mọi KEK; phân loại riêng. |
| **CONTEXT_MISMATCH** | Không thể unwrap vì context khác. | Cách ly record, xác minh schema/context gốc. |
| **ACCESS_DENIED** | IAM/key policy từ chối. | Sửa quyền theo quy trình; không fallback sang secret. |
| **SOURCE_KEY_DISABLED** | KEK cũ không dùng để unwrap. | Đánh giá trạng thái sự cố và recovery path; không tự bật lại. |
| **KMS_UNAVAILABLE/THROTTLED** | Lỗi tạm/quota. | Retry có backoff và giới hạn. |
| **INVALID_WRAPPED_DEK** | Blob không hợp lệ, bị sửa hoặc sai format. | Điều tra integrity, không ghi kết quả đoán. |
| **RESTORE_DEPENDENCY_PENDING** | Backup/archive vẫn cần KEK cũ. | Chưa destroy; xử lý theo retention/DR. |

**Mục tiêu không phải 0 lỗi bằng mọi giá**. Có những bản ghi **không thể migrate tự động** vì dữ liệu hoặc metadata đã hỏng. Phải công bố backlog và mức ảnh hưởng trước khi retire/hủy khóa cũ.

## 10. Những biến thể và góc cạnh khó

### 10.1. KEK rotation tự động bên trong cùng key object

Nếu provider tự rotate vật liệu trong cùng một key object và vẫn decrypt được blob cũ, **ứng dụng có thể không cần thay wrapped DEK**. Việc re-wrap ở mức ứng dụng vẫn có thể được yêu cầu để giới hạn phụ thuộc vào bản mã/phiên bản lịch sử, nhưng điều đó phải được **provider hỗ trợ và quan sát được**.

Không bịa material version ID khi KMS không cho biết. Inventory nên ghi **key object, thông tin rotation mà provider công khai** và các giới hạn chưa quan sát được.

### 10.2. KEK v3 bị nghi compromise

Đây không phải rotation định kỳ thông thường:

- Đội Security có thể cần **hạn chế ngay thao tác trên v3**.
- Migration worker có thể cần quyền dùng v3 để re-wrap; đây là một **xung đột availability-security** cần quyết định có thẩm quyền.
- Nếu attacker có **KEK v3 rõ** và wrapped DEK cũ, họ có thể đã lấy DEK; chuyển blob sang KEK v4 **không thu hồi quyền đã có** của attacker với DEK/ciphertext cũ.
- Nếu chỉ **quyền KMS API** bị lộ chứ không phải key material, phải điều tra các lượt `Decrypt/Unwrap` đã thực hiện và dữ liệu thực sự bị truy cập.
- Nếu phạm vi có DEK compromise, cần **rotate DEK + re-encrypt** hoặc biện pháp khác theo đánh giá thiệt hại.

**Không thiết kế runbook “re-wrap = xử lý mọi compromise”**. Mức đáp ứng cần dựa trên **loại bí mật bị lộ, thời điểm, logs, inventory và khả năng truy cập ciphertext của attacker**.

### 10.3. Nhiều wrapped copies của cùng một DEK

Một DEK có thể được bọc dưới **nhiều KEK** để phục vụ DR hoặc nhiều vùng. Nếu giữ đồng thời `W3` và `W4`, policy phải làm rõ:

- Bản sao nào là **active** để đọc?
- Bản sao cũ có còn cần cho backup/restore không?
- Ai được phép tạo thêm recipient/wrapping key?
- Khi cần crypto-shred, tất cả những đường bọc nào cần hủy?
- Có trường hợp rewrap một bản sao nhưng quên bản sao ở archive khác không?

**Một wrapped DEK mới không vô hiệu hóa các wrapped DEK cũ.** Nếu KEK v3 còn tồn tại và có blob dưới v3, DEK vẫn có thể được giải bọc qua đường đó.

### 10.4. Multi-region và cross-account

KMS key resources và wrapped blobs có thể phụ thuộc **region, account, provider hoặc domain bảo vệ**. Nếu chuyển sang v4 ở nơi khác:

- Kiểm tra source/target API có cho phép chuyển **cross-region/cross-account** không.
- Xác minh **workload identity, network boundary, key policies, grants** ở cả hai bên.
- Phân biệt **replicated key** với **key object khác**: tên giống nhau không chứng minh cùng vật liệu.
- Kiểm tra plan DR có bản sao dữ liệu và wrapped DEK **phù hợp với KEK vùng phục hồi**.
- Không lấy plaintext DEK xuất qua một channel không được phê duyệt để bù cho API thiếu.

### 10.5. Thay thuật toán bọc khóa

Nếu đổi từ một cơ chế wrap sang cơ chế khác, metadata cần ghi **algorithm/format version và các tham số cần thiết**. Không suy mọi wrapped DEK đều có cùng cấu trúc. API KMS/HSM phải bảo đảm **authentication/integrity** của lớp bọc và giới hạn key usage.

Đừng coi re-wrap là “mã hóa lại bất kỳ bytes nào”: dữ liệu bọc phải đúng **DEK material** theo giao thức. Nếu key size, purpose hay provider restrictions không tương thích, không thể tự đặt lại `algorithm=...` trong metadata để làm hợp lệ.

### 10.6. AAD bao gồm KEK reference cũ

Đây là tình huống quan trọng: AES-GCM ciphertext được tạo với AAD có chứa `kekRef=kek-v3`. Re-wrap blob rồi cập nhật metadata sang `kek-v4` khiến AAD tính lại khác đi, và **tag verification sẽ thất bại**.

Hướng xử lý có thể là:

- **Giữ nguyên AAD gốc** trong một field độc lập với current KEK, theo schema đã thiết kế từ trước.
- **Định nghĩa phiên bản format mới** tách AAD ổn định và wrapping metadata; migration phải kiểm tra chính xác dữ liệu cũ.
- Khi cần đổi AAD đã được AEAD bảo vệ, phải **giải mã rồi mã hóa lại dữ liệu với AAD mới** trong quy trình được phép.

**Không được bỏ qua GCM tag** để “chạy qua” migration. Một lỗi tag là thất bại bảo vệ tính toàn vẹn, không phải cảnh báo nhẹ.

## 11. Backup, restore, retention và hủy KEK cũ

Một bản ghi live đã được re-wrap có thể dùng v4, trong khi một **snapshot tháng trước** vẫn chứa wrapped DEK dưới v3. Nếu xóa v3, snapshot đó có thể trở thành dữ liệu **không thể phục hồi**.

### 11.1. Những thứ phải đối soát

| Nguồn dữ liệu | Câu hỏi cần trả lời |
| --- | --- |
| **Primary database** | Có còn record nào có source KEK v3? |
| **Read replicas/cache** | Có record hoặc application version cũ dùng v3? |
| **Object storage/cold archive** | Có wrapped DEK ở tệp lâu năm không được migration? |
| **Snapshots/backup** | Sau restore, có đủ KEK/material versions để mở DEK không? |
| **Recovery region** | Có KEK v4 hoặc đường recovery hợp lệ? |
| **KMS/HSM backups** | Provider có giữ v3; quyền/retention/hủy thế nào? |
| **Audit/event history** | Có chứng cứ ai đã re-wrap, thất bại nào chưa xử lý? |
| **Legal hold/retention** | Dữ liệu cũ phải giữ bao lâu; có ngoại lệ không? |

**Backup policy** phải theo **khả năng phục hồi dữ liệu**, không chỉ theo trạng thái key registry. Nếu retention yêu cầu phục hồi snapshots v3, có thể cần tiếp tục bảo vệ v3 hoặc chủ động **migrate snapshots** trước khi destroy.

### 11.2. RPO/RTO trong migration

**RPO** là lượng trạng thái có thể mất, **RTO** là thời gian mục tiêu phục hồi. Cần xét một điểm phục hồi gồm **dữ liệu và metadata khóa nhất quán**:

- Data snapshot có wrapped DEK v4, nhưng recovery KMS chỉ có v3: không đọc được.
- Data snapshot có wrapped DEK v3, nhưng KEK v3 đã destroyed: không đọc được.
- DB record được cập nhật thành v4 nhưng `wrappedDek` vẫn là blob v3 do ghi không nguyên tử: có thể lỗi giải bọc.
- Restore alias current mà bỏ key version: có thể gọi sai khóa.

**DR drill phải thử dữ liệu thật được phép hoặc mẫu đại diện bằng key versions cũ/mới**, không chỉ kiểm tra endpoint KMS trả API health OK.

### 11.3. Re-wrap khác crypto-shredding

**Crypto-shredding** đòi hỏi dữ liệu không còn đường giải mã hợp lệ. Re-wrap chỉ đổi cách bảo vệ **cùng DEK**, không khiến dữ liệu mất khả năng đọc; ngược lại, có thể tăng số đường đọc nếu giữ cả W3 và W4.

Khi có yêu cầu **hủy KEK v3**, tổ chức phải kiểm kê các bản sao và dependency còn dùng nó; khi có yêu cầu **hủy DEK để làm dữ liệu không đọc được**, phải xem **mọi bản DEK, wrapped copies, escrow, plaintext export và KMS backups** trong phạm vi kiểm soát.

**Đừng khẳng định crypto-shredding hoàn tất** chỉ vì xóa một alias, một blob wrapped DEK hoặc một bản ghi inventory.

## 12. IAM, KMS policy, tách nhiệm vụ và audit

Migration worker cần một quyền đặc biệt nhưng có giới hạn.

### 12.1. Phân quyền gợi ý

| Vai trò | Quyền cần thiết | Không nên mặc định có |
| --- | --- | --- |
| **Application writer** | Tạo/wrap DEK mới dưới KEK v4. | Quyền dùng mọi key hoặc sửa policy. |
| **Application reader** | Unwrap/Decrypt với key version được phép cho dữ liệu đã xác thực. | Quyền re-wrap toàn bộ hoặc DeleteKey. |
| **Re-wrap worker** | Source unwrap/re-encrypt-from và destination wrap/re-encrypt-to theo API, key IDs và context hạn chế. | Export KEK, Sign, chỉnh key policy, xóa key, đọc mọi tenant. |
| **Security approver** | Duyệt kế hoạch chuyển phiên bản, revoke/retire/destruction. | Tự thực thi toàn bộ luồng mà không cần vận hành. |
| **KMS/HSM operator** | Quản trị key states/availability/backup theo phạm vi. | Truy cập plaintext dữ liệu nghiệp vụ không cần thiết. |
| **Auditor** | Xem event, policy và bằng chứng đã lọc. | Plaintext DEK/KEK hoặc quyền KMS crypto. |

Quyền của migration worker có thể là **JIT, theo lịch và theo phạm vi** nếu nền tảng hỗ trợ. Khi migration xong, thu hồi grant/session và kiểm tra không còn key policy rộng ngoài ý muốn.

### 12.2. Audit nên ghi gì?

Ví dụ một sự kiện đã lọc:

~~~json
{
  "eventType": "DEK_REWRAP_COMPLETED",
  "migrationPlanRef": "billing-kek-v3-to-v4",
  "recordRef": "opaque-invoice-ref",
  "sourceKekRef": "billing-kek-v3",
  "destinationKekRef": "billing-kek-v4",
  "actorRef": "approved-migration-worker",
  "operation": "REWRAP",
  "outcome": "MIGRATED",
  "policyVersion": "billing-key-policy-v6",
  "correlationId": "opaque-request-id"
}
~~~

**Không log plaintext DEK, KEK, full wrapped DEK, KMS import token, ciphertext dữ liệu hoặc HSM recovery shares.** Ngay cả key ID và record ID cũng là metadata cần phân loại quyền.

### 12.3. Vì sao phải kiểm soát operation và provenance?

Một người có quyền `Decrypt`/ `Unwrap` có thể làm mất bí mật dữ liệu nếu lạm dụng. KMS-native re-wrap giúp giới hạn việc **trả plaintext DEK về ứng dụng**, nhưng bản thân **quyền re-wrap** cũng có thể bị lạm dụng để chuyển DEK sang một destination key do attacker kiểm soát.

Do đó source/destination **không được client tự nhập tùy ý**; phải đến từ kế hoạch đã được duyệt/registry có thẩm quyền. KMS policy phải ràng buộc **source key, destination key, principal và các điều kiện thực sự được provider hỗ trợ**.

## 13. Kiểm thử migration và tiêu chí nghiệm thu

Một kế hoạch không được coi hoàn tất chỉ vì một KMS call báo thành công.

### 13.1. Các kiểm thử cần có

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Record dưới KEK v3, data AES-GCM hợp lệ | Re-wrap thành v4, ciphertext/nonce/tag không đổi, giải mã đúng. |
| Record đã ở v4 | Không gọi lại KMS, báo `ALREADY_TARGET`. |
| Record thuộc KEK khác | Không thử key khác, báo `SOURCE_MISMATCH`. |
| CAS conflict với worker khác | Không ghi đè metadata, reload và đánh giá. |
| Consumer đang ghi data mới | New writes dùng v4; old data vẫn đọc theo policy. |
| Source encryption context sai | KMS từ chối, không thay blob/metadata. |
| Target KEK không có quyền | AccessDenied, không fallback sang key cố định. |
| Blob wrapped DEK bị sửa | KMS không chấp nhận theo cơ chế integrity, record được cách ly. |
| Ciphertext/AAD bị sửa | AES-GCM tag verify thất bại; không bỏ qua. |
| KEK v3 disabled trước khi migrate hết | Worker báo blocker, restore plan được xem xét. |
| KMS timeout sau khi đã re-wrap | Retry idempotent; không làm hỏng record đang active. |
| DB write lỗi sau KMS success | Blob mới chưa được commit; record v3 vẫn đọc được theo policy. |
| Snapshot trước rotation | Restore được dưới KEK cũ theo retention hoặc đã migrate snapshot. |
| DEK đã compromise | Không tuyên bố re-wrap hoàn tất nghĩa là dữ liệu an toàn. |
| Khóa signing key bị rotate | Không nhầm với DEK re-wrap; verifier trust được xử lý riêng. |
| Multi-tenant record tampered | Không re-wrap hoặc unwrap ngoài scope được phép. |
| Log và trace được kiểm tra | Không chứa raw DEK/KEK, private key hoặc blobs không cần thiết. |

### 13.2. Tiêu chí kết thúc gợi ý

- Toàn bộ **new writes** đã chuyển sang KEK v4 và được giám sát.
- Migration backlog của v3 đã được xử lý, **ngoại lệ được liệt kê rõ**.
- Số liệu từ DB, archive, snapshots và inventory được **đối soát**.
- Đã kiểm thử decrypt/AEAD verify bằng dữ liệu đại diện theo key versions.
- Restore drill và recovery path đáp ứng chính sách RPO/RTO.
- Key v3 chỉ được retire/disable sau khi owner/security phê duyệt; **destroy là quyết định riêng**.
- KMS IAM grants tạm đã được thu hồi; audit và chứng cứ được lưu theo retention.
- Nếu có incident compromise, hậu quả **DEK/KEK lộ** được đánh giá ngoài phạm vi re-wrap.

## 14. Tình huống thực tế: Billing chuyển KEK v3 sang v4

Nền tảng thanh toán có:

- **Billing Service:** mã hóa hóa đơn bằng AES-GCM với DEK.
- **Payment Service:** ký sự kiện bằng private signing key Ed25519 trong KMS/HSM.
- **Ledger Service:** Verify chữ ký dựa trên trusted public key và quy tắc nghiệp vụ.

Chỉ **Billing KEK** thuộc phạm vi re-wrap của tình huống này; khóa ký Ed25519 của Payment là một family khác, **không có quan hệ predecessor hay WRAPS với Billing DEK**.

### 14.1. Trạng thái trước rotation

~~~text
Billing:
  1.200.000 invoice records
  live records: 1.000.000
  archive records: 200.000

KEK: billing-kek-v3
DEK: riêng theo invoice hoặc partition theo policy
Dữ liệu: AES-GCM ciphertext + nonce/tag + wrapped DEK(v3)
Backup: snapshot lịch sử vẫn cần v3
~~~

Các số liệu chỉ để **minh họa tình huống**, không phải dữ liệu hệ thống thực. Inventory phải xác minh số liệu qua nguồn có thẩm quyền.

### 14.2. Kế hoạch chuyển đổi

1. Security và Billing owner xác nhận rotation là **theo lịch**, không phải DEK compromise.
2. KMS/HSM tạo KEK v4, gắn predecessor v3 trong key registry, áp least-privilege IAM.
3. Billing chuyển **new writes sang v4**, nhưng vẫn đọc dữ liệu cũ qua v3.
4. Migration worker lấy record v3 theo batch, gọi KMS-native re-wrap, CAS lưu blob v4.
5. Với mẫu được phép, Billing giải mã dữ liệu trước/sau và kiểm tra ciphertext/tag không bị thay.
6. Đối soát live database và archive, chạy restore drill cho backup có key v3.
7. Nếu backup vẫn phải giữ v3 theo retention, **chưa destroy v3**, dù bản ghi live đã dùng v4.
8. Thu hồi quyền re-wrap tạm, lưu audit, lên lịch đối soát lại.

### 14.3. Nếu sau đó phát hiện KEK v3 bị lộ?

Thay đổi phân loại từ **rotation định kỳ** sang **incident response**:

- Điều tra khả năng attacker tiếp cận wrapped DEK v3 và ciphertext tương ứng.
- Phân biệt **lộ key material** với **lộ credential có quyền KMS API**.
- Xác định DEK nào có thể đã bị unwrap/đọc và dữ liệu nào cần **DEK rotation/re-encryption**.
- Không kết luận bản mã an toàn trở lại chỉ vì wrapped DEK đang dưới v4.
- Hạn chế quyền trên v3 và xử lý bản sao/backup theo quyết định bảo mật có thẩm quyền.

### 14.4. Đối chiếu với rotation khóa ký Payment

Khi Payment chuyển signing key **S1 → S2**, việc cần làm là công bố public key S2, cập nhật verifier trust, ký mới bằng S2 và đánh giá chữ ký S1 theo policy. **Không gọi đó là re-wrap DEK**. Hai loại rotation cần inventory và audit riêng để tránh hiểu lầm giữa **bảo vệ bí mật dữ liệu** và **nguồn xác thực của chữ ký số**.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi rotate KEK là mọi DEK đã tự re-wrap | Còn wrapped DEK cũ trên DB/backup. | Inventory và migration riêng, kiểm tra provider semantics. |
| Coi re-wrap là re-encrypt dữ liệu | Tính sai effort, bảo mật và trạng thái ciphertext. | Phân biệt DEK không đổi với DEK rotation. |
| Chỉ đổi field `kekRef` sang v4 | Blob DEK vẫn dưới v3, unwrap thất bại. | Cập nhật blob và key ref atomically. |
| Đưa wrapped DEK cũ vào một record khác | Mismatch tenant/object/dek context, rủi ro tráo dữ liệu. | AAD/context binding và authorization. |
| AAD của dữ liệu có `kekRef` cũ nhưng cập nhật không nhất quán | AES-GCM tag validation thất bại. | Stable AAD hoặc re-encryption theo schema migration. |
| Disable/destroy KEK v3 trước khi đối soát | Không unwrap được DEK cũ. | Read compatibility, backups và retention trước retire. |
| Re-wrap bằng cách xuất raw KEK | Phá ranh giới KMS/HSM và tăng nguy cơ lộ. | KMS-native re-wrap hoặc secure workflow được duyệt. |
| Gọi re-wrap tới destination do client nhập | DEK có thể bị bọc bằng khóa kẻ tấn công quản lý. | Target key allowlist và IAM policy tại provider. |
| Cho worker quyền `*` trên KMS | Một workload có thể Sign/Decrypt/Delete ngoài scope. | Least privilege và JIT scoped grants. |
| Log plaintext DEK hoặc toàn bộ KMS response | Rò bí mật qua observability. | Typed audit event, no raw key/blob. |
| Không có CAS khi hai workers cùng migrate | Metadata bị ghi đè, có thể lệch với DEK/ciphertext. | Optimistic concurrency và atomic update. |
| Retry vô hạn khi context sai | Tăng chi phí và che giấu corruption. | Phân loại lỗi, quarantine, điều tra schema gốc. |
| Tin KMS ReEncrypt hỗ trợ mọi source/target | API fail khi cross-provider/region/key type. | Xác minh capabilities và test adapter. |
| Re-wrap DEK đã lộ rồi tuyên bố dữ liệu an toàn | Attacker đã có DEK có thể giải mã ciphertext cũ. | Đánh giá DEK rotation/re-encryption, incident response. |
| Chỉ scan live DB, quên archive/snapshot | Không thể restore khi hủy KEK cũ. | Dependency graph và restore drill. |
| Không khóa đường new writes cũ | Sau migration vẫn có record mới dưới v3. | Single-write v4 và alert legacy writers. |
| Dùng alias làm material version duy nhất | Sai lịch sử rotation, không tìm đúng old key. | Ghi trusted key references và version metadata. |
| Coi mã `MIGRATED` là đã verify dữ liệu | Chưa kiểm AAD/tag và read compatibility. | Negative tests và decrypt checks đại diện. |
| Coi non-exportable là không thể bị lạm dụng | Actor có quyền API vẫn có thể unwrap/re-wrap. | Policy scoped, workflow approval, audit. |
| Xóa wrapped DEK cũ rồi coi đã crypto-shred | Có thể còn bản sao DEK/KEK và plaintext. | Kiểm kê mọi đường khôi phục và phụ thuộc. |

## 16. Checklist thiết kế re-wrap DEK

Trước khi thực hiện rotation, hãy kiểm tra:

1. **Mục tiêu:** vì sao đổi KEK và có thật sự cần re-wrap từng DEK?
2. **Compromise status:** có bằng chứng DEK hoặc KEK đã lộ không? Re-wrap thuần có đủ mục tiêu bảo mật không?
3. **Provider API:** KMS/HSM hỗ trợ re-wrap trong boundary nào; có giới hạn source/target không?
4. **Source/target trust:** key references, versions và migration plan có đến từ registry đã phê duyệt không?
5. **Identity/IAM:** migration worker có least privilege và không có quyền ExportKey/Destroy không?
6. **DEK handling:** có tránh trả plaintext DEK về ứng dụng nếu provider hỗ trợ native re-wrap không?
7. **Schema:** wrapped DEK, key reference/version, record revision và context có được lưu đầy đủ không?
8. **AAD:** dữ liệu AES-GCM có gắn KEK ref hoặc wrapped blob cũ vào AAD không? Nếu có, migration xử lý ra sao?
9. **Authorization:** ứng dụng/worker xác minh tenant và object trước KMS operation chưa?
10. **New writes:** tất cả writer đã chuyển sang KEK mới trước khi backlog migration chạy chưa?
11. **Read path:** có thể đọc v3 và v4 theo policy, xử lý disabled/revoked keys đúng không?
12. **Concurrency:** cập nhật wrapped DEK và key ref/version trong một CAS/transaction chưa?
13. **Idempotency:** retry sau timeout và conflict có giữ dữ liệu nhất quán không?
14. **Batching:** có giới hạn KMS quotas, concurrency, cost và backoff theo lỗi không?
15. **Observability:** có audit migration, error codes và metrics mà không log raw DEK/KEK/blob không?
16. **Dependencies:** database, archive, snapshots, queues, replicas, consumer và backups đã được kiểm kê chưa?
17. **DR:** restore point có đồng bộ data snapshot với key/material versions không?
18. **Verification:** có thử decrypt/AEAD verify mẫu bằng DEK giữ nguyên và ciphertext không đổi không?
19. **Retirement:** điều kiện retire/disable/destroy v3 có được owner/security phê duyệt không?
20. **Cleanup:** đã thu hồi grants tạm, kiểm tra không còn new writes dưới v3 và lưu bằng chứng chưa?

## 17. Câu hỏi tự kiểm tra

1. **DEK** và **KEK** khác nhau ở vai trò nào trong envelope encryption?
2. Khi re-wrap DEK từ KEK v3 sang v4, những bytes nào đổi và những bytes nào không đổi?
3. Vì sao không nhất thiết phải re-wrap khi provider tự rotate key material nội bộ?
4. Phương án KMS-native re-wrap có lợi gì so với unwrap+wrap trong ứng dụng?
5. Nếu KMS không hỗ trợ cross-provider rewrap, có thể tự xuất raw KEK để hoàn thành không?
6. **Re-wrap DEK** khác **rotate DEK/re-encrypt ciphertext** về chi phí và rủi ro thế nào?
7. Vì sao re-wrap cùng DEK không bảo vệ được bản mã khi DEK đã bị lộ?
8. `predecessor` giữa KEK v3/v4 khác quan hệ `WRAPS` giữa KEK v4 và DEK-A ra sao?
9. Nếu dữ liệu AES-GCM AAD chứa `kekRef=v3`, điều gì xảy ra khi chỉ cập nhật metadata sang v4?
10. Vì sao không được cho client tự chọn destination KEK cho re-wrap?
11. Vì sao ứng dụng vẫn cần kiểm tra tenant authorization trước KMS Decrypt/Unwrap?
12. Nếu hai workers cùng re-wrap một record, CAS giải quyết vấn đề nào?
13. KMS re-wrap thành công nhưng DB CAS thất bại thì nên làm gì?
14. Các lỗi `context mismatch`, `AccessDenied` và `KMS throttling` có cùng cách retry không?
15. Vì sao một bản backup snapshot cũ có thể vẫn cần KEK v3 dù live DB đã dùng v4?
16. Việc hủy alias current có đồng nghĩa hủy toàn bộ key material cũ không?
17. Một key non-exportable có bảo đảm principal không thể lạm dụng quyền ReEncrypt/Decrypt không?
18. Migration được đánh dấu completed có đủ chứng minh AES-GCM ciphertext vẫn verify được không?
19. Tại sao khi signing key S1 đổi sang S2 lại không gọi là re-wrap DEK?
20. KMS audit nên ghi thông tin nào để điều tra re-wrap nhưng không làm lộ secret?

**Ghi nhớ:** **Re-wrap DEK khi rotate KEK** chuyển **cùng một DEK** sang lớp bảo vệ **KEK mới**, thường **không đụng đến ciphertext dữ liệu**. Để thực hiện an toàn cần kết hợp **KMS/HSM API được hỗ trợ, key reference/version và predecessor rõ ràng, encryption context/AAD ổn định, phân quyền và kiểm toán, idempotency + CAS, new-write cutover, đối soát inventory/backup và restore drill**. Nếu **DEK đã bị lộ**, re-wrap **không đủ**: phải đánh giá **DEK rotation, re-encryption và ứng phó sự cố**. Chỉ retire hoặc hủy KEK cũ khi thực sự không còn dependency cần đường khôi phục và có phê duyệt theo vòng đời khóa.

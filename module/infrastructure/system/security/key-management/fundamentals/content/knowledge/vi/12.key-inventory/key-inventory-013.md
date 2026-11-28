# Version và predecessor – Theo dõi phiên bản và quan hệ tiền nhiệm của khóa mật mã

**Version (phiên bản khóa)** và **predecessor (khóa hoặc phiên bản tiền nhiệm)** là hai khái niệm giúp **key inventory** ghi nhận chính xác **vật liệu khóa nào đã được sử dụng, nó thay thế phiên bản nào và những hệ thống/dữ liệu nào còn phụ thuộc phiên bản cũ**. Khi xoay vòng (rotation), một khóa mới có thể được cấp phát cho thao tác mã hóa hoặc ký mới trong khi khóa tiền nhiệm vẫn phải được quản lý có kiểm soát để giải mã dữ liệu hoặc xác minh chữ ký lịch sử.

Trong chương **Key inventory** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, theo dõi version và predecessor tạo nền tảng cho vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Hai trường này liên kết mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán để tránh **dùng nhầm khóa, mất dữ liệu sau rotation hoặc tiếp tục tin khóa đã bị lộ**.

> **Cốt lõi:** Version cho biết **đang nói về thế hệ vật liệu khóa nào**; predecessor thể hiện **quan hệ kế tiếp trực tiếp trong một chuỗi thay khóa do hệ thống định nghĩa**. Cả hai chỉ là **metadata quản trị**, không tự bảo đảm khóa an toàn, không phải secret và không có nghĩa khóa mới được dẫn xuất bằng mật mã từ khóa cũ.

## 1. Tại sao key inventory cần version và predecessor?

Giả sử Billing Service dùng **KEK v3** trong KMS để bọc 50.000 DEK phục vụ dữ liệu hóa đơn. Khi tạo KEK v4, hệ thống cần biết:

- Phiên bản nào **được phép wrap DEK mới**?
- Những DEK nào vẫn được bảo vệ bằng **KEK v3**, kể cả ở backup?
- **KEK v4 thay thế v3 hay là khóa của một nhóm khác**?
- Nếu ngừng v3, các dịch vụ đang chạy phiên bản cũ có còn khả năng **unwrap** không?
- Khi v4 bị nghi lộ, cần điều tra v4 và những phiên bản nào khác?
- Có thể chứng minh **ai phê duyệt và khi nào** việc chuyển từ v3 sang v4?

Nếu chỉ có một alias **billing-kek-current**, các câu hỏi trên khó trả lời vì alias có thể đã đổi từ v3 sang v4. Inventory cần ghi nhận **định danh phiên bản bất biến, quan hệ tiền nhiệm, trạng thái từng phiên bản và dữ liệu còn phụ thuộc**.

Một ví dụ khác: Payment Service xoay khóa ký từ **S1** sang **S2**. Sau khi S2 ký sự kiện mới, Ledger Service có thể vẫn phải xác minh sự kiện cũ bằng **public key S1** trong thời hạn được cho phép. Nếu xóa S1 khỏi mọi nguồn trust quá sớm, các sự kiện cũ bị từ chối; nếu tiếp tục tin S1 vô thời hạn sau khi private key bị lộ, chữ ký giả có thể được chấp nhận.

**Version và predecessor cho phép phân biệt hai câu hỏi khác nhau:** khóa **nào hiện được ưu tiên cho thao tác mới**, và khóa **nào còn cần cho thao tác lịch sử**.

## 2. Bốn lớp định danh thường bị nhầm

Một hệ thống quản lý khóa có thể đồng thời sử dụng **logical key**, **key object**, **material version** và **alias**.

| Khái niệm | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **Logical key family** | billing-invoice-kek | Nhóm khóa cùng mục đích, owner và phạm vi nghiệp vụ; do hệ thống quản trị định nghĩa. |
| **Provider key object** | ID hoặc resource URI của KMS/HSM | Đối tượng mà nhà cung cấp quản lý; có thể duy trì nhiều phiên bản vật liệu hoặc dùng đối tượng mới khi rotate. |
| **Key material version** | v3, v4 hoặc một version ID bất biến | Xác định **thế hệ vật liệu mật mã** cụ thể; quan trọng khi phân tích dữ liệu và lịch sử sử dụng. |
| **Alias/current pointer** | billing-kek-current | Đường tham chiếu tiện dụng đến khóa/phiên bản dùng cho thao tác mới; có thể thay đổi theo thời gian. |

**Không có một quy ước version chung cho mọi KMS.** Một số nhà cung cấp tự động xoay vật liệu bên trong cùng một key ID và giải mã bản mã cũ theo cơ chế nội bộ; nơi khác tạo key object mới hoặc công khai version ID. Inventory nên lưu **đúng định danh bất biến mà provider thực sự cung cấp**, cộng với **phiên bản logic** của tổ chức nếu cần, đồng thời ghi rõ hai lớp này khác nhau.

### 2.1. Ví dụ các bản ghi theo thời gian

| Ngày hiệu lực minh họa | Logical family | Material version | Predecessor | Dùng cho thao tác mới? |
| --- | --- | --- | --- | --- |
| Giai đoạn đầu | billing-invoice-kek | v1 | Không có | Có, ở thời điểm v1 hoạt động. |
| Sau rotation lần 1 | billing-invoice-kek | v2 | v1 | Có, sau khi v2 được kích hoạt. |
| Sau rotation lần 2 | billing-invoice-kek | v3 | v2 | Có, sau khi v3 được kích hoạt. |
| Giai đoạn hiện tại | billing-invoice-kek | v4 | v3 | Có, khi v4 active và hệ thống đã chuyển. |

Khi v4 active, v1–v3 không tự biến mất. Chúng có thể được duy trì cho **decrypt/unwrap/verify lịch sử**, hoặc chuyển sang trạng thái revoked/disabled nếu có sự cố theo chính sách. **Trạng thái** là một chiều quản trị riêng, không suy ra trực tiếp chỉ từ số version.

### 2.2. Version không phải độ mạnh của thuật toán

**v4 không mặc nhiên an toàn hơn v3**: phiên bản mới có thể được sinh từ RNG cấu hình sai, bị cấp quyền quá rộng hoặc dùng thuật toán không phù hợp. Đánh giá an toàn phải dựa trên **algorithm, key size, key usage, custody, access policy, provenance và rủi ro đã biết**.

Tương tự, tên **AES-256** cho biết thuật toán/kích thước khóa nhưng **không chỉ ra phiên bản DEK**. Hai DEK đều là AES-256 vẫn là hai vật liệu khóa khác nhau.

## 3. Predecessor là gì và khác với dependency ra sao?

**Predecessor** là một **liên kết lịch sử có hướng** từ phiên bản khóa mới tới **phiên bản trực tiếp đứng trước trong cùng chuỗi thay thế** do ứng dụng định nghĩa.

~~~mermaid
flowchart LR
    V1["KEK v1"] --> V2["KEK v2"]
    V2 --> V3["KEK v3"]
    V3 --> V4["KEK v4: active"]
~~~

Đọc sơ đồ theo chiều thời gian: **v4 có predecessor là v3**, v3 có predecessor là v2, v2 có predecessor là v1. Liên kết này ghi nhận lịch sử **thay thế vì mục đích vận hành**; nó không nói khóa v4 được suy ra bằng KDF từ v3.

**Phân biệt predecessor với các quan hệ khác:**

| Quan hệ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **PREDECESSOR_OF / SUCCESSOR_OF** | v3 → v4 | Lịch sử phiên bản và lần thay khóa. |
| **WRAPS / WRAPPED_BY** | KEK v4 → DEK-A | Vật liệu khóa nào bảo vệ khóa nào. |
| **ENCRYPTS / ENCRYPTED_BY** | DEK-A → invoice-2026 | Dữ liệu nào được mã hóa bởi khóa nào. |
| **SIGNS / VERIFIED_BY** | signing S2 → event-batch | Bản ghi được ký bằng private key nào và xác minh theo public key nào. |
| **TRUSTS** | Ledger Service → signing S1 | Consumer còn chấp nhận public key nào. |
| **OWNED_BY** | KEK v4 → Billing Security | Trách nhiệm quản trị, không phải quan hệ mật mã. |
| **REPLICATED_TO / BACKED_UP_IN** | wrapped DEK → archive | Những bản sao nào còn phụ thuộc bản mã/khóa. |

**Một key có thể có predecessor nhưng vẫn không có dependency nào được ghi nhận.** Ngược lại, một KEK đang active có thể bọc hàng nghìn DEK mà không có predecessor nếu nó là khóa đầu tiên trong family.

### 3.1. Predecessor có bắt buộc là version n − 1?

**Không phải quy tắc chung.** Nếu tổ chức dùng version tuần tự cho **một chuỗi tuyến tính**, có thể áp dụng n → n+1. Nhưng trong thực tế:

- Version ID do provider cấp có thể là UUID/chuỗi không có thứ tự số học.
- Một phiên bản thử nghiệm có thể **chưa từng được kích hoạt**.
- Một lần migration có thể đưa dữ liệu sang **key object mới** với hệ version khác.
- Có thể cần phục hồi về một phiên bản được tin cậy cũ; việc đổi alias trở lại **không tạo ra vật liệu khóa mới**.
- Sau sự cố có thể xuất hiện **nhánh hoặc nhiều thế hệ song song** cần được quản lý riêng.

Vì vậy predecessor cần là **tham chiếu rõ ràng tới bản ghi trước**, không nên suy bằng phép trừ số version. Nếu mô hình chỉ cho phép một chuỗi tuyến tính, phải **thực thi ràng buộc đó** thay vì giả định nó luôn đúng.

### 3.2. Nhánh, rollback và migration

Một số tổ chức có thể chọn mô hình **lineage dạng đồ thị** thay vì linked list:

~~~mermaid
flowchart TD
    A["v1: ban đầu"] --> B["v2: production"]
    B --> C["v3: kế hoạch rotate A"]
    B --> D["v3b: kế hoạch phục hồi B"]
    C --> E["v4: chọn thay thế"]
    D --> E
~~~

Nếu có **hai nhánh tiền nhiệm** đi vào một nút, trường đơn **predecessor** không đủ mô tả toàn bộ lịch sử. Khi đó có thể cần **lineage edges** có loại quan hệ, hoặc một chuỗi chính kèm **migrationFrom/relatedVersions**. Không tự ép mọi quan hệ migration thành predecessor trực tiếp.

**Rollback alias** từ v4 trở về v3 cũng không đồng nghĩa “v3 mới là successor của v4”. Phải ghi **alias history / activation event**, không sửa lại lịch sử sinh vật liệu khóa.

**Đơn giản hóa hợp lý cho đa số dịch vụ:** mỗi logical family có **một nhánh active cho thao tác mới**, version bất biến, **predecessor một bước**, và ghi lại các sự kiện rollback/migration riêng. Chỉ mở rộng thành DAG khi nghiệp vụ thực sự cần.

## 4. Metadata để mô tả version và predecessor

Một bản ghi key inventory có thể chứa:

| Trường minh họa | Công dụng | Ràng buộc nên có |
| --- | --- | --- |
| **familyId** | Nhóm khóa theo owner, scope và purpose. | Không đồng nhất giữa tenant/môi trường không liên quan. |
| **materialVersionId** | Định danh bất biến của vật liệu khóa. | Duy nhất trong phạm vi family/provider đã định nghĩa. |
| **providerKeyRef** | Đường tham chiếu thật trong KMS/HSM. | Được xác nhận từ provider và kiểm soát quyền xem. |
| **predecessorRef** | Bản ghi khóa được phiên bản này thay thế trực tiếp. | Phải tồn tại hoặc có trạng thái migration được xác nhận; không được tạo vòng. |
| **algorithm/keyUsage** | AES/Ed25519/RSA..., WRAP/UNWRAP/SIGN... | Có chính sách chuyển đổi giữa phiên bản và mục đích rõ ràng. |
| **createdAt/activatedAt/retiredAt** | Mốc thời gian trong vòng đời. | Phân biệt thời điểm tạo với thời điểm chuyển traffic. |
| **lifecycleState** | PREPARED, ACTIVE, RETIRED, REVOKED... | Không suy từ version; phải cập nhật qua quy trình được phép. |
| **custody/exportability** | Nơi giữ private/secret key và ranh giới bảo vệ. | Không ghi secret bytes vào inventory. |
| **rotationReason/approvalRef** | Vì sao thay và ai phê duyệt. | Có audit trail và yêu cầu separation of duties. |
| **dependencies** | Ciphertext, wrapped DEK, consumer, backup. | Có nguồn đối soát, không tin một số đếm tự khai. |
| **observationSource/observedAt** | Nguồn và độ mới của dữ liệu. | Phân biệt trạng thái quan sát với state đã được xác nhận. |

Ví dụ tài liệu metadata **giả lập**:

~~~yaml
familyId: billing-invoice-kek
materialVersionId: v4
providerKeyRef: "kms://prod/billing/keys/kek-v4"
predecessorRef:
  familyId: billing-invoice-kek
  materialVersionId: v3
algorithm: AES-256
keyUsage: [WRAP, UNWRAP]
owner: billing-security
environment: production
state: ACTIVE
createdAt: "2026-11-18T08:00:00Z"
activatedAt: "2026-11-20T10:00:00Z"
rotation:
  reason: scheduled-cryptoperiod
  approvalRef: "change-request-example"
dependencies:
  wrappedDekIndexRef: "metadata://billing/dek-index"
observation:
  source: verified-kms-metadata
  observedAt: "2026-11-28T00:00:00Z"
~~~

Đây **không phải schema của nhà cung cấp cụ thể**. Một KMS có thể chỉ trả về key ID và trạng thái hiện tại; inventory không được bịa **materialVersionId** hoặc giả định provider cung cấp mapping đầy đủ giữa các thế hệ. Khi thiếu dữ liệu xác minh, ghi nhận **unknown/not exposed** và tham chiếu chứng cứ, thay vì công bố lineage như sự thật đã kiểm chứng.

**Không đưa KEK/DEK/private key vào YAML inventory**. Chỉ lưu metadata và các tham chiếu được phân quyền; bản thân đường dẫn, owner và dependency graph cũng có thể nhạy cảm và cần RBAC.

## 5. Các bất biến cần giữ khi xây version chain

Một hệ thống quản trị không nên coi predecessor là trường văn bản để client ghi tùy ý. Các bất biến giúp giảm lỗi và tấn công:

1. **Identity bất biến:** sau khi tạo, materialVersionId và familyId không được thay đổi tùy tiện.
2. **Không tự tham chiếu:** một phiên bản không thể là predecessor của chính nó.
3. **Không tạo chu trình:** chuỗi v2 → v3 → v4 không được nối ngược từ v2 tới v4.
4. **Scope nhất quán:** mặc định predecessor phải cùng logical family/owner/tenant/environment, trừ migration được phê duyệt.
5. **Ý nghĩa thay thế rõ:** successor thay thế vai trò nào (SIGN mới, ENCRYPT mới, WRAP mới), không tự suy quyền cho thao tác khác.
6. **Một điểm active cho thao tác mới:** nếu chính sách yêu cầu chuỗi tuyến tính, chỉ một version được chỉ định để tạo mới ở thời điểm đã xác định.
7. **Không ghi đè lịch sử:** không tái sử dụng một version ID cho vật liệu khóa khác hay xóa audit của lần chuyển trước.
8. **Tính toàn vẹn nguồn:** chỉ actor/pipeline có quyền mới được đăng ký successor và thay current pointer.
9. **Ràng buộc dữ liệu phụ thuộc:** metadata ciphertext/signature phải cho phép truy đúng version hoặc cơ chế giải mã/xác minh lịch sử mà provider bảo đảm.
10. **Xử lý đồng thời:** hai yêu cầu rotate xuất phát từ cùng predecessor không được âm thầm thay current pointer theo thứ tự bất định.

### 5.1. Vì sao cần idempotency và compare-and-swap?

Giả sử hai worker cùng phát hiện cần rotate **KEK v4**. Worker A tạo successor **v5a**, worker B tạo **v5b**. Nếu cả hai đều ghi alias current mà không kiểm soát, các dịch vụ có thể đan xen dữ liệu mới giữa hai khóa và không biết ai đã được phê duyệt.

Giải pháp có thể bao gồm:

- **Idempotency key** cho từng kế hoạch rotation: retry không tạo version mới không cần thiết.
- **Optimistic concurrency / compare-and-swap (CAS):** chỉ chuyển current từ v4 sang v5 nếu current **vẫn là v4**.
- **Transaction hoặc cơ chế bù trừ:** metadata inventory, policy KMS và phân phối trust có thể không cập nhật cùng một giao dịch; phải có trạng thái **PREPARED/ACTIVATING** để quan sát và phục hồi.
- **Audit đầy đủ:** ghi lại ai đề xuất, bản kế hoạch, phiên bản nguồn/đích, thời điểm switch và kết quả.

**Không cập nhật current trước khi successor sẵn sàng dùng**. Với khóa ký, phải đảm bảo verifier đã nhận public key mới; với KEK, phải đảm bảo ứng dụng có quyền sử dụng phiên bản mới và đường khôi phục dữ liệu cũ hoạt động.

## 6. Chuyển version trong envelope encryption

Trong **envelope encryption**, dữ liệu được mã hóa bằng **DEK** (thường AES-GCM), còn DEK được bảo vệ bởi **KEK** trong KMS/HSM. Hai chuỗi version riêng biệt có thể tồn tại đồng thời.

~~~mermaid
flowchart TD
    K3["KEK v3: tiền nhiệm"] --> K4["KEK v4: active"]
    K3 -. "rewrap DEK-A" .-> WK4["DEK-A được bọc dưới KEK v4"]
    K4 --> WK4
    D1["DEK-A v1"] --> C1["Ciphertext hóa đơn lịch sử"]
    WK4 --> D1
    D1 --> D2["DEK-A v2: thay DEK"]
    D2 --> C2["Ciphertext được mã hóa lại"]
~~~

Sơ đồ thể hiện hai loại thay đổi **khác nhau**:

- **KEK rotation / DEK rewrap:** DEK-A v1 có thể **giữ nguyên giá trị bí mật**; chỉ bản bọc DEK chuyển từ KEK v3 sang KEK v4. Dữ liệu mã hóa dưới DEK-A v1 **thường không cần mã hóa lại**.
- **DEK rotation:** DEK-A v2 là vật liệu khóa **mới**; nếu muốn thay thế bảo vệ dữ liệu cũ, cần **re-encrypt/migrate ciphertext** theo kế hoạch. Chỉ đổi alias DEK hoặc thay metadata version mà không thay bản mã là sai.

**Predecessor của KEK v4 là KEK v3**, không phải DEK-A v1. Quan hệ **KEK v4 WRAPS DEK-A v1** là dependency khác; **predecessor của DEK-A v2** (nếu ứng dụng chọn theo dõi như family) là DEK-A v1.

### 6.1. Những gì ciphertext cần mang theo

Một record mã hóa hoặc metadata liên kết cần đủ dữ liệu để giải mã đúng, ví dụ:

- **Thuật toán/mode**: AES-GCM và tham số phù hợp.
- **Nonce/IV và authentication tag** theo format mã hóa.
- **DEK ID/material version** hoặc tham chiếu đến một đối tượng chứa thông tin cần giải mã.
- **Wrapped DEK** và **KMS key reference/phiên bản** nếu giao thức/provider cần; một số blob do KMS sinh đã tự mang thông tin nội bộ.
- **AAD/encryption context** phù hợp và cơ chế bảo vệ tính toàn vẹn của các trường nhạy cảm với ngữ cảnh.
- **Định dạng/phiên bản schema** để code cũ và mới đọc thống nhất trong giai đoạn chuyển đổi.

**Không phải mọi KMS cho phép hoặc yêu cầu ứng dụng chọn một material version cụ thể để decrypt.** Một số dịch vụ tự chọn lịch sử vật liệu tương ứng theo blob mã hóa. Do đó inventory cần ghi **mức lineage thực sự quan sát được**, không giả định mỗi ciphertext đều có một phiên bản provider do application đọc ra.

### 6.2. Dual-read và single-write

Trong cửa sổ migration, một chiến lược thường dùng là:

1. **Single-write:** mọi dữ liệu mới được mã hóa/wrap bằng version hiện hành.
2. **Dual-read hoặc multi-version read:** hệ thống vẫn có khả năng đọc dữ liệu cũ bằng version tương ứng theo metadata/khả năng của KMS.
3. **Migration/rewrap nền:** dần chuyển các đối tượng còn phụ thuộc version tiền nhiệm.
4. **Đối soát:** inventory xác nhận những bản mã, archive và backup nào còn dùng predecessor.
5. **Retire rồi destroy:** chỉ ngừng quyền cũ và hủy vật liệu sau khi đánh giá đầy đủ nhu cầu khôi phục, retention và sự cố.

**Dual-read không có nghĩa “thử mọi secret key đến khi giải mã thành công”**. Hãy sử dụng key reference đã xác thực và phiên bản phù hợp; việc thử bừa có thể gây lỗi phân quyền, khó kiểm toán và mở rộng bề mặt lạm dụng API Decrypt.

### 6.3. Rủi ro khi predecessor bị lộ

Nếu **DEK v1 đã bị lộ**, bọc lại **cùng DEK v1** dưới KEK v4 không làm ciphertext cũ bí mật trở lại. Cần đánh giá tạo **DEK v2 và re-encrypt** những dữ liệu còn nhạy cảm.

Nếu **KEK v3 bị nghi lộ**, phải đánh giá DEK nào có thể đã được lấy hoặc mở từ v3, ai đã gọi Unwrap và những bản sao lịch sử nào còn tồn tại. Việc tạo KEK v4 là một phần ứng phó, **không tự xóa tác động đã xảy ra**.

## 7. Version và predecessor của khóa ký số

Đối với khóa ký Ed25519/ECDSA/RSA-PSS, **version chain** giúp chuyển người ký sang cặp khóa mới và bảo đảm bên xác minh không nhầm khóa.

~~~mermaid
sequenceDiagram
    participant K as KMS / Key registry
    participant S as Payment Service
    participant V as Ledger Service
    K->>K: Sinh signing key S2, predecessor S1
    K->>V: Công bố public key S2 qua kênh tin cậy
    V->>K: Xác nhận trust policy/khả năng Verify S2
    K->>S: Cho phép chuyển signer sang S2
    S->>V: Sự kiện mới + signature + key ID S2
    V->>V: Verify bằng public key S2 đã xác thực
    Note over V: S1 có thể còn dùng xác minh sự kiện cũ theo policy
    K->>K: Retire quyền Sign của S1, đánh giá thu hồi/hủy
~~~

**Key ID/kid** giúp bên xác minh chọn **đúng khóa trong tập khóa đáng tin**, nhưng **không tự tạo niềm tin**. Verifier vẫn phải kiểm tra issuer, thuật toán, audience, mục đích, thời hạn và nguồn public key (ví dụ JWKS/chứng chỉ/registry đã được cấu hình tin cậy).

**Điểm đặc thù:** Hủy **private signing key S1** không khiến public key S1 mất khả năng xác minh chữ ký cũ về mặt toán học. Tuy nhiên việc **còn được chấp nhận một chữ ký S1 hay không** phụ thuộc trạng thái thu hồi, thời điểm ký, chứng chỉ, bằng chứng thời gian và chính sách nghiệp vụ.

### 7.1. Không suy ra chính sách trust chỉ từ predecessor

Không nên thiết kế “nếu S2 được tin thì mọi predecessor của S2 đều được tin”. Khóa tiền nhiệm có thể đã **bị lộ**, dùng thuật toán bị cấm hoặc vượt hạn sử dụng. Một successor mới không tự khôi phục sự tin cậy của các predecessor.

Trust policy cần xác định:

- Version nào **được phép ký mới**.
- Version nào **được phép xác minh bản ghi lịch sử** và trong thời hạn/điều kiện nào.
- Version nào **bị thu hồi hoàn toàn** hoặc chỉ có giá trị xác minh bằng chứng lịch sử cụ thể.
- Consumer nào còn dùng public key cũ và đã cập nhật đến phiên bản nào.

## 8. Version trong KMS/HSM và các hệ thống nhiều nhà cung cấp

KMS/HSM có thể dùng nhiều mô hình quản lý version:

| Mô hình | Đặc điểm | Thiết kế inventory phù hợp |
| --- | --- | --- |
| **Một key object, nhiều thế hệ vật liệu bên trong** | Provider tự rotate và giữ khả năng decrypt theo cơ chế riêng. | Ghi key object + version/rotation metadata **nếu provider công khai**; không bịa version ID nội bộ. |
| **Mỗi rotation tạo key object mới** | Alias/current pointer chuyển từ object cũ sang object mới. | Dùng **logical family** để nối predecessor giữa các provider key objects. |
| **HSM slot/label + object ID** | Định danh phụ thuộc thiết bị/cluster và khả năng backup. | Ghi tham chiếu bất biến trong phạm vi HSM, phân biệt label có thể đổi. |
| **BYOK/imported key material** | Vật liệu do bên ngoài tạo/nhập với quy tắc riêng. | Ghi provenance, phạm vi export, hạn dùng, rotation/backup khác khóa provider-generated. |
| **Cross-region/cross-provider migration** | Dữ liệu và key reference có thể đổi namespace. | Dùng edge migration riêng hoặc predecessor được phê duyệt, có mapping minh bạch. |

**Không nên ép ứng dụng đọc raw key để tự tính version.** Key fingerprint của public key có thể là metadata công khai, nhưng với khóa đối xứng, không nên gọi ExportKey hoặc băm secret thô chỉ để định danh. Dùng **provider key ID, phiên bản có thẩm quyền và hệ thống đăng ký đã kiểm chứng**.

Một **KMS non-exportable key** giảm rủi ro lộ vật liệu, nhưng không ngăn dịch vụ có quyền gọi **Sign/Decrypt/Unwrap** lạm dụng API. Inventory cần ghi **policy và principal được phép**, không chỉ version.

## 9. Java 17: mô phỏng key version chain và chuyển current an toàn

Ví dụ dưới đây chỉ quản lý **metadata** theo một logical family; không tạo, xuất, mã hóa hoặc sao chép vật liệu khóa. Nó minh họa:

- Mỗi version có **định danh bất biến** và **predecessor trực tiếp**.
- Successor chỉ được đăng ký khi predecessor **đang là current**.
- Một successor được tạo ở trạng thái **PREPARED**, chưa dùng cho thao tác mới.
- **Activate** chỉ chuyển current nếu predecessor vẫn đúng; phiên bản cũ thành **RETIRED**, để còn phục vụ lịch sử theo chính sách.
- Bản ghi version cũ có thể tra cứu qua ID ngay cả khi alias/current đã chuyển.

~~~java
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class KeyVersionInventoryDemo {
    enum State { PREPARED, ACTIVE, RETIRED, REVOKED }

    record KeyRef(String family, int version) {
        KeyRef {
            if (family == null || family.isBlank() || version < 1) {
                throw new IllegalArgumentException("Invalid key reference");
            }
        }
    }

    record KeyRecord(KeyRef ref, KeyRef predecessor, String custodyRef,
                     String purpose, State state, Instant createdAt) {
        KeyRecord withState(State next) {
            return new KeyRecord(ref, predecessor, custodyRef,
                    purpose, next, createdAt);
        }
    }

    static final class Inventory {
        private final Map<KeyRef, KeyRecord> records = new HashMap<>();
        private final Map<String, KeyRef> current = new HashMap<>();
        private final Map<String, KeyRef> prepared = new HashMap<>();

        synchronized void registerFirst(String family, String custody,
                                        String purpose) {
            if (current.containsKey(family)) {
                throw new IllegalStateException("Family already exists");
            }
            KeyRef first = new KeyRef(family, 1);
            records.put(first, new KeyRecord(
                    first, null, custody, purpose, State.ACTIVE, Instant.now()));
            current.put(family, first);
        }

        synchronized KeyRef prepareSuccessor(KeyRef expectedPredecessor,
                                             String newCustodyRef) {
            if (!expectedPredecessor.equals(
                    current.get(expectedPredecessor.family()))) {
                throw new IllegalStateException("Current version changed");
            }
            if (prepared.containsKey(expectedPredecessor.family())) {
                throw new IllegalStateException("Rotation already prepared");
            }
            KeyRecord old = records.get(expectedPredecessor);
            if (old == null || old.state() != State.ACTIVE) {
                throw new IllegalStateException("Predecessor is not active");
            }

            KeyRef next = new KeyRef(
                    expectedPredecessor.family(),
                    expectedPredecessor.version() + 1);
            if (records.containsKey(next)) {
                throw new IllegalStateException("Version already reserved");
            }
            records.put(next, new KeyRecord(
                    next, expectedPredecessor, newCustodyRef,
                    old.purpose(), State.PREPARED, Instant.now()));
            prepared.put(next.family(), next);
            return next;
        }

        synchronized void activate(KeyRef successor,
                                   KeyRef expectedPredecessor) {
            KeyRecord next = records.get(successor);
            if (next == null || next.state() != State.PREPARED
                    || !Objects.equals(next.predecessor(), expectedPredecessor)
                    || !Objects.equals(current.get(successor.family()),
                                       expectedPredecessor)
                    || !Objects.equals(prepared.get(successor.family()),
                                       successor)) {
                throw new IllegalStateException("Invalid rotation state");
            }

            // Mô phỏng CAS trong một tiến trình. Production cần transaction
            // hoặc CAS bền vững + phối hợp policy KMS và consumer readiness.
            records.put(expectedPredecessor, records.get(
                    expectedPredecessor).withState(State.RETIRED));
            records.put(successor, next.withState(State.ACTIVE));
            current.put(successor.family(), successor);
            prepared.remove(successor.family());
        }

        synchronized KeyRef currentForNewUse(String family) {
            return current.get(family);
        }

        synchronized KeyRecord historical(KeyRef ref) {
            // Chỉ tra metadata; việc Decrypt/Verify còn phải qua policy.
            return records.get(ref);
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();
        inventory.registerFirst(
                "billing-kek", "kms://prod/billing/kek-v1", "WRAP_UNWRAP");

        KeyRef v1 = inventory.currentForNewUse("billing-kek");
        KeyRef v2 = inventory.prepareSuccessor(
                v1, "kms://prod/billing/kek-v2");
        System.out.println("Before activate: " +
                inventory.currentForNewUse("billing-kek")); // v1

        // Ở hệ thống thật: xác minh key v2 sẵn sàng, quyền KMS,
        // consumer readiness và kế hoạch dữ liệu trước khi activate.
        inventory.activate(v2, v1);
        System.out.println("After activate: " +
                inventory.currentForNewUse("billing-kek")); // v2
        System.out.println("v2 predecessor: " +
                inventory.historical(v2).predecessor());    // v1
        System.out.println("v1 state: " +
                inventory.historical(v1).state());          // RETIRED
    }
}
~~~

### 9.1. Tại sao ví dụ không tự gọi Decrypt hoặc Destroy?

**RETIRED** trong ví dụ chỉ là trạng thái metadata: chính sách thật có thể cho phép **UNWRAP dữ liệu lịch sử**, hoặc có thể cấm ngay nếu sự cố. **Không được suy quyền mật mã từ enum Java** mà bỏ qua ACL và trạng thái thật của KMS/HSM.

Ngoài ra, code dùng **synchronized và HashMap trong một tiến trình** nên không giải quyết hai instance ghi cùng lúc, crash giữa các bước, retry mạng, race với consumer hoặc KMS policy cập nhật không đồng bộ. Production cần lưu **idempotency key, revision/CAS tại database**, nhật ký sự kiện, chính sách quyền và một quy trình điều phối rotation có thể tiếp tục sau lỗi.

### 9.2. Điểm cần bổ sung trong triển khai thật

- **Tách quyền PREPARE, APPROVE, ACTIVATE và DESTROY**.
- Lưu **rotation request ID**, actor, reason, approval, expected old/current và timestamps.
- Dùng **providerKeyRef** đã được xác thực từ KMS; không tin đường dẫn do caller tự khai.
- Kiểm tra **owner, tenant, environment, key usage, algorithm** của successor trước khi kích hoạt.
- Thực thi **cập nhật current an toàn khi có nhiều node** và ghi audit có tính toàn vẹn.
- Có **quy trình quay lại** nếu activation thất bại, nhưng không sửa ngược quan hệ predecessor đã ghi.
- Liên kết **ciphertext/DEK/signing consumer** để xác minh khả năng đọc và chuyển sử dụng.
- Không tự động hủy predecessor chỉ vì successor đã active.

## 10. Kiểm toán phiên bản và truy vết sự kiện thay khóa

Inventory cần giữ được chuỗi sự kiện, không chỉ trạng thái cuối.

| Sự kiện | Dữ liệu nên ghi | Rủi ro cần tránh |
| --- | --- | --- |
| **KeyCreated / KeyImported** | Key ref, owner, thuật toán, purpose, nguồn, thời gian, actor. | Không log private/secret key material. |
| **VersionRegistered** | Material version, predecessor, approval, provenance. | Không cho sửa predecessor sau khi đã được xác nhận. |
| **RotationPrepared** | Old/new refs, kế hoạch, trạng thái consumer, request ID. | Không coi PREPARED là ACTIVE. |
| **TrustPublished / ConsumerReady** | Signing public key/chứng chỉ và consumer readiness đã xác minh. | Không suy public key đáng tin chỉ vì được đăng ký. |
| **VersionActivated** | CAS expected/current, old/new, actor, thời điểm, policy revision. | Tránh hai successor đồng thời cùng được chọn làm current. |
| **KeyRetired / Disabled / Revoked** | Lý do, phạm vi tác động, chính sách read/verify lịch sử. | Không đánh đồng retire với destroy hoặc revoke. |
| **Rewrap / ReencryptProgress** | Số đối tượng đã xử lý, dữ liệu tồn đọng và nguồn đối soát. | Không ghi plaintext/DEK vào audit. |
| **KeyDestroyed** | Bằng chứng hủy, bản sao và phụ thuộc đã được kiểm kê, phê duyệt. | Không tuyên bố destroyed chỉ vì xóa một bản ghi inventory. |

Nên giữ **event history dạng append-only hoặc có khả năng phát hiện sửa đổi**, đồng thời giới hạn người có quyền thay lineage. Nếu một bản ghi bị xóa hoặc một predecessor bị tráo, việc điều tra phải có cơ sở truy ra giá trị trước và người thay đổi.

**Timeline của khóa không chỉ có một đồng hồ:** createdAt, approvedAt, activatedAt, firstUsedAt, retiredAt và destroyedAt có thể khác nhau. Đối với signing key, thời điểm ký một tài liệu và thời gian chứng chỉ/chính sách còn hiệu lực cũng là các khái niệm riêng.

## 11. Các tình huống vận hành cần xử lý

### 11.1. Predecessor đã hủy nhưng còn backup

**Tình huống:** Inventory chỉ còn KEK v4 active; predecessor v3 đã hủy sau khi các DEK trực tuyến được rewrap, nhưng snapshot cũ vẫn chứa wrapped DEK chỉ dưới v3.

**Tác động:** Khi phục hồi snapshot, hệ thống có thể **không unwrap được DEK**, làm mất khả năng đọc dữ liệu.

**Phòng vệ:** Trước hủy, kiểm kê **backup/replica/archive**, thử restore theo quy trình, xác định chính sách retention và phương án rewrap/migration. **Không mặc định khi dữ liệu trực tuyến đã chuyển thì mọi bản sao cũng đã chuyển**.

### 11.2. Khóa ký mới đã dùng nhưng verifier chưa cập nhật

**Tình huống:** Payment Service chuyển từ signing S1 sang S2 ngay sau khi tạo S2; Ledger Service vẫn chỉ có public key S1.

**Tác động:** Chữ ký mới hợp lệ về mật mã nhưng Ledger từ chối vì thiếu trust mapping hoặc key version.

**Phòng vệ:** **Công bố và xác minh readiness của public key S2 trước**, rồi mới kích hoạt luồng ký mới. Kiểm tra issuer, key usage, thuật toán và audience; trong giai đoạn chuyển đổi giữ khả năng xác minh S1 theo chính sách.

### 11.3. Hai pipeline cùng tạo successor

**Tình huống:** Từ v4, hai pipeline tạo v5a và v5b. Nếu chỉ dùng một trường version=5, inventory không thể phân biệt vật liệu khóa nào đang được dùng.

**Phòng vệ:** Có **material ID bất biến** cho từng khóa, idempotency, CAS, phê duyệt và kiểm soát branch. Khi có nhiều nhánh hợp lệ, model lineage cần hỗ trợ **khóa có liên quan** mà không giả định một predecessor duy nhất mô tả hết.

### 11.4. Xóa alias bị hiểu nhầm là đã hủy khóa

**Tình huống:** Quản trị viên xóa alias billing-kek-current, nhưng key object và các phiên bản cũ trong KMS vẫn còn.

**Tác động:** Ứng dụng dùng alias có thể lỗi, nhưng key material chưa chắc bị hủy. Ngược lại, xóa bản ghi inventory cũng không hủy private key.

**Phòng vệ:** Phân biệt **alias update, permission disable, key deletion scheduling, crypto-shredding và destruction evidence**. Mỗi thao tác có tác động và điều kiện riêng.

### 11.5. Chuyển thuật toán hoặc KMS provider

**Tình huống:** Một tổ chức muốn chuyển từ RSA signing key sang Ed25519, hoặc chuyển KEK từ KMS A sang KMS B.

**Phòng vệ:** Có thể tạo **logical successor** theo mục đích nhưng phải ghi **migration type**, thuật toán/provider cũ-mới, khả năng consumer tương thích, chính sách xuất/nhập key, rewrap hoặc chuyển dữ liệu. Đừng mặc định successor có thể giải mã bản mã predecessor hoặc xác minh chữ ký bằng cùng API/encoding.

## 12. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ lưu alias current, không lưu version đã dùng | Không tìm được khóa giải mã/xác minh dữ liệu lịch sử. | Lưu material version/ref bất biến và chính sách tương thích. |
| Suy predecessor bằng version − 1 | Sai khi có gap, rollback, UUID version hoặc migration. | Ghi liên kết predecessor tường minh, kiểm tra nguồn. |
| Đồng nhất predecessor với khóa wrap DEK | Sai dependency graph, có thể hủy KEK/DEK nhầm. | Tách edge SUCCEEDS, WRAPS, ENCRYPTS, TRUSTS. |
| Dùng predecessor như secret để dẫn xuất key mới | Trộn khái niệm quản trị với mật mã, có thể tạo khóa không an toàn. | Sinh vật liệu bằng CSPRNG/KMS/HSM hoặc KDF chuẩn khi thiết kế yêu cầu. |
| Cho caller tự sửa predecessor/owner/version | Có thể tạo lịch sử giả, vượt quyền hoặc che giấu khóa bị lộ. | RBAC, kiểm tra invariant, audit không thể sửa tùy tiện. |
| Kích hoạt successor trước khi consumer sẵn sàng | Chữ ký mới bị từ chối; dữ liệu mới không giải mã được. | PREPARED → kiểm tra readiness → CAS activation. |
| Coi v4 active là v3 đã an toàn để hủy | Có thể còn ciphertext, backup hoặc event ký lịch sử. | Đối soát dependency graph và retention trước hủy. |
| Chỉ rewrap KEK khi DEK đã bị lộ | Ciphertext cũ vẫn có thể bị giải mã. | Thay DEK và re-encrypt dữ liệu còn cần bảo vệ. |
| Coi mọi predecessor vẫn đáng tin | Khóa bị lộ/hết hạn có thể được chấp nhận vô hạn. | Trust policy độc lập theo version, thời điểm và trạng thái sự cố. |
| Dùng cùng AES-GCM key và reset nonce counter sau rotate alias | Dễ trùng key+nonce khi alias đổi nhưng material không đổi. | Kiểm soát nonce theo vật liệu khóa thật và key lifetime. |
| Cập nhật current bằng last-write-wins | Hai kế hoạch rotation ghi đè nhau, lệch metadata. | Idempotency, CAS/transaction, audit/điều phối. |
| Nhầm một KMS key ID với một material version | Không phản ánh rotation nội bộ của provider. | Lưu cả logical family và version nếu có; ghi thiếu thông tin nếu provider không cung cấp. |
| Mặc định provider luôn hỗ trợ decrypt theo version ID | Lỗi tương thích hoặc mất khả năng tìm lại khóa. | Theo dõi hợp đồng API/provider và định dạng ciphertext thật. |
| Xóa lịch sử predecessor khi retire | Không điều tra được sự cố hoặc di chuyển dữ liệu. | Lưu lịch sử lineage và metadata theo retention. |
| Không ghi private-key custody và quyền API | Non-exportable vẫn bị lạm dụng để Sign/Decrypt trái phép. | Least privilege, KMS/HSM policy và giám sát thao tác. |

## 13. Checklist thiết kế version lineage

Trước khi triển khai version và predecessor cho key inventory, hãy kiểm tra:

1. **Logical family** có gắn rõ owner, môi trường, tenant và mục đích khóa chưa?
2. **Key object**, **material version** và **alias** có được phân biệt trong schema và API không?
3. Predecessor biểu diễn **thay thế trực tiếp** hay một quan hệ migration rộng hơn? Có định nghĩa rõ không?
4. Nếu provider không công khai version nội bộ, inventory có phản ánh hạn chế đó trung thực không?
5. Có bảo đảm **identity bất biến, không vòng, không nhánh ngoài ý muốn** không?
6. Có CAS/idempotency để tránh hai pipeline cùng kích hoạt successor không?
7. Có tách trạng thái **PREPARED, ACTIVE, RETIRED, REVOKED/COMPROMISED, DESTROYED** theo policy không?
8. Dữ liệu mã hóa/chữ ký cũ có chỉ ra đúng key ref và scheme để xử lý lịch sử không?
9. Trong envelope encryption, có phân biệt **KEK rotation/rewrap** với **DEK rotation/re-encrypt** không?
10. Với khóa ký, verifier đã nhận public key mới trước khi signer chuyển sang successor chưa?
11. Có biết những **ciphertext, wrapped DEK, certificate, token, release, consumer và backup** còn phụ thuộc predecessor không?
12. Có kế hoạch khi **private key, DEK hoặc KEK bị lộ** mà không nhầm lẫn giữa việc thay vật liệu và việc bảo vệ dữ liệu cũ không?
13. Có audit actor, approval, old/new ref, thời điểm và kết quả change policy/current pointer không?
14. Việc hủy predecessor có phụ thuộc **recovery test và retention** chứ không chỉ số version không?
15. Tài liệu và cảnh báo có chỉ rõ trạng thái nào là **source-of-truth** từ KMS/HSM/trust registry không?

## 14. Câu hỏi tự kiểm tra

1. Version khác **logical key family**, **provider key ID** và **alias current** như thế nào?
2. Predecessor của KEK v4 nói lên điều gì? Nó có chứng minh KEK v4 được dẫn xuất từ KEK v3 không?
3. Vì sao **predecessor không nhất thiết là version n − 1**?
4. Predecessor khác quan hệ **WRAPS** hoặc **ENCRYPTS** như thế nào?
5. Nếu alias chuyển sang v4, có thể bỏ v3 ra khỏi hệ thống ngay không? Vì sao?
6. Tại sao **KEK rewrap** thường không đòi hỏi mã hóa lại dữ liệu, còn **DEK rotation** thường có?
7. Nếu DEK v1 bị lộ, chỉ rotate KEK có đủ bảo vệ bản mã cũ không?
8. Vì sao **public key S2** nên được công bố trước khi chuyển signer sang S2?
9. Sau khi private signing key S1 bị hủy, hệ thống còn xác minh chữ ký lịch sử bằng dữ liệu nào?
10. Hai worker cùng tạo successor từ một predecessor cần kiểm soát đồng thời thế nào?
11. Khi KMS không cung cấp version ID nội bộ, inventory có nên tự bịa ID để coi là đã kiểm kê đầy đủ không?
12. Nếu v4 bị revoke, tất cả predecessor có tự trở nên đáng tin hoặc không đáng tin không?
13. Khác nhau giữa **rollback alias**, **register successor** và **destroy key material** là gì?
14. Một inventory chỉ biết current version nhưng không biết backup phụ thuộc có đủ cơ sở để crypto-shred khóa cũ không?

**Ghi nhớ:** **Version** xác định thế hệ vật liệu khóa cần quản lý; **predecessor** liên kết thế hệ đó với phiên bản được thay thế trong lịch sử. Chúng giúp **key inventory** truy vết rotation, lựa chọn đúng khóa cho dữ liệu mới và cũ, kiểm soát tác động tới DEK/KEK, chữ ký số, consumer và backup. Tuy nhiên **lineage không thay thế key usage policy, KMS/HSM, xác thực nguồn public key, phân quyền, kiểm toán hay kiểm kê dependency thực tế**. Chỉ khi phối hợp các yếu tố này mới có thể xoay vòng, thu hồi và hủy khóa **mà không làm mất dữ liệu hoặc tiếp tục tin khóa không an toàn**.

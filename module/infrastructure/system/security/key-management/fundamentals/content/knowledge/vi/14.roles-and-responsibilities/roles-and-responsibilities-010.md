# Dual control — Kiểm soát hai người trong quản lý khóa mật mã

## 1. Dual control là gì?

**Dual control** (*kiểm soát hai người*, đôi khi gọi *two-person control* hoặc *four-eyes principle*) là cơ chế quản trị yêu cầu **ít nhất hai chủ thể được ủy quyền, độc lập theo chính sách, cùng tham gia hoặc chấp thuận một hành động nhạy cảm** trước khi hành động đó được thực hiện.

Trong quản lý khóa mật mã, dual control có thể được áp dụng khi **khởi tạo HSM**, tạo hoặc thay khóa gốc, thay chính sách quản trị KMS, nhập/xuất vật liệu khóa, kích hoạt đường khôi phục, thu hồi khẩn cấp, xoay khóa quan trọng, thay đổi người giữ quyền và hủy khóa. Một người có thể khởi xướng yêu cầu nhưng **không được một mình hoàn tất** toàn bộ đường thực thi khi chính sách yêu cầu nhiều người.

Ví dụ, hệ thống Billing lưu dữ liệu bằng DEK được bọc bởi KEK trong KMS. Một quản trị viên muốn hủy `billing-kek-v3`. Nếu quyền hủy nằm trong tay một người, một thao tác sai có thể khiến hàng triệu bản ghi và các bản backup không giải mã được. Với dual control, hệ thống yêu cầu **một người đề xuất và một người phê duyệt độc lập** sau khi kiểm tra danh sách DEK còn phụ thuộc; chỉ khi điều kiện đạt, một workflow được ủy quyền mới được phép tiến hành hủy theo cơ chế của nhà cung cấp.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, dual control là thành phần của chương **Vai trò và trách nhiệm**: nó nối chính sách của **key owner**, thao tác của **key custodian**, quyền **key user**, kiểm tra của security/auditor với toàn bộ vòng đời từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy khóa**. Nó cũng áp dụng cho mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM và kiểm toán.

> **Nguyên tắc:** Dual control chỉ có ý nghĩa khi **một người không thể tự vượt qua cơ chế phê duyệt bằng đường kỹ thuật khác**. Hai chữ ký duyệt trong ticket không tạo ra an toàn nếu cùng một admin có thể tự cấp quyền, sửa workflow, xuất khóa hoặc xóa log.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **dual control**, **separation of duties**, **dual authorization**, **split knowledge** và **M-of-N/threshold**.
2. Xác định thao tác quản lý khóa nào thực sự cần hai người và thao tác nào cần tự động hóa theo policy.
3. Thiết kế phê duyệt ràng buộc **đúng key ID/version, operation, phạm vi, người thực thi và thời hạn**.
4. Hiểu cách cưỡng chế dual control qua **IAM/PAM, control plane, KMS/HSM và workflow có kiểm toán**.
5. Đánh giá rủi ro với **DEK/KEK, signing key, HMAC, ECDH, recovery key và key destruction**.
6. Thiết kế kiểm thử, giám sát và runbook khi quyền quản trị bị lạm dụng.

## 2. Dual control không đồng nghĩa “hai tài khoản”

Một sự kiện chỉ có hai account xuất hiện trong log **chưa chứng minh có hai người độc lập**. Các trường hợp sau **không đạt mục tiêu dual control**:

- Một nhân viên giữ cả hai tài khoản quản trị và tự đăng nhập hai lần để phê duyệt.
- Người tạo yêu cầu có quyền đổi `approvedBy` trong database hoặc thêm chính mình vào nhóm approver.
- Admin có thể thay IAM/key policy trước rồi gọi thẳng `Decrypt`, `Sign`, `Export` hay `ScheduleDeletion`.
- Hai approver được hiển thị khác nhau nhưng đều do một service account/automation không kiểm soát phát ra.
- Hệ thống yêu cầu hai người trong giao diện, nhưng **API trực tiếp** của provider không đi qua workflow.
- Phê duyệt có thể được tái sử dụng cho key khác, hành động khác hoặc phiên bản policy đã thay đổi.

**Độc lập** ở đây không nhất thiết nghĩa hai bộ phận hoàn toàn tách biệt trong mọi trường hợp; nó có nghĩa **không một chủ thể có thể một mình thỏa mãn các điều kiện cần để hoàn thành thao tác** trong mô hình quyền được chọn.

### Phân biệt người tham gia và nguồn danh tính

Hai approver cần được **xác thực** bằng danh tính cá nhân có thể quy trách nhiệm, lý tưởng qua MFA hoặc xác thực mạnh phù hợp rủi ro. Nếu hệ thống cho phép ủy quyền thay mặt, việc ủy quyền phải được ghi nhận và **không biến thành một cá nhân phê duyệt hai lần**.

Quyền sửa nhóm phê duyệt, cấu hình IdP, mã nguồn workflow và key policy cũng là **đường leo thang gián tiếp** cần kiểm soát.

## 3. So sánh Dual control, separation of duties và split knowledge

Những thuật ngữ này thường xuất hiện cùng nhau nhưng **giải quyết các rủi ro khác nhau**.

| Khái niệm | Cơ chế | Bảo vệ chính | Không tự bảo đảm |
| --- | --- | --- | --- |
| **Dual control** | Cần ít nhất hai người có thẩm quyền tham gia hoặc phê duyệt hành động | Ngăn một người tự hoàn thành thao tác nhạy cảm | Không nhất thiết chia bí mật, không tự kiểm soát mọi API |
| **Separation of duties (SoD)** | Phân tách vai trò đề xuất, phê duyệt, thực thi, sử dụng và audit | Ngăn xung đột lợi ích/tự kiểm soát toàn bộ quy trình | Không đồng nghĩa mọi thao tác đều cần hai người đồng thời |
| **Dual authorization** | Hai quyết định cho phép riêng biệt được workflow xác minh | Kiểm soát quyền trước thao tác | Không đủ nếu executor có quyền bypass |
| **Split knowledge** | Bí mật được chia/đại diện để không ai nắm toàn bộ | Giảm rủi ro một người biết đủ secret | Không mặc nhiên chứng minh có hai phê duyệt hợp lệ |
| **M-of-N / threshold** | Cần ít nhất M trong N share/participant theo cơ chế được thiết kế | Bảo đảm điều kiện ngưỡng cho khôi phục/tác vụ mật mã | Không tự kiểm tra purpose, business approval, audit |
| **Two-person integrity** | Hai người giám sát hoặc xác nhận thao tác nhạy cảm | Phát hiện thao tác không phù hợp, tăng trách nhiệm | Không tự ngăn bypass nếu không có enforcement |
| **Key ceremony** | Kịch bản vận hành khóa có vai trò, kiểm soát và bằng chứng | Quy trình có thể kiểm tra khi thao tác đặc biệt | Không nhất thiết dùng threshold hay split knowledge |

### 3.1. Dual control khác split knowledge

**Dual control** có thể chỉ yêu cầu hai người chấp thuận một thao tác trong HSM; private key có thể **không bao giờ được xuất** dưới dạng rõ. **Split knowledge** tập trung vào việc **không người nào biết đủ vật liệu bí mật**.

Một hệ thống có thể triển khai cả hai, chỉ một, hoặc không cái nào tùy mức rủi ro. Đừng dùng các thuật ngữ thay thế nhau trong chính sách.

### 3.2. Dual control khác M-of-N

**M-of-N** là cơ chế ngưỡng: ví dụ cần tối thiểu 3 trong 5 người/thiết bị/share để kích hoạt một thủ tục khôi phục. **Dual control** ở nhiều tổ chức được quy định tối thiểu hai người, nhưng thiết kế thật có thể yêu cầu nhiều hơn hoặc hai vai trò bắt buộc khác nhau.

Đặc biệt, **không tự tạo split knowledge bằng cách cắt một chuỗi AES key thành hai đoạn text** và coi đó là một sơ đồ chia sẻ bí mật đã an toàn. Dùng cơ chế key sharing/threshold đã được đánh giá, đúng ràng buộc an toàn và sản phẩm hỗ trợ.

### 3.3. Dual control khác peer review thông thường

Một pull request cần hai review có thể giảm rủi ro cấu hình, nhưng **không đủ** nếu admin có quyền sửa trực tiếp policy production ngoài pipeline. Cần kiểm soát **cả đường duyệt lẫn đường thực thi**.

## 4. Khi nào nên yêu cầu dual control?

Không nên bắt buộc hai người duyệt **mỗi lần AES-GCM Encrypt** hoặc mỗi handshake TLS: việc đó không khả thi, ảnh hưởng availability và không giải quyết đúng rủi ro. Thay vào đó, dual control phù hợp với những **thao tác quản trị có phạm vi ảnh hưởng lớn hoặc khó đảo ngược**.

| Hành động | Có thể cần dual control? | Tại sao |
| --- | --- | --- |
| Tạo hoặc kích hoạt root/master key quan trọng trong HSM | **Thường có trong môi trường rủi ro cao** | Thiết lập vùng tin cậy và quyền lâu dài |
| Import/export key material nhạy cảm nếu được phép | **Nên đánh giá nghiêm ngặt** | Khóa có thể rời vùng bảo vệ |
| Thay key policy/grant cấp quyền `Decrypt` rộng | **Có thể cần** | Admin có thể tự nâng quyền |
| Khôi phục KEK/DEK từ backup hoặc recovery mechanism | **Thường có nếu rủi ro cao** | Mở đường tới dữ liệu nhạy cảm |
| Thay khóa ký CA/TSA/firmware/release quan trọng | **Thường cần kiểm soát chặt** | Ảnh hưởng niềm tin của nhiều bên |
| Hủy KEK có dữ liệu lịch sử phụ thuộc | **Rất nên yêu cầu** | Có thể gây mất dữ liệu không thể phục hồi |
| Đổi alias routing của signing key production | **Tùy rủi ro** | Có thể phát hành bằng sai khóa |
| Tạo DEK ngẫu nhiên cho một record qua API đã cấp phép | **Không thường cần hai người mỗi lần** | Nên dùng chính sách tự động, IAM và audit |
| Verify chữ ký bằng public key | **Thường không** | Không sử dụng private key |
| ECDHE ephemeral key cho mỗi TLS handshake | **Không** | Do giao thức xử lý với policy đã duyệt |
| Giám sát log và inventory read-only | **Không thường** | Quyền đọc hạn chế có thể đủ |
| Thao tác suspend khẩn cấp | **Có thể cho phép một người cô lập nhanh theo runbook** | Tốc độ phản ứng có thể quan trọng hơn chờ phê duyệt |

**Không có bảng “bắt buộc” phổ quát cho tất cả KMS/HSM.** Cần dựa vào phân loại dữ liệu, mô hình đe dọa, yêu cầu kiểm soát nội bộ, tiêu chuẩn áp dụng và khả năng nền tảng.

### Quy tắc chọn mức kiểm soát

- **Tác động cao, khó đảo ngược:** hai người hoặc ngưỡng mạnh hơn.
- **Quyền có thể dẫn đến xuất/lộ secret:** đánh giá cả đường **tự sửa policy**.
- **Tác vụ thường xuyên, đã được giới hạn:** cấp quyền workload và tự động hóa an toàn; dual control ở **cấp phê duyệt workflow/chính sách**, không ở từng API request.
- **Sự cố đang diễn ra:** cho phép **cô lập nhanh** dưới quyền ứng cứu đã chuẩn bị, nhưng phục hồi quyền hoặc tiêu hủy vĩnh viễn cần kiểm soát riêng.

## 5. Phân vai: Owner, custodian, executor, approver và auditor

Dual control chỉ hoạt động khi biết rõ **ai ra quyết định** và **ai được thi hành**.

| Vai trò | Chịu trách nhiệm | Không nên mặc nhiên có |
| --- | --- | --- |
| **Key owner** | Phê duyệt purpose, mức rủi ro, cryptoperiod, việc thay/hủy/khôi phục | Quyền tự giải mã hoặc xuất raw key |
| **Key custodian** | Sinh, bảo quản, cấu hình HSM/KMS, IAM, backup và thực thi theo phê duyệt | Quyền tự duyệt hành động mình thực thi hoặc ký dữ liệu nghiệp vụ |
| **Security approver/reviewer** | Đánh giá độc lập, phê duyệt ngoại lệ và thao tác nhạy cảm | Quyền sửa audit hoặc sử dụng private key |
| **Key user / workload** | Gọi `Encrypt`, `Sign`, `DeriveKey`, `Unwrap` theo phạm vi đã cấp | Quyền tự đổi policy hay hủy key |
| **Control-plane executor** | Thực thi đúng một yêu cầu đã được xác minh đủ phê duyệt | Quyền thay payload, bỏ qua kiểm tra hay tự mint approval |
| **Auditor** | Đối chiếu phê duyệt, thao tác và kết quả thực tế | Quyền tự sửa log/secret |
| **Incident responder** | Cô lập nhanh theo quyền khẩn cấp và ghi bằng chứng | Quyền mở lại key compromised ngoài review |

### Một RACI minh họa

| Tác vụ | Key owner | Custodian | Security | Application owner | Auditor |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa purpose và risk tier | **A** | C | C | R/C | I |
| Thiết kế dual-control rule | **A** | R | **R/C** | C | I |
| Tạo tài nguyên KEK/HSM | A theo policy | **R** | C | I | I |
| Đề xuất hủy khóa | **A** | R | C | C xác nhận phụ thuộc | I |
| Phê duyệt hủy khóa độc lập | A | Không tự phê duyệt thao tác mình thực hiện | **R/C** | C | I |
| Thực thi hủy khi đủ điều kiện | I | **R** qua workflow | C | I | I |
| Kiểm tra bằng chứng | I | C | C | C | **R** |

Các chữ **R/A/C/I** là ký hiệu RACI mang tính gợi ý; không phải cấu hình IAM. Chính sách thực tế phải tránh **một người vừa có A, vừa có R và vừa có thể sửa bằng chứng** với thao tác rủi ro cao.

## 6. Mô hình thực thi dual control end-to-end

Một thiết kế phổ biến có **người đề xuất**, **hai approver đáp ứng chính sách**, và **executor** được giới hạn chỉ thi hành yêu cầu đã phê duyệt. Trong vài mô hình, người đề xuất hoặc executor có thể được tính là một trong hai người nếu chính sách cho phép; điều quan trọng là **ít nhất hai chủ thể độc lập** và không ai có thể tự hoàn tất thao tác.

~~~mermaid
sequenceDiagram
    participant Requester as Người đề xuất
    participant CP as Control plane
    participant Owner as Key owner
    participant Security as Security approver
    participant Executor as Workflow executor
    participant KMS as KMS/HSM
    participant Audit as Audit
    Requester->>CP: Tạo yêu cầu keyId, version, operation, scope
    CP->>CP: Kiểm tra policy, khóa payload/revision
    CP->>Owner: Đề nghị phê duyệt yêu cầu
    CP->>Security: Đề nghị phê duyệt độc lập
    Owner-->>CP: Approval gắn với request digest và thời hạn
    Security-->>CP: Approval gắn với cùng request digest và thời hạn
    CP->>CP: Kiểm tra hai identity khác nhau, đúng role, còn hiệu lực
    CP->>Executor: Lệnh có thể thực thi, idempotency key
    Executor->>KMS: Gọi đúng operation/resource đã duyệt
    KMS-->>Executor: Kết quả provider
    Executor->>Audit: Ghi decision, thao tác, kết quả, policy revision
    Executor-->>CP: Trạng thái hoàn thành/không thành công
~~~

Sơ đồ chỉ là **kiến trúc khái niệm**. Không phải nhà cung cấp KMS nào cũng có API bản địa nhận **hai approval token**. Nếu KMS chỉ biết một IAM principal, cần thiết kế control plane, IAM/PAM, giới hạn credential và mạng sao cho **không có đường bypass trực tiếp**.

### Sáu lớp bảo vệ cần có

1. **Danh tính:** Hai approver là hai người có thể quy trách nhiệm, với quyền và xác thực đúng mức.
2. **Yêu cầu bất biến:** Approval gắn với **một nội dung hành động cụ thể**, không phải một câu “đồng ý chung”.
3. **Phê duyệt độc lập:** Không trùng người, không tự duyệt khi bị cấm, đúng vai trò và không dùng credential chung.
4. **Cưỡng chế:** Hệ thống **không thực thi** trước khi đủ approval; backend/provider không có đường đi tắt.
5. **Đồng bộ trạng thái:** Kiểm tra key/version/policy và điều kiện mới nhất ngay trước thao tác, chống race.
6. **Audit và đối chiếu:** Ghi cả **quyết định duyệt**, **thao tác provider thật** và **kết quả**.

## 7. Approval phải ràng buộc đúng yêu cầu

Một approval kiểu “Tôi đồng ý cho team KMS làm việc” **không đủ cụ thể** cho các thao tác có thể dẫn đến mất dữ liệu hoặc lộ bí mật.

### Metadata nên ràng buộc

| Trường | Ý nghĩa | Rủi ro nếu thiếu |
| --- | --- | --- |
| `requestId` | Định danh duy nhất yêu cầu | Không chống dùng lại approval |
| `action` | `ROTATE`, `UNWRAP_FOR_RECOVERY`, `DISABLE`, `DESTROY`… | Duyệt một việc nhưng làm việc khác |
| `keyId` và `keyVersion` | Resource/vật liệu cụ thể | Lệnh sang nhầm khóa |
| `purpose` | Mục đích đã phê duyệt | Dùng key sai chức năng |
| `environment`, `tenant`, `dataScope` | Phạm vi sử dụng hoặc dữ liệu | Mở quyền vượt tenant |
| `parameters` | Chi tiết operation, cửa sổ, key policy hay recipient | Đổi payload sau khi duyệt |
| `policyRevision` | Phiên bản chính sách được đánh giá | Dùng approval dưới điều kiện đã thay đổi |
| `expectedKeyState/revision` | Trạng thái phải vẫn còn đúng | Race với suspend/rotate khác |
| `requestedBy` và `executedBy` | Vai trò đề xuất/thực thi | Không xác minh SoD |
| `approvedBy` và `approverRole` | Hai chủ thể và quyền của họ | “Hai approval” do cùng một người tạo |
| `expiresAt` và `consumedAt` | Hiệu lực và sử dụng một lần | Replay hoặc tái sử dụng lâu dài |

### Tính toàn vẹn nội dung

Nên có một **cách mã hóa chính tắc (canonical encoding)** cho các trường request, sau đó tạo **request digest** hoặc định danh có thể kiểm tra. Approval phải gắn với **đúng digest, đúng policy revision và đúng request ID**.

Một hash không tự chứng minh ai phê duyệt. Cần **nguồn approval đáng tin**, phiên xác thực mạnh, cơ chế chống sửa record và quyền ghi được giới hạn; ở một số kiến trúc có thể sử dụng chữ ký số trên yêu cầu hoặc quyết định phê duyệt.

### Chống TOCTOU

**Time-of-check/time-of-use (TOCTOU)** xảy ra khi điều kiện đúng lúc phê duyệt nhưng thay đổi trước lúc thi hành.

Ví dụ: Owner phê duyệt hủy `kek-v1` sau khi hệ thống báo không còn wrapped DEK nào phụ thuộc. Trước khi job hủy chạy, một worker cũ lại tạo wrapped DEK dưới `kek-v1`. Nếu chỉ dùng approval cũ, việc hủy có thể làm mất dữ liệu.

Cần **chặn các writer cũ**, xác nhận **trạng thái/phụ thuộc mới nhất** và áp dụng cơ chế revision/compare-and-swap hoặc quy trình có khóa nhất quán trước khi thực thi. Dual control **không thay thế kiểm tra dữ liệu phụ thuộc**.

## 8. Cưỡng chế dual control trong KMS/HSM

### 8.1. KMS không tự hiểu mọi quy trình phê duyệt

Các dịch vụ cloud KMS có thể hỗ trợ **IAM policy, grant, key state, audit, managed rotation và một số điều kiện truy cập**. Nhưng chúng **không nhất thiết có tính năng bản địa “hai người phê duyệt mọi Decrypt hoặc DeleteKey”**.

Mô hình có thể gồm:

- **PAM/JIT access**: quyền quản trị nhạy cảm chỉ được cấp cho executor theo yêu cầu và thời hạn đã phê duyệt.
- **Workflow control plane**: chỉ một workload đặc biệt có quyền thực thi API rủi ro cao; workload xác minh hai approval trước khi gọi KMS.
- **IAM deny/guardrails**: cấm người thường trực tự cấp quyền `Decrypt`, `Sign`, `Export` hoặc thay policy ngoài đường được chấp thuận.
- **Event/audit reconciliation**: đối soát lời gọi KMS thực tế với request ID và quyết định phê duyệt.
- **Phân cấp tài khoản/boundary**: hạn chế quyền root/break-glass và dùng bảo vệ tổ chức phù hợp sản phẩm.

**Nếu admin có thể sửa ngay IAM để tự cấp quyền executor**, phê duyệt trên giao diện trở thành kiểm soát mang tính hình thức. Cần kiểm tra quyền gián tiếp như `PutKeyPolicy`, quản lý grant, sửa role trust, thay code workflow và quyền tạo access token.

### 8.2. HSM và key ceremony

Một số HSM hoặc module bảo mật hỗ trợ **role riêng, quorum, multi-person authentication, M-of-N activation hoặc split knowledge**. Khả năng có sẵn, thuật toán, cách lưu key share và ý nghĩa “hai người” là **đặc thù sản phẩm**.

Key custodian cần kiểm tra tài liệu của HSM và **không giả định rằng `CKA_SIGN`/`CKA_DECRYPT` trong PKCS#11 tự tạo dual control**. Các thuộc tính key usage giới hạn loại phép toán, còn yêu cầu nhiều người thường thuộc cơ chế quản trị hoặc workflow riêng.

### 8.3. Chặn ở đúng điểm thực thi

~~~mermaid
flowchart TD
    R[Yêu cầu tác vụ nhạy cảm trên key] --> I[Identity + policy kiểm tra]
    I --> P[Khóa request payload và revision]
    P --> A[Approval độc lập #1]
    P --> B[Approval độc lập #2]
    A --> Q{Đúng role, identity khác nhau, còn hạn?}
    B --> Q
    Q -->|Không| Deny[Từ chối và ghi audit]
    Q -->|Có| Recheck[Kiểm tra state, policy, dependency lần cuối]
    Recheck -->|Sai hoặc thay đổi| Deny
    Recheck -->|Đạt| E[Executor được giới hạn quyền gọi KMS/HSM]
    E --> K[KMS/HSM kiểm tra IAM và key state]
    K --> Audit[Provider event + đối soát approval]
    Deny --> Audit
~~~

**Không chỉ kiểm tra ở giao diện.** Người dùng có thể gọi thẳng API, sửa request qua automation hoặc dùng credential khác. Enforcement cần nằm tại **control plane và boundary quyền thực tế**, với mọi đường thay đổi quyền đều được quản lý.

## 9. Dual control và key lifecycle

Mỗi trạng thái của khóa có kiểu rủi ro khác nhau, nên **không áp một quy trình giống hệt** cho mọi chuyển trạng thái.

| Giai đoạn/trạng thái | Hành động nhạy cảm | Kiểm soát gợi ý |
| --- | --- | --- |
| **Pre-activation** | Kích hoạt key root/CA/recovery hoặc cấp key usage rộng | Owner approval + kiểm tra an ninh độc lập |
| **Active** | Thay IAM/grant hoặc mở quyền `Sign/Decrypt/Unwrap` | SoD và dual control theo risk tier |
| **Rotation** | Tạo v2, cutover alias/key version, retire v1 | Người phê duyệt khác người thực thi, preflight và audit |
| **Suspended** | Tạm khóa khi phát hiện bất thường | Có thể cho responder cô lập nhanh theo runbook |
| **Resume** | Khôi phục quyền sau điều tra | Review độc lập, bằng chứng key material còn đáng tin |
| **Deactivated** | Cho phép legacy decrypt/verify | Quyền hẹp, thời hạn và lý do được phê duyệt |
| **Compromised** | Thay key, thu hồi trust, xử lý dữ liệu cũ | Incident workflow; không chỉ mở lại key cũ |
| **Destroyed** | Hủy vật liệu khóa, có thể không đảo ngược | Dual approval, dependency check, retention và audit |

### Suspended không đồng nghĩa compromised

Một khóa có thể bị đình chỉ **phòng ngừa** khi còn đang điều tra. Nếu raw private key hoặc DEK đã bị sao chép, việc hai người cùng phê duyệt `Enable` **không giúp khóa an toàn trở lại**. Cần thay vật liệu, xử lý dữ liệu/chữ ký lịch sử và thu hồi trust theo chính sách.

### Destroy cần nhiều hơn hai chữ ký

Một key chỉ được hủy khi **không còn phụ thuộc dữ liệu và bản backup theo retention**. Hai approver không thể biến việc hủy một KEK còn bọc hàng nghìn DEK thành hành động an toàn. Cần **kết quả kiểm tra kỹ thuật** cùng quyết định nghiệp vụ.

## 10. Dual control cho DEK/KEK và envelope encryption

Trong **envelope encryption**, **DEK** mã hóa dữ liệu bằng cơ chế đối xứng như AES-GCM; **KEK** bọc/giải bọc DEK bằng KMS/HSM. Hai loại khóa này có **blast radius** khác nhau.

~~~mermaid
flowchart LR
    P[Dữ liệu hóa đơn] --> Enc[AES-GCM với DEK]
    D[DEK sinh bằng CSPRNG] --> Enc
    Enc --> DB[(Ciphertext + nonce + tag + key version)]
    D --> W[Wrap DEK]
    K[KEK trong KMS/HSM] --> W
    W --> DB
    Req[Yêu cầu restore/rotate/destroy KEK] --> Ctrl[Dual-control workflow]
    Ctrl -->|Đủ phê duyệt + checks| K
    Ctrl -->|Thiếu điều kiện| Deny[Từ chối]
~~~

### 10.1. Đối với DEK

Không nên bắt hai người phê duyệt **mỗi lần sinh DEK cho một bản ghi** nếu workload đã được cấp chính sách đúng. Nhưng có thể yêu cầu dual control khi:

- Xuất hoặc phục hồi **raw DEK** từ một vùng bảo vệ đặc biệt.
- Thay chính sách cho phép giải mã hàng loạt dữ liệu nhạy cảm.
- Hủy tập DEK đã bảo vệ một lượng lớn dữ liệu hoặc backup.
- Di chuyển DEK khỏi boundary đang áp dụng, nếu được phép.

DEK được dùng trong RAM/cache có thể tiếp tục hoạt động khi KEK bị disable. Dual control cho thao tác KMS **không tự vô hiệu hóa plaintext DEK đã được cấp**; cần quản lý cache, session, IAM workload và khả năng cô lập.

### 10.2. Đối với KEK

KEK có thể bọc nhiều DEK, vì vậy sửa quyền `Unwrap`, thay key policy hoặc hủy KEK có thể ảnh hưởng rất rộng. Nên có **dependency inventory**: DEK nào bị bọc bằng KEK/version nào, backup nào còn cần key cũ, dịch vụ nào được phép unwrap.

**Rewrap**: chuyển bản bọc của DEK từ KEK v1 sang v2, DEK và ciphertext có thể không đổi.

**Re-encrypt**: thay DEK mã hóa dữ liệu và tạo ciphertext/nonce/tag mới theo giao thức.

Nếu **DEK plaintext đã bị lộ**, chỉ rewrap dưới KEK v2 không khôi phục tính bí mật; cần đánh giá re-encrypt và tác động lịch sử.

### 10.3. Ví dụ dual control cho recovery

Một recovery operator cần giải bọc DEK từ backup để khôi phục hồ sơ khách hàng. Workflow có thể yêu cầu:

1. **Data owner** xác nhận dữ liệu cần khôi phục, lý do, người nhận và phạm vi.
2. **Security approver** xác nhận yêu cầu hợp lệ và giới hạn thời gian.
3. **Custodian/executor** dùng quyền phục hồi tạm thời để `Unwrap` đúng key và dữ liệu.
4. **Audit** ghi key ID, mục đích, identity, request digest và kết quả; không lưu raw DEK.

Nếu nền tảng chỉ cung cấp lệnh `Decrypt` chung, lớp kiểm soát trên **cần ngăn cấp quyền không giới hạn** và bảo vệ nơi plaintext được nhận.

## 11. Dual control trong chữ ký số, PKI và phát hành phần mềm

### 11.1. Signing key không xuất được vẫn có thể bị lạm dụng

Một private signing key trong HSM có thể **non-exportable**. Tuy nhiên ai có quyền `Sign` có thể ký dữ liệu sai mục đích nếu không kiểm soát **nội dung đầu vào và quy trình nghiệp vụ**. Đây là rủi ro *signing oracle*.

Với **CA root key, firmware signing key, release signing key** hoặc khóa ký giao dịch rủi ro cao, dual control có thể nằm ở:

- Kích hoạt hoặc mở quyền `Sign` cho phiên vận hành.
- Phê duyệt release manifest hoặc digest cần ký.
- Thay đổi key policy, HSM role hoặc chứng thư.
- Rotate signing key, thu hồi key cũ và cập nhật trust.
- Thực thi các nghi thức key ceremony nhạy cảm.

**Hai approver phải cùng duyệt đúng artifact/digest hoặc tập lệnh**, không chỉ duyệt “cho phép ký trong hôm nay” rồi executor có thể ký bất kỳ payload nào.

### 11.2. Phân biệt approval với chữ ký số

Một chữ ký số trên quyết định phê duyệt có thể cung cấp **xác thực và tính toàn vẹn** của quyết định, nhưng **không tự chứng minh người ký có thẩm quyền** hoặc độc lập với người đề xuất. Cần kiểm tra **identity, role, key usage, thời hạn, trust và policy** của người phê duyệt.

Ngược lại, dual control có thể được triển khai qua **workflows có xác thực mạnh và log bất biến** mà không nhất thiết mỗi approval là một chữ ký số PKI riêng; lựa chọn phụ thuộc yêu cầu chứng cứ.

### 11.3. Bảo vệ chữ ký lịch sử

Suspend/rotate private key **không tự xóa** các chữ ký đã phát hành. Public key/chứng thư, CRL/OCSP, timestamp hoặc cơ chế **long-term validation** có thể cần được duy trì theo chính sách. Nếu private key bị compromise, phải đánh giá chữ ký theo thời gian và bằng chứng, không kết luận chỉ từ phép `Verify` toán học.

### 11.4. JWT, JWKS và key IDs

Với JWT signing key, dual control có thể yêu cầu cho **thay khóa, sửa JWKS trust, cấp quyền ký token rủi ro cao**. Verifier vẫn cần kiểm tra `issuer`, `audience`, thuật toán và nguồn key tin cậy. Không cho phép kẻ tấn công dùng `kid` hoặc URL trong token để ép chọn một public key không được chấp nhận.

## 12. HMAC, ECDH và key use thường xuyên

### 12.1. HMAC key chia sẻ giữa các bên

HMAC dùng cùng secret cho tạo và xác minh MAC. Khi cấp một **HMAC key cho đối tác** hoặc thay key webhook, hai người có thể cần phê duyệt **đối tác, phạm vi, thời hạn, kênh phân phối**. Không có nghĩa mỗi webhook phải được hai người xác nhận trước khi tạo HMAC.

Khi secret HMAC lộ, kẻ tấn công có thể giả mạo tag trong phạm vi khóa; rotation phải điều phối cả sender và receiver. **Một lịch duyệt định kỳ không thay thế anti-replay và quản lý phiên bản HMAC.**

### 12.2. Static ECDH/X25519 key

Với static agreement key, dual control có thể yêu cầu khi **đăng ký public peer mới**, thay trust anchor, thay private agreement key hoặc mở quyền `DeriveKey` cho ứng dụng. **ECDH thuần túy không tự xác thực đối tác**; IAM và approval phải đi cùng giao thức có chứng thực public key/transcript.

### 12.3. Ephemeral ECDHE key

Trong TLS hoặc giao thức AKE chuẩn, ephemeral ECDH key thường được sinh theo từng phiên/handshake. **Không yêu cầu hai nhân viên thủ công phê duyệt mỗi lần thỏa thuận khóa**. Dual control nên áp dụng ở **thay cấu hình trust, provider, nhóm thuật toán, private authentication key và policy của hệ thống**, trong khi thao tác mỗi phiên do giao thức an toàn thực hiện.

### 12.4. Password-derived KEK và recovery

Nếu người dùng quên mật khẩu dùng dẫn xuất KEK, **reset mật khẩu đăng nhập không tự lấy lại KEK cũ**. Trường hợp tổ chức giữ recovery KEK để phục hồi DEK, dual control có thể là lớp bảo vệ cho thao tác **recovery `Unwrap`**, kết hợp MFA, hạn mức dữ liệu, audit và thông báo.

Nếu dịch vụ tuyên bố **end-to-end encryption / zero-knowledge**, cần công khai đúng mô hình: một recovery KEK do nhà vận hành có thể truy cập là **năng lực kỹ thuật phục hồi dữ liệu**, không thể vừa có quyền này vừa khẳng định không một ai phía server có thể giải mã trong mọi hoàn cảnh.

## 13. Key ceremony: hai người phải làm gì?

**Key ceremony** là quy trình tạo, kích hoạt, nhập, sao lưu, phục hồi hoặc hủy khóa có kịch bản, vai trò, kiểm soát và bằng chứng. Nó phù hợp với **root CA, HSM master key, TSA signing key, recovery root key** và các tài sản có mức rủi ro cao.

### Trước buổi ceremony

- **Owner** phê duyệt mục đích, loại khóa, thuật toán, cryptoperiod và kế hoạch.
- **Security reviewer** kiểm tra threat model, quy tắc dual control, điều kiện M-of-N/split knowledge nếu có và phản ứng khi lỗi.
- **Custodian** chuẩn bị HSM, phiên bản firmware/configuration, quyền operator và kết nối được phép.
- **Witness/Auditor** chuẩn bị cách ghi nhận bằng chứng, serial, thời điểm, role và kiểm thử.
- Quy định rõ ai có quyền **dừng**, **thử lại**, **hủy key tạo dở** hoặc báo incident.

### Trong buổi ceremony

~~~mermaid
sequenceDiagram
    participant Owner as Key owner
    participant Sec as Security approver
    participant Cust as Key custodian
    participant HSM as HSM
    participant Audit as Witness/Auditor
    Owner->>Cust: Lệnh ceremony với purpose và key spec
    Sec->>Cust: Phê duyệt độc lập đúng operation
    Cust->>HSM: Xác thực role và tạo/thiết lập key
    HSM-->>Cust: Key handle/public metadata + status
    Cust->>HSM: Thiết lập hạn chế usage/export và policy
    Cust->>Audit: Kết quả, key ID, provider evidence
    Audit-->>Owner: Biên bản và sai lệch nếu có
    Owner->>Cust: Phê duyệt activation ở bước riêng
~~~

Sơ đồ không thay thế cơ chế dual-control **bản địa của HSM nếu sản phẩm yêu cầu quorum tại thiết bị**. Nếu một thao tác có thể chạy ngoài ceremony chỉ bằng một admin, cần kiểm tra và chặn đường đó.

### Sau buổi ceremony

- Kiểm tra key ID/handle, thuật toán, trạng thái, key usage và hạn chế export.
- Đối chiếu log HSM với biên bản và approval.
- Lưu bằng chứng trong kho có giới hạn sửa/xóa và retention.
- Chỉ cho phép dùng production khi hoàn tất **pre-activation gates**.
- Không ghi raw secret hoặc key share ra ảnh chụp màn hình, ticket hoặc biên bản.

## 14. Ví dụ chính sách dual control theo cấp rủi ro

Một hệ thống lớn không nên dùng cùng một quy tắc cho mọi khóa. Có thể dùng **risk tier** với phạm vi và thời hạn được định nghĩa.

| Risk tier | Ví dụ khóa/hành động | Mẫu phê duyệt gợi ý |
| --- | --- | --- |
| **Standard** | Tạo DEK theo API cho workload được cấp phép | Policy tự động, IAM least privilege, audit |
| **Elevated** | Thay KEK cho dữ liệu production, mở grants lớn | Owner + approver độc lập, executor giới hạn |
| **Critical** | Root CA/TSA/release key, thay trust root | Hai vai trò bắt buộc, ceremony hoặc provider quorum khi cần |
| **Recovery** | Giải bọc khóa phục hồi nhạy cảm | Data owner + security, giới hạn dữ liệu/thời gian |
| **Destructive** | Hủy KEK/root key hoặc xóa backup chứa vật liệu khóa | Hai approval hoặc kiểm soát mạnh hơn, dependency check và grace period |
| **Emergency containment** | Khóa nhanh credential đang bị lạm dụng | Một responder được ủy quyền có thể chặn ngay, audit và review hậu kiểm |
| **Emergency re-enable** | Resume khóa đã suspend sau sự cố | Phê duyệt độc lập và bằng chứng key còn đáng tin |

Đây là **mẫu để thiết kế**, không phải tiêu chuẩn quy định số người cho từng nhóm. Có những thao tác cần hơn hai người hoặc yêu cầu người giữ share vật lý, tùy HSM/PKI/chính sách.

### Ngoại lệ không được thành đường bypass thường trực

Nếu tổ chức cho phép **break-glass** khi mất khả năng truy cập KMS/HSM, quy trình cần:

- Điều kiện kích hoạt và danh tính được ủy quyền trước.
- Quyền hẹp nhất có thể, **TTL ngắn**, audit độc lập và thông báo.
- Giới hạn dữ liệu/key ID/operation, không mặc định “superadmin toàn vùng”.
- Phê duyệt hậu kiểm và điều tra bất thường.
- Thu hồi credential và đánh giá mọi thao tác đã thực hiện.

Một lối break-glass luôn mở, không được giám sát, có thể **vô hiệu toàn bộ cơ chế dual control**.

## 15. Mẫu metadata cho yêu cầu có hai phê duyệt

Một bản ghi khái niệm có thể như sau:

~~~yaml
requestId: "key-change-2030-0042"
action: "ROTATE_KEK"
key:
  id: "billing-kek-v3"
  version: "v3"
  purpose: "DEK_KEY_WRAPPING"
  environment: "production"
  tenantScope: "billing"
expectedState: "ACTIVE"
expectedPolicyRevision: 27
requestedBy: "kms-operator-a"
reason: "scheduled-rotation"
approvedParameters:
  targetKeyId: "billing-kek-v4"
  newUseCutoverAtUtc: "2030-05-10T00:00:00Z"
  prohibitOldWrapAfterCutover: true
  preserveLegacyUnwrap: true
approvalRequirements:
  requiredDistinctPeople: 2
  requiredRoles:
    - "KEY_OWNER"
    - "SECURITY_APPROVER"
  prohibitRequesterSelfApproval: true
approvals:
  - identity: "billing-key-owner"
    role: "KEY_OWNER"
    requestDigestRef: "digest-of-canonical-request"
    approvedAtUtc: "2030-05-01T09:00:00Z"
    expiresAtUtc: "2030-05-08T09:00:00Z"
  - identity: "security-reviewer-b"
    role: "SECURITY_APPROVER"
    requestDigestRef: "digest-of-canonical-request"
    approvedAtUtc: "2030-05-01T10:00:00Z"
    expiresAtUtc: "2030-05-08T10:00:00Z"
execution:
  executorIdentity: "kms-workflow-executor"
  idempotencyKey: "rotate-billing-kek-v3-to-v4"
  status: "PENDING"
  dependentKeyMigrationPlanRef: "rewrap-plan-id"
  auditCorrelationId: "audit-request-id"
~~~

**Đây chỉ là metadata minh họa**: các trường approval không tự có giá trị tin cậy khi nằm trong một YAML bất kỳ. Trong hệ thống thật, approval phải phát ra từ nguồn định danh/quyết định được bảo vệ, ràng buộc request bất biến và được executor xác minh.

### Tại sao cần kiểm tra phiên bản chính sách?

Nếu yêu cầu tạo dưới `policyRevision=27` nhưng policy đã được cập nhật sang revision 29 để cấm một hành động, executor **không nên tự suy luận approval cũ vẫn dùng được**. Quy tắc có thể yêu cầu **phê duyệt lại** hoặc một chiến lược chuyển đổi được thiết kế trước.

### Chống replay và sử dụng một lần

Approval không nên là “vé vĩnh viễn”. Khi request được dùng, workflow phải đánh dấu **consumed** hoặc hoàn tất với idempotency, đồng thời từ chối thay payload. Retry do lỗi mạng chỉ được thực thi **cùng một yêu cầu đã được khóa nội dung**, không thể đổi `keyId` mà giữ approval cũ.

## 16. Java 11+: minh họa policy gate yêu cầu hai phê duyệt độc lập

Đoạn mã sau chỉ mô phỏng **kiểm tra metadata của yêu cầu rotation nhạy cảm**. Nó **không sinh khóa, không đổi IAM, không gọi KMS/HSM, không thực hiện rotation và không tạo/chứng thực approval**. Mục tiêu là thể hiện các điều kiện: đúng action và key, **hai người độc lập ở hai vai trò**, không tự phê duyệt, còn thời hạn và đúng request fingerprint/policy revision.

Để ngắn gọn, `requestFingerprint` được minh họa như **giá trị bất biến đã được workflow tạo**. Trong production, cần canonical serialization, digest có kiểm tra toàn vẹn hoặc định danh tương đương và **nguồn approval đáng tin**; không nhận fingerprint tùy ý từ client.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.HashSet;

public final class DualControlPolicyDemo {

    enum Role {
        KEY_OWNER, SECURITY_APPROVER, KEY_CUSTODIAN
    }

    enum Action {
        ROTATE_KEK, UNWRAP_FOR_RECOVERY, DESTROY_KEY
    }

    static final class Request {
        final String requestId;
        final Action action;
        final String keyId;
        final long policyRevision;
        final String requestedBy;
        final String requestFingerprint;
        final Instant expiresAt;

        Request(String requestId, Action action, String keyId,
                long policyRevision, String requestedBy,
                String requestFingerprint, Instant expiresAt) {
            this.requestId = Objects.requireNonNull(requestId);
            this.action = Objects.requireNonNull(action);
            this.keyId = Objects.requireNonNull(keyId);
            this.policyRevision = policyRevision;
            this.requestedBy = Objects.requireNonNull(requestedBy);
            this.requestFingerprint = Objects.requireNonNull(requestFingerprint);
            this.expiresAt = Objects.requireNonNull(expiresAt);
        }
    }

    static final class Approval {
        final String approverId;
        final Role role;
        final String requestFingerprint;
        final Instant expiresAt;

        Approval(String approverId, Role role,
                 String requestFingerprint, Instant expiresAt) {
            this.approverId = Objects.requireNonNull(approverId);
            this.role = Objects.requireNonNull(role);
            this.requestFingerprint = Objects.requireNonNull(requestFingerprint);
            this.expiresAt = Objects.requireNonNull(expiresAt);
        }
    }

    static void requireTwoIndependentApprovals(
            Request request, List<Approval> approvals,
            String executorId, long currentPolicyRevision, Clock clock) {

        Objects.requireNonNull(request);
        Objects.requireNonNull(approvals);
        Objects.requireNonNull(executorId);
        Objects.requireNonNull(clock);
        Instant now = clock.instant();

        if (request.policyRevision != currentPolicyRevision
                || request.policyRevision < 0
                || !now.isBefore(request.expiresAt)) {
            throw new SecurityException("Stale request or policy");
        }
        if (request.action != Action.ROTATE_KEK) {
            throw new SecurityException("Wrong action for workflow");
        }
        if (approvals.size() != 2) {
            throw new SecurityException("Exactly two approvals required here");
        }

        Set<String> distinctPeople = new HashSet<>();
        Set<Role> distinctRoles = new HashSet<>();

        for (Approval approval : approvals) {
            if (approval == null
                    || !now.isBefore(approval.expiresAt)
                    || !request.requestFingerprint.equals(
                            approval.requestFingerprint)
                    || approval.approverId.equals(request.requestedBy)
                    || approval.approverId.equals(executorId)
                    || !distinctPeople.add(approval.approverId)
                    || !distinctRoles.add(approval.role)) {
                throw new SecurityException("Invalid/duplicate approval");
            }
        }

        if (!distinctRoles.contains(Role.KEY_OWNER)
                || !distinctRoles.contains(Role.SECURITY_APPROVER)) {
            throw new SecurityException("Required roles missing");
        }

        // Production: control plane phải kiểm tra nguồn approval,
        // identity/MFA, quyền thực tế của approver, key ID/version,
        // fingerprint của payload BẤT BIẾN, revision và idempotency.
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2030-05-02T12:00:00Z"), ZoneOffset.UTC);
        Instant validUntil = Instant.parse("2030-05-03T00:00:00Z");

        Request request = new Request(
                "rotate-0042", Action.ROTATE_KEK, "billing-kek-v3",
                27L, "kms-operator-a", "trusted-fingerprint-0042",
                validUntil);

        Approval owner = new Approval(
                "billing-key-owner", Role.KEY_OWNER,
                "trusted-fingerprint-0042", validUntil);
        Approval security = new Approval(
                "security-reviewer-b", Role.SECURITY_APPROVER,
                "trusted-fingerprint-0042", validUntil);

        requireTwoIndependentApprovals(
                request, List.of(owner, security),
                "kms-workflow-executor", 27L, clock);
        System.out.println("Two independent approvals: accepted");

        try {
            requireTwoIndependentApprovals(
                    request, List.of(owner, owner),
                    "kms-workflow-executor", 27L, clock);
            throw new AssertionError("Duplicate must fail");
        } catch (SecurityException expected) {
            System.out.println("Duplicate approver: denied");
        }

        try {
            requireTwoIndependentApprovals(
                    request, List.of(owner, security),
                    "kms-workflow-executor", 28L, clock);
            throw new AssertionError("Stale policy must fail");
        } catch (SecurityException expected) {
            System.out.println("Changed policy revision: denied");
        }

        Approval wrongScope = new Approval(
                "security-reviewer-b", Role.SECURITY_APPROVER,
                "fingerprint-for-another-key", validUntil);
        try {
            requireTwoIndependentApprovals(
                    request, List.of(owner, wrongScope),
                    "kms-workflow-executor", 27L, clock);
            throw new AssertionError("Wrong payload must fail");
        } catch (SecurityException expected) {
            System.out.println("Approval for another request: denied");
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Two independent approvals: accepted
Duplicate approver: denied
Changed policy revision: denied
Approval for another request: denied
~~~

### Điều ví dụ thể hiện

- Phê duyệt phải đến từ **hai danh tính khác nhau** và đủ **hai role bắt buộc**.
- Một approval không được tạo bởi người đề xuất hoặc executor khi chính sách yêu cầu độc lập.
- Approval hết hạn hoặc dùng ở policy revision khác phải bị từ chối.
- Dấu vân tay request phải trùng, không dùng approval của key/action khác.

### Giới hạn của đoạn mã

1. Các `Approval` là **object giả lập**, chưa được xác thực bằng IdP, chữ ký số, session hay workflow tin cậy. Client có thể tự tạo hai object và vượt qua ví dụ nếu đem dùng nguyên mẫu trong production.
2. `requestFingerprint` chỉ là chuỗi minh họa, **không phải hash được tính từ canonical request**. Phải ràng buộc đầy đủ `keyId`, **key version**, action, parameters, scope, policy revision và requester.
3. Ví dụ không kiểm tra role của `executorId` với IAM hay việc một người điều khiển nhiều identity.
4. Không có **atomic consume/idempotency** và kiểm soát race giữa approvals, trạng thái khóa và lệnh KMS.
5. Không kiểm tra **dependency của dữ liệu**, cryptoperiod, trạng thái HSM hoặc khả năng rollback.
6. Không có policy đối với **hành động khác** `ROTATE_KEK` hoặc quy tắc quorum 3-of-5.
7. Không gọi KMS/HSM để **cưỡng chế**. Một người có quyền gọi API provider trực tiếp vẫn có thể bypass nếu IAM không được thiết kế đúng.

**Vì vậy đây là ví dụ cho tư duy kiểm soát quyền, không phải hệ thống phê duyệt production hoàn chỉnh.**

## 17. Case study: Dual control khi hủy KEK production

### Bối cảnh

Dịch vụ Billing đã xoay KEK từ `kek-v3` sang `kek-v4`. Key custodian yêu cầu **hủy v3** để giảm vật liệu không còn dùng. Trong database có bản ghi DEK được bọc bằng hai phiên bản; backup lưu trữ ngoài vùng chính có thể vẫn phụ thuộc v3.

### Quy trình mong muốn

1. **Custodian tạo yêu cầu** `DESTROY_KEY` cho đúng key ID/version, reason và expected state.
2. **Application/data owner** xuất bằng chứng rằng không còn wrapped DEK hoặc backup nào cần v3, và writer đã dừng dùng v3.
3. **Key owner** phê duyệt quyết định hủy dựa vào retention và trách nhiệm nghiệp vụ.
4. **Security approver độc lập** xác minh key đã deactivated, không còn phụ thuộc và không có incident/legal hold ngăn hủy.
5. **Executor** kiểm tra policy revision, điều kiện deletion của provider, dependency mới nhất và approval còn hiệu lực.
6. **HSM/KMS** thực hiện thủ tục xóa/hủy theo semantics của dịch vụ: có thể là hẹn xóa, chờ grace period, hoặc hủy vật liệu theo cơ chế chuyên dụng.
7. **Auditor** đối chiếu provider event, thời gian, key version và evidence, bảo đảm không xóa vật liệu của key khác do nhầm alias.

### Điều có thể sai dù đã có hai người duyệt

Giả sử writer cũ ghi thêm một wrapped DEK bằng `kek-v3` sau khi các approver đã xem bảng thống kê. Nếu workflow không kiểm tra lại **đường new use và dependency** trước deletion, hủy vẫn gây mất dữ liệu.

Nếu một cloud KMS hỗ trợ **scheduled deletion**, hai phê duyệt chỉ cho phép đi vào trạng thái chờ xóa; chưa thể coi vật liệu đã bị tiêu hủy cho đến khi có **sự kiện hoàn tất** và đối chiếu trạng thái provider.

### Rút ra

Dual control là **điều kiện quản trị cần**, nhưng **không thay kiểm tra kỹ thuật, tính nhất quán dữ liệu, retention hay backup**.

## 18. Case study: Dual control cho ký release artifact

Một pipeline CI/CD tạo artifact và manifest. Private signing key `release-signing-v5` nằm trong HSM, không xuất được. Kẻ tấn công chiếm service account có thể cố gửi digest của artifact độc hại tới `Sign`.

### Mô hình phê duyệt

- **Build system** tạo artifact, SBOM/manifest và digest dưới quy trình có kiểm soát.
- **Release owner** phê duyệt phiên bản, channel và tập artifact cụ thể.
- **Security/release approver độc lập** xác nhận provenance, policy và các dấu hiệu bất thường.
- **Signing executor** chỉ nhận **digest đúng tập artifact đã phê duyệt**, xác minh approval còn hiệu lực, rồi gọi HSM.
- **Verifier/consumer** kiểm tra chữ ký, key ID, trust, metadata và chính sách kênh phát hành.

~~~mermaid
flowchart TD
    Artifact[Build artifact + canonical manifest] --> Digest[Digest/ID được bảo vệ]
    Digest --> R[Release approval]
    Digest --> S[Security approval độc lập]
    R --> Gate{Hai approval đúng artifact, phiên bản, TTL?}
    S --> Gate
    Gate -->|Không| Deny[Từ chối ký + audit]
    Gate -->|Có| Exec[Signing executor được hạn chế quyền]
    Exec --> HSM[HSM Sign đúng digest]
    HSM --> Record[Chữ ký + manifest + audit]
~~~

### Tại sao không chỉ dùng `CKA_SIGN=true`?

HSM có thể biết một key được phép `Sign` nhưng **không biết digest có thuộc release đã được phê duyệt**. Nếu service account có quyền ký tùy ý, private key non-exportable vẫn có thể bị lạm dụng thành signing oracle.

Dual control cho **artifact digest** giúp hạn chế quyền ký; cần kết hợp xác thực build provenance, chống thay đổi manifest sau duyệt, IAM ở HSM và cơ chế phát hành đáng tin.

### Còn những chữ ký cũ?

Khi thay signing key, các bản phát hành cũ có thể vẫn cần public key/chứng thư và bằng chứng xác minh. Không xóa toàn bộ vật liệu xác minh lịch sử chỉ vì private key đã nghỉ sử dụng. Nếu key bị lộ, cần đánh giá trust/revocation/ảnh hưởng của artifact đã phát.

## 19. Case study: khôi phục dữ liệu bằng recovery KEK

### Tình huống

Một nhóm hỗ trợ cần phục hồi dữ liệu hóa đơn đã mã hóa cho một khách hàng. Hệ thống có **recovery KEK** trong KMS để giải bọc DEK khi đường thông thường bị mất. Đường này có thể cho phép truy cập dữ liệu rất nhạy cảm.

### Luồng kiểm soát

1. Khách hàng hoặc đại diện có thẩm quyền khởi tạo yêu cầu khôi phục theo quy trình.
2. **Data owner** xác minh danh tính và phạm vi chính xác: tenant, bản ghi, mục đích và người nhận kết quả.
3. **Security approver** đánh giá điều kiện và khả năng lạm dụng, dùng MFA/step-up theo risk tier.
4. Workflow phát quyền `Unwrap` tạm thời cho executor trên **đúng key ID và tập dữ liệu**, thay vì cấp grant toàn hệ thống.
5. Executor xử lý dữ liệu trong môi trường giới hạn, bảo vệ DEK/KEK/plaintext ở mức được phép.
6. Sau khi hoàn thành, quyền bị thu hồi; audit chứa **request ID, owner, approvers, key ID, số lượng bản ghi, thời gian và kết quả**, nhưng không chứa plaintext/DEK.
7. Thông báo và kiểm toán hậu kiểm theo chính sách, đặc biệt nếu có đường phục hồi ngoài quyền của chủ dữ liệu.

### Rủi ro đặc biệt

Nếu attacker có thể tự phê duyệt cả hai bước thông qua hai account, hoặc tự cấp quyền `kms:Decrypt` qua policy edit, dual control thất bại.

Nếu raw DEK bị lộ trong lúc khôi phục, rewrap dưới KEK mới **không thu hồi được bản sao DEK đã bị lấy**. Cần xem xét re-encrypt, phạm vi dữ liệu đã lộ và quy trình ứng cứu.

## 20. Kiểm toán và phát hiện bypass dual control

Một hệ thống có nhiều approval nhưng thiếu audit độc lập vẫn có thể không chứng minh được các ràng buộc đã được tuân thủ.

### Các event cần ghi

| Event | Nội dung tối thiểu | Không nên ghi |
| --- | --- | --- |
| `KEY_ACTION_REQUESTED` | Request ID, actor, action, key ID/version, policy revision | Raw private key/DEK/KEK |
| `APPROVAL_GRANTED` | Approver identity/role, thời điểm, request digest, TTL | Credential/MFA secret |
| `APPROVAL_DENIED` | Lý do từ chối và phạm vi an toàn | Dữ liệu nhạy cảm quá chi tiết cho client |
| `APPROVAL_EXPIRED` | Request ID và thời hạn | Secret |
| `POLICY_CHANGED` | Người sửa, thay đổi, revision trước/sau | Token truy cập |
| `KEY_ACTION_EXECUTED` | Executor, provider API, key ID, kết quả, idempotency ID | Plaintext và key material |
| `BREAK_GLASS_USED` | Điều kiện, quyền tạm, danh tính, TTL và review | Raw recovery key |
| `KEY_DESTRUCTION_COMPLETED` | Provider evidence, trạng thái cuối, approval refs | Bản sao khóa trong log |

### Những tín hiệu cần cảnh báo

- Cùng một identity hoặc cùng yếu tố điều khiển được dùng cho cả hai bước duyệt.
- Approval gắn request fingerprint không khớp hoặc bị dùng lại cho key khác.
- Provider ghi nhận `Delete`, `Decrypt`, `Export`, `Sign` hoặc policy change **không tìm thấy request đã duyệt tương ứng**.
- Một admin tự cấp IAM grant sau khi bị workflow từ chối.
- Executor dùng quyền ngoài khung thời gian được cấp.
- Key state hoặc policy revision thay đổi sau duyệt nhưng trước thi hành.
- Break-glass được dùng lặp lại thành quy trình thường nhật.
- Hành động hủy xảy ra khi dependency inventory còn dữ liệu phụ thuộc.

**Log approval cần đối soát với log provider**. Một workflow có thể ghi “Approved” nhưng lệnh KMS chưa chạy hoặc thất bại; ngược lại lệnh provider có thể đã chạy qua đường bypass mà workflow không biết.

## 21. Kiểm thử và threat modeling cho dual control

### 21.1. Các negative test quan trọng

1. **Một approval duy nhất:** Hệ thống phải từ chối.
2. **Hai approval cùng identity:** Phải từ chối.
3. **Người đề xuất tự phê duyệt khi policy cấm:** Phải từ chối.
4. **Hai role không đủ:** Ví dụ hai custodian không thay cho owner + security khi policy yêu cầu.
5. **Approval hết hạn:** Phải từ chối.
6. **Khác key ID/version hoặc tenant:** Phải từ chối dù request trông tương tự.
7. **Thay payload sau phê duyệt:** Phải yêu cầu phê duyệt lại.
8. **Policy revision thay đổi:** Phải kiểm tra lại, không mặc định dùng approval cũ.
9. **Replay/duplicate execution:** Chỉ cùng tác vụ hợp lệ được retry an toàn; không thực hiện lần hai ngoài ý định.
10. **Direct provider call:** Principal không được duyệt không thể bypass control plane.
11. **Admin tự sửa IAM/role/approval store:** Phải bị chặn hoặc cần kiểm soát tương đương.
12. **Đổi alias trong lúc đang chờ:** Executor không được thao tác nhầm key material.
13. **Key bị suspend/compromised trước thi hành:** Phải đánh giá lại.
14. **Data dependency xuất hiện sau kiểm tra:** Không hủy khi chưa giải quyết.
15. **Cố ngắt mạng ở giữa thực thi:** Workflow không được rơi vào trạng thái không rõ đã hủy/rotate hay chưa.

### 21.2. Threat model nên xét người nội bộ

Nhóm đe dọa không chỉ là attacker bên ngoài. Cần xét:

- **Insider** có đặc quyền KMS hoặc IdP.
- Người có quyền merge code/deploy pipeline workflow.
- Người quản trị audit/log pipeline.
- Service account có quyền rộng và có thể bị chiếm.
- Người có thể reset MFA hoặc cấp quyền approver.
- Người giữ HSM quorum token/key share không bảo vệ đúng.
- Thành viên rời tổ chức nhưng chưa thu hồi các quyền hoặc thiết bị xác thực.

### 21.3. Không đánh đổi availability một cách mù quáng

Nếu một thao tác cứu dữ liệu hoặc cô lập lỗ hổng đang diễn ra bị kẹt vì approver vắng mặt, hệ thống cần **quy trình dự phòng hợp lệ** (backup approver, ca trực, break-glass đã định). Tránh tạo áp lực khiến người vận hành chia sẻ tài khoản hoặc giữ quyền superadmin luôn mở.

**Bảo mật và khả dụng phải được thiết kế cùng nhau**, với thử nghiệm diễn tập trước sự cố.

## 22. Sai lầm thường gặp

| Sai lầm | Hậu quả | Biện pháp |
| --- | --- | --- |
| Hai checkbox phê duyệt nhưng cùng người điều khiển hai account | Dual control chỉ mang tính hình thức | Identity độc lập, MFA, kiểm soát ủy quyền |
| Đếm hai lượt click của cùng một approver | Không có bên thứ hai | Unique person/role checks |
| Phê duyệt không ràng buộc key ID/version | Chuyển approval sang khóa khác | Canonical request fingerprint |
| Phê duyệt chung “cho làm mọi việc” | Mở quyền ngoài mục đích | Scope theo operation, tenant, TTL, payload |
| Cho admin sửa approval DB trực tiếp | Dễ giả mạo quyết định | Approval source có integrity và IAM |
| Cho custodian tự cấp `Sign/Decrypt` qua policy | Bypass SoD | Chặn quyền gián tiếp/self-escalation |
| Chỉ đặt kiểm tra ở UI | API trực tiếp vẫn chạy | Enforcement tại control plane/provider |
| Tin PKCS#11 key usage đồng nghĩa dual control | HSM vẫn có thể nhận lời gọi một người | Dùng quorum/workflow được hỗ trợ |
| Dùng hai người nhưng không kiểm tra dependency trước Destroy | Có thể mất dữ liệu | Chặn writer, kiểm tra retention/backup |
| Không ràng buộc revision/thời gian | Approval cũ dùng dưới policy mới | Revalidate, TTL, one-time use |
| Tự chia key bằng cách cắt chuỗi byte | Không bảo đảm split knowledge | Cơ chế threshold/sharing chuẩn |
| Bắt hai người duyệt mọi Encrypt | Không vận hành được, không tăng bảo mật thích đáng | Áp dụng dual control cho thay đổi policy và thao tác rủi ro cao |
| Luôn yêu cầu chờ duyệt trước khi suspend khẩn cấp | Chậm cô lập lạm dụng | Emergency containment role + hậu kiểm |
| Coi non-exportable HSM key là không thể bị lạm dụng | Signing oracle, Decrypt oracle | Business approval, IAM, audit |
| Không quản lý người rời tổ chức | Approval token/role còn hiệu lực | Offboarding và rotation credential |
| Log chỉ có approval, không có provider event | Không chứng minh đã thực thi đúng | Cross-check KMS/HSM audit |
| Break-glass quyền vĩnh viễn | Trở thành đường vòng luôn mở | TTL, scope, báo cáo, thu hồi |
| Hai người duyệt resume key đã lộ | Không khôi phục tính bí mật | Thay key material và đánh giá sự cố |
| Hủy khóa sau khi rewrap nhưng còn backup cũ | Không restore được bản backup | Dependency inventory và DR test |
| Đánh đồng dual control với một nghi thức thủ công | Bỏ sót automation và API | Thiết kế cưỡng chế end-to-end |

## 23. Checklist triển khai Dual control trong production

1. **Phạm vi:** Các thao tác nào thuộc dual control? Có gắn theo key purpose, risk tier, dữ liệu và môi trường?
2. **Identity:** Hai approver có thực sự là hai chủ thể độc lập, danh tính có thể quy trách nhiệm và xác thực mạnh?
3. **Role:** Có yêu cầu cụ thể owner + security, custodian + security hay quorum được phê duyệt?
4. **SoD:** Người đề xuất, người duyệt, người thực thi, người sử dụng key và auditor có được tách quyền?
5. **Indirect privilege:** Có ai tự cấp `Decrypt/Sign/Export`, sửa IAM/key policy, role trust hoặc code workflow để bypass?
6. **Request:** Approval gắn action, key ID/version, purpose, tenant, data scope, parameters và policy revision?
7. **Canonicalization:** Payload bất biến và request digest/định danh được bảo vệ khỏi sửa đổi?
8. **TTL/replay:** Approval có thời hạn, dùng một lần/idempotency, bị hủy khi policy thay đổi?
9. **Final recheck:** State, cryptoperiod, phiên bản, data dependency và incident status được kiểm tra sát lúc gọi provider?
10. **Provider enforcement:** KMS/HSM/IAM có ngăn các đường trực tiếp ngoài workflow và quyền self-escalation?
11. **Key generation:** Với root/CA/recovery key, có key ceremony, RNG/DRBG được phê duyệt, HSM boundary phù hợp?
12. **Split knowledge:** Nếu dùng M-of-N hoặc secret sharing, có cơ chế chuẩn và quản lý share độc lập không?
13. **DEK/KEK:** Các thao tác `Unwrap`, backup, rewrap, re-encrypt và Destroy được phân loại đúng rủi ro?
14. **Signing:** Có kiểm soát nội dung artifact/digest, signing oracle, cert/JWKS và lịch sử chữ ký?
15. **HMAC/ECDH:** Dual control áp vào phân phối/trust/rotation, không làm chậm mỗi webhook hoặc TLS handshake?
16. **Recovery:** Quy trình phục hồi dữ liệu có approver đúng vai trò, least privilege, giới hạn tenant/time và audit?
17. **Emergency:** Có cách suspend nhanh, backup approver, quyền break-glass ngắn hạn và review hậu kiểm?
18. **Consistency:** Workflow có revision, transaction/idempotency, kiểm soát race và cơ chế khôi phục sau lỗi?
19. **Evidence:** Log approval và provider action có thể đối soát, integrity/retention được bảo vệ, không lộ key material?
20. **Negative tests:** Đã thử các trường hợp duplicate identity, sai role, hết hạn, đổi key/payload và direct provider bypass?
21. **Retirement:** Trước xóa key có dependency inventory, backup/DR test và phê duyệt destruction thực sự?
22. **Offboarding:** Có thu hồi quyền/thiết bị của approver hoặc custodian nghỉ việc và cập nhật nhóm dự phòng?
23. **Đánh giá định kỳ:** Có rà soát các ngoại lệ dual control, quyền superadmin và sự kiện sử dụng break-glass?
24. **Kết quả:** Có thể chứng minh **một người đơn lẻ không thể hoàn tất thao tác rủi ro cao** qua bất kỳ đường được quản lý nào?

### Ghi nhớ

**Dual control** là cơ chế yêu cầu **hai chủ thể có thẩm quyền và độc lập cùng tham gia/cho phép thao tác nhạy cảm**, đặc biệt khi quản lý **root key, KEK, private signing key, HSM, recovery và destruction**. Nó **khác separation of duties, split knowledge và M-of-N**, dù các cơ chế có thể bổ trợ nhau. Điều quan trọng không phải số chữ ký trong ticket, mà là **tính độc lập của danh tính, tính bất biến của yêu cầu, quyền không thể bypass tại KMS/HSM, kiểm tra trạng thái mới nhất và audit đối chiếu được**. Trong vòng đời khóa, dual control giúp hạn chế một người tự tạo, cấp quyền, sử dụng, xoay, phục hồi hoặc hủy khóa trái phép; đồng thời phải kết hợp **CSPRNG, IAM least privilege, DEK/KEK trong envelope encryption, chữ ký số, KDF, rotation, suspension, thu hồi và lưu giữ dữ liệu lịch sử**. Một chính sách dual control hiệu quả vừa **ngăn lạm dụng**, vừa **cho phép vận hành và ứng cứu sự cố** theo những đường đã được thiết kế và kiểm chứng.

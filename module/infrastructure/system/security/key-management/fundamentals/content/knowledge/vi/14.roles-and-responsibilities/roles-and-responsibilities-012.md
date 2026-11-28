# Break-glass access – Quyền truy cập khẩn cấp khi quản lý khóa mật mã

**Break-glass access** (quyền truy cập khẩn cấp) là cơ chế cho phép một người hoặc một nhóm đã được tổ chức ủy quyền **thực hiện một số thao tác đặc quyền trong tình huống bất thường, có giới hạn rõ về mục đích, thời gian, phạm vi và bằng chứng kiểm toán**. Trong quản lý khóa mật mã, cơ chế này có thể được dùng để **phục hồi khả năng giải mã, cô lập khóa bị lộ, khắc phục cấu hình KMS/HSM hoặc xử lý tình huống mất đường quản trị thông thường**.

Tên gọi “break glass” gợi hình ảnh phá hộp kính để lấy thiết bị cứu hộ: chỉ sử dụng khi thật sự có sự cố, không phải lối tắt cho công việc hằng ngày. Khác biệt quan trọng là **mở đường khẩn cấp không có nghĩa được bỏ qua mọi kiểm soát bảo mật**; thiết kế tốt chuyển sang một **quy trình kiểm soát được định nghĩa trước** với phê duyệt, giới hạn đặc quyền, giám sát, thu hồi và hậu kiểm.

Bài thuộc chương **Vai trò và trách nhiệm** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Break-glass cần được thiết kế cùng toàn bộ vòng đời khóa **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**, đồng thời liên hệ mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM, phân quyền và kiểm toán.

> **Nguyên tắc cốt lõi:** Break-glass là **ngoại lệ được quản trị**, không phải tài khoản “siêu quản trị không bị giám sát”. Khả năng khôi phục khẩn cấp phải tồn tại **trước khi có sự cố**, được thử nghiệm, có nguồn tin cậy độc lập và không vô tình tạo thêm điểm lộ DEK, KEK, private key hoặc dữ liệu nhạy cảm.

## 1. Khi nào cần break-glass access?

Các tình huống có thể cần cơ chế truy cập khẩn cấp gồm:

1. **Mất đường quản trị KMS:** hệ thống cấp quyền thông thường gặp sự cố, trong khi cần phục hồi khả năng giải mã dữ liệu đang phục vụ hoạt động thiết yếu.
2. **Khóa có dấu hiệu bị lộ:** phải nhanh chóng chặn thao tác ký, giải mã hoặc unwrap trái phép trước khi luồng phê duyệt thường lệ kịp hoàn tất.
3. **Cấu hình IAM sai:** người vận hành bị khóa khỏi một miền quản lý khóa và cần khôi phục quyền tối thiểu theo thủ tục đã được phê duyệt.
4. **Sự cố vùng triển khai:** phải kích hoạt đường dự phòng hoặc phục hồi HSM/KMS bằng cơ chế nhà cung cấp hỗ trợ.
5. **Khôi phục dữ liệu theo DR:** cần truy cập khóa hoặc chức năng unwrap cho một tập dữ liệu và khoảng thời gian xác định, sau khi đã xác nhận quyền và phạm vi sự cố.
6. **Sự cố hệ thống PKI hoặc signing:** cần ngừng khóa ký bị nghi xâm phạm, chuyển trust sang khóa mới và bảo vệ các consumer.

**Không nên kích hoạt break-glass** chỉ vì developer muốn debug nhanh, pipeline thiếu một quyền IAM, một nhân viên nghỉ phép, hoặc một tác vụ thường lệ đang bị quy trình phê duyệt chặn lại. Trường hợp đó cần sửa **access request/Just-in-Time (JIT) privilege** hoặc lịch trực, không biến ngoại lệ khẩn cấp thành quyền thường trực.

### 1.1. Phân biệt các loại quyền

| Cơ chế | Mục đích | Cấp quyền như thế nào? |
| --- | --- | --- |
| **Quyền thường trực theo vai trò** | Vận hành bình thường theo trách nhiệm. | Hạn chế theo IAM/RBAC/ABAC và key usage; review định kỳ. |
| **JIT / Privileged Access Management (PAM)** | Cấp đặc quyền tạm thời cho công việc có kế hoạch. | Có yêu cầu, thời hạn, phê duyệt và phạm vi; thường không phải tình huống khẩn cấp. |
| **Break-glass access** | Xử lý tình huống rủi ro cao khi đường bình thường không đáp ứng. | Theo runbook khẩn cấp, danh tính dành riêng hoặc cơ chế phục hồi, mức giám sát cao hơn. |
| **HSM recovery/quorum** | Khôi phục hoặc thực hiện hành động HSM cần nhiều bên. | Theo cơ chế kỹ thuật của HSM; có thể là **một phần** của break-glass. |
| **Root/owner account của cloud** | Quyền quản trị cấp cao trong phạm vi nền tảng. | Không mặc nhiên nên sử dụng làm break-glass; tuân thủ mô hình nhà cung cấp và kiểm soát tổ chức. |

**Break-glass account và quyền break-glass không nhất thiết giống nhau.** Có nền tảng duy trì một danh tính khẩn cấp đã được chuẩn bị sẵn; nơi khác cấp quyền JIT qua một luồng đặc biệt, hoặc sử dụng cơ chế phục hồi do nhà cung cấp quản lý. Không giả định mọi KMS/HSM đều có API `BreakGlass` hoặc hỗ trợ xuất khóa để “cứu dữ liệu”.

## 2. Threat model: break-glass giải quyết một rủi ro nhưng tạo rủi ro khác

Một đường truy cập khẩn cấp có thể giúp chống **mất khả dụng**. Nhưng nếu bị lạm dụng, nó có thể vượt qua chính những lớp bảo vệ thường lệ và ảnh hưởng đến **tính bí mật, toàn vẹn, xác thực và khả năng phục hồi**.

| Đối tượng/rủi ro | Kịch bản | Biện pháp bắt buộc cân nhắc |
| --- | --- | --- |
| **Insider có đặc quyền** | Dùng tình huống “khẩn cấp” giả để truy cập DEK hoặc ký giao dịch trái phép. | Phê duyệt độc lập, tách nhiệm vụ, mục đích được ghi nhận, giám sát liên tục. |
| **Credential bị đánh cắp** | Kẻ tấn công chiếm tài khoản break-glass chưa được dùng. | MFA/phương thức xác thực mạnh và độc lập theo khả năng, bảo vệ kho credential, cảnh báo mọi lần đăng nhập. |
| **Compromise IAM/PAM** | Kẻ tấn công sửa role policy hoặc quy trình phê duyệt. | Ranh giới phục hồi độc lập, cơ chế xác minh actor, nhật ký không thể sửa tùy ý. |
| **Lạm dụng API ký/giải mã** | Khóa trong HSM non-exportable nhưng vẫn bị dùng để Sign/Decrypt. | Giới hạn key IDs, operations, approval và theo dõi mức sử dụng, không chỉ cấm ExportKey. |
| **Rò rỉ backup/recovery material** | Bản sao KEK/secret phục hồi nằm ngoài HSM và bị lấy cắp. | Chỉ dùng cơ chế secure backup/restore được hỗ trợ; bảo vệ tách miền. |
| **Khôi phục policy cũ** | Restore làm khóa đã thu hồi có thể ký trở lại. | Đối chiếu trạng thái revocation/compromise mới nhất trước khi bật quyền. |
| **Sự cố lan rộng** | Một người có thể xóa khóa lẫn toàn bộ backup. | Separation of duties, hạn chế Delete/Destroy và phương án DR độc lập. |
| **Audit bị tắt hoặc sửa** | Đường khẩn cấp được dùng mà không để lại bằng chứng. | Thu thập audit bên ngoài miền có thể bị chiếm quyền; cảnh báo theo sự kiện. |

**Không thể đạt mức “zero risk” chỉ bằng một tài khoản khẩn cấp.** Phải xác định **những hành động mà cơ chế được phép làm** và **những hành động vẫn phải bị chặn** ngay cả khi đang khẩn cấp.

### 2.1. Vì sao “unlimited admin” là phương án yếu?

Một tài khoản có mọi quyền `Sign`, `Decrypt`, `Unwrap`, `ExportKey`, `ChangePolicy` và `ScheduleDeletion` có thể vừa đọc dữ liệu, giả mạo giao dịch, vừa phá hủy khả năng khôi phục. Nếu credential hoặc người giữ nó bị xâm nhập, phạm vi thiệt hại rất lớn.

Phương án tốt hơn là chia thành **nhóm tác vụ khẩn cấp được xác định rõ**: khôi phục cấu hình truy cập, vô hiệu hóa một key bị lộ, sử dụng Decrypt/Unwrap với một tập dữ liệu phục hồi đã được duyệt, hoặc khôi phục hệ thống HSM theo thủ tục chuyên biệt. Quyền nguy hiểm như **xuất private key, hủy root KEK, xóa audit** cần chính sách riêng và có thể **không bao giờ được cấp qua break-glass thông thường**.

## 3. Ai chịu trách nhiệm trong một sự kiện break-glass?

Break-glass chỉ an toàn nếu không có tình trạng “người yêu cầu cũng tự phê duyệt, tự thực hiện và tự xác nhận”. Các vai trò có thể phân định theo bảng **RACI minh họa** (R = Responsible, A = Accountable, C = Consulted, I = Informed).

| Công việc | Incident commander | Security approver | KMS/HSM operator | Application owner | Auditor/SOC |
| --- | --- | --- | --- | --- | --- |
| Xác định sự cố và mức khẩn cấp | **A/R** | C | C | C | I |
| Duyệt ngoại lệ quyền | C | **A/R** | I | C | I |
| Kích hoạt credential/session khẩn cấp | I | A | **R** | I | I |
| Giới hạn key ID và thao tác | C | **A** | **R** | C | I |
| Thực thi khôi phục/cô lập theo runbook | A | C | **R** | **R** khi ứng dụng liên quan | I |
| Thu hồi quyền và kiểm tra hậu quả | A | **R** | **R** | C | I |
| Đối chiếu log, hậu kiểm và cải tiến | A | C | C | C | **R** |

Tổ chức có thể chọn tên vai trò khác, nhưng cần bảo đảm **người phê duyệt đủ thẩm quyền**, **người thực thi có năng lực**, và **người kiểm toán không phụ thuộc vào chính người dùng quyền khẩn cấp**.

### 3.1. Dual control, quorum và separation of duties

- **Dual control:** hai vai trò độc lập phải tham gia/phê duyệt một hành động nhạy cảm.
- **Quorum / m-of-n:** một số quy trình HSM, recovery hoặc chính sách tổ chức yêu cầu **m trong n người được ủy quyền** cùng đáp ứng điều kiện.
- **Separation of duties:** người đề xuất, người phê duyệt và người hậu kiểm không nên là cùng một chủ thể nếu rủi ro đòi hỏi kiểm soát độc lập.

**Hai lượt click từ cùng một tài khoản không phải dual control**. Tương tự, việc hai người nhập một chuỗi vào giao diện không tự tạo ra quorum mật mã: điều đó phụ thuộc cơ chế của nền tảng, danh tính đã xác thực và bằng chứng độc lập.

Với **tình huống không liên lạc được người phê duyệt**, runbook phải nêu phương án leo thang đã được phê duyệt trước (ví dụ người trực thay thế), chứ không âm thầm bỏ qua bước xác thực chỉ vì SLA khẩn cấp.

## 4. Điều kiện kích hoạt và phạm vi đặc quyền

Một yêu cầu break-glass nên có tối thiểu:

1. **Incident ID** và mô tả cụ thể hệ thống bị ảnh hưởng.
2. **Bằng chứng trigger:** sự cố gì, vì sao kênh quyền thông thường không đáp ứng.
3. **Requester và owner:** danh tính, nhóm, thông tin liên lạc, xác thực mạnh theo policy.
4. **Key/asset scope:** key ID/version, KMS/HSM environment, account, region, tenant, workload hoặc tập dữ liệu.
5. **Operation scope:** chẳng hạn `DescribeKey`, `DisableKey`, `Decrypt`/ `Unwrap` với dữ liệu đã phê duyệt; không dùng wildcard.
6. **Time-to-live (TTL):** khoảng hiệu lực tối thiểu cho mục tiêu, thời điểm bắt đầu/kết thúc và cơ chế thu hồi sớm.
7. **Approvals:** ai phê duyệt, độc lập với requester theo yêu cầu, phạm vi phê duyệt.
8. **Monitoring:** ai nhận cảnh báo khi kích hoạt và từng thao tác nhạy cảm; lưu audit ở đâu.
9. **Exit criteria:** khi nào kết thúc, quyền nào cần vô hiệu hóa, dữ liệu/key nào phải đối soát.
10. **Recovery/rollback:** nếu thao tác thất bại hoặc gây gián đoạn, đường quay lại an toàn nào được cho phép.

**TTL không chỉ là hạn trên một trang ticket.** Quyền trong IAM/session/KMS phải thực sự **hết hiệu lực hoặc được thu hồi** khi hết hạn, kể cả token đã cấp và các phiên hoạt động nếu nền tảng có cơ chế xử lý. Đừng mặc định xóa một ticket sẽ lập tức vô hiệu hóa tất cả credential liên quan.

### 4.1. Chính sách nên giới hạn đến mức nào?

| Thuộc tính | Quyền rộng, khó kiểm soát | Phạm vi khẩn cấp có giới hạn |
| --- | --- | --- |
| **Resource** | Tất cả khóa toàn tổ chức. | Một key family/phiên bản hoặc tập key IDs cho incident. |
| **Operation** | Toàn bộ API quản trị và mật mã. | Các thao tác cần thiết cho runbook được duyệt. |
| **Tenant** | Có thể giải mã mọi tenant. | Chỉ tenant/dataset trong phạm vi phục hồi. |
| **Time** | Credential không hết hạn. | Quyền ngắn hạn, có giám sát và thu hồi. |
| **Identity** | Shared account không xác định người dùng. | Danh tính cá nhân/actor có bằng chứng xác thực, kể cả khi dùng account khẩn cấp. |
| **Approval** | Một người tự cấp và tự duyệt. | Hai bên độc lập hoặc quorum theo mức rủi ro. |
| **Audit** | Log nội bộ có thể bị người dùng quyền xóa. | Nhật ký tập trung/tách quyền, cảnh báo thời gian gần thực. |

Trong sự cố cực kỳ nghiêm trọng, không phải mọi hệ thống đều cấp quyền chi tiết đến từng bản ghi. Khi không đạt điều kiện kỹ thuật, policy cần **ghi nhận phạm vi rộng hơn cùng biện pháp bù trừ** như giám sát trực tiếp, hạn chế thời gian và phê duyệt cấp cao, thay vì giả vờ IAM đã giới hạn theo tenant.

## 5. Chuẩn bị sẵn cơ chế trước khi có sự cố

Một đường khẩn cấp không nên được thiết kế lần đầu trong lúc KMS đang ngừng hoạt động.

### 5.1. Danh tính và credential khẩn cấp

- Chuẩn bị theo **mô hình nhà cung cấp được hỗ trợ**, không tự tạo cửa hậu trong ứng dụng.
- Giữ credential hoặc cơ chế khôi phục ở **kho riêng/miền phục hồi an toàn**, tránh cùng failure domain với hệ IAM có thể gặp sự cố.
- Dùng **MFA hoặc phương thức xác thực chống phishing** phù hợp với điều kiện vận hành, nhưng phải bảo đảm đường dự phòng thực sự dùng được khi hạ tầng chính lỗi.
- Hạn chế người có quyền truy cập, có **đường liên lạc và người thay thế** cho ca trực.
- Giám sát cả **đăng nhập thử, đăng nhập thành công và thay đổi policy** của danh tính khẩn cấp.
- Không dùng thường xuyên cho tác vụ maintenance; mọi lần dùng phải gắn incident/ticket được kiểm soát.

**Không nên lưu mật khẩu break-glass trong wiki, email, repository hoặc tài liệu không được bảo vệ.** Nếu dùng cơ chế niêm phong vật lý hoặc password vault được quản lý, phải bảo đảm quy trình mở, kiểm tra và cấp lại secret sau khi sử dụng.

### 5.2. HSM và vật liệu phục hồi

Trong một số HSM, các nhiệm vụ phục hồi yêu cầu **security officer role, backup token, recovery card hoặc quorum**. Danh sách cụ thể phụ thuộc sản phẩm. Developer và người vận hành **không được suy rằng có thể lấy private key/KEK dạng rõ** chỉ vì đã kích hoạt break-glass.

Nếu khóa là **non-exportable**, phục hồi phải dựa trên cơ chế chính thức do nhà cung cấp hỗ trợ. **Non-exportable không đồng nghĩa tự có khả năng backup/restore**; cần kiểm tra trước, theo dõi key provenance và thử quy trình trong điều kiện phù hợp.

### 5.3. Không tạo bootstrap dependency vòng

Ví dụ: tất cả credential break-glass được lưu trong một vault chỉ mở được bằng KMS đang bị lỗi; khi xảy ra sự cố, không thể lấy credential để khôi phục KMS. Đây là **phụ thuộc vòng**.

Một thiết kế phục hồi cần biết: ai xác thực được khi identity provider lỗi, audit đi đâu khi hệ thống logging chính ngừng hoạt động, làm sao phê duyệt khi mạng nội bộ không sẵn sàng, và KMS/HSM nào giữ khóa bảo vệ bản sao phục hồi.

**Không giải quyết bootstrap problem bằng cách đặt một root key plaintext cố định ngoài kiểm soát**. Đường thay thế phải có cơ chế bảo vệ, giới hạn đặc quyền và quản trị được kiểm thử.

## 6. Quy trình break-glass từ kích hoạt đến hậu kiểm

~~~mermaid
flowchart TD
    START["Phát hiện sự cố có thể cần quyền khẩn cấp"] --> TRIAGE["Incident commander phân loại mức độ và phạm vi"]
    TRIAGE --> NEED{"Quyền thường lệ/JIT có xử lý kịp và an toàn?"}
    NEED -->|Có| NORMAL["Dùng luồng thông thường"]
    NEED -->|Không| REQUEST["Lập yêu cầu incident, key scope, operations, TTL"]
    REQUEST --> APPROVE["Xác thực và phê duyệt độc lập/quorum theo policy"]
    APPROVE --> GATE{"Đủ điều kiện?"}
    GATE -->|Không| DENY["Từ chối hoặc leo thang theo runbook"]
    GATE -->|Có| ACTIVATE["Cấp session/quyền có hạn, phát cảnh báo"]
    ACTIVATE --> EXECUTE["Thực thi đúng runbook và kiểm soát key usage"]
    EXECUTE --> AUDIT["Audit từng hành động + giám sát ngoài băng"]
    AUDIT --> EXIT["Thu hồi quyền, khóa session, rotate credential khi cần"]
    EXIT --> VERIFY["Đối soát IAM, KMS state, dữ liệu và consumer"]
    VERIFY --> REVIEW["Hậu kiểm độc lập và cập nhật runbook"]
~~~

### 6.1. Bước 1 – Xác định thật sự cần break-glass

Tìm nguyên nhân: đang thiếu quyền JIT thông thường, hệ thống IAM lỗi, hay có nguy cơ tiếp tục lộ dữ liệu nếu chậm cô lập một key? Người chỉ huy sự cố phải xác nhận **không có đường xử lý ít đặc quyền hơn đáp ứng được mục tiêu**.

Một thông báo “dịch vụ đang chậm” chưa đủ lý do để mở quyền `Decrypt` trên toàn bộ key store. Có thể chỉ cần xử lý quota, queue hoặc sửa cấu hình ứng dụng.

### 6.2. Bước 2 – Xác thực và phê duyệt

Kiểm tra người yêu cầu và approver trong một **nguồn danh tính hoặc thủ tục khẩn cấp đáng tin**, bảo đảm phê duyệt **khác chủ thể**. Nếu có requirement quorum HSM, phải hoàn thành quorum thật ở cơ chế HSM chứ không chỉ ghi `approved=true` trong ticket.

Ticket nên chứa incident severity, lý do không dùng quyền thường lệ, danh sách resource/key IDs, operations, TTL, nguy cơ nghiệp vụ, phương án kết thúc. **Không chứa khóa bí mật**.

### 6.3. Bước 3 – Cấp quyền và thông báo

Kích hoạt **session ngắn hạn hoặc role tạm thời** theo cơ chế IAM/PAM/provider đã chọn. Thiết lập alert tới Security Operations Center (SOC), owner của KMS/HSM và đội ứng dụng. Khi nền tảng không thể cấp TTL tự động, cần phương án **thu hồi thủ công có hai người xác nhận** và một hạn chót đủ rõ.

Mỗi lần cấp quyền phải được liên kết với **principal, incident ID, grant ID và policy version**. Không dựa duy nhất vào IP allowlist để thay xác thực người dùng.

### 6.4. Bước 4 – Thực thi và theo dõi

Chỉ chạy thao tác nằm trong runbook. Ví dụ để giải mã tập backup A, không cấp quyền Sign cho một signing key B. Những thao tác có thể làm mất dữ liệu như hủy khóa cần điều kiện riêng và kiểm tra dependency.

Ghi **request ID của KMS, key reference, action, actor, thời điểm, kết quả**; không ghi DEK/KEK, private key, plaintext, seed, recovery shares hoặc credential. Trong tình huống nhạy cảm, nên có giám sát độc lập hoặc session recording theo chính sách **được bảo vệ khỏi lộ dữ liệu**.

### 6.5. Bước 5 – Thoát chế độ khẩn cấp

Khi đạt mục tiêu hoặc TTL kết thúc:

1. Thu hồi role/session và mọi token có thể tiếp tục dùng theo cơ chế provider.
2. Xử lý **credential đã được tiết lộ hoặc sử dụng**: rotate/cấp lại theo policy.
3. Kiểm tra key policy đã trở về trạng thái mong muốn, không để lại quyền quá rộng.
4. Đối chiếu các thao tác `Decrypt`, `Sign`, `Disable`, `Reenable` đã thực hiện.
5. Kiểm tra dữ liệu, wrapped DEK, trust mapping, bản sao lưu và consumer có bị tác động ngoài dự kiến không.
6. Hoàn thiện audit, đánh giá phạm vi ảnh hưởng và đề xuất sửa lỗi gốc.

**Hết hạn quyền chưa có nghĩa sự cố đã kết thúc.** Có thể vẫn tồn tại bản sao plaintext bị xuất trái phép hoặc một chính sách trust đã bị sửa; phải có bước hậu kiểm độc lập.

## 7. Break-glass khi quản lý KEK, DEK và envelope encryption

Trong **envelope encryption**, ứng dụng mã hóa dữ liệu bằng **DEK** và KMS/HSM bảo vệ DEK dưới **KEK**. Tác vụ khẩn cấp có thể là phục hồi khả năng sử dụng `Unwrap`/ `DecryptDataKey` đối với wrapped DEK và ciphertext đã được xác định.

~~~mermaid
flowchart LR
    REQ["Incident và yêu cầu restore đã duyệt"] --> GATE["Kiểm tra identity, key ID, tenant, TTL, approval"]
    GATE --> KMS["KMS/HSM: Unwrap/DecryptDataKey"]
    STORE["Ciphertext + wrapped DEK + key version + AAD"] --> KMS
    KMS --> APP["Ứng dụng/restore worker đã cấp quyền"]
    APP --> VERIFY["AEAD tag, encryption context, quyền dữ liệu"]
    VERIFY --> RESTORE["Phục hồi tập dữ liệu được duyệt"]
    GATE --> AUDIT["Audit và cảnh báo"]
    KMS --> AUDIT
~~~

Cần phân biệt ba lớp kiểm soát:

- **KMS IAM:** workload nào được phép gọi thao tác trên KEK.
- **Encryption context/AAD:** dữ liệu được ràng buộc với **tenant, purpose, object** theo giao thức/SDK hỗ trợ.
- **Application/data authorization:** người yêu cầu phục hồi có quyền với **đúng tập dữ liệu** hay không.

Một KMS `Decrypt` thành công **không tự chứng minh** người phục hồi có quyền đọc mọi bản mã thuộc KEK đó. Phải giới hạn dữ liệu theo incident và owner, không cấp một quyền wildcard vì “không biết DEK nào”.

### 7.1. Khi KEK bị nghi lộ

Break-glass có thể được dùng để **ngăn thêm thao tác trái phép, khóa hoặc thay policy của một key, cấp key version mới và điều phối khôi phục**. Tuy nhiên:

- **Rotate KEK** hoặc **rewrap DEK** không chữa được dữ liệu cũ nếu DEK đã bị lộ.
- Nếu KEK bị lộ dưới dạng vật liệu khóa, các DEK lịch sử được bọc dưới KEK đó có thể cần đánh giá lại.
- `DisableKey` có thể chặn cả **ứng dụng hợp lệ**, cần kế hoạch duy trì dịch vụ và bảo vệ dữ liệu.
- `ScheduleKeyDeletion`/destruction có thể gây mất dữ liệu vĩnh viễn nếu còn ciphertext/backup phụ thuộc.

Đội xử lý sự cố và data owner cần đánh giá **blast radius** dựa trên **key inventory, version/predecessor, wrapped DEK dependencies và backup** trước khi quyết định hành động không thể đảo ngược.

### 7.2. Khi phải restore từ backup

Một snapshot dữ liệu có thể cần KEK predecessor, DEK phiên bản cũ, AAD và metadata ciphertext chính xác. Break-glass **không cho phép tự bỏ qua key version** hoặc coi “thử mọi khóa cho tới khi decrypt được” là chiến lược khôi phục.

Restore phải kiểm tra:

1. **Điểm khôi phục nhất quán:** bản dữ liệu và các key versions liên quan tồn tại.
2. **Provider-supported recovery:** key material có thể phục hồi theo phương án đã được kiểm thử không?
3. **Current revocation state:** không vô tình bật lại khóa signing/identity bị lộ từ snapshot cũ.
4. **Tenant scope:** chỉ xử lý dữ liệu có quyền theo incident.
5. **Khả năng giải mã và integrity:** kiểm tra AEAD tag, key context và kết quả dữ liệu đại diện.
6. **Cleanup:** quyền khẩn cấp và secret tạm đã được xử lý sau sự cố.

## 8. Break-glass đối với chữ ký số, PKI và HSM

Với private signing key **Ed25519/ECDSA/RSA-PSS**, break-glass cần đặc biệt thận trọng. Người có quyền `Sign` có thể tạo chữ ký **hợp lệ về mật mã** dưới danh tính tổ chức nếu không có kiểm soát nghiệp vụ.

| Nhu cầu | Hướng giải quyết | Điều không được ngầm chấp nhận |
| --- | --- | --- |
| Khóa ký release bị nghi lộ | Vô hiệu hóa quyền ký, chuyển key S1 → S2, cập nhật verifier trust. | Dùng chính private key S1 để ký “thông báo hết hạn” mà không kiểm tra phương án đáng tin. |
| HSM ký không sẵn sàng | Dùng đường dự phòng/khôi phục được phê duyệt, hoặc hoãn phát hành theo chính sách. | Xuất private key rõ để ký trên máy bất kỳ. |
| Chứng chỉ TLS/mTLS hết hạn hàng loạt | Cấp lại/chuyển identity theo PKI, xác minh trust và workload identity. | Tắt certificate hoặc hostname verification. |
| Cần kiểm tra chữ ký cũ | Bảo lưu public key/chứng chỉ, chứng cứ thời gian và trust policy lịch sử. | Mở lại quyền Sign của private key đã retired. |
| Khóa xác minh/JWKS bị thay trái phép | Khôi phục trust mapping từ nguồn có thẩm quyền, điều tra bản ghi giả. | Tin một public key mới chỉ vì nó nằm trong key registry. |

**Hủy private signing key không ngăn public key xác minh chữ ký lịch sử về mặt toán học**. Nhưng nếu key bị compromised, ứng dụng phải đánh giá **tính đáng tin của chữ ký** theo thời điểm và policy. Việc break-glass để cập nhật trust phải lưu bằng chứng độc lập, tránh một người tự thay public key và hợp thức hóa chữ ký giả.

**HSM non-exportable** giúp giữ private key trong ranh giới được thiết kế, nhưng **không ngăn lạm dụng một API Sign đã được cấp quyền**. Break-glass nên ràng buộc quyền ký với workflow, loại thông điệp, lý do và thời gian nếu khả năng nền tảng cho phép; tránh mở quyền Sign không giới hạn chỉ vì đang khẩn cấp.

## 9. Java 17: policy gate minh họa cho một yêu cầu break-glass

Ví dụ Java 17 dưới đây mô phỏng **lớp kiểm tra metadata trước khi yêu cầu IAM/PAM/KMS thực thi**. Nó cho thấy cách ràng buộc **incident ID, actor, key ID, operation, tenant, thời hạn và hai phê duyệt độc lập**.

> **Giới hạn:** Đoạn mã **không cấp quyền KMS thật, không xác thực danh tính thật, không phát hành token IAM, không thực hiện HSM quorum**. Nó chỉ mô tả một **policy gate** để đào tạo. Trong production, các phê duyệt phải đến từ nguồn xác thực đáng tin, quyền phải được thực thi ở **IAM/PAM/KMS/HSM**, log audit phải được bảo vệ và trạng thái phải được lưu bền vững.

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Set;

public final class BreakGlassPolicyDemo {
    enum Operation {
        DESCRIBE_KEY,
        DECRYPT_FOR_APPROVED_RESTORE,
        SIGN,
        EXPORT_KEY,
        SCHEDULE_KEY_DELETION
    }

    record EmergencyGrant(
            String incidentId,
            String requester,
            String targetKeyId,
            String tenantId,
            Set<Operation> allowedOperations,
            Set<String> verifiedApprovers,
            Instant issuedAt,
            Instant expiresAt,
            boolean active) {}

    record Attempt(
            String actor,
            String targetKeyId,
            String tenantId,
            Operation operation,
            Instant at) {}

    record Decision(boolean allowed, String reasonCode) {}

    // Chỉ minh họa metadata gate; các trường trong grant phải đến
    // từ hệ thống phê duyệt/IAM có thẩm quyền, không từ client tự khai.
    static Decision check(EmergencyGrant grant, Attempt attempt) {
        if (grant == null || attempt == null
                || grant.incidentId() == null
                || grant.incidentId().isBlank()
                || !grant.active()) {
            return new Decision(false, "NO_ACTIVE_INCIDENT_GRANT");
        }

        if (grant.issuedAt() == null || grant.expiresAt() == null
                || !grant.issuedAt().isBefore(grant.expiresAt())
                || grant.expiresAt().isAfter(
                        grant.issuedAt().plus(30, ChronoUnit.MINUTES))
                || attempt.at() == null
                || attempt.at().isBefore(grant.issuedAt())
                || !attempt.at().isBefore(grant.expiresAt())) {
            return new Decision(false, "EXPIRED_OR_INVALID_TTL");
        }

        if (grant.requester() == null
                || !grant.requester().equals(attempt.actor())
                || grant.targetKeyId() == null
                || !grant.targetKeyId().equals(attempt.targetKeyId())
                || grant.tenantId() == null
                || !grant.tenantId().equals(attempt.tenantId())) {
            return new Decision(false, "ACTOR_KEY_OR_TENANT_MISMATCH");
        }

        if (grant.verifiedApprovers() == null
                || grant.verifiedApprovers().contains(grant.requester())
                || grant.verifiedApprovers().stream()
                    .filter(id -> id != null && !id.isBlank())
                    .distinct().count() < 2) {
            return new Decision(false, "INDEPENDENT_APPROVALS_REQUIRED");
        }

        // Demo chỉ cho hai loại thao tác; Sign, Export, Destroy luôn chặn.
        if (attempt.operation() == null
                || (attempt.operation() != Operation.DESCRIBE_KEY
                    && attempt.operation()
                        != Operation.DECRYPT_FOR_APPROVED_RESTORE)
                || grant.allowedOperations() == null
                || !grant.allowedOperations().contains(
                        attempt.operation())) {
            return new Decision(false, "OPERATION_NOT_ALLOWED");
        }

        return new Decision(true, "POLICY_METADATA_ACCEPTED");
    }

    public static void main(String[] args) {
        Instant now = Instant.now();

        // Demo: giả sử incident và approvers đã được xác thực
        // bởi một hệ thống độc lập. Trong thực tế không hard-code
        // danh tính hay tự tin vào input chưa được kiểm tra.
        EmergencyGrant grant = new EmergencyGrant(
                "INC-2026-017",
                "recovery-operator-1",
                "kms/prod/billing/kek-v4",
                "tenant-billing-A",
                Set.of(Operation.DESCRIBE_KEY,
                       Operation.DECRYPT_FOR_APPROVED_RESTORE),
                Set.of("security-approver-1", "incident-commander-2"),
                now,
                now.plus(15, ChronoUnit.MINUTES),
                true);

        Attempt permitted = new Attempt(
                "recovery-operator-1",
                "kms/prod/billing/kek-v4",
                "tenant-billing-A",
                Operation.DECRYPT_FOR_APPROVED_RESTORE,
                now.plus(1, ChronoUnit.MINUTES));

        Attempt forbidden = new Attempt(
                "recovery-operator-1",
                "kms/prod/billing/kek-v4",
                "tenant-billing-A",
                Operation.EXPORT_KEY,
                now.plus(1, ChronoUnit.MINUTES));

        Attempt expired = new Attempt(
                "recovery-operator-1",
                "kms/prod/billing/kek-v4",
                "tenant-billing-A",
                Operation.DESCRIBE_KEY,
                now.plus(16, ChronoUnit.MINUTES));

        System.out.println(check(grant, permitted));
        // Decision[allowed=true, reasonCode=POLICY_METADATA_ACCEPTED]
        System.out.println(check(grant, forbidden));
        // Decision[allowed=false, reasonCode=OPERATION_NOT_ALLOWED]
        System.out.println(check(grant, expired));
        // Decision[allowed=false, reasonCode=EXPIRED_OR_INVALID_TTL]

        // KHÔNG trả key material, token IAM hoặc plaintext ra console.
    }

    private BreakGlassPolicyDemo() {}
}
~~~

### 9.1. Những điểm học được từ ví dụ

1. **Incident binding:** mọi quyền có `incidentId`, tránh quyền khẩn cấp tồn tại mà không có lý do.
2. **Principal binding:** requester phải là actor đang thực hiện; một ticket được duyệt cho người A không tự cho người B dùng.
3. **Key/tenant scope:** không cho phép một grant của Billing tenant A dùng trên key hoặc tenant khác.
4. **TTL:** demo giới hạn thời hạn tối đa 30 phút và từ chối thao tác sau `expiresAt`.
5. **Phê duyệt độc lập:** cần hai approvers không phải requester; danh tính phê duyệt **phải được kiểm chứng ở hệ thống thực**.
6. **Allowlist operation:** `Sign`, `ExportKey` và `ScheduleKeyDeletion` luôn bị từ chối trong ví dụ; không dựa vào wildcard.
7. **Fail closed:** dữ liệu thiếu, grant không active hoặc scope không khớp đều trả `allowed=false`.

### 9.2. Vì sao code chưa thể bảo vệ hệ thống production?

- Một object Java có `active=true` và `verifiedApprovers` **có thể bị caller giả mạo** nếu lấy trực tiếp từ request. Phải tạo grant từ **workflow đáng tin** và xác minh tính toàn vẹn ở phía server.
- **Decision true chưa cấp quyền thật**. IAM/PAM phải kiểm tra principal, action, resource, condition và thời gian ngay tại **điểm thực thi**; không chỉ có một if trong application.
- Không có **replay protection, session revocation, persistence, audit append-only, rate limiting, concurrency, KMS policy enforcement** hoặc cơ chế challenge xác thực.
- Demo chỉ kiểm `tenantId` như metadata; production cần kiểm tra **quyền đối với dataset/object thực**, không tin chuỗi tenant tự khai.
- Code chưa thực thi phê duyệt **m-of-n vật lý/mật mã** cho HSM. Không thể thay thế HSM quorum bằng `Set<String>`.
- Giới hạn **30 phút và 2 approvers chỉ là chính sách minh họa**; hệ thống thật xác định theo độ nhạy cảm và năng lực vận hành.

**Thiết kế an toàn:** Ứng dụng dùng gate để diễn đạt ý định, nhưng **IAM/KMS/HSM vẫn phải từ chối độc lập** khi principal không có quyền. Khi đồng bộ trạng thái bị lỗi, chọn phương án fail closed hoặc phương án khẩn cấp **được chuẩn bị và kiểm soát riêng**, không tự động bỏ qua policy.

## 10. Những điểm developer phải thực hiện trong ứng dụng

Ngay cả khi break-glass do Security và KMS/HSM team quản trị, developer vẫn có các trách nhiệm:

- **Không xây endpoint backdoor** như `/admin/decrypt-all` không yêu cầu xác thực hoặc tự động bỏ qua kiểm soát.
- **Kiểm tra data authorization** trong đường phục hồi, không chỉ kiểm tra IAM Decrypt trên KEK.
- **Dùng đúng key ID/version và encryption context/AAD**, kể cả với dữ liệu từ backup.
- **Không log plaintext DEK, KEK, private key, token khẩn cấp hoặc secret recovery**.
- **Thiết kế read compatibility** để giải mã bản mã cũ khi rotation, không buộc sử dụng alias current sai phiên bản.
- **Có cơ chế thu hồi cache/session** và ngừng sử dụng key bị compromise sau sự cố.
- **Phân tách quyền nghiệp vụ** cho các thao tác phục hồi, ký số và xóa khóa.
- **Theo dõi lỗi/giới hạn tài nguyên** để một workload khẩn cấp không làm cạn quota KMS, queue hoặc bộ nhớ.
- **Viết negative tests** cho actor sai, tenant sai, key ID sai, TTL hết hạn, thiếu approver và operation bị cấm.
- **Cung cấp metadata dependency** cho key inventory, data owner và đội DR để quyết định an toàn.

Developer có thể cần một **chế độ chạy phục hồi** riêng, nhưng nó vẫn phải dùng thư viện mật mã và API KMS chuẩn. Không tự tạo cách giải mã “nhanh hơn” bằng AES-ECB, private key export hoặc tắt tag verification chỉ vì đang khẩn cấp.

## 11. Audit, giám sát và bằng chứng tối thiểu

Break-glass là một trong những tình huống cần **audit chặt nhất** vì nó thay đổi ranh giới quyền. Một bộ sự kiện nên theo dõi:

| Sự kiện | Metadata nên có | Điều không được ghi |
| --- | --- | --- |
| **EmergencyAccessRequested** | Incident ID, requester, reason code, key scope, operations, TTL. | Password, recovery token hoặc secret. |
| **EmergencyAccessApproved/Denied** | Approver, policy version, thời điểm, điều kiện/quorum. | HSM shares, OTP hoặc bí mật xác thực. |
| **EmergencyAccessActivated** | Principal/session/grant ref, scope, expiry, nguồn chứng thực. | Access token dạng rõ. |
| **KMSOperationExecuted/Denied** | Key ID/version, operation, request ID, actor, outcome, thời điểm. | DEK/KEK, private key, plaintext, raw HSM command secret. |
| **EmergencyAccessExpired/Revoked** | Grant ID, trạng thái thu hồi, thời gian, chủ thể thực hiện. | Dữ liệu nhạy cảm không phục vụ kiểm toán. |
| **PostIncidentReview** | Kết quả đối soát, phạm vi ảnh hưởng, hành động sửa, owner. | Bản sao credential hoặc dữ liệu khách hàng không được phép. |

Nên có **cảnh báo tức thời hoặc gần thời gian thực** khi danh tính break-glass được sử dụng, khi thao tác `Decrypt`/`Sign` tăng bất thường, hoặc khi key policy thay đổi. Audit log cần được **bảo vệ khỏi người đang sử dụng đặc quyền**, ví dụ gửi tới kho/tài khoản quản trị tách biệt theo khả năng nền tảng.

**Một sự kiện “break-glass login succeeded” chưa đủ:** tổ chức cần biết **đã làm gì, lên key nào, vì sao và hậu quả gì**. Đồng thời, việc không có log từ một nguồn không chứng minh không có hành động nếu nguồn log đã lỗi hoặc retention không bao phủ.

### 11.1. Mẫu sự kiện đã lọc

~~~json
{
  "eventType": "BREAK_GLASS_KMS_ACTION",
  "incidentRef": "INC-2026-017",
  "actorRef": "recovery-operator-1",
  "approvalRef": "approved-emergency-grant",
  "keyRef": "kms/prod/billing/kek-v4",
  "operation": "DecryptDataKey",
  "scopeRef": "billing-restore-batch-A",
  "result": "ALLOWED_BY_POLICY",
  "policyVersion": "emergency-kms-policy-v2",
  "requestCorrelationId": "opaque-request-id"
}
~~~

Đây chỉ là **dữ liệu minh họa**, không phải audit event thật. Một bản ghi như `ALLOWED_BY_POLICY` không thay chứng cứ KMS thực sự đã cho phép phép toán; cần đối chiếu với provider audit và kết quả tác vụ phục hồi.

## 12. Thực hành định kỳ và mục tiêu khôi phục

Một cơ chế break-glass chưa từng được thử có thể **thất bại đúng lúc cần nhất**. Cần chạy **tabletop exercise** và **drill được phê duyệt** với dữ liệu giả hoặc môi trường được cô lập.

### 12.1. Những điều phải thử

1. Tìm được đúng người trực/approver khi hệ thống nội bộ không dùng được.
2. Xác thực bằng phương thức dự phòng mà không cần bootstrap qua KMS đang lỗi.
3. Kích hoạt được quyền chỉ cho key ID/operation được duyệt.
4. KMS/HSM thực sự thực thi deny đối với key khác, `ExportKey` hoặc thao tác ngoài TTL.
5. Audit và cảnh báo đến nhóm SOC/owner, kể cả khi một vùng giám sát chính lỗi.
6. Dùng được đường khôi phục dữ liệu với wrapped DEK/KEK và phiên bản đúng.
7. Không vô tình bật lại signing key hoặc chứng chỉ đã revoked.
8. Thu hồi quyền và các credential/session còn tồn tại sau khi kết thúc.
9. Thời gian thực tế nằm trong **RTO** và điểm phục hồi đạt **RPO** đã được phê duyệt khi thích hợp.
10. Mọi sai khác so với runbook được ghi và có owner sửa trước kỳ drill tiếp theo.

**Drill không phải lý do để giải mã dữ liệu thật không có phép**. Nên dùng key test chuyên dụng, dữ liệu mô phỏng và môi trường DR tách biệt; khi buộc kiểm tra production, phải phê duyệt phạm vi và biện pháp an toàn đặc biệt.

### 12.2. Gợi ý KPI

| Chỉ số | Ý nghĩa | Lưu ý diễn giải |
| --- | --- | --- |
| **Time to authorized activation** | Thời gian từ trigger được xác thực đến quyền có hiệu lực. | Không tối ưu bằng cách bỏ phê duyệt cần thiết. |
| **Grant TTL compliance** | Mức tuân thủ thời gian cấp quyền và thu hồi. | Kiểm tra session/token thực tế, không chỉ ticket. |
| **Approval separation** | Tỷ lệ lần kích hoạt đủ approvers độc lập/quorum. | Phải kiểm nguồn danh tính có thẩm quyền. |
| **Audit coverage** | Tỷ lệ session/operation được đối chiếu với audit nguồn. | Một event stream thiếu không được tính là an toàn. |
| **Recovery success** | Tỷ lệ drill đạt restore, đúng key version và đúng quyền. | Cần bao gồm negative tests và các trường hợp DR. |
| **Post-incident review completion** | Kết quả hậu kiểm và remediation. | Không đo chỉ số lượng tài liệu đóng ticket. |

Những mục tiêu định lượng phải được thiết lập theo loại khóa, phân loại dữ liệu và nhu cầu hoạt động của tổ chức; không có một TTL/RTO/quorum cố định đúng cho mọi hệ thống.

## 13. Tình huống thực tế: Billing Service mất đường giải mã

**Bối cảnh:** Billing Service dùng **AES-256-GCM** để mã hóa hóa đơn. Mỗi DEK được bọc dưới **billing-kek-v4** trong KMS. Một thay đổi IAM ngoài ý muốn làm ứng dụng production không thể gọi `DecryptDataKey`. Bản mã và wrapped DEK vẫn còn nguyên.

### 13.1. Hướng xử lý đúng

1. **SRE xác nhận lỗi:** lỗi AccessDenied xuất hiện sau đợt thay policy; chưa có bằng chứng key material bị mất.
2. **Incident commander đánh giá:** sự cố ảnh hưởng dịch vụ trọng yếu, đường sửa policy thường lệ không thể hoàn tất kịp theo tiêu chí đã duyệt.
3. **Security approvers xác thực yêu cầu:** giới hạn resource **billing-kek-v4**, tenant/batch bị ảnh hưởng, quyền phục hồi IAM hoặc Decrypt được xác định rõ, TTL ngắn và chủ thể vận hành.
4. **KMS operator kích hoạt quyền:** dùng cơ chế PAM/IAM được hỗ trợ, không xuất KEK hay DEK ra máy của nhân viên.
5. **Billing recovery worker kiểm tra data authorization:** chỉ giải mã tập hóa đơn được phê duyệt, dùng wrapped DEK, encryption context và AAD đúng.
6. **Giám sát trực tiếp:** KMS audit và security monitoring đối soát `DecryptDataKey` theo key ID, actor, kết quả và số lượng yêu cầu.
7. **Khắc phục nguyên nhân:** sửa policy thường trực qua quy trình có thẩm quyền, kiểm tra không mở rộng quyền ngoài ý muốn.
8. **Kết thúc:** thu hồi session khẩn cấp, đối chiếu các bản ghi bị truy cập, xem lại IAM diff, cập nhật runbook và kiểm thử.

### 13.2. Những cách xử lý sai

- **Gắn quyền `kms:*` vào role của mọi service** để các lệnh Decrypt chạy lại.
- Tắt kiểm tra tenant trong Billing Service vì “chỉ dùng để restore”.
- Ghi DEK rõ và toàn bộ hóa đơn vào log để debug vấn đề KMS.
- Khôi phục IAM snapshot cũ làm sống lại signing key hoặc role đã bị revoked.
- Xóa KEK v4 và tạo một KEK mới mà không kiểm tra các DEK vẫn chỉ được bọc dưới v4.

**Kết luận:** Sửa lỗi permission không cần mở toàn bộ kho khóa. Break-glass có thể phục hồi **khả năng hoạt động**, nhưng phải duy trì **ranh giới dữ liệu, chính sách sử dụng khóa và kiểm toán**.

### 13.3. Tình huống khác: private signing key bị lộ

Giả sử Payment Service ký sự kiện bằng S1, còn Ledger Service tin public key S1. Khi private key S1 bị nghi lộ:

- Đội Security có thể cần khẩn cấp **chặn Sign S1** hoặc vô hiệu hóa principal có quyền dùng S1.
- Đội ký tạo/cấp phát S2 theo chính sách; verifier nhận public key S2 từ nguồn tin cậy trước khi chuyển luồng.
- Ledger phải xử lý **chữ ký lịch sử** và nguy cơ chữ ký giả trong thời kỳ S1 bị ảnh hưởng, không đơn thuần chấp nhận mọi chữ ký có `kid=S1`.
- Break-glass không được dùng để **xuất S1** với lý do “điều tra” trừ khi có một quy trình chuyên biệt được đánh giá và cho phép; đa số điều tra có thể dựa trên metadata và audit.
- Sau thu hồi phải xác minh **không còn quyền Sign cũ**, và consumer trust được cập nhật đúng phạm vi.

## 14. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi break-glass là root account dùng thường xuyên | Mất ý nghĩa ngoại lệ; khó phát hiện lạm dụng. | Quy trình riêng, incident binding và cảnh báo mọi lần dùng. |
| Credential khẩn cấp nằm trong hệ thống cần chính nó khôi phục | Không thể truy cập khi outage. | Recovery trust domain độc lập, diễn tập bootstrap. |
| Chia sẻ password/OTP của một account giữa nhiều người | Không chứng minh ai đã thực hiện hành động. | Danh tính cá nhân hoặc cơ chế attribution được thiết kế, vault/PAM. |
| Bỏ qua MFA/approver khi “quá gấp” | Tăng nguy cơ chiếm quyền và insider abuse. | Phương án leo thang dự phòng đã được phê duyệt trước. |
| Một approver cũng là requester | Mất separation of duties. | Phê duyệt độc lập/quorum theo mức rủi ro. |
| Cấp `*` quyền toàn bộ KMS | Có thể giải mã, ký và phá hủy nhiều key ngoài scope. | Scope theo key, action, time, principal và tenant khi có hỗ trợ. |
| Chỉ đặt TTL trong ticket, không kiểm IAM session | Credential thực tế còn hiệu lực. | Thu hồi thực tế và xác minh token/session sau khi kết thúc. |
| Cho phép ExportKey vì muốn phục hồi nhanh | Private key/KEK có thể bị lộ vĩnh viễn. | Dùng HSM/KMS native recovery, wrap/escrow được phê duyệt. |
| Bỏ qua xác thực AEAD tag hoặc data authorization | Có thể chấp nhận dữ liệu giả hoặc đọc sai tenant. | Giữ nguyên quy trình xác thực và kiểm tra quyền trong restore. |
| Khôi phục policy/trust snapshot cũ mà không đối chiếu revoke | Khóa đã lộ được kích hoạt lại. | Reconcile với nguồn revocation có thẩm quyền trước khi dùng. |
| Hủy KEK ngay khi thấy key compromise | Có thể mất khả năng đọc dữ liệu và backup. | Dependency inventory, plan rewrap/re-encrypt, phê duyệt. |
| Rotate KEK mà bỏ qua DEK đã lộ | Bản mã cũ vẫn có nguy cơ giải mã. | Đánh giá thay DEK và re-encrypt theo phạm vi ảnh hưởng. |
| Tắt KMS audit để tăng throughput khi khẩn cấp | Mất bằng chứng và khả năng phát hiện hành động trái phép. | Bảo đảm đường ghi audit độc lập và theo dõi hoạt động. |
| Không dọn quyền/caches sau sự cố | Quyền khẩn cấp trở thành quyền thường trực. | Expiry, revoke, reissue credential và hậu kiểm. |
| Chỉ diễn tập “đăng nhập thành công” | Không biết có thể restore dữ liệu và khóa đúng phiên bản hay không. | Drill toàn chuỗi, negative tests, RPO/RTO. |
| Đưa secret khẩn cấp vào ticket/chat | Rò vật liệu khóa/credential tới nơi ngoài scope. | Lưu tham chiếu và bằng chứng đã lọc, không copy secret. |

## 15. Checklist thiết kế và vận hành break-glass

Trước khi chấp nhận một thiết kế, cần trả lời:

1. **Trigger:** tình huống nào được coi là khẩn cấp, và ai được quyền xác nhận?
2. **Fallback:** đã thử đường khẩn cấp khi IAM/IdP/KMS hoặc vùng triển khai chính gặp lỗi chưa?
3. **Identity:** ai giữ credential; MFA và attribution được thực hiện thế nào?
4. **Approval:** có separation of duties/dual control/quorum phù hợp không?
5. **Scope:** quyền được giới hạn theo key ID, operation, workload, environment và tenant khi nền tảng hỗ trợ chưa?
6. **TTL:** IAM/PAM/session có hết hạn thật và được thu hồi khi kết thúc không?
7. **Recovery material:** nếu HSM/KMS cần backup, phương án có được provider hỗ trợ và thử phục hồi chưa?
8. **Non-exportable:** có ngăn việc xuất private/KEK sai policy không?
9. **Dependencies:** inventory có tìm được wrapped DEK, ciphertext, archive, signing consumers và backups liên quan không?
10. **AEAD/authorization:** ứng dụng vẫn kiểm tra GCM tag, encryption context và quyền đọc dữ liệu chưa?
11. **Trust:** key ký/chứng chỉ đã revoked có bị tái kích hoạt khi restore không?
12. **Audit:** log được bảo vệ ngoài tầm sửa của người dùng quyền khẩn cấp và có cảnh báo kịp thời không?
13. **Destroy:** hành động hủy key có yêu cầu phê duyệt và kiểm kê dữ liệu độc lập không?
14. **Exit:** runbook có bước revoke session, rotate credential, kiểm tra policy và hậu kiểm không?
15. **Drill:** đã kiểm thử cả success path và các trường hợp thất bại trong đúng giới hạn an toàn chưa?
16. **Ownership:** đội nào chịu trách nhiệm cập nhật, thử lại và duyệt ngoại lệ của runbook?

## 16. Câu hỏi tự kiểm tra

1. **Break-glass access** khác quyền IAM thường trực và JIT privilege ở đâu?
2. Vì sao tài khoản khẩn cấp với mọi quyền KMS có thể nguy hiểm hơn thiếu một đường phục hồi được thiết kế tốt?
3. **Dual control/quorum** khác việc một người bấm phê duyệt hai lần như thế nào?
4. Khi IAM chính đang lỗi, cần chú ý gì để credential và cơ chế phê duyệt khẩn cấp vẫn dùng được?
5. Tại sao `Sign`, `Decrypt` và `ExportKey` cần những chính sách khẩn cấp khác nhau?
6. Nếu ứng dụng đã có quyền KMS Decrypt, nó có được phép bỏ kiểm tra quyền tenant trong giai đoạn phục hồi không?
7. **HSM non-exportable key** có thể bị lạm dụng qua Sign/Decrypt API không?
8. Khi KEK v4 bị nghi lộ và còn wrapped DEK trên backup, điều gì cần được đánh giá trước khi destroy?
9. Vì sao một snapshot IAM có tính toàn vẹn nhưng được tạo trước revocation vẫn không nên restore quyền nguyên xi?
10. TTL ghi trong ticket có đủ để bảo đảm quyền khẩn cấp tự mất hiệu lực không?
11. Nếu khóa ký S1 bị lộ, việc chuyển sang S2 có tự xử lý tất cả chữ ký lịch sử hay không?
12. Tại sao audit log nên nằm ngoài miền quyền có thể bị người dùng break-glass sửa?
13. Một drill đăng nhập thành công đã chứng minh đạt RTO và khôi phục đúng key versions chưa?
14. Developer cần hỗ trợ những điểm nào trong ứng dụng để quá trình break-glass không phá vỡ AAD, key usage và phân quyền?
15. Cần thực hiện điều gì ngay sau khi kết thúc một phiên break-glass để tránh quyền khẩn cấp tồn tại lâu dài?
16. Trong tình huống mất đường KMS Decrypt do policy sai, tại sao không nên xuất KEK dạng rõ để giải mã tạm?

**Ghi nhớ:** **Break-glass access** là cơ chế truy cập **được chuẩn bị trước, chỉ dùng khi khẩn cấp, giới hạn quyền và thời gian, có phê duyệt độc lập và kiểm toán chặt chẽ**. Trong quản lý khóa, nó không cho phép bỏ qua **key usage, tenant authorization, xác thực chữ ký/AEAD tag, KMS/HSM custody hoặc dependency inventory**. Cơ chế tốt giúp tổ chức **khôi phục an toàn, cô lập khóa bị lộ, thu hồi quyền và tiếp tục vòng đời khóa** mà không biến tình huống khẩn cấp thành con đường đánh cắp bí mật hoặc hủy dữ liệu.

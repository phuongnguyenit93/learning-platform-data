# Kiểm tra privacy control: Từ yêu cầu quyền riêng tư đến bằng chứng assurance

## 1. Kiểm tra privacy control là gì?

**Kiểm tra privacy control** (*privacy control assessment/testing*) là quá trình đánh giá có hệ thống, dựa trên bằng chứng, xem những biện pháp bảo vệ quyền riêng tư của một tổ chức hoặc hệ thống có **được thiết kế phù hợp, triển khai đúng và vận hành hiệu quả** trong phạm vi được xác định hay không.

Một **privacy control** có thể là biện pháp kỹ thuật, quy trình, quản trị hoặc tổ chức nhằm bảo vệ dữ liệu cá nhân và các quyền/lợi ích riêng tư. Ví dụ:

- Chỉ thu thập trường dữ liệu thực sự cần cho mục đích đã xác định.
- Không dùng dữ liệu cho mục đích mới khi chưa có cơ sở xử lý phù hợp.
- Ghi nhận, thực thi và kiểm chứng việc người dùng rút lại sự đồng ý **khi consent là cơ sở được yêu cầu**.
- Giới hạn thời gian lưu giữ, xóa hoặc hạn chế xử lý đúng theo chính sách và nghĩa vụ có áp dụng.
- Tạo cơ chế tiếp nhận, xác minh, xử lý và phản hồi yêu cầu của chủ thể dữ liệu.
- Kiểm tra việc chia sẻ dữ liệu cho đối tác/nhà cung cấp theo mục đích, phạm vi và điều kiện được phê duyệt.
- Hạn chế dữ liệu cá nhân trong log, analytics, backup, môi trường kiểm thử và bằng chứng bảo mật.
- Kiểm soát khả năng tái nhận diện đối với dữ liệu đã được ẩn danh hóa hoặc giả danh hóa.

Trong module **SECURITY_SECURITY_ASSURANCE**, trọng tâm không chỉ là viết một chính sách quyền riêng tư hoặc triển khai tính năng “Xóa tài khoản”, mà là xây dựng **kết luận có bằng chứng**: một yêu cầu privacy cụ thể dẫn tới control nào, kiểm tra được bằng phương pháp nào, đã quan sát thấy điều gì, còn giới hạn nào, và ai chịu trách nhiệm khắc phục.

> **Nguyên tắc:** “Có trang Privacy Policy”, “đã bật mã hóa” hoặc “đã gửi thông báo consent” không tự động chứng minh các yêu cầu quyền riêng tư đang được đáp ứng. Mỗi kết luận phải gắn với **mục đích, loại dữ liệu, chủ thể, hoạt động xử lý, hệ thống, khoảng thời gian và bằng chứng thích hợp**.

### 1.1. Privacy assurance khác privacy compliance và security assurance thế nào?

| Khái niệm | Câu hỏi cần trả lời | Giới hạn thường gặp |
| --- | --- | --- |
| **Privacy control** | Biện pháp nào bảo vệ một mục tiêu/quyền lợi riêng tư? | Có control không có nghĩa control hoạt động |
| **Privacy compliance** | Hoạt động xử lý có đáp ứng các nghĩa vụ thực sự áp dụng không? | Một checklist pháp lý không tự chứng minh thực thi trong production |
| **Privacy assurance** | Bằng chứng nào tạo cơ sở tin cậy rằng control đạt mục tiêu trong phạm vi? | Phải nêu sai lệch, vùng chưa đánh giá và độ tin cậy |
| **Security assurance** | Bằng chứng nào cho thấy security controls bảo vệ bí mật, toàn vẹn, sẵn sàng và mục tiêu bảo mật khác? | Bảo mật kỹ thuật tốt chưa đủ bảo đảm mọi mục đích xử lý là phù hợp |
| **Privacy impact/risk assessment** | Một hoạt động xử lý tạo rủi ro riêng tư nào và cần biện pháp giảm thiểu gì? | Đánh giá rủi ro dự kiến không thay kiểm tra vận hành |

**Security là thành phần quan trọng của privacy, nhưng privacy rộng hơn security.** Một hệ thống có thể mã hóa dữ liệu và phân quyền đúng mà vẫn thu thập quá nhiều trường không cần thiết, lưu quá lâu hoặc dùng dữ liệu ngoài mục đích được công bố. Ngược lại, một cơ chế thực thi quyền xóa có thể đúng về logic nhưng thiếu kiểm tra phân quyền và vô tình xóa dữ liệu của người khác.

### 1.2. Khi nào nên kiểm tra privacy control?

- Trước khi triển khai sản phẩm/tính năng xử lý dữ liệu cá nhân.
- Khi thay đổi mục đích xử lý, loại dữ liệu, đối tác, vị trí lưu hoặc thời hạn lưu.
- Khi mở rộng analytics, AI, personalization, quảng cáo hoặc dùng dữ liệu thứ cấp.
- Khi ra mắt self-service privacy settings, export, correction hoặc deletion.
- Sau thay đổi consent management, identity, logging, data pipeline hoặc backup.
- Theo kỳ đánh giá dựa trên rủi ro/chuẩn áp dụng.
- Sau sự cố, audit finding, khiếu nại hoặc sai lệch được phát hiện.
- Khi thay đổi nghĩa vụ pháp lý/hợp đồng **đã được xác nhận có áp dụng**.

Không có một tần suất cố định phù hợp với mọi tổ chức. Rủi ro, độ nhạy dữ liệu, quy mô và mức biến động phải quyết định phạm vi và chu kỳ kiểm tra.

## 2. Xác định phạm vi và chuẩn đánh giá trước khi thử nghiệm

### 2.1. Không thể đánh giá “đạt privacy” trong chân không

Một cuộc kiểm tra cần chốt những thông tin tối thiểu:

1. **Bối cảnh hệ thống:** ứng dụng, dịch vụ, vùng triển khai, data store, event bus, nhà cung cấp và chủ sở hữu.
2. **Dữ liệu:** loại dữ liệu cá nhân, độ nhạy cảm, nguồn, người liên quan, nơi lưu và bản sao.
3. **Hoạt động xử lý:** thu thập, tạo, đọc, kết hợp, phân tích, chia sẻ, lưu giữ, xóa hoặc chuyển.
4. **Mục đích:** tại sao từng trường dữ liệu được dùng, mục đích nào đã được phê duyệt.
5. **Yêu cầu áp dụng:** policy, standard, hợp đồng và nghĩa vụ pháp lý trong đúng phạm vi, phiên bản và khu vực liên quan.
6. **Cơ sở xử lý:** lý do/căn cứ được tổ chức xác định cho từng mục đích theo quy tắc áp dụng.
7. **Đối tượng đánh giá:** production, pre-production, data processor, nhóm tài khoản, user journey.
8. **Thời kỳ:** hiện trạng tại một thời điểm hay hiệu quả vận hành trong một khoảng thời gian.
9. **Bằng chứng:** design, configuration, code, test, audit, monitoring và records vận hành.
10. **Giới hạn:** những hệ thống/đường xử lý ngoài phạm vi và phần chưa có bằng chứng.

Một privacy control có thể **đạt** cho đơn hàng ở ứng dụng A nhưng **chưa được xác minh** ở analytics lake hoặc đối tác B. Không suy rộng kết luận ra các hệ thống chưa đánh giá.

### 2.2. Đừng mặc định mọi mục đích đều dựa trên consent

**Consent** (sự đồng ý) chỉ là **một dạng cơ sở hoặc điều kiện xử lý** trong những hệ thống pháp luật/quy tắc có áp dụng. Một hoạt động xử lý có thể có cơ sở hợp lệ khác tùy bối cảnh; và mỗi cơ sở có nghĩa vụ, giới hạn, quyền hoặc ngoại lệ riêng.

Ví dụ minh họa:

- Xử lý địa chỉ giao hàng để thực hiện đơn hàng có thể được đánh giá theo cơ sở/điều kiện liên quan việc cung cấp dịch vụ, tùy quy định áp dụng.
- Gửi quảng cáo cá nhân hóa có thể yêu cầu **sự đồng ý riêng**, tùy đối tượng, khu vực và hoạt động.
- Lưu chứng từ phục vụ một nghĩa vụ bắt buộc có thể cần tiếp tục trong thời hạn luật định dù người dùng yêu cầu xóa các dữ liệu khác.

**Không được tự lập luận** “user đồng ý với mọi thứ” hoặc “user rút consent nên phải xóa tất cả dữ liệu ngay”. Bộ phận phụ trách privacy/legal cần xác nhận căn cứ, quyền và ngoại lệ thực sự áp dụng. Ví dụ kỹ thuật trong bài **chỉ giả định một mục đích quảng bá có yêu cầu consent**, không áp đặt lên mọi loại xử lý.

### 2.3. Gắn tiêu chí với nguồn yêu cầu có hiệu lực

Một mẫu mapping:

| Nguồn yêu cầu | Privacy objective kiểm chứng được | Control | Người chịu trách nhiệm |
| --- | --- | --- | --- |
| Chính sách giảm thiểu dữ liệu | Không thu thập trường ngoài tập được phê duyệt cho đăng ký tài khoản | API schema allowlist, review payload | App/data owner |
| Quy tắc xử lý theo mục đích | Event quảng bá chỉ được tạo/gửi khi điều kiện xử lý hợp lệ | Purpose policy và consent state | Privacy platform/marketing owner |
| Chính sách lưu giữ | Dữ liệu hết hạn được xử lý theo retention schedule và ngoại lệ được quản lý | Retention job, deletion workflow | Data/platform owner |
| Quy trình quyền chủ thể dữ liệu | Request hợp lệ được xác minh, phân loại, xử lý và phản hồi | DSAR workflow, identity verification | Privacy operations |
| Quy tắc chia sẻ dữ liệu | Chỉ chia sẻ đúng trường/đích/phạm vi với nhà xử lý được duyệt | Vendor contract, API/data transfer control | Data owner/vendor owner |
| Quy tắc bảo vệ log | Không đưa dữ liệu cá nhân nhạy cảm không cần thiết vào trace/ticket | Logging filter, access, retention | SRE/security owner |

Các hàng trên là **yêu cầu nội bộ minh họa**. Để đánh giá tuân thủ quy định cụ thể, phải xác nhận **văn bản, phiên bản, nơi áp dụng và nội dung thực tế**, không dùng bảng trên như kết luận pháp lý.

## 3. Đánh giá theo vòng đời dữ liệu

### 3.1. Data inventory và data flow là nền tảng

Một privacy assessment không nên bắt đầu bằng câu “chúng tôi có công cụ quét PII”. Trước tiên cần biết **dữ liệu thực sự đi đâu**.

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Thông tin phục vụ đơn hàng"| API["Orders API"]
    API --> DB[("Orders DB")]
    API --> E["Outbox / Event Bus"]
    E --> M["Marketing Worker"]
    E --> BI["Analytics Pipeline"]
    M --> PARTNER["Delivery Provider"]
    BI --> LAKE[("Analytics Store")]
    API --> LOG[("Audit / Telemetry")]
    DB --> BACKUP[("Backups")]
    REQUEST["Privacy Request"] --> WF["Privacy Workflow"]
    WF --> DB
    WF --> LAKE
    WF --> PARTNER
    WF --> BACKUP
~~~

Sơ đồ nhấn mạnh rằng dữ liệu có thể xuất hiện trong **hệ thống giao dịch, event, analytics, nhà cung cấp, log và backup**. Một request xóa trên Orders DB chưa chứng minh dữ liệu liên quan đã được xử lý trên toàn bộ vòng đời.

Các câu hỏi cần ghi:

- Ai/nguồn nào tạo dữ liệu?
- Dữ liệu là **trực tiếp định danh**, **gián tiếp định danh** hay dữ liệu đã biến đổi?
- Dữ liệu được chuyển tới những nơi nào và vì mục đích gì?
- Có bản sao, cache, indexing, audit, data lake và hệ thống downstream?
- Mỗi nơi có controller/processor/owner thích hợp theo bối cảnh và thỏa thuận?
- Thời hạn lưu, hành động khi hết hạn và ngoại lệ nào đang áp dụng?
- Control nào có thể ngăn hoặc phát hiện sử dụng sai mục đích?

### 3.2. Ma trận privacy controls theo vòng đời

| Giai đoạn | Privacy risk điển hình | Control cần kiểm tra | Bằng chứng hữu ích |
| --- | --- | --- | --- |
| **Thu thập** | Thu quá nhiều, thu không có mục đích rõ | Schema allowlist, collection notice, purpose mapping | API test, data dictionary, UX/notice review |
| **Ghi nhận căn cứ xử lý** | Không phân biệt mục đích hoặc trạng thái consent | Purpose registry, consent evidence/version | Consent events, state machine, test rút consent |
| **Lưu trữ** | Dữ liệu nằm ở nơi không được biết hoặc sai classification | Inventory, access, encryption, location governance | Storage inventory, IAM config, discovery scan |
| **Sử dụng** | Secondary use ngoài mục đích đã xác định | Purpose gate, query policy, data minimization | Code review, negative tests, business approvals |
| **Phân tích** | Re-identification, suy luận quá mức, dùng dữ liệu không phù hợp | Privacy review, aggregation, restriction, PETs | Model/data review, re-identification risk assessment |
| **Chia sẻ** | Gửi sai đối tác, quá nhiều trường, không kiểm soát downstream | Data contract, recipient scope, transfer controls | API payload tests, transfer record, vendor review |
| **Hiển thị/xuất dữ liệu** | Truy cập nhầm người, lộ dữ liệu của tenant khác | Object-level authorization, field masking, export limit | Cross-tenant tests, DLP/authorization review |
| **Truy cập/chỉnh sửa theo yêu cầu** | Giả mạo người yêu cầu hoặc sửa nhầm dữ liệu | Identity verification, scope-based workflow | Request case, authorization tests |
| **Lưu giữ** | Giữ lâu hơn lịch đã phê duyệt | Retention schedule, expiration tags/jobs | Data age report, job run, exception register |
| **Xóa/hạn chế xử lý** | Xóa thiếu bản sao hoặc xóa dữ liệu phải giữ hợp lệ | Deletion/restriction workflow, dependency tracking | Deletion jobs, reconciliation, holds |
| **Backup/khôi phục** | Dữ liệu xóa bị hồi sinh khi restore | Backup lifecycle và post-restore reconciliation | Restore test, tombstone policy, replay controls |
| **Giám sát/audit** | Log chứa PII hoặc chia sẻ cho quá nhiều người | Minimization, RBAC, retention và protected evidence | Log scanning, access review, audit trail |

Mỗi hàng có thể cần nhiều control. **Một control phục vụ một mục tiêu trong một system** không tự bao phủ mọi hệ thống sử dụng cùng loại dữ liệu.

## 4. Những nhóm privacy control cần kiểm chứng

### 4.1. Data minimization – giảm thiểu dữ liệu

Mục tiêu: chỉ thu thập/xử lý/lưu những dữ liệu **thực sự cần** cho mục đích đã xác định.

Kiểm tra:

- Request body có cho phép gửi các trường ngoài schema cần thiết?
- Backend có vô tình lưu toàn bộ payload vào JSON column?
- API trả về trường nhạy cảm không được yêu cầu?
- Analytics/event có gửi raw email, địa chỉ, tên khi chỉ cần ID giả danh?
- Có trường hợp mặc định thu telemetry hoặc tracking không liên quan mục đích?
- Cache, debug log và tracing có giữ bản sao vô tình?

**Test âm:** gửi các thuộc tính không được cho phép trong request và xác nhận hệ thống **không lưu/truyền** chúng. Nếu có chế độ mở rộng schema có kiểm soát, cần test ranh giới rõ.

### 4.2. Purpose limitation – giới hạn mục đích

Dữ liệu được cung cấp cho mục đích A **không tự được dùng cho B**. Đây là control ở cả mức **policy lẫn implementation**.

Ví dụ: số điện thoại giao hàng được lưu để đơn vị vận chuyển liên hệ nhưng không tự được coi là được phép đưa vào danh sách quảng cáo.

Kiểm tra:

- Mỗi use case và data flow có **purpose ID** và người phê duyệt?
- Có cơ sở xử lý/điều kiện hợp lệ cho mục đích đó?
- Code/job/event pipeline có kiểm tra purpose tại thời điểm xử lý phù hợp?
- Marketing worker có nhận dữ liệu không được phép trong event?
- Data lake có ngăn query hoặc export cho mục đích không được duyệt?
- Một mục đích mới có kích hoạt privacy review và cập nhật thông tin minh bạch không?

**Purpose trong header do client gửi** không tự phải được tin. Server phải xác định mục đích theo chức năng, actor, dữ liệu và policy đang hiệu lực.

### 4.3. Transparency – minh bạch thông tin xử lý

Mục tiêu: chủ thể dữ liệu được cung cấp thông tin đúng, rõ và phù hợp về các hoạt động xử lý theo yêu cầu áp dụng.

Kiểm tra:

- Tài liệu/notice có phản ánh **các trường và use case thực tế** không?
- Có phiên bản, ngày hiệu lực và nơi hiển thị liên quan đến thời điểm thu thập?
- Có thay đổi mục đích hay đối tác sau khi notice được ban hành?
- Có ngôn ngữ/UX phù hợp người dùng và ngữ cảnh?
- Những điểm chạm thu thập dữ liệu có hiển thị notice phù hợp?
- Có lịch sử cập nhật và review nội dung với privacy/legal owner?

Một **đường link Privacy Policy** không chứng minh người dùng nhận thông tin phù hợp trước hoặc tại thời điểm cần thiết; cần kiểm tra luồng UX và bản ghi phiên bản.

### 4.4. Consent management – khi consent là yêu cầu

Nếu một hoạt động được tổ chức xác định **phải dựa trên consent**, control cần bảo đảm:

- Consent **được ghi nhận theo mục đích cụ thể**, không dùng một boolean toàn cục vô nghĩa.
- Quy trình thu nhận đáp ứng các điều kiện hợp lệ theo nghĩa vụ áp dụng.
- Có **bản ghi chứng cứ**: subject, purpose, status, thời điểm, nguồn/luồng, notice version và các metadata cần thiết.
- **Không giả định im lặng hoặc dữ liệu có sẵn** là đồng ý.
- User có cách **rút consent** phù hợp, và việc rút được thực thi theo quy tắc thời điểm.
- Những event, queue, job hoặc cache đang chờ không tiếp tục xử lý trái chính sách.
- Không dùng consent cho một mục đích để tự hợp thức hóa một mục đích khác.
- Có quy định rõ xử lý những hành động đã diễn ra hợp lệ trước khi rút consent và nghĩa vụ lưu giữ khác.

**Không phải mọi xử lý dữ liệu cá nhân phải ngừng chỉ vì rút consent** nếu có cơ sở khác được xác nhận áp dụng cho hoạt động độc lập. Ngược lại, không thể tùy tiện đổi tên cơ sở xử lý sau khi user rút consent nhằm tiếp tục mục đích cũ trái quy tắc.

### 4.5. Data subject rights (DSAR) – yêu cầu của chủ thể dữ liệu

Các quyền cụ thể phụ thuộc luật, vai trò và hoàn cảnh. Một privacy program có thể cần xử lý yêu cầu:

- Truy cập hoặc cung cấp bản sao thông tin.
- Chỉnh sửa dữ liệu không chính xác.
- Xóa hoặc hạn chế xử lý trong những điều kiện thích hợp.
- Phản đối một số hoạt động xử lý.
- Rút sự đồng ý khi có thể áp dụng.
- Portability hoặc quyền khác theo nguồn yêu cầu thực sự áp dụng.

Kiểm tra:

1. Nhận diện và **xác minh người yêu cầu** phù hợp, không tiết lộ dữ liệu cho người giả mạo.
2. Xác định scope của dữ liệu, mục đích và hệ thống liên quan.
3. Phân loại yêu cầu, ngoại lệ, giới hạn và nghĩa vụ lưu giữ có áp dụng.
4. Thực hiện ở hệ thống gốc và downstream theo trách nhiệm.
5. Bảo đảm phản hồi đúng đối tượng, không lộ dữ liệu của người khác.
6. Ghi tiến độ, thời hạn được xác nhận, trách nhiệm, kết quả và bằng chứng.
7. Có khả năng xử lý case thất bại, kháng nghị hoặc yêu cầu phức tạp.

**Một nút “Download my data” không chứng minh đầy đủ quyền truy cập** nếu bản tải thiếu dữ liệu thuộc scope, không xem dữ liệu ở processor hoặc vô tình lộ dữ liệu người khác.

### 4.6. Retention và deletion – lưu giữ, xóa, hạn chế xử lý

Control cần có:

- **Retention rule** theo loại dữ liệu và mục đích; kỳ bắt đầu tính được định nghĩa.
- **Tình huống phải giữ** vì yêu cầu bắt buộc, tranh chấp/hợp đồng hoặc hold được phê duyệt.
- **Lịch chạy** và điều kiện xử lý khi dữ liệu hết hạn.
- **Deletion/restriction action** cho mỗi kho và bản sao có liên quan.
- **Reconciliation** giữa request, job, data store và kết quả.
- **Khả năng phục hồi** khi job bị lỗi hoặc một nhà cung cấp không phản hồi.
- **Bằng chứng**, nhưng không lưu toàn bộ dữ liệu đã xóa trong hồ sơ kiểm toán.
- **Chính sách backup** để ngăn dữ liệu đã xóa quay lại sử dụng sau restore.

Xóa có thể là **hard delete, tombstone, crypto-erasure hoặc hạn chế xử lý** tùy kiến trúc và nghĩa vụ. Không tự coi đặt cờ **deleted=true** là xóa thực tế nếu bản ghi vẫn được truy vấn hoặc dùng trong analytics.

### 4.7. Third-party / processor controls

Cần xem nhà cung cấp hoặc bên nhận dữ liệu:

- Có mục đích, điều kiện và phạm vi xử lý được xác định?
- Có thỏa thuận và phân vai phù hợp theo yêu cầu áp dụng?
- Chỉ nhận **trường dữ liệu tối thiểu**?
- Có kiểm soát quyền, retention, subcontractor và cách xử lý sự cố?
- Có quy trình hỗ trợ DSAR/deletion/consent status ở hệ thống downstream?
- Đã xác định vị trí xử lý và yêu cầu chuyển dữ liệu nếu có?
- Có bằng chứng đối chiếu và biện pháp theo dõi khi data flow thay đổi?

Một bản **hợp đồng với vendor** là bằng chứng quản trị nhưng **không tự chứng minh** API gửi đúng tập trường hoặc nhà cung cấp đã xóa bản sao theo yêu cầu.

### 4.8. Privacy-enhancing technologies và giảm khả năng tái nhận diện

Những kỹ thuật như masking, pseudonymization, aggregation, access restriction, tokenization, differential privacy hoặc encryption có thể giúp giảm rủi ro trong bối cảnh phù hợp.

Phân biệt:

- **Pseudonymization/giả danh hóa:** dữ liệu vẫn có thể liên kết lại với người bằng thông tin bổ sung; không tự trở thành dữ liệu không còn liên quan đến người.
- **Anonymization/ẩn danh hóa:** mục tiêu ngăn nhận diện theo giả định, phương pháp và bối cảnh phù hợp; phải đánh giá **re-identification risk** thay vì chỉ xóa tên/email.
- **Hash trực tiếp của email/số điện thoại:** thường vẫn có thể dò bằng từ điển hoặc liên kết; không tự chứng minh ẩn danh.
- **Aggregation:** tập rất nhỏ hoặc nhiều chiều có thể vẫn cho phép suy luận về cá nhân.
- **Differential privacy:** chỉ có ý nghĩa khi cơ chế, privacy parameters, composition/budget và cách áp dụng đúng mục tiêu; không phải chỉ gắn nhãn “DP enabled”.

Bất kỳ kỹ thuật nào cũng cần **security/privacy claim và test** phù hợp, tránh kết luận quá mức.

## 5. Quy trình kiểm tra privacy control từ đầu đến cuối

### Bước 1. Xác định risk scenario, mục tiêu và phạm vi

Ví dụ:

- Asset: dữ liệu đơn hàng, email và số điện thoại.
- Processing: giao dịch đơn hàng và gửi thông điệp quảng bá.
- Privacy risk: dữ liệu được dùng cho quảng bá dù user chưa cho phép hoặc đã rút sự đồng ý, trong phạm vi giả định phải có consent.
- Security/privacy objective: chỉ phát event quảng bá khi có căn cứ và trạng thái consent hợp lệ tại điểm quyết định.
- Scope: Orders API, event queue, marketing worker và nhà cung cấp gửi thông điệp.
- Period: release cụ thể và vận hành sau phát hành.

Ghi **risk owner, privacy owner, data owner, control owner và giới hạn dữ liệu**. Không dùng tên sản phẩm làm mô tả scope duy nhất.

### Bước 2. Lập dữ liệu/hoạt động xử lý và applicability matrix

Đối chiếu data catalog, schema, database, logs, queue, analytics, processor và backup. Tạo ma trận:

| Use case | Data fields | Purpose ID | Điều kiện xử lý | Data destination | Control |
| --- | --- | --- | --- | --- | --- |
| Giao đơn hàng | Tên, địa chỉ giao hàng, thông tin liên lạc cần thiết | ORDER_FULFILLMENT | Theo cơ sở áp dụng được privacy owner xác nhận | Delivery partner đã duyệt | Field minimization, access, transfer |
| Khuyến mại qua email | Email, một số thông tin được phép dùng | PROMOTION_EMAIL | **Giả định yêu cầu consent** | Marketing provider được duyệt | Consent purpose gate, revoke, outbox filter |
| Báo cáo vận hành | Order ID, trạng thái, tổng số tiền | OPS_REPORT | Theo chính sách nội bộ và nghĩa vụ áp dụng | Internal analytics | Aggregation/access/retention |
| Điều tra sự cố | Audit metadata tối thiểu | SECURITY_AUDIT | Theo căn cứ/ngoại lệ đã xác định | Protected log storage | Minimization, RBAC, retention |

Các điều kiện trong ví dụ **không phải kết luận pháp lý** cho mọi nơi. Phải có căn cứ do bộ phận có thẩm quyền xác nhận.

### Bước 3. Chuyển mục tiêu thành security/privacy claims đo được

Ví dụ:

- **MIN-01:** API đăng ký không lưu trường ngoài allowlist theo mục đích đã được phê duyệt.
- **PUR-01:** Marketing event chỉ được phát khi user có consent hiệu lực cho mục đích PROMOTION_EMAIL theo policy áp dụng.
- **PUR-02:** Rút consent làm các dispatch tiếp theo không tiếp tục gửi từ queue trái quy định.
- **RET-01:** Bản ghi đến kỳ retention được xử lý bởi job và được đối chiếu, trừ hold hợp lệ.
- **DSAR-01:** Yêu cầu truy cập của A không trả dữ liệu của B dù biết ID.
- **DSAR-02:** Request xóa được phân loại theo từng hệ thống và ngoại lệ lưu giữ, có trạng thái hoàn tất minh bạch.
- **SHARE-01:** Payload tới provider chỉ gồm các trường được phê duyệt cho purpose và processor đó.
- **LOG-01:** Token, email đầy đủ hoặc trường nhạy cảm không bị đưa vào audit/log nếu không có căn cứ cần thiết.

**Security claim tốt** phải đủ cụ thể để xác định test, scope và kết quả **đạt/không đạt**; không dùng câu “người dùng được tôn trọng quyền riêng tư” làm tiêu chí duy nhất.

### Bước 4. Review thiết kế control

Hỏi:

- Dữ liệu được lưu/truyền đến đâu và lý do?
- Có nơi xử lý bị bỏ qua trong sơ đồ không?
- Quyết định dựa trên **nguồn dữ liệu đáng tin** hay client tự khai?
- Có mục đích và quy tắc xử lý riêng cho từng data flow?
- Race condition, cache, queue và retry có làm trạng thái privacy bị cũ?
- Khi dependency privacy service không hoạt động, hệ thống có **fail safely** với mục đích nhạy cảm?
- Logging, metrics và error handling có tạo bản sao ngoài mong muốn?
- Có cơ chế kiểm soát quyền trên request của chủ thể dữ liệu?
- Có cách kiểm tra bản lưu/backup và processor?
- Có phương án hỗ trợ người dùng hợp lệ và khắc phục tình huống thất bại?

**Design review chỉ chứng minh tính hợp lý của cơ chế dự kiến**, không tự chứng minh các service production đã thực thi.

### Bước 5. Kiểm tra implementation và configuration

Thu thập:

- API contract, DTO, validation, object mapping, database schema.
- Code thực thi purpose/consent/access checks.
- Cấu hình retention scheduler, queue, retry và lifecycle storage.
- IAM, bucket policy, log filtering, access to support tools.
- Vendor integration payload, webhook, data contract.
- Deployment manifest, feature flags, config và artifact version.
- Quy trình approval/DSAR và bản ghi case.

Không chỉ nhìn PR. Cần xác minh **đúng bản build, môi trường và điểm thực thi**; một policy guard ở controller có thể bị bypass bởi worker hoặc API nội bộ.

### Bước 6. Thiết kế behavioral tests – cả positive và negative

Test tối thiểu cho từng claim phải có:

1. **Positive:** dữ liệu/hành động hợp lệ được xử lý đúng.
2. **Negative:** điều kiện không hợp lệ bị từ chối/không xử lý.
3. **Boundary:** thay purpose, role, user, tenant, thời gian, notice version hoặc data type.
4. **Race/retry:** trạng thái đổi giữa khi kiểm tra và khi thực thi.
5. **Failure:** privacy service, database, provider, queue hoặc backup không sẵn sàng.
6. **Cross-system:** dữ liệu downstream chịu cùng điều kiện khi cần.
7. **Audit/privacy:** bằng chứng đủ nhưng không lộ dữ liệu không cần thiết.
8. **Operational:** control còn hoạt động sau deploy hoặc qua khoảng thời gian đánh giá.

Test có thể là unit, integration, end-to-end, config review, data scan, sampled case review, restore exercise và kiểm toán độc lập tùy control. Không dùng một loại test cho tất cả.

### Bước 7. Kiểm tra operating effectiveness

Với privacy control chạy theo sự kiện hoặc theo lịch, cần xem:

- Các consent events và trạng thái hiện hành có đồng nhất không.
- Các marketing dispatch thực tế có tương ứng trạng thái purpose/consent khi thực thi không.
- Retention jobs có chạy đúng lịch và xử lý toàn bộ dữ liệu thuộc scope không.
- DSAR cases có owner, quyết định, bằng chứng xử lý và phản hồi không.
- Deletion failures có được retry và chuyển cấp không.
- Processor có phản hồi/xác nhận yêu cầu downstream đúng phạm vi không.
- Audit event có bảo vệ dữ liệu cá nhân, được truy cập đúng quyền không.
- Những thay đổi sản phẩm gần đây có làm phát sinh data flow chưa được kiểm soát không.

Một lần test PASS không tự chứng minh control **vận hành liên tục**. Khoảng quan sát và cách lấy mẫu phải phù hợp tần suất hoạt động của control.

### Bước 8. Đánh giá bằng chứng và đưa kết luận có giới hạn

Đánh giá **relevance, accuracy, integrity, freshness, coverage, repeatability, independence và protection** của evidence. Gắn:

- Privacy requirement/control IDs và phiên bản.
- Data class, purpose, asset, service, build, environment.
- Test run hoặc record đã kiểm tra.
- Kết quả, sai lệch, phạm vi chưa kiểm tra.
- Người thực hiện/reviewer, thời gian và confidence.
- Các quyết định ngoại lệ, treatment và residual risk.

Kết luận “đạt” phải nêu **trong phạm vi nào**. Trạng thái **chưa đủ bằng chứng** khác **có bằng chứng không đạt**.

### Bước 9. Phân loại finding và quản lý khắc phục

| Gap | Ví dụ | Hành động |
| --- | --- | --- |
| **Requirement/applicability gap** | Chưa xác định mục đích và cơ sở xử lý cho data flow mới | Privacy/legal/data owner xác nhận điều kiện |
| **Design gap** | Kiểm tra consent lúc queue nhưng không kiểm tra khi gửi, dù policy yêu cầu | Sửa kiến trúc và acceptance criteria |
| **Implementation gap** | Worker bỏ qua purpose gate hoặc gửi thêm raw PII | Sửa code, mapping và test |
| **Operating gap** | Retention job dừng chạy, data hết hạn còn lưu | Sửa vận hành, theo dõi và kiểm tra backlog |
| **Evidence gap** | Có xóa dữ liệu nhưng thiếu bằng chứng downstream/backup | Bổ sung reconciliation hoặc kiểm chứng |
| **Ownership gap** | Không ai nhận trách nhiệm xử lý DSAR ở provider | Giao owner, cập nhật hợp đồng/quy trình |
| **Process gap** | Support tự phê duyệt yêu cầu xóa không xác minh identity | Sửa workflow, approval và audit |
| **Scope gap** | Data lake hoặc log còn giữ dữ liệu ngoài mục tiêu | Mở rộng inventory, rules và remediation |

Mỗi finding nên có **ID, yêu cầu, hệ thống, risk scenario, bằng chứng, mức ảnh hưởng, action owner, thời hạn, tiêu chí đóng và retest**. Không hạ yêu cầu privacy chỉ để báo tỷ lệ tuân thủ cao hơn.

### Bước 10. Retest và trigger đánh giá lại

Một finding chỉ nên được đóng khi:

- Fix đã đến **đúng build/môi trường/tập dữ liệu**.
- Kịch bản lỗi ban đầu được kiểm tra lại.
- Các regression tests liên quan đạt.
- Điều kiện vận hành hoặc data migration được xử lý.
- Bằng chứng được gắn và review phù hợp.
- Residual risk/ngoại lệ được quyết định đúng quyền.
- Có trigger/tần suất đánh giá lại.

Các trigger đáng chú ý: thêm SDK tracking, đổi purpose, áp dụng AI/analytics mới, thêm data processor, chuyển vùng lưu trữ, sửa consent library, thay retention hoặc restore từ backup.

## 6. Quy trình đánh giá tổng thể (Mermaid)

~~~mermaid
flowchart TD
    A["Privacy risk / processing purpose"] --> B["Xác nhận requirement, scope, data inventory"]
    B --> C["Map requirement → control → security/privacy claim"]
    C --> D["Review design và data flows"]
    D --> E["Kiểm tra code/config và đường downstream"]
    E --> F["Positive, negative, boundary và failure tests"]
    F --> G["Review evidence + operating effectiveness"]
    G --> H{"Đạt trong phạm vi và bằng chứng đủ?"}
    H -- "Thiếu bằng chứng" --> I["Mở evidence gap và đánh giá bổ sung"]
    I --> G
    H -- "Không đạt" --> J["Finding, risk assessment, owner và remediation"]
    J --> K["Deploy, retest và reconcile downstream"]
    K --> G
    H -- "Đạt" --> L["Kết luận có điều kiện + confidence"]
    L --> M["Theo dõi thay đổi / DSAR / retention / incident"]
    M --> A
~~~

Trong trường hợp có dấu hiệu tiết lộ dữ liệu nghiêm trọng, cần **giảm thiểu và ứng cứu phù hợp ngay** theo quy trình, không đợi toàn bộ ma trận đánh giá hoàn tất.

## 7. Ví dụ xuyên suốt: privacy control cho Orders API và marketing workflow

### 7.1. Bối cảnh và mục tiêu

Giả sử một nền tảng thương mại điện tử dùng **Java/Spring Boot** cho Orders API. Hệ thống có:

- Database đơn hàng, địa chỉ giao hàng, thông tin liên hệ.
- Outbox/event bus cho các sự kiện nghiệp vụ.
- Marketing worker gửi thông điệp khuyến mại qua bên thứ ba.
- Consent management service quản lý quyết định cho mục đích **PROMOTION_EMAIL**.
- Analytics pipeline, support tooling, audit logging và backup.

**Giả định về yêu cầu đã được privacy owner phê duyệt trong bài tập:** marketing email cá nhân hóa chỉ được gửi khi có consent hợp lệ theo purpose PROMOTION_EMAIL; người dùng có thể rút sự đồng ý và mọi dispatch tiếp theo phải tuân theo semantics thời điểm đã định.

Đây là **bối cảnh giả định**, không phải khẳng định mọi marketing đều luôn phải xử lý dựa trên consent.

### 7.2. Privacy claims kiểm chứng được

| Claim ID | Yêu cầu | Kết quả phải chứng minh |
| --- | --- | --- |
| **CONSENT-01** | Không tạo/sử dụng marketing event nếu consent hiện tại không hợp lệ cho PROMOTION_EMAIL | Request sai trạng thái/purpose không được enqueue |
| **CONSENT-02** | Rút consent ngăn dispatch chưa thực hiện theo policy | Worker kiểm tra trạng thái khi gửi, không tin bản snapshot cũ vô hạn |
| **PURPOSE-01** | Consent cho mục đích A không tự cho mục đích B | Test purpose mismatch |
| **MIN-01** | Marketing payload chỉ gồm thông tin được phê duyệt | Không dùng toàn bộ OrderEntity hoặc full customer profile |
| **ACCESS-01** | Actor không được thay consent của user khác trái quyền | Cross-subject negative test |
| **AUDIT-01** | Có evidence của quyết định và thay đổi consent | Actor, purpose, version, time, decision; không log token/PII không cần thiết |
| **SHARE-01** | Provider chỉ nhận dữ liệu hợp lệ theo contract và mục đích | Contract test, payload review, delivery evidence |
| **FAIL-01** | Consent service unavailable không tự dẫn đến gửi marketing trái điều kiện | Failure-mode test, retry/dead-letter process |
| **RET-01** | Marketing artifacts được xử lý theo retention đã duyệt | Job/run và data scan theo scope |

### 7.3. Data flow ở điểm quyết định

~~~mermaid
flowchart LR
    U["User preference"] --> C[("Consent Registry")]
    O["Orders API"] --> P["Purpose Gate"]
    P --> C
    P -->|"Eligible and allowed"| E[("Marketing Outbox")]
    P -->|"Denied/unknown"| X["Do not enqueue; audit"]
    E --> W["Marketing Dispatcher"]
    W --> C
    W -->|"Revalidated"| V["Approved provider"]
    W -->|"Revoked/invalid"| SKIP["Skip / quarantine / audit"]
    W --> LOG[("Protected decision log")]
    O --> LOG
~~~

**Tại sao kiểm tra hai lần?** Consent có thể hợp lệ khi Orders API tạo event nhưng user rút consent **trước khi worker gửi**. Nếu policy yêu cầu các dispatch chưa thực hiện phải dừng, worker cần **revalidate** theo trạng thái cập nhật thay vì tin hoàn toàn vào event cũ.

Tuy nhiên hai lần kiểm tra **không loại bỏ toàn bộ race** giữa lúc worker đọc consent và lúc provider thực sự chấp nhận thông điệp. Hệ thống phải định nghĩa **ranh giới thời điểm và consistency semantics**, quản lý retry, audit và phản hồi từ provider. Nếu yêu cầu mạnh hơn, cần thiết kế cơ chế đồng bộ, invalidation và protocol phù hợp; không tuyên bố hai lệnh kiểm tra tự bảo đảm tính nguyên tử end-to-end.

## 8. Java/Spring Boot minh họa: purpose gate và consent recheck

### 8.1. Phân biệt trusted state và input do client gửi

Một thiết kế nguy hiểm là backend tin payload từ client:

~~~json
{
  "userId": "user-B",
  "purpose": "PROMOTION_EMAIL",
  "consentGranted": true,
  "email": "example@example.com"
}
~~~

Nếu user A có thể tự gửi **consentGranted=true** cho user B, client đang cấp quyền xử lý thay server. Consent phải được quản lý qua **workflow có xác thực, kiểm tra quyền, evidence và trạng thái tin cậy**. Không dùng boolean tự khai trong request gửi đơn hàng để chứng minh consent còn hiệu lực.

### 8.2. Ví dụ service tạo event có giới hạn mục đích

Đoạn Java dưới đây minh họa **control invariant**, không phải chương trình độc lập. Các interface và domain type cần được triển khai phù hợp.

~~~java
@Service
public class MarketingEventApplicationService {
    private static final String PURPOSE = "PROMOTION_EMAIL";

    private final CurrentSubject currentSubject;
    private final SubjectPermission permissions;
    private final ConsentRegistry consents;
    private final MarketingPayloadMapper mapper;
    private final MarketingOutbox outbox;
    private final PrivacyDecisionAudit audit;

    public MarketingEventApplicationService(
            CurrentSubject currentSubject,
            SubjectPermission permissions,
            ConsentRegistry consents,
            MarketingPayloadMapper mapper,
            MarketingOutbox outbox,
            PrivacyDecisionAudit audit) {
        this.currentSubject = currentSubject;
        this.permissions = permissions;
        this.consents = consents;
        this.mapper = mapper;
        this.outbox = outbox;
        this.audit = audit;
    }

    @Transactional
    public UUID queuePromotion(UUID subjectId, OrderSummary order) {
        VerifiedActor actor = currentSubject.requireAuthenticated();

        // Khong tin subjectId hay "consentGranted" client tu khai.
        permissions.requireCanActFor(actor, subjectId);

        ConsentSnapshot state =
                consents.currentFor(subjectId, PURPOSE);

        if (state == null || !state.isCurrentlyValid()) {
            audit.recordDecision(subjectId, PURPOSE, "DENY");
            throw new ProcessingNotPermittedException();
        }

        // Chi dua truong da duoc phe duyet cho muc dich vao event.
        PromotionPayload limited = mapper.toApprovedFields(order);

        UUID eventId = UUID.randomUUID();
        outbox.insert(new PromotionOutboxEvent(
                eventId,
                subjectId,
                PURPOSE,
                state.version(),
                limited));

        audit.recordDecision(subjectId, PURPOSE, "ENQUEUED");
        return eventId;
    }
}
~~~

Giải thích:

1. **CurrentSubject** và **SubjectPermission** cần xác thực và kiểm tra actor thật, không đọc userId tùy ý từ HTTP header.
2. **ConsentRegistry** là trạng thái server-side đáng tin theo **subject + purpose + phiên bản/thời điểm**; phương thức isCurrentlyValid() phải kiểm tra điều kiện policy thực tế.
3. **MarketingPayloadMapper** chỉ tạo các trường đã được phép sử dụng cho mục đích; không serialize toàn bộ OrderEntity.
4. **Outbox** hỗ trợ ghi sự kiện cùng giao dịch database nếu cùng nguồn dữ liệu; tránh phát message tới bên ngoài rồi rollback transaction mà vẫn gửi.
5. **PrivacyDecisionAudit** cần bảo vệ consistency: transaction/outbox/audit phải được thiết kế phù hợp để tránh lưu “đã cho phép” khi commit thất bại hoặc không có audit khi event phát.
6. **Không dùng UUID.randomUUID() như bằng chứng của sự đồng ý**; ID event chỉ hỗ trợ truy vết, còn consent evidence là bản ghi khác.
7. **Trạng thái consent có thể thay đổi** sau khi enqueue, nên dispatcher phải recheck khi policy yêu cầu.

### 8.3. Kiểm tra lại trong dispatcher

~~~java
@Service
public class MarketingDispatcher {
    private static final String PURPOSE = "PROMOTION_EMAIL";

    private final ConsentRegistry consents;
    private final ApprovedMarketingProvider provider;
    private final PrivacyDecisionAudit audit;

    public MarketingDispatcher(
            ConsentRegistry consents,
            ApprovedMarketingProvider provider,
            PrivacyDecisionAudit audit) {
        this.consents = consents;
        this.provider = provider;
        this.audit = audit;
    }

    public void dispatch(PromotionOutboxEvent event) {
        if (!PURPOSE.equals(event.purpose())) {
            audit.recordDecision(event.subjectId(), PURPOSE,
                    "SKIP_WRONG_PURPOSE");
            return;
        }

        ConsentSnapshot state =
                consents.currentFor(event.subjectId(), PURPOSE);

        if (state == null || !state.isCurrentlyValid()) {
            audit.recordDecision(event.subjectId(), PURPOSE,
                    "SKIP_NOT_PERMITTED");
            return;
        }

        // Event, retry, provider callback va revocation timing
        // can co semantics thong nhat voi privacy policy.
        provider.sendApproved(event.payload(), event.idempotencyKey());

        audit.recordDecision(event.subjectId(), PURPOSE, "SENT");
    }
}
~~~

Đây là mã **minh họa**, chưa xử lý đầy đủ lỗi network, retry, cache, transaction boundary, idempotency, duplicate delivery, rate limit, validation của provider, mối liên hệ event–recipient hoặc quy trình thu hồi khi đã gửi.

**Không được mặc định** recheck trước send giải quyết hoàn toàn race giữa việc user rút consent và provider nhận thông điệp. Phải xác định khi nào một dispatch được coi là đã bắt đầu/hoàn tất, cách xử lý các message đang gửi, và thiết kế đảm bảo phù hợp với chính sách. Nếu consent service lỗi, **không sử dụng trạng thái mặc định cho phép** đối với mục đích trong ví dụ yêu cầu consent; có thể trì hoãn/đưa vào queue chờ xử lý và theo dõi.

### 8.4. Ma trận kiểm thử consent và purpose limitation

| Test | Điều kiện | Kết quả kỳ vọng |
| --- | --- | --- |
| User chưa cấp consent | Không có bản ghi hợp lệ cho PROMOTION_EMAIL | Không enqueue marketing event |
| User đã rút consent | Status revoked/withdrawn | Không enqueue; dispatcher không gửi event chưa xử lý theo policy |
| Consent cho mục đích khác | Có consent ANALYTICS nhưng không có PROMOTION_EMAIL | Không cho phép PROMOTION_EMAIL |
| Consent hợp lệ | Đúng subject, purpose, version và điều kiện | Chỉ enqueue payload tối thiểu |
| User A yêu cầu thay consent của B | Không có quyền trên subject B | API từ chối trước khi ghi state |
| User rút consent giữa enqueue và dispatch | Event đang chờ trong outbox | Không tiếp tục dispatch trái semantics đã phê duyệt |
| Consent service unavailable | Không xác minh được state | Không tự gửi do fail-open |
| Nhận webhook retry | Cùng event ID nhiều lần | Không gửi trùng trái yêu cầu; audit rõ |
| Trường dữ liệu thừa | Order có địa chỉ/ghi chú không cần cho marketing | Payload không chứa trường thừa |
| Notice version không phù hợp | Policy yêu cầu review hoặc re-collection | Không tự coi consent cũ hợp lệ |
| Event purpose bị sửa | Purpose lạ hoặc metadata không đáng tin | Bị từ chối hoặc cách ly |
| Cache dữ liệu consent cũ | State đã withdraw nhưng cache còn allow | Không bypass được điều kiện hiệu lực được đặt ra |
| Provider destination sai | Chuyển sang processor chưa được duyệt | Không gửi; phát finding/alert theo policy |
| Log/telemetry | Có deny, enqueue, skip, send | Ghi metadata cần thiết, không raw PII/token |

Những test này cần được nối tới **build, consent policy/version, data fixture, environment, thời điểm và reviewer**. Một unit test với mocked ConsentRegistry không thay thế integration test của registry, outbox và dispatcher trong môi trường thực tế.

## 9. Kiểm tra quyền truy cập và xóa dữ liệu (DSAR/erasure)

### 9.1. Một request “xóa dữ liệu” không phải một lệnh DELETE đơn giản

Một yêu cầu xóa có thể liên quan nhiều hệ thống và nghĩa vụ khác nhau:

1. **Xác minh người yêu cầu** đúng tài khoản và không lộ dữ liệu của người khác.
2. **Xác định dữ liệu thuộc scope:** đơn hàng, hồ sơ, consent events, analytics, cache, processor, backup.
3. **Phân loại điều kiện:** dữ liệu nào có thể xóa, dữ liệu nào cần hạn chế xử lý, dữ liệu nào phải giữ theo căn cứ đã xác nhận.
4. **Lập kế hoạch xử lý** theo data owner, system owner và processor.
5. **Thực thi và đối chiếu** kết quả xóa/hạn chế ở hệ thống gốc và downstream.
6. **Ngăn dữ liệu được tạo lại** qua replay event, restore backup hoặc sync ngược.
7. **Phản hồi đúng người yêu cầu** theo quy trình/thời hạn có áp dụng.
8. **Lưu bằng chứng tối thiểu**, có bảo vệ, không tái tạo hồ sơ cá nhân vừa xóa.

Không nên khẳng định user có quyền tuyệt đối xóa mọi chứng từ trong mọi trường hợp; bộ phận privacy/legal phải xác định **nghĩa vụ lưu giữ và ngoại lệ hợp lệ**.

### 9.2. State machine cho erasure request

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> IDENTITY_CHECK
    IDENTITY_CHECK --> REJECTED: Người yêu cầu không hợp lệ
    IDENTITY_CHECK --> SCOPED: Xác minh hợp lệ
    SCOPED --> ASSESS_RETENTION
    ASSESS_RETENTION --> APPROVED: Thuộc phạm vi xử lý
    ASSESS_RETENTION --> RESTRICTED_WITH_REASON: Phải hạn chế/giữ theo căn cứ áp dụng
    APPROVED --> PROCESSING
    PROCESSING --> RECONCILING
    RECONCILING --> COMPLETED: Các bước cần thiết đạt
    RECONCILING --> PARTIAL: Một hoặc nhiều hệ thống chưa xác minh
    PARTIAL --> PROCESSING: Khắc phục / retry
    RESTRICTED_WITH_REASON --> NOTIFIED
    COMPLETED --> NOTIFIED
    REJECTED --> NOTIFIED
    NOTIFIED --> [*]
~~~

Không tự chuyển sang **COMPLETED** chỉ vì một database trả HTTP 200 hoặc đã xóa dòng gốc, khi những hệ thống downstream cần xử lý vẫn chưa có kết quả.

### 9.3. Test matrix cho quyền chủ thể dữ liệu

| Kịch bản | Kết quả kiểm chứng |
| --- | --- |
| A yêu cầu dữ liệu của A | Chỉ cung cấp đúng phần dữ liệu A có quyền nhận theo phạm vi |
| A yêu cầu dữ liệu của B | Từ chối và không lộ dữ liệu B |
| Tài khoản bị nghi compromise yêu cầu xóa | Đòi hỏi xác minh và xử lý rủi ro theo policy |
| Request hợp lệ có bản sao analytics | Các hệ thống thuộc phạm vi nhận action và có reconciliation |
| Có dữ liệu cần giữ theo nghĩa vụ | Được phân loại, hạn chế/giữ với lý do và trách nhiệm phù hợp |
| Downstream processor timeout | Request chuyển trạng thái chờ, retry/chuyển cấp; không báo hoàn tất giả |
| Request lặp lại | Xử lý idempotent, không tạo xóa sai hoặc ghi trùng không kiểm soát |
| Data restore từ backup cũ | Không tái sử dụng dữ liệu lẽ ra phải xóa/hạn chế trái policy |
| Job xóa hoàn tất | Có evidence tối thiểu ở đúng scope, không lưu lại raw PII trái mục tiêu |
| Người yêu cầu rút/cập nhật request | Workflow xử lý theo policy và trạng thái thực tế |
| Response gửi sai email/subject | Không tiết lộ dữ liệu cho người không được xác minh |
| Exception hết hạn | Được xem xét lại, không tự giữ dữ liệu vô thời hạn |

### 9.4. Backup và dữ liệu được phục hồi

Dữ liệu trong backup có thể không hỗ trợ xóa từng bản ghi ngay lập tức. Privacy assurance cần xem **thiết kế bảo vệ và thời hạn thực tế**, bao gồm:

- Backup có thời hạn lưu, bảo vệ quyền, encryption và quy tắc không sử dụng ngoài mục đích phục hồi.
- Điều kiện restore, quyền người thực hiện, môi trường restore và audit.
- Có cơ chế **deletion ledger/tombstone** hoặc reconciliation để ngăn dữ liệu đã xóa trở lại trạng thái sử dụng không phù hợp sau phục hồi.
- Các bản sao được đánh giá theo nghĩa vụ áp dụng, không tự xác định rằng backup được miễn mọi yêu cầu xóa.
- Có test restore kiểm tra privacy state và data deletion semantics, không chỉ kiểm tra dữ liệu nghiệp vụ phục hồi thành công.

**Privacy deletion và backup recoverability là hai yêu cầu cần được thiết kế cùng nhau**, không phải xem riêng từng đội.

## 10. Kiểm tra minimization, logging và analytics

### 10.1. Test minimization trên API và dữ liệu lưu

Một bài test có thể:

1. Gửi request hợp lệ với dữ liệu cần thiết và **trường thừa** không được phê duyệt.
2. Xác minh API từ chối trường thừa hoặc bỏ qua mà **không lưu/truyền**.
3. Query database, outbox, cache và audit trong phạm vi để kiểm tra trường không xuất hiện.
4. Kiểm tra response và các bản ghi analytics; chỉ xuất những trường được phép.
5. Thử các biến thể JSON nested, optional fields và serializer.
6. Lưu kết quả dưới dạng assertion/metadata, không chứa raw PII thật.

Không thể kết luận “đã minimization” chỉ vì DTO có ít trường nếu logging middleware lưu **toàn bộ request body** trước khi mapping.

### 10.2. Log, trace và dữ liệu gỡ lỗi

Rủi ro:

- Access log chứa query string có email, token hoặc dữ liệu cá nhân.
- Exception ghi toàn bộ user record hoặc request body.
- APM, profiling, crash dump và telemetry gửi PII tới dịch vụ thứ ba.
- Debug mode/feature flag không được tắt sau sự cố.
- Evidence từ test dùng dữ liệu thật được chia sẻ quá rộng.

Control kiểm tra:

- **Field-level logging policy**, redaction và allowlist.
- Pseudonymous IDs khi đủ phục vụ điều tra.
- Giới hạn truy cập, retention, encryption và audit view.
- Test cố ý tạo lỗi với **canary/synthetic sensitive marker** rồi kiểm tra log/trace/queue.
- Giám sát thay đổi cấu hình làm logging tăng độ chi tiết.
- Quy trình trích xuất log cho incident không tạo bản sao không kiểm soát.

**Không lưu log toàn bộ payload “để có bằng chứng”**; evidence phải thỏa cả an ninh lẫn privacy.

### 10.3. Analytics và rủi ro tái nhận diện

Ví dụ một pipeline bỏ tên/email nhưng vẫn chứa tổ hợp thời gian, vị trí chi tiết, đơn hàng hiếm và device ID. Các trường này có thể cho phép liên kết với người cụ thể.

Kiểm tra:

- Có cần dữ liệu ở cấp cá nhân hay có thể aggregate?
- Join keys có tạo khả năng nhận diện khi kết hợp dataset khác?
- Có kịch bản re-identification hợp lý theo threat model?
- Dữ liệu phân tích có mục đích và thời hạn riêng?
- Những người nhận truy vấn được giới hạn ra sao?
- Các lớp masking/pseudonymization có tương ứng claim thực tế?

**Không có một công thức chung** bảo đảm dữ liệu đã trở thành anonymous chỉ vì đã xóa hai trường trực tiếp định danh. Kết luận phải dựa trên phương pháp, context và khả năng liên kết thực tế.

## 11. Kiểm tra bên thứ ba, chia sẻ và thay đổi data flow

### 11.1. Vendor assessment không chỉ là xem hợp đồng

Một bộ hồ sơ đánh giá có thể gồm:

| Đối tượng | Câu hỏi và bằng chứng |
| --- | --- |
| **Mục đích** | Vendor nhận dữ liệu để làm gì, có được phê duyệt cho mục đích đó không? |
| **Tập trường** | Data contract và payload có được giảm thiểu đúng không? |
| **Phạm vi** | Vendor xử lý cho sản phẩm, vùng và nhóm người dùng nào? |
| **Access** | Những tài khoản, service, subprocessors nào có quyền? |
| **Retention** | Có hạn lưu, delete/reconciliation và điều kiện backup? |
| **DSAR** | Có khả năng hỗ trợ yêu cầu hợp lệ và trả evidence? |
| **Sự cố** | Có quy trình báo cáo, phối hợp và phản ứng theo thỏa thuận? |
| **Bằng chứng** | Test payload, audit, báo cáo, attestation có đúng scope và đủ mới? |
| **Thay đổi** | Vendor thêm subprocessor, chuyển vùng hoặc mở mục đích sẽ kích hoạt review nào? |

Có thể tồn tại các yêu cầu riêng đối với **chuyển dữ liệu xuyên biên giới**, nhưng không được giả định một cơ chế/điều kiện áp dụng cho mọi quốc gia. Privacy/legal cần đánh giá nghĩa vụ thực tế và cập nhật control mapping.

### 11.2. Contract test của payload

Ví dụ marketing provider chỉ cần **recipient token và template parameters tối thiểu**, không cần toàn bộ địa chỉ giao hàng. Test cần kiểm tra:

- JSON schema không chứa các trường ngoài allowlist.
- Không dùng raw OrderEntity làm payload.
- Webhook callback chỉ chứa reference ID cần thiết.
- Có ràng buộc recipient và purpose.
- Retry và dead-letter queue không lưu raw PII quá hạn hoặc sai quyền.
- Provider metadata/logs được quản lý theo mục đích và retention đã duyệt.

Một report “API trả 200” chỉ chứng minh một request được nhận xử lý ở mức giao thức; nó **không chứng minh dữ liệu được xử lý đúng privacy purpose hoặc đã bị xóa ở downstream**.

## 12. Bằng chứng: tiêu chí tin cậy và kỹ thuật đánh giá

### 12.1. Các lớp bằng chứng

| Loại | Ví dụ | Điều không thể tự suy ra |
| --- | --- | --- |
| **Governance** | Privacy policy, retention schedule, data owner approval | Production đã làm đúng |
| **Design** | DFD, threat/privacy risk model, DPIA/PIA, data contract | Code đã triển khai đầy đủ |
| **Implementation** | Code review, policy-as-code, schema, IAM config | Control đã vận hành đúng suốt kỳ |
| **Behavioral test** | Consent negative tests, DSAR cross-account, deletion reconciliation | Bao phủ mọi data flow ngoài test |
| **Operational** | Consent events, job logs, DSAR case samples, processor receipts | Không có lỗi ngoài phần đã quan sát |
| **Independent review** | Audit, assessment từ bên độc lập | Kết luận tự động mở rộng đến mọi hệ thống |
| **Remediation** | PR, deploy record, retest, risk decision | Ticket Done không thay evidence retest |

Một assessment tốt xem xét **mối liên hệ giữa các lớp**. Ví dụ:

**Notice version → consent evidence → purpose gate code → event/dispatch test → production decision logs → reviewer conclusion.**

Nếu một mắt xích không có, cần xác định đó là **evidence gap** hay **control gap**, không tự điền trạng thái “PASS”.

### 12.2. Chất lượng evidence

Đánh giá:

- **Relevance:** có trả lời đúng privacy claim không?
- **Completeness:** data flow/subject/purpose/processor nào trong phạm vi?
- **Correctness:** expected và observed có nhất quán?
- **Freshness:** có đúng build, policy version, data contract và kỳ hoạt động?
- **Integrity:** evidence có nguồn, không sửa đổi tùy ý?
- **Repeatability:** có thể tái chạy/tái dựng với dữ liệu thử phù hợp?
- **Independence:** người đánh giá có đủ độc lập theo rủi ro?
- **Protection:** evidence có bản thân tạo privacy risk không?
- **Traceability:** link requirement–control–test–finding–action–retest có rõ?

Đối với privacy assurance, thuộc tính **protection** đặc biệt quan trọng: hồ sơ test hoặc audit không được trở thành một kho dữ liệu cá nhân vượt quá mục đích.

### 12.3. Data fixture và privacy-safe testing

Nên ưu tiên:

- **Synthetic test data** đủ đại diện cho schema và edge cases.
- Canary markers không mang dữ liệu cá nhân thật để kiểm tra rò qua log/queue.
- Dữ liệu đã được kiểm soát, che hoặc giảm mức nhạy cảm khi phải đánh giá vấn đề gần thực tế.
- Tài khoản và consent trạng thái giả lập có kiểm tra quyền rõ ràng.
- Không tải dữ liệu production vào laptop/dev environment chỉ để test.
- Có thời hạn lưu và phương án xóa dữ liệu test.
- Quy trình cấp quyền đặc biệt khi cần dùng dữ liệu thực, đánh giá rủi ro và lưu evidence tối thiểu.

**Synthetic data** vẫn cần được thiết kế cẩn thận để mô phỏng trường hợp xử lý thật; một tập test quá đơn giản có thể bỏ qua dữ liệu nested, delayed events hoặc multi-tenant.

### 12.4. Lấy mẫu privacy control

Nếu không thể đánh giá mọi bản ghi:

1. Xác định **population**: số yêu cầu DSAR, số job xóa, số marketing event, số processor, số data store.
2. Nêu **kỳ**, cách chọn mẫu, rủi ro và quy mô mẫu.
3. Bao gồm trường hợp **edge, exception, failure và change**.
4. Phân biệt test một lần với lấy mẫu vận hành theo khoảng thời gian.
5. Không gọi kết quả của mẫu nhỏ là đại diện thống kê nếu không thiết kế phương pháp phù hợp.
6. Tăng cường kiểm tra với dữ liệu nhạy cảm, đối tác mới hoặc hệ thống từng có finding.

Ví dụ kiểm tra **20/200 yêu cầu DSAR**, tất cả đạt, chỉ hỗ trợ kết luận trong phạm vi mẫu và giả định đã ghi; không tự chứng minh 180 yêu cầu còn lại hoàn toàn đúng.

## 13. Quy trình DPIA/PIA và vị trí của control testing

**Privacy Impact Assessment (PIA)** hoặc **Data Protection Impact Assessment (DPIA)** là cách đánh giá rủi ro/ảnh hưởng quyền riêng tư, có thể bắt buộc trong những điều kiện pháp lý cụ thể. Tên, thời điểm, tiêu chí và nghĩa vụ khác nhau theo phạm vi áp dụng.

Một đánh giá tác động thường giúp:

- Mô tả xử lý và mục đích.
- Nhận diện loại dữ liệu, nhóm chủ thể và mức nhạy cảm.
- Phân tích necessity/proportionality trong phạm vi yêu cầu.
- Xác định risk scenario và tác động với người liên quan.
- Lựa chọn control giảm rủi ro.
- Ghi quyết định, owner, residual risk và kế hoạch theo dõi.

**Kiểm tra privacy control** sau đó xác minh rằng những biện pháp nêu trong PIA/DPIA **đã thực sự được triển khai và hoạt động**, với bằng chứng phù hợp. Không coi việc đã ký DPIA/PIA là kết quả cuối cùng khi phần triển khai còn thay đổi.

Ví dụ:

| Privacy risk trong assessment | Biện pháp đề xuất | Kiểm tra sau triển khai |
| --- | --- | --- |
| Analytics có thể tái nhận diện user | Giảm trường, giới hạn join và truy cập | Schema/permissions review, test liên kết |
| Marketing dùng dữ liệu sai purpose | Consent purpose gate | Negative tests, revoke/queue tests, operational sample |
| Xóa dữ liệu không tới provider | DSAR orchestration | End-to-end case, processor receipt/reconciliation |
| Retention không nhất quán | Lifecycle rules và owner | Job run, data age scan, exceptions |
| Support có thể xem quá nhiều hồ sơ | Scoped access và masking | Role/resource test, audit review |

Trong trường hợp rủi ro tồn đọng cao, phải chuyển cấp đúng thẩm quyền trước khi triển khai nếu quy tắc áp dụng yêu cầu.

## 14. Đo hiệu quả privacy controls bằng KPI/KRI

| Chỉ số | Điều phản ánh | Không nên suy ra |
| --- | --- | --- |
| **Purpose mapping coverage** | Data flow thuộc phạm vi có purpose và owner rõ | Mọi hoạt động đều hợp lệ |
| **Minimization coverage** | API/event được kiểm tra không truyền trường thừa theo rule | Toàn bộ dữ liệu cá nhân đã được giảm thiểu |
| **Consent decision correctness in tested cases** | Các test trạng thái/purpose/revoke đạt | Không có race ngoài phạm vi test |
| **DSAR verified completion** | Case đã xử lý với bằng chứng phù hợp trong scope | Có thể đáp ứng mọi quyền trong mọi bối cảnh |
| **DSAR overdue or exception age** | Các case chậm/có ngoại lệ cần theo dõi | Thời gian xử lý tự nó thể hiện tính hợp lệ |
| **Retention job completion** | Job chạy và xử lý các đối tượng đến hạn trong scope | Không có bản sao ngoài scope |
| **Downstream reconciliation rate** | Tỷ lệ tác vụ xử lý được xác nhận ở hệ thống mục tiêu | Email xác nhận từ vendor tự chứng minh mọi bản ghi |
| **PII in logs findings** | Kết quả quét/log review phát hiện dữ liệu không phù hợp | Không có finding nghĩa là không có rò |
| **Vendor/privacy review currency** | Data processors có đánh giá trong kỳ được xác định | Hợp đồng đủ chứng minh thực thi |
| **Privacy control evidence freshness** | Bằng chứng tương ứng build/version hiện hành | Có file test nghĩa là control đạt |
| **Repeat findings** | Gap đã xử lý nhưng tái diễn | Cần đánh giá nguyên nhân gốc và phạm vi |
| **Verified remediation time** | Từ phát hiện đến retest đạt | Ticket Done là đủ |
| **High-risk processing unassessed** | Những hoạt động rủi ro cao chưa đủ evidence | Không được lẫn vào nhóm compliant |

**Ví dụ giả định:** trong 30 data flows thuộc scope, 21 flow đã được kiểm tra đủ bộ yêu cầu và evidence được review, 5 flow đang xử lý và 4 flow chưa đánh giá. **Coverage = 21/30 = 70%** đối với việc kiểm chứng, **không có nghĩa tổ chức bảo vệ quyền riêng tư được 70%**. Bốn flow chưa đánh giá có thể là những flow rủi ro cao nhất.

### 14.1. Không dùng tỷ lệ PASS che lỗi nghiêm trọng

Nếu 99 test consent đạt nhưng một test cho phép marketing worker tiếp tục gửi sau khi rút sự đồng ý theo điều kiện phải dừng, cần xem **impact, số người có thể bị ảnh hưởng và thời gian phơi nhiễm**, không chỉ báo “99% PASS”.

Tương tự, một request xóa dữ liệu đã được xử lý trên 8/9 hệ thống nhưng hệ thống thứ chín giữ toàn bộ hồ sơ nhạy cảm có thể chưa thỏa tiêu chí đóng. Phải kết luận theo **requirement và risk**, không lấy trung bình không có ý nghĩa.

## 15. Ngoại lệ, residual privacy risk và các quyết định khó

### 15.1. Ngoại lệ phải phân biệt với nghĩa vụ bắt buộc

Một team có thể đề nghị ngoại lệ vì dữ liệu cũ chưa thể xóa, provider chưa hỗ trợ hoặc tính năng logging còn lưu trường nhạy cảm. Nhưng:

- Ngoại lệ chỉ hợp lệ khi có **thẩm quyền, phạm vi và căn cứ phù hợp**.
- Phải có **risk owner**, thời hạn, control bù trừ, mốc xử lý và kế hoạch đánh giá lại.
- Phải xác định rõ những nghĩa vụ bắt buộc **không thể miễn trừ bằng quyết định nội bộ**.
- Trạng thái **Exception approved** không bằng **Control effective**.
- Bằng chứng phải cho thấy control bù trừ thực sự giảm rủi ro trong scope.

Ví dụ, khi một data lake chưa thể xóa ngay bản ghi theo cơ chế hiện tại, tổ chức có thể xem **hạn chế truy cập/xử lý tạm thời** nếu được pháp lý và quản trị cho phép, đồng thời có kế hoạch chuyển sang xử lý đúng; không được tự tuyên bố yêu cầu xóa đã hoàn tất.

### 15.2. Trạng thái kết luận đáng tin

| Trạng thái | Ý nghĩa |
| --- | --- |
| **Effective in assessed scope** | Có bằng chứng đủ phù hợp cho requirement đã đánh giá |
| **Partially effective** | Một phần đạt, còn sai lệch hoặc phần chưa được kiểm chứng |
| **Ineffective** | Có bằng chứng control không đáp ứng mục tiêu quan trọng |
| **Insufficient evidence** | Chưa đủ căn cứ kết luận đạt hay không |
| **Approved exception with residual risk** | Chưa đáp ứng đầy đủ nhưng có quyết định có điều kiện và theo dõi |
| **Not applicable with rationale** | Có căn cứ chính thức một requirement không áp dụng trong scope |

**Insufficient evidence** không đồng nghĩa “không có lỗi”, cũng không tự đồng nghĩa “đã vi phạm”. Tùy mức rủi ro, có thể cần giới hạn xử lý tạm thời hoặc tăng giám sát trước khi có kết luận.

### 15.3. Khi có nghi ngờ privacy incident

Nếu phát hiện dữ liệu bị chia sẻ trái phạm vi, ghi log không phù hợp hoặc có sự cố deletion, cần:

1. Xác minh và giảm thiểu tiếp diễn.
2. Bảo toàn bằng chứng ở mức tối thiểu, an toàn.
3. Đánh giá loại dữ liệu, số người/phạm vi, thời gian và các bên nhận.
4. Phối hợp incident response, privacy/legal và risk owner theo trách nhiệm.
5. Xác định nghĩa vụ thông báo hoặc hành động bắt buộc **thực sự có áp dụng**.
6. Sửa control, retest và theo dõi rủi ro còn lại.
7. Cập nhật data flow, policy, test plan và bài học.

Một audit finding không tự đồng nghĩa incident đã xảy ra; nhưng một privacy incident có thể làm lộ **design gap, operating gap hoặc thiếu bằng chứng** cần giải quyết.

## 16. Quản trị và RACI của privacy assurance

| Vai trò | Trách nhiệm | Không tự suy |
| --- | --- | --- |
| **Privacy/data protection owner** | Xác định mục tiêu và yêu cầu privacy, điều phối review | Không tự chứng minh production đã áp dụng |
| **Data owner** | Xác định mục đích, classification, phạm vi chia sẻ, retention theo thẩm quyền | Không tự miễn trừ nghĩa vụ bắt buộc |
| **Legal/compliance** | Xác nhận nghĩa vụ và cơ sở xử lý thực sự áp dụng | Không thay thế test kỹ thuật |
| **Application/control owner** | Enforce purpose, minimization, access, deletion và evidence | Không có quyền chấp nhận mọi rủi ro |
| **Platform/SRE/engineering** | Vận hành data pipelines, logs, retention jobs, processor integration | Health check không chứng minh toàn bộ privacy control |
| **DSAR/privacy operations** | Tiếp nhận, xác minh, điều phối, theo dõi và phản hồi request | Không được tùy ý cấp dữ liệu cho người chưa xác minh |
| **Risk owner** | Quyết định xử lý residual risk trong thẩm quyền | Không thay review technical/privacy |
| **Assurance reviewer/auditor** | Kiểm tra bằng chứng, nêu kết luận, phát hiện và giới hạn | Không tự động chịu trách nhiệm sửa control |
| **Vendor/processor owner** | Quản lý data contract, đối tác và bằng chứng downstream | Không mặc định hợp đồng đã kiểm chứng thực thi |

Một RACI **minh họa** (*R: thực hiện, A: chịu trách nhiệm cuối cùng, C: tham vấn, I: thông báo*):

| Hoạt động | Privacy owner | Data owner | App/platform owner | Risk owner | Assurance |
| --- | --- | --- | --- | --- | --- |
| Xác định policy và mục tiêu privacy | **A/R** | C | C | C | C |
| Phê duyệt purpose/data fields trong quyền của data owner | C | **A/R** | C | C | I |
| Triển khai privacy controls | C | C | **A/R** | I | C |
| Điều phối DSAR cross-system | **A/R** | C | R | C | C |
| Thu thập test và runtime evidence | C | C | **A/R** | I | C |
| Đánh giá assurance độc lập khi cần | C | C | C | I | **A/R** |
| Chấp nhận residual risk thuộc quyền được giao | C | C | C | **A/R** | I |
| Khắc phục gap kỹ thuật và retest | C | C | **A/R** | C | C |

RACI phải điều chỉnh theo quy chế tổ chức. Có thể có nhiều người thực hiện nhưng cần nhận diện rõ **chủ thể chịu trách nhiệm và cấp phê duyệt** cho từng quyết định.

## 17. Mẫu kế hoạch kiểm tra và hồ sơ đánh giá

Dưới đây là YAML **giả định** mô tả một cuộc kiểm tra privacy controls. Không dùng nó làm chứng nhận compliance hay evidence production:

~~~yaml
assessment_id: "PRIVACY-CONTROL-DEMO-010"
service: "orders-api"
module: "SECURITY_SECURITY_ASSURANCE"
title: "Kiem tra privacy control"
assessment_scope:
  business_process: "Order fulfillment and promotional messages"
  environments:
    - "integration"
  systems:
    - "orders-api"
    - "consent-registry"
    - "marketing-dispatcher"
  excluded:
    - "production runtime evidence"
    - "vendor data deletion verification"
requirement_basis:
  policy_ref: "POL-PRIVACY-DEMO"
  standard_ref: "STD-DATA-PROCESSING-DEMO"
  version: "draft-1.0"
  lawful_basis_review: "PENDING_PRIVACY_OWNER"
controls:
  - id: "CTRL-PURPOSE-01"
    objective: "Marketing event only when processing permitted"
    tests:
      - "No-consent and wrong-purpose"
      - "Withdraw-before-dispatch"
      - "Consent service unavailable"
  - id: "CTRL-MIN-01"
    objective: "No unnecessary PII in marketing payload"
    tests:
      - "Field allowlist and nested fields"
      - "Error/log redaction"
  - id: "CTRL-DSAR-01"
    objective: "Access and erasure cases scoped to verified subject"
    tests:
      - "Cross-subject negative test"
      - "Downstream reconciliation"
evidence:
  design_review: "PENDING"
  implementation_review: "NOT_VERIFIED"
  operating_review: "NOT_VERIFIED"
  test_run_refs: []
  reviewer: null
assessment_result:
  conclusion: "INSUFFICIENT_EVIDENCE"
  confidence: "LOW"
  known_limitations:
    - "No production evidence"
    - "No vendor deletion receipt"
findings: []
risk_owner: "Orders Product Owner"
control_owner: "Orders Platform Technical Owner"
next_action: "Validate applicability and execute test plan"
exception:
  approved: false
  approval_ref: null
~~~

Trạng thái **PENDING/NOT_VERIFIED/INSUFFICIENT_EVIDENCE** là có chủ ý. Đối với cuộc đánh giá thật, cần điền test run, expected/actual, scope, policy revision, người review, tình trạng data stores và quyết định của cấp có quyền.

### 17.1. Mẫu finding record

| Trường | Nội dung |
| --- | --- |
| **Finding ID** | Định danh ổn định |
| **Requirement / control** | Chính sách/tiêu chí nào không được chứng minh hoặc không đạt |
| **Affected processing** | Purpose, dataset, service, processor và môi trường |
| **Evidence** | Test ID, sample, log/record tham chiếu, thời điểm |
| **Gap type** | Design, implementation, operation, evidence, ownership hoặc applicability |
| **Risk assessment** | Loại dữ liệu, số người, khả năng/tác động, độ chắc chắn |
| **Treatment** | Sửa, hạn chế xử lý, giảm thiểu, ngoại lệ hợp lệ hoặc chuyển cấp |
| **Action owner / due date** | Người thực hiện và mốc |
| **Closure criteria** | Những test/reconciliation và phê duyệt cần đạt |
| **Retest result** | Build, môi trường, reviewer và kết luận sau sửa |
| **Residual risk decision** | Người quyết định, phạm vi, điều kiện và thời hạn |

Không đưa raw PII, consent secret, token hoặc toàn bộ yêu cầu khách hàng vào finding khi có thể dùng mã tham chiếu và evidence được bảo vệ.

## 18. Các sai lầm phổ biến khi kiểm tra privacy control

### 18.1. Kiểm tra “có Privacy Policy” rồi kết luận đạt

**Vấn đề:** tài liệu có thể không phản ánh hệ thống thật.

**Cách đúng:** ánh xạ từng mục đích/data flow tới yêu cầu, kiểm tra code, payload, UX, logs, processor và bằng chứng vận hành.

### 18.2. Giả định privacy = security

Một API được mã hóa và authenticated vẫn có thể thu thập quá nhiều dữ liệu hoặc dùng dữ liệu sai purpose.

**Cách đúng:** đánh giá minimization, purpose, retention, transparency và các quyền phù hợp bên cạnh bảo mật kỹ thuật.

### 18.3. Áp consent cho mọi hoạt động mà không xét cơ sở khác

Một boolean consent chung không chứng minh tính hợp lệ của mọi mục đích.

**Cách đúng:** xác nhận basis/điều kiện áp dụng theo từng purpose với privacy/legal owner; kiểm thử consent ở những luồng thực sự dùng consent.

### 18.4. Tin trạng thái consent do client gửi

Client có thể giả mạo “granted=true” cho subject khác.

**Cách đúng:** dùng consent registry tin cậy, identity verification và purpose-specific state; có test cross-subject.

### 18.5. Chỉ kiểm tra lúc enqueue mà không xem worker

User có thể rút consent khi message đang chờ.

**Cách đúng:** định nghĩa semantics thời điểm, kiểm tra worker, retry, cache và các trường hợp race theo policy.

### 18.6. Dùng soft-delete là bằng chứng đã xóa

Bản ghi có thể còn ở analytics, cache, backup hoặc provider.

**Cách đúng:** xây data lineage, xử lý hoặc hạn chế theo scope, reconcile downstream và kiểm tra restore.

### 18.7. Xóa tất cả dữ liệu bất kể nghĩa vụ lưu giữ

Có thể trái nghĩa vụ khác hoặc làm mất hồ sơ cần giữ hợp lệ.

**Cách đúng:** phân loại dữ liệu, retention basis, legal hold, phạm vi hạn chế xử lý và quyết định có căn cứ.

### 18.8. Lưu raw PII trong evidence

Test/audit lại tạo một bản sao dữ liệu không cần thiết.

**Cách đúng:** synthetic data, masked references, metadata tối thiểu, access control và retention.

### 18.9. Hợp đồng vendor được xem là chứng minh hoạt động

Data processor có thể nhận thêm trường hoặc chưa xóa bản sao.

**Cách đúng:** kết hợp contract review với API/payload tests, processor evidence và reconciliation khi có thể.

### 18.10. Không kiểm tra log và dữ liệu thứ cấp

Dữ liệu có thể tiếp tục xuất hiện trong telemetry, crash report, backup, analytics.

**Cách đúng:** inventory toàn bộ luồng, quét dấu canary trong phạm vi được phép, kiểm tra logging schema và retention.

### 18.11. Chỉ kiểm thử đường thành công

Không kiểm tra wrong subject, purpose mismatch, timeout, revoke race hoặc processor failure.

**Cách đúng:** negative/failure-mode tests và end-to-end reconciliation theo threat scenario.

### 18.12. Coi kiểm tra một lần là assurance vô thời hạn

Data flow, SDK, notice, nhà cung cấp và policy thay đổi liên tục.

**Cách đúng:** thêm trigger trong SDLC, change review, monitoring và re-assessment dựa trên rủi ro.

### 18.13. Báo phần trăm compliance không có mẫu số

“90% privacy secure” không thể hiện 10% còn lại là các processing có dữ liệu nhạy cảm hay không.

**Cách đúng:** báo scope, applicable requirements, verified/failed/unknown và severity từng finding.

### 18.14. Tự kết luận đáp ứng luật khi chưa xác định phạm vi áp dụng

Các quy tắc privacy có thể khác nhau theo khu vực, loại hoạt động và vai trò xử lý.

**Cách đúng:** gắn kết luận với nguồn nghĩa vụ đã được chủ thể có thẩm quyền xác nhận, không suy đoán từ tên framework.

## 19. Checklist thực hành privacy control assessment

- [ ] Đã ghi **assessment ID, purpose, scope, environment và risk owner**.
- [ ] Có data inventory và data flow gồm hệ thống gốc, log, event, analytics, processor, backup.
- [ ] Phân loại dữ liệu và chủ thể, có data owner và mục đích được phê duyệt.
- [ ] Có nguồn yêu cầu privacy, phiên bản và căn cứ áp dụng được xác nhận.
- [ ] Không giả định mọi xử lý đều dựa trên consent.
- [ ] Mỗi requirement có control ID, security/privacy claim và tiêu chí đạt.
- [ ] Đã kiểm tra **data minimization** từ API tới storage/log/event/response.
- [ ] Đã kiểm tra **purpose limitation** tại nơi thực thi và downstream.
- [ ] Nếu cần consent, đã kiểm tra thu nhận, lưu evidence, purpose/version và withdrawal.
- [ ] Đã thử race giữa revoke và queue/dispatch, cùng tình huống service lỗi.
- [ ] Có kiểm tra quyền subject trên DSAR/access/export/deletion.
- [ ] DSAR có quy trình identity verification, scope, ngoại lệ, phản hồi và audit.
- [ ] Retention jobs có owner, lịch, reconciliation, monitoring và retry.
- [ ] Deletion không được báo hoàn tất khi downstream cần xử lý vẫn thiếu xác minh.
- [ ] Backup/restore có chính sách ngăn hồi sinh dữ liệu đã xóa trái quy định.
- [ ] Dữ liệu analytics được kiểm tra minimization, liên kết và nguy cơ re-identification.
- [ ] Đã xem payload/contract, subprocessor và kiểm soát của bên thứ ba.
- [ ] Log/telemetry không chứa raw PII/token không cần thiết, có quyền và retention.
- [ ] Test dùng synthetic data hoặc dữ liệu được bảo vệ và cho phép theo quy trình.
- [ ] Đã kiểm tra **design, implementation và operating effectiveness**.
- [ ] Negative tests gồm cross-subject, wrong purpose, revoked, expired và failure.
- [ ] Evidence gắn policy/standard version, build, environment, period và reviewer.
- [ ] Có ghi coverage, sampling method, limitations và confidence.
- [ ] Findings có mức ảnh hưởng, owner, hạn, control bù trừ và tiêu chí retest.
- [ ] Residual risk/ngoại lệ được quyết định theo đúng thẩm quyền.
- [ ] Có trigger re-assessment khi data flow, mục đích, vendor, SDK, retention hoặc luật áp dụng thay đổi.

Checklist là công cụ hỗ trợ phương pháp; một danh sách đã đánh dấu **không thay thế kết quả kiểm chứng** ở hệ thống thực tế.

## 20. Câu hỏi tự kiểm tra

1. Privacy control khác security control ở những mục tiêu nào? Khi nào hai loại control giao nhau?
2. Vì sao hệ thống mã hóa và phân quyền đúng vẫn có thể xâm phạm nguyên tắc giảm thiểu dữ liệu?
3. Những yếu tố nào cần được xác định trước khi kết luận một privacy requirement áp dụng cho hệ thống?
4. Tại sao không được mặc định mọi mục đích xử lý dữ liệu cá nhân đều dựa trên consent?
5. Khi user rút consent giữa lúc enqueue và dispatch, những control và test nào cần xem?
6. Vì sao consentGranted từ HTTP request của client không phải bằng chứng hợp lệ?
7. Có thể dùng kiểm thử unit của purpose gate để chứng minh marketing provider chỉ nhận dữ liệu hợp lệ không? Cần kiểm tra thêm gì?
8. Trong ví dụ Orders API, những trường nào không nên gửi cho provider nếu không cần cho mục đích PROMOTION_EMAIL?
9. Retention job chạy “success” có đủ chứng minh mọi bản ghi đã hết hạn đều được xử lý không?
10. Vì sao soft delete trên database gốc chưa bảo đảm xử lý yêu cầu xóa ở các processor khác?
11. Nếu một backup cũ được restore sau khi user đã được xử lý xóa dữ liệu, cần kiểm tra những điều kiện nào?
12. Một yêu cầu DSAR của A có thể bị lạm dụng để đọc dữ liệu B ra sao? Test âm nào giúp phát hiện?
13. Sự khác biệt giữa pseudonymization và anonymization là gì? Hash email đã phải ẩn danh không?
14. Vì sao privacy audit evidence cũng có thể tạo privacy risk?
15. Khi một vendor có hợp đồng và báo cáo compliance, tổ chức còn cần kiểm tra những bằng chứng thực thi nào?
16. Phân biệt design, implementation, operating và evidence gap qua ví dụ consent worker.
17. Nếu chỉ 21/30 data flows được verified, tỷ lệ 70% nói lên điều gì và không nói lên điều gì?
18. Ai có quyền quyết định residual risk, ai chịu trách nhiệm control, ai xác nhận nghĩa vụ privacy?
19. Một ngoại lệ được phê duyệt có biến control không đạt thành effective không? Vì sao?
20. Những thay đổi nào trong SDLC phải kích hoạt rà soát lại privacy controls?
21. Sau khi sửa một finding về log chứa PII, cần thu thập những bằng chứng nào để đóng finding?
22. Hãy thiết kế ba negative tests cho một luồng xóa dữ liệu có queue và provider downstream.

## 21. Tổng kết

**Kiểm tra privacy control** là việc đánh giá **có bằng chứng** rằng những biện pháp bảo vệ dữ liệu cá nhân và quyền riêng tư **đạt mục tiêu trong phạm vi xử lý cụ thể**. Phương pháp hiệu quả bắt đầu từ **data inventory, mục đích, nghĩa vụ áp dụng và privacy risk**, sau đó ánh xạ từng yêu cầu tới control và security/privacy claim, kiểm tra **thiết kế, triển khai, hành vi, hoạt động vận hành và các hệ thống downstream**. Các lĩnh vực quan trọng gồm **data minimization, purpose limitation, consent khi có áp dụng, minh bạch, quyền chủ thể dữ liệu, retention/deletion, chia sẻ với vendor, log/analytics và nguy cơ tái nhận diện**. Trong chương trình **SECURITY_SECURITY_ASSURANCE**, kết luận phải gắn với **test/audit/evidence đúng phiên bản, môi trường và thời gian**, phân biệt rõ **không đạt** với **chưa đủ bằng chứng**, và theo dõi finding đến khi **khắc phục và retest**. Mục tiêu không phải tạo một checklist đẹp, mà là duy trì **privacy assurance liên tục** khi sản phẩm và luồng dữ liệu thay đổi.

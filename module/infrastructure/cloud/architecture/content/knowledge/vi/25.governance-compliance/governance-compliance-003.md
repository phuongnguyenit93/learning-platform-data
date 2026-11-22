# Chính sách lưu giữ, xóa dữ liệu và quyền riêng tư

Hệ thống cloud có thể tạo và sao chép dữ liệu ở nhiều nơi: database, object storage, cache, search index, message broker, log, data lake, backup và bản sao ở region khác. Khi một dữ liệu được tạo, tổ chức cần biết dữ liệu đó thuộc ai, được dùng cho mục đích nào, ai có quyền truy cập, phải giữ bao lâu và phải xử lý ra sao khi hết mục đích hoặc có yêu cầu xóa.

Nếu chỉ tập trung bảo vệ dữ liệu khỏi bị mất, hệ thống có thể giữ quá nhiều thông tin vô thời hạn. Nếu xóa quá nhanh, tổ chức có thể mất bằng chứng giao dịch, không đáp ứng nghĩa vụ lưu giữ hoặc không thể điều tra sự cố. Vì vậy, **retention, deletion và privacy phải được thiết kế thành một lifecycle có kiểm soát**, gắn với phân loại dữ liệu, mục đích xử lý, yêu cầu nghiệp vụ, hợp đồng và quy định áp dụng.

Trong module **CLOUD_ARCHITECTURE**, bài học này trình bày cách chuyển chính sách quản trị và quyền riêng tư thành kiểm soát kỹ thuật: data inventory, classification, retention schedule, legal hold, xóa dữ liệu trên nhiều bản sao, xử lý backup, quyền truy cập, audit và bằng chứng hoàn tất. Đây là nội dung kiến trúc và vận hành; thời hạn pháp lý cụ thể cần được chủ sở hữu dữ liệu và bộ phận pháp chế/compliance xác định theo phạm vi áp dụng.

## 1. Retention và deletion là bài toán kiến trúc

Một bản ghi khách hàng có thể xuất hiện trong nhiều thành phần:

~~~mermaid
flowchart TB
    APP["Application"]
    DB["Primary database"]
    CACHE["Cache"]
    SEARCH["Search index"]
    EVENT["Event broker"]
    LAKE["Data lake / analytics"]
    OBJ["Object storage"]
    BACKUP["Backup / replica"]
    APP --> DB
    DB --> CACHE
    DB --> SEARCH
    DB --> EVENT
    EVENT --> LAKE
    APP --> OBJ
    DB --> BACKUP
    OBJ --> BACKUP
~~~

Một yêu cầu xóa chỉ tác động lên database có thể để lại dữ liệu trong search index, cache, event replay, export, backup hoặc object version. Ngược lại, xóa dữ liệu nguồn quá sớm có thể làm pipeline chưa xử lý xong hoặc phá hủy audit/evidence cần giữ hợp lệ.

Retention và deletion cần trả lời cùng lúc:

- Dữ liệu nào được thu thập và mục đích cụ thể là gì?
- Mục đích đó còn hiệu lực tới khi nào?
- Có nghĩa vụ lưu giữ theo luật, hợp đồng, bảo hành, kế toán hoặc tranh chấp không?
- Dữ liệu được sao chép tới những hệ thống nào?
- Ai có quyền đặt/gỡ legal hold và phê duyệt xóa?
- Xóa logic hay xóa vật lý, và khi nào dữ liệu không còn khả năng truy cập?
- Backup hết hạn và được xử lý ra sao?
- Tổ chức chứng minh việc xóa/ẩn danh đã hoàn tất bằng cách nào?

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Data retention** | Giữ dữ liệu trong một khoảng thời gian hoặc tới khi một điều kiện được đáp ứng |
| **Retention schedule** | Tập quy tắc nêu thời hạn, điểm bắt đầu, ngoại lệ và hành động cuối vòng đời theo loại dữ liệu |
| **Deletion** | Loại bỏ dữ liệu khỏi phạm vi sử dụng/lưu trữ theo quy trình đã định |
| **Erasure** | Xóa dữ liệu cá nhân theo yêu cầu/quyền hoặc chính sách áp dụng |
| **Soft delete** | Đánh dấu không còn hiển thị/hoạt động nhưng dữ liệu có thể vẫn được giữ để phục hồi |
| **Hard delete** | Xóa dữ liệu khỏi storage theo semantics của hệ thống; không nhất thiết đồng nghĩa mọi backup đã hết |
| **Anonymization** | Biến đổi dữ liệu sao cho cá nhân không còn có thể được nhận diện bằng phương tiện hợp lý trong bối cảnh áp dụng |
| **Pseudonymization** | Thay định danh trực tiếp bằng mã khác; vẫn có thể liên kết lại nếu còn thông tin bổ sung |
| **Legal hold** | Tạm giữ dữ liệu liên quan tới nghĩa vụ pháp lý/điều tra, không cho lifecycle xóa thông thường |
| **Data minimization** | Chỉ thu thập và giữ dữ liệu cần thiết cho mục đích xác định |
| **Data residency** | Yêu cầu hoặc chính sách về nơi dữ liệu được lưu/truy cập/xử lý |

Soft delete không phải hard delete. Pseudonymization không tự động biến dữ liệu thành anonymous. Một dữ liệu được mã hóa vẫn có thể là dữ liệu cá nhân nếu tổ chức hoặc bên khác còn khả năng giải mã/liên kết.

### Retention khác với backup retention

Retention của bản ghi hoạt động nghiệp vụ và retention của backup có thể khác nhau. Bản ghi hóa đơn có thể phải được giữ theo lịch lưu trữ; backup database giữ các recovery point theo RPO/RTO. Khi một hóa đơn hết retention và bị xóa khỏi nguồn, backup cũ có thể vẫn chứa nó tới khi hết chu kỳ backup. Chính sách phải mô tả ngoại lệ và giới hạn thời gian còn tồn tại này.

## 3. Data inventory: biết dữ liệu ở đâu trước khi đặt chính sách

Không thể thực thi retention/deletion đáng tin cậy nếu không biết dữ liệu nằm ở đâu. Data inventory là danh mục có chủ sở hữu, phân loại, mục đích và vị trí lưu trữ.

### Thông tin inventory tối thiểu

| Trường | Nội dung |
| --- | --- |
| Dataset/entity | Tên bộ dữ liệu hoặc loại bản ghi |
| Business owner | Người/bộ phận chịu trách nhiệm nghiệp vụ |
| System owner | Nhóm vận hành hệ thống |
| Purpose | Mục đích thu thập/sử dụng |
| Data category | Định danh, liên hệ, tài chính, sức khỏe, telemetry... |
| Sensitivity/classification | Mức nhạy cảm và yêu cầu kiểm soát |
| Data subjects | Cá nhân/nhóm người có dữ liệu liên quan |
| Source of truth | Hệ thống authoritative |
| Locations/copies | Database, bucket, cache, index, broker, warehouse, backup |
| Processors/recipients | Dịch vụ nội bộ và bên thứ ba xử lý dữ liệu |
| Region/residency | Vị trí lưu/truy cập/xử lý |
| Retention rule | Quy tắc và trigger hết hạn |
| Deletion method | Xóa, ẩn danh, archive hoặc legal hold |
| Evidence | Log, report, ticket hoặc chứng từ chứng minh thực thi |

### Data lineage và bản sao phát sinh

Inventory cần phản ánh dữ liệu được sinh ra từ dữ liệu khác. Ví dụ:

- Tên và email trong bảng customer.
- Email trong event đã publish.
- Email trong search document.
- Email trong log application.
- File export chứa tên khách hàng.
- Bản dữ liệu tổng hợp trong analytics.

Một yêu cầu xóa có thể không cần xóa mọi thống kê đã được ẩn danh thực sự, nhưng cần đánh giá khả năng suy ngược và mục đích giữ. Hãy ghi rõ nguồn nào tạo ra bản sao và consumer nào phải nhận deletion/tombstone event.

### Đừng chỉ inventory hệ thống production

Môi trường staging, dev, test, support export, local download, data science workspace và bản dump phục vụ debug cũng có thể chứa dữ liệu thật. Đưa các bản sao này vào phạm vi chính sách hoặc thay bằng dữ liệu synthetic/masked.

## 4. Phân loại dữ liệu và data minimization

Classification giúp chọn retention, encryption, access control và deletion method. Mô hình phân loại phải đủ đơn giản để đội phát triển áp dụng nhất quán.

Ví dụ nhóm:

| Nhóm | Ví dụ | Kiểm soát thường cân nhắc |
| --- | --- | --- |
| Public | Nội dung đã công khai | Integrity, availability, retention theo nhu cầu |
| Internal | Cấu hình vận hành không nhạy cảm | IAM, audit và lifecycle |
| Confidential | Thông tin khách hàng, hợp đồng | Encryption, least privilege, retention có owner |
| Restricted | Credential, dữ liệu nhạy cảm cao, thông tin chịu ràng buộc đặc biệt | Tách quyền, audit tăng cường, hạn chế export, retention chặt |

Tên mức phân loại là ví dụ; tổ chức cần chuẩn hóa taxonomy riêng. Một field trong dataset có thể có độ nhạy khác các field khác. Không nên mặc định cả bảng đều public hoặc đều restricted khi có thể phân vùng field và kiểm soát chính xác hơn.

### Data minimization ở thời điểm thiết kế

Trước khi lưu một field, hỏi:

1. Mục đích xử lý cụ thể là gì?
2. Có thể đạt mục đích bằng dữ liệu ít chi tiết hơn không?
3. Có cần lưu dữ liệu nhận dạng hay dùng token/reference?
4. Cần giữ field bao lâu và ai cần truy cập?
5. Có thể không lưu hoặc tính lại thay vì giữ lâu dài không?

Ví dụ, hệ thống có thể chỉ lưu trạng thái xác minh và transaction reference thay vì lưu lại toàn bộ nội dung giấy tờ định danh nếu không có nhu cầu và cơ sở phù hợp. Không thu thập “để sau này có thể cần” nếu chưa có mục đích được phê duyệt.

### Purpose limitation

Một dữ liệu được thu thập cho mục đích hoàn tất booking không tự động được phép dùng cho quảng cáo, profiling hoặc chia sẻ cho đối tác. Cần gắn purpose với dataset/field, service consumer và quyền truy cập; thay đổi mục đích cần quy trình đánh giá và phê duyệt phù hợp.

## 5. Xây dựng retention schedule

Retention schedule chuyển yêu cầu nghiệp vụ/pháp lý thành quy tắc máy có thể thực thi. Mỗi rule cần nêu rõ loại dữ liệu, trigger bắt đầu tính thời gian, thời hạn, ngoại lệ, hành động khi hết hạn và owner phê duyệt.

### Thành phần của một retention rule

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Dataset/class | Quy tắc áp dụng cho loại dữ liệu nào? |
| Trigger | Tính từ ngày tạo, kết thúc hợp đồng, đóng tài khoản, hoàn tất giao dịch hay mốc khác? |
| Duration | Giữ trong bao lâu? Nguồn yêu cầu là gì? |
| Scope | Field, record, object version hay toàn bộ hồ sơ? |
| Exceptions | Legal hold, dispute, investigation hoặc nghĩa vụ khác? |
| Action | Xóa, ẩn danh, archive, chuyển tier hay review thủ công? |
| Owner/approval | Ai chịu trách nhiệm và ai duyệt thay đổi? |
| Execution | Job, lifecycle policy, database partition expiry hay workflow nào? |
| Evidence | Log/report/ticket nào chứng minh đã thực thi? |

### Trigger phải xác định được

“Giữ 5 năm” là chưa đủ nếu không biết 5 năm tính từ đâu. Với hồ sơ hợp đồng, mốc có thể là ngày kết thúc hợp đồng; với log, có thể là thời điểm phát sinh; với dữ liệu support, có thể là lúc ticket đóng. Trigger phải nằm trong metadata đáng tin cậy và được xử lý đúng timezone/calendar theo chính sách.

### Lịch mẫu mang tính minh họa

| Loại dữ liệu | Trigger giả định | Hành động sau khi hết thời hạn |
| --- | --- | --- |
| Session/token cache | Hết hạn phiên hoặc token | Xóa tự động |
| File upload tạm | Job hoàn tất hoặc quá hạn | Xóa object và metadata phụ |
| Support ticket | Ticket đóng và hết thời gian cần thiết | Xóa hoặc ẩn danh theo policy |
| Contract/invoice | Mốc pháp lý/nghiệp vụ được phê duyệt | Archive hoặc xóa khi đủ điều kiện |
| Security logs | Thời điểm log được tạo | Xóa/aggregate sau retention đã xác định |
| Backup recovery point | Điểm backup hết cửa sổ bảo vệ | Expire theo lifecycle backup |

Không lấy các ví dụ này làm thời hạn pháp lý. Con số cụ thể phải được xác định theo loại hồ sơ, khu vực, loại hình tổ chức, hợp đồng và quy định hiện hành.

### Retention không được thay đổi âm thầm

Chỉnh một rule từ 5 năm thành 1 năm có thể ảnh hưởng dữ liệu đã tạo. Cần version policy, approval, effective date, migration plan và audit. Xác định thay đổi áp dụng cho record mới hay cả record cũ; nếu có legal hold, rule mới không được tự động gỡ hold.

## 6. Retention engine và cách thực thi

Một hệ thống lớn thường cần retention engine hoặc lifecycle service để tập trung quản lý chính sách, thay vì mỗi ứng dụng tự cài một cron job không thống nhất.

~~~mermaid
flowchart TB
    POLICY["Approved retention policy"]
    INVENTORY["Data inventory / classification"]
    ENGINE["Retention evaluator"]
    HOLD["Legal hold / exception registry"]
    PLAN["Deletion plan / dry-run"]
    APPROVAL["Approval where required"]
    EXEC["Execution adapters"]
    DB["Database"]
    OBJ["Object storage"]
    INDEX["Search / cache / analytics"]
    EVIDENCE["Audit + deletion evidence"]
    POLICY --> ENGINE
    INVENTORY --> ENGINE
    HOLD --> ENGINE
    ENGINE --> PLAN
    PLAN --> APPROVAL
    APPROVAL --> EXEC
    EXEC --> DB
    EXEC --> OBJ
    EXEC --> INDEX
    EXEC --> EVIDENCE
~~~

### Separation of duties

Retention engine có thể đánh giá dữ liệu đủ điều kiện, nhưng không nhất thiết có quyền xóa mọi dữ liệu. Tách vai trò:

- Policy owner đề xuất và phê duyệt retention.
- Data owner xác nhận scope và mục đích.
- Compliance/legal quản lý ngoại lệ và legal hold.
- Execution service chỉ thực hiện đúng deletion plan đã được xác thực.
- Auditor đọc evidence, không sửa trạng thái thực thi.

Điều này giảm nguy cơ một lỗi hoặc tài khoản bị chiếm có thể thay policy và xóa dữ liệu hàng loạt.

### Dry-run và canary

Trước khi xóa thật:

1. Tính tập record/object đủ điều kiện.
2. Thống kê số lượng, dung lượng, tenant và system copy.
3. So sánh với kỳ chạy trước để phát hiện biến động bất thường.
4. Kiểm tra hold, legal basis, retention end date và owner.
5. Xuất manifest deletion plan bất biến.
6. Chạy canary trên phạm vi nhỏ được phê duyệt.
7. Xác minh kết quả rồi mới mở rộng.

Nếu dry-run cho thấy hàng triệu object bị xóa thay vì vài nghìn như dự kiến, dừng thực thi và điều tra dữ liệu trigger/tag hoặc policy version.

### Idempotent execution

Deletion job có thể chạy lại do timeout, worker restart hoặc queue redelivery. Mỗi action nên có operation ID, target identity và trạng thái. Xóa lại một object đã xóa cần trả kết quả ổn định; không được chuyển nhầm sang xóa một version khác chỉ vì key hiện tại đã thay đổi.

## 7. Yêu cầu quyền riêng tư và data subject request

Tùy quy định áp dụng, cá nhân có thể có các quyền liên quan tới dữ liệu của mình như truy cập, sửa, xóa, hạn chế xử lý, phản đối hoặc nhận bản sao/chuyển dữ liệu. Không phải mọi quyền đều áp dụng giống nhau trong mọi trường hợp; có ngoại lệ khi tổ chức có nghĩa vụ lưu giữ, bảo vệ quyền của người khác hoặc căn cứ hợp pháp khác.

Kiến trúc cần hỗ trợ quy trình tiếp nhận, xác minh, tìm kiếm, phê duyệt, thực thi và phản hồi yêu cầu.

### Các loại request cần hỗ trợ

| Request | Khả năng hệ thống cần có |
| --- | --- |
| Access/export | Tìm dữ liệu theo subject, tập hợp có scope và xuất an toàn |
| Rectification | Sửa dữ liệu nguồn và đồng bộ các projection/bản sao |
| Erasure | Xác định dữ liệu được phép xóa, ngoại lệ và mọi bản sao |
| Restriction | Đánh dấu trạng thái hạn chế và ngăn xử lý không được phép |
| Objection/opt-out | Cập nhật preference và truyền tới hệ thống downstream |
| Portability | Xuất dữ liệu theo định dạng cấu trúc được xác định |

### Xác minh chủ thể

Không được xóa hoặc xuất dữ liệu chỉ vì người gửi biết email hoặc một ID. Cần xác minh danh tính và quyền đại diện; với tài khoản doanh nghiệp, xác minh người yêu cầu có quyền thay mặt tổ chức hoặc cá nhân liên quan. Mức xác minh phải cân bằng giữa ngăn lộ dữ liệu và không thu thập thêm dữ liệu quá mức.

### Tìm dữ liệu theo subject

Một subject có thể có nhiều định danh: account ID, email cũ, phone, external identity, customer ID, booking reference. Cần identity mapping có kiểm soát và lineage; không dùng fuzzy match tùy tiện để xóa dữ liệu người khác. Các hệ thống phụ cần có cách truy vấn subject reference mà không phải lưu quá nhiều PII.

### Workflow xử lý request

~~~mermaid
flowchart TD
    REQ["Receive request"]
    VERIFY["Verify identity / authority"]
    SCOPE["Resolve subject + data scope"]
    REVIEW["Check purpose, retention, legal hold, exceptions"]
    PLAN["Create action plan"]
    APPROVE["Approval / legal review if needed"]
    EXECUTE["Execute across systems"]
    VERIFY2["Verify completion / residual copies"]
    RESP["Respond + preserve evidence"]
    REQ --> VERIFY --> SCOPE --> REVIEW --> PLAN --> APPROVE --> EXECUTE --> VERIFY2 --> RESP
~~~

Một request có thể hoàn thành một phần: một số dữ liệu được xóa, một số được giữ do nghĩa vụ, và một số bản sao backup hết hạn theo lịch. Phản hồi cần phân biệt rõ kết quả, ngoại lệ và thời gian dự kiến, theo yêu cầu pháp lý/contract áp dụng.

### Không dùng request xóa làm lệnh xóa mù

Trước khi thực thi, kiểm tra:

- Dữ liệu có thuộc đúng subject không?
- Có dữ liệu chung với người khác hoặc doanh nghiệp khác không?
- Có transaction/record cần giữ vì nghĩa vụ hợp pháp không?
- Có legal hold hoặc dispute không?
- Có thể xóa field nhận dạng trong khi giữ record đã ẩn danh hợp lệ không?
- Các bản sao, backup và processor được xử lý theo policy nào?

## 8. Xóa dữ liệu xuyên nhiều hệ thống

Một thiết kế đáng tin cần có data lineage và deletion propagation. Một service xóa bản ghi nguồn nên phát tín hiệu tới các consumer cần xử lý bản sao.

~~~mermaid
flowchart LR
    API["Privacy / deletion API"]
    ORCH["Deletion orchestrator"]
    SRC["Source database"]
    OUTBOX["Outbox / tombstone event"]
    BROKER["Broker"]
    CACHE["Cache invalidator"]
    SEARCH["Search eraser"]
    LAKE["Analytics pipeline"]
    OBJ["Object storage"]
    EVIDENCE["Evidence registry"]
    API --> ORCH
    ORCH --> SRC
    SRC --> OUTBOX
    OUTBOX --> BROKER
    BROKER --> CACHE
    BROKER --> SEARCH
    BROKER --> LAKE
    ORCH --> OBJ
    ORCH --> EVIDENCE
    CACHE --> EVIDENCE
    SEARCH --> EVIDENCE
    LAKE --> EVIDENCE
~~~

### Deletion event / tombstone

Event xóa có thể mang:

- Request ID và deletion operation ID.
- Subject reference pseudonymous.
- Dataset/entity và resource identifier.
- Tenant/scope nếu dữ liệu đa khách hàng.
- Policy version, reason code và thời điểm.
- Danh sách consumer cần xác nhận.

Không publish PII thô hoặc nội dung record vào event nếu không cần. Consumer xác thực producer, schema và scope; xử lý idempotent; cập nhật trạng thái hoàn tất hoặc lỗi.

### Outbox và retry

Nếu source commit deletion nhưng message publish thất bại, downstream copy có thể còn nguyên. Ghi tombstone/outbox trong cùng transaction với trạng thái xóa (khi khả thi), rồi relay publish. Consumer có thể nhận event lặp; cần idempotency và checkpoint. DLQ phải có alert và quy trình replay.

### Deletion orchestration và completion barrier

Orchestrator giữ trạng thái mỗi hệ thống: pending, completed, deferred, exception hoặc failed. Với hệ thống trọng yếu, chỉ đánh dấu request hoàn tất sau khi consumer xác nhận. Với backup hoặc third-party processor có thời gian xử lý khác, policy cần định nghĩa completion semantics và giới hạn tồn tại còn lại.

Không nên báo “đã xóa hoàn toàn” khi chỉ mới xóa source database nhưng chưa xử lý search, object, export hoặc processor.

## 9. Backup, replica và bản sao immutable

Backup có vai trò khôi phục sau sự cố, nhưng cũng có thể lưu dữ liệu đã bị xóa khỏi production. Đây là một trong những điểm khó nhất của deletion lifecycle.

### Các chiến lược thường gặp

| Chiến lược | Cách xử lý deletion | Đánh đổi |
| --- | --- | --- |
| Backup hết hạn theo lịch | Record đã xóa có thể còn trong backup cũ tới khi recovery point hết retention | Dễ vận hành nhưng cần công bố/định nghĩa thời gian tồn tại |
| Tombstone/replay | Ghi deletion marker và áp lại khi restore | Cần lưu tombstone đủ lâu và đảm bảo replay không bị bỏ |
| Selective purge | Xóa subject khỏi backup nếu sản phẩm hỗ trợ | Có thể phức tạp, tốn chi phí và làm thay đổi tính bất biến |
| Cryptographic erasure | Hủy key riêng sau khi kiểm tra không còn bản sao cần đọc | Chỉ phù hợp khi mô hình mã hóa/key lifecycle thực sự hỗ trợ |
| Restore rồi re-delete | Khi khôi phục backup, áp lại deletion log trước khi mở hệ thống | Cần quy trình bắt buộc trong mọi restore path |

### Quy tắc restore bắt buộc

Nếu backup chứa record đã được xóa sau thời điểm backup:

1. Restore vào môi trường cô lập.
2. Nạp deletion tombstone/ledger có thẩm quyền.
3. Áp lại các yêu cầu xóa còn hiệu lực.
4. Xử lý legal hold/retention ngoại lệ.
5. Rebuild search/cache/analytics từ trạng thái đã lọc.
6. Kiểm tra không phát lại event cũ làm tái tạo record đã xóa.
7. Chỉ sau khi xác minh mới đưa dữ liệu trở lại production.

Không restore backup thẳng vào production mà bỏ qua deletion ledger; dữ liệu đã xóa có thể xuất hiện lại.

### Immutable backup và legal hold

Immutable backup/Object Lock có thể ngăn sửa hoặc xóa trong thời hạn được khóa. Nếu một request erasure tới trong khoảng đó, tổ chức cần policy xử lý: dữ liệu có nghĩa vụ phải giữ hay không, có thể loại bỏ khả năng truy cập bằng key riêng hay phải đợi retention kết thúc, và dữ liệu sẽ được xóa khi nào. Không bypass hoặc phá retention bất biến nếu chưa có căn cứ và phê duyệt hợp lệ.

### Tách mục tiêu backup và data subject erasure

Backup thường được thiết kế để khôi phục whole-system hoặc point-in-time, không phải tra cứu và xóa từng cá nhân. Cần ghi rõ rằng backup rotation có thể làm dữ liệu còn tồn tại tới thời điểm recovery point hết hạn; trong lúc đó, backup phải được cô lập, không dùng cho hoạt động thường ngày và deletion ledger phải được áp lại khi restore.

## 10. Soft delete, hard delete và purge vật lý

Soft delete thường đổi trạng thái record thành deleted/deactivated và ẩn khỏi truy vấn thường. Nó hữu ích cho khôi phục ngắn hạn hoặc workflow phê duyệt, nhưng dữ liệu vẫn tồn tại trong storage, backup, log và có thể bị truy cập bởi query khác.

### Vòng đời mẫu

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> SoftDeleted: Deletion request accepted
    SoftDeleted --> Restored: Undo within allowed window
    SoftDeleted --> PurgePending: Retention/approval complete
    PurgePending --> Purged: Delete from active stores
    Purged --> BackupExpiry: Await backup rotation / tombstone replay
    BackupExpiry --> [*]
    SoftDeleted --> LegalHold: Hold applied
    LegalHold --> SoftDeleted: Hold released
~~~

Trạng thái minh họa; hệ thống có thể dùng state machine khác. Cần tách “không còn hiển thị”, “đã purge khỏi active store” và “backup không còn chứa dữ liệu” thành các mốc riêng.

### Hard delete ở các storage engine

Lệnh DELETE trong database thường đánh dấu record đã xóa ở logical layer. Page, WAL, snapshot, replica, backup hoặc storage block có thể còn giữ dữ liệu một thời gian. Object storage có versioning/delete marker và lifecycle riêng. Search index cần delete-by-query/reindex. Vì vậy hard delete ở ứng dụng không đồng nghĩa dữ liệu đã bị ghi đè vật lý tức thì trên mọi media.

### Purge an toàn

- Xác định đúng primary key và mọi denormalized copy.
- Kiểm tra legal hold/retention.
- Xóa qua API/driver được hỗ trợ; không sửa trực tiếp storage block.
- Ghi audit operation và kết quả.
- Xác nhận không thể truy cập qua API, query, search, cache hoặc export.
- Theo dõi backup expiration và thực hiện re-delete sau restore.

Không cam kết physical overwrite nếu nền tảng cloud không cung cấp hoặc không chứng minh semantics đó. Diễn đạt kết quả theo phạm vi kiểm soát thật: removed from active processing, purged from primary service, scheduled to expire from backup, v.v.

## 11. Anonymization, pseudonymization và masking

Ẩn danh có thể là phương án khi tổ chức vẫn cần thống kê hoặc phân tích sau khi không còn cần định danh cá nhân. Nhưng không phải phép thay tên thành một mã ngẫu nhiên là đủ.

### Pseudonymization

Thay email/customer ID bằng token hoặc surrogate ID, giữ bảng mapping riêng. Nếu mapping hoặc dữ liệu bổ sung vẫn cho phép liên kết về cá nhân, dữ liệu vẫn có khả năng nhận diện. Cần bảo vệ mapping, giới hạn người có quyền re-identify, audit truy cập và đặt retention riêng.

### Anonymization

Mục tiêu là giảm/loại khả năng nhận diện cá nhân trong bối cảnh dữ liệu và phương tiện có thể sử dụng hợp lý. Cần xem xét:

- Direct identifiers: tên, email, số điện thoại, số giấy tờ.
- Quasi-identifiers: tuổi, địa bàn, nghề, thời gian giao dịch.
- Unique combinations: tổ hợp ít người có thể khớp.
- Linkability: khả năng nối với dataset khác.
- Small cells: nhóm có số lượng quá nhỏ.
- Free-text/file metadata: có thể còn tên hoặc nội dung định danh.

Không chỉ xóa cột tên rồi gọi dataset là anonymous. Đánh giá phải dựa trên nguy cơ nhận diện và mục đích sử dụng cụ thể.

### Kỹ thuật thường dùng

| Kỹ thuật | Mô tả | Hạn chế |
| --- | --- | --- |
| Generalization | Giảm độ chi tiết, ví dụ tuổi thành nhóm | Có thể vẫn nhận diện qua tổ hợp field |
| Suppression | Bỏ một giá trị/field/record | Mất thông tin phân tích |
| Aggregation | Chỉ công bố số liệu tổng hợp | Có thể suy luận qua nhiều truy vấn |
| Tokenization | Thay ID bằng token | Cần bảo vệ vault/mapping |
| Masking | Hiển thị một phần, ví dụ email đã che | Bản gốc vẫn tồn tại và vẫn là dữ liệu nhạy cảm |
| Differential privacy | Thêm nhiễu có kiểm soát cho thống kê | Cần privacy budget và thiết kế truy vấn đúng |

### Differential privacy

Differential privacy cung cấp một cách định lượng để giới hạn mức ảnh hưởng của một cá nhân lên kết quả thống kê. Nó thường phù hợp với báo cáo/analytics tổng hợp hơn là thay thế authorization cho dữ liệu transaction. Cần quản lý epsilon/delta, composition và ngân sách truy vấn; nhiều lần truy vấn có thể làm lộ thông tin tích lũy dù từng truy vấn riêng lẻ có nhiễu.

### Masking không phải erasure

Masking trên giao diện chỉ hạn chế người xem thấy dữ liệu. Nó không xóa source, export, log hoặc backup. Cần xác định yêu cầu là hide, redact, tokenize, anonymize hay erase và chọn hành động tương ứng.

## 12. Cryptographic erasure và quản lý khóa

Cryptographic erasure là làm dữ liệu không thể giải mã bằng cách hủy hoặc vô hiệu hóa khóa mã hóa liên quan, thay vì ghi đè từng block. Cách này chỉ đáng tin khi encryption architecture được thiết kế trước với phạm vi key phù hợp.

### Điều kiện cần có

- Dữ liệu được mã hóa bằng key riêng hoặc key hierarchy cho phép cô lập đúng subject/dataset.
- Mọi bản sao, replica, export và backup đều phụ thuộc vào key đó.
- Không còn bản plaintext hoặc cache/export có thể đọc độc lập.
- Key không có bản backup/escrow khác còn hoạt động ngoài dự kiến.
- Việc hủy key có audit, approval và kiểm tra dependency.
- Có bằng chứng rằng không còn bản sao có thể giải mã bằng key khác.

### Per-subject key và trade-off

Một DEK riêng cho từng subject hoặc nhóm dữ liệu nhỏ có thể hỗ trợ crypto-erasure chọn lọc. Nhưng nó làm tăng số lượng key, thao tác KMS, metadata và độ phức tạp rotation/recovery. Nếu key dùng chung cho nhiều subject, hủy key có thể làm mất dữ liệu của những người khác.

### KMS key deletion không tự động đồng nghĩa xóa dữ liệu

Xóa customer-managed key ở KMS có thể chặn giải mã các object sử dụng key đó, nhưng cần xem bản sao key, replica key, grant, cache plaintext, client-side copy và thời gian chờ xóa key. Một thao tác key deletion thiếu kiểm soát có thể gây mất dữ liệu ngoài phạm vi hoặc phá backup.

Không dùng crypto-erasure để né retention/legal hold. Việc chọn phương pháp cần được security, privacy và legal owner phê duyệt.

## 13. Quyền truy cập và bảo vệ dữ liệu theo vòng đời

Retention không làm giảm yêu cầu bảo mật. Dữ liệu càng được giữ lâu thì thời gian phơi nhiễm càng dài; cần least privilege, encryption, audit và access review xuyên suốt.

### Phân tách vai trò

| Vai trò | Trách nhiệm | Quyền không nên mặc định có |
| --- | --- | --- |
| Data owner | Mục đích, phân loại và retention | Xóa log/audit độc lập |
| Privacy/compliance | Điều phối request, ngoại lệ và evidence | Quyền sửa dữ liệu nghiệp vụ không kiểm soát |
| Application service | Xử lý nghiệp vụ theo scope | Đổi retention/legal hold |
| Deletion worker | Thực hiện deletion plan | Thay đổi policy hoặc mở rộng scope |
| Backup operator | Vận hành backup/restore | Xóa backup immutable hoặc bypass hold |
| Security auditor | Đọc bằng chứng, kiểm tra policy | Sửa log/retention |
| Break-glass admin | Xử lý tình huống đặc biệt | Hoạt động thường xuyên không approval |

### Least privilege và separation of duties

Không cấp một service account vừa được sửa retention, gỡ legal hold, xóa database và xóa audit. Tách quyền đề xuất, phê duyệt, thực thi và kiểm tra. Với thao tác phá hủy hàng loạt, dùng approval nhiều bên, MFA/strong auth, giới hạn thời gian và log độc lập.

### Encryption và key lifecycle

Encryption at rest/in transit cần được bật theo classification; key policy tách khỏi data policy. Rotation không được làm mất khả năng đọc backup còn trong retention. Key deletion chỉ thực hiện khi đã kiểm tra legal hold, backup, replica và phụ thuộc của consumer.

## 14. Cloud policy, infrastructure as code và guardrail

Chính sách lưu giữ và quyền riêng tư phải được thể hiện trong cấu hình có thể kiểm tra, không chỉ nằm trong tài liệu quy trình. Infrastructure as Code (IaC), policy-as-code và cloud organization guardrail giúp giảm drift giữa các môi trường.

### Các kiểm soát kỹ thuật

- Bucket/container có encryption, public access block và lifecycle policy theo classification.
- Object Lock/retention chỉ bật với loại dữ liệu được phê duyệt.
- Database encryption, backup retention và deletion protection theo tier.
- Log/audit export sang account hoặc project độc lập.
- KMS/key policy tách quyền encrypt/decrypt/admin/delete.
- Storage region và replication destination được giới hạn theo data residency policy.
- Resource tag bắt buộc: data owner, classification, purpose, retention class, environment.
- Policy phát hiện bucket không có owner hoặc retention class.

### Tagging không phải enforcement duy nhất

Tag là metadata thuận tiện để inventory và lifecycle, nhưng nếu workload có thể tự sửa/xóa tag rồi policy dựa hoàn toàn vào tag, nó có thể bỏ qua kiểm soát. Với dữ liệu quan trọng, cần enforce tag creation/update qua IAM/organization policy, validate trước khi upload và có inventory reconciliation.

### Policy-as-code

Có thể kiểm tra trong CI/CD:

- Không tạo bucket public ngoài exception được phê duyệt.
- Không tạo storage không mã hóa.
- Không có retention value tùy ý vượt/thiếu policy.
- Production backup destination phải tách quyền theo baseline.
- Audit logging không được tắt.
- Resource có owner/classification/retention metadata.
- Region và replication destination thuộc allowlist.

Policy kiểm tra IaC không thay runtime control; cần drift detection và audit thay đổi trực tiếp trên cloud console/API.

### Deletion guardrail

Các hành động xóa hàng loạt hoặc rút ngắn retention cần điều kiện:

1. Có deletion plan đã được phê duyệt.
2. Scope/manifest xác định và có checksum/hash.
3. Không có legal hold hoặc ngoại lệ chưa xử lý.
4. Thực thi bằng role ngắn hạn, quyền hẹp.
5. Dry-run/canary đã đạt.
6. Audit và kết quả được lưu ngoài vùng bị xóa.

## 15. Data residency, cross-region và data transfer

Một dataset có thể rời region nguồn thông qua backup, replication, support export, telemetry hoặc third-party processor. Do đó residency không chỉ là region của primary database.

### Lập bản đồ luồng dữ liệu

Với mỗi dataset, xác định:

- Region xử lý request và lưu primary.
- Region lưu replica, backup và disaster recovery.
- Region chạy log, tracing, analytics và support tooling.
- Vị trí nhân sự/processor có thể truy cập.
- Nơi tạo export, temporary file và cache.
- Cross-border transfer, subprocessor và encryption key location.

### Regional routing và failover

Nếu policy yêu cầu dữ liệu chỉ lưu ở một khu vực, DR failover sang region khác có thể không phù hợp nếu chưa có đánh giá. Cần xác định trước:

- Region dự phòng được phép hay không.
- Loại dữ liệu nào có thể replicate.
- Key, backup và log có cùng residency constraint không.
- Có thể phục vụ read-only tại region khác không.
- Cơ chế failover có phát sinh copy mới hoặc processor mới không.

### Residency không chỉ là nơi lưu ổ đĩa

Dữ liệu có thể xuất hiện trong log, support ticket, tracing baggage, email notification, crash dump và data science workspace. Phải đưa cả access/processing location và subprocessor vào data flow map. Không tuyên bố “data stays in region X” nếu log/backup/export đi ra ngoài mà không được kiểm soát.

## 16. Third-party processor và shared responsibility

Ứng dụng cloud thường sử dụng email, payment, support, analytics, observability, CRM và SaaS khác. Khi dữ liệu được gửi cho processor, tổ chức cần biết processor lưu gì, ở đâu, bao lâu và hỗ trợ deletion/return ra sao.

### Đánh giá processor

| Chủ đề | Câu hỏi cần hỏi |
| --- | --- |
| Purpose | Processor dùng dữ liệu cho mục đích nào? Có dùng cho mục đích riêng không? |
| Data scope | Field, event, file và identifier nào được gửi? |
| Retention | Processor giữ log, event, backup và export bao lâu? |
| Deletion | Có API/workflow xóa? Có bằng chứng? |
| Subprocessors | Có bên thứ ba tiếp tục xử lý không? |
| Region | Data at rest, support access và telemetry ở đâu? |
| Security | Encryption, IAM, audit, incident response thế nào? |
| Portability | Có thể export dữ liệu khi kết thúc hợp đồng không? |
| Termination | Sau chấm dứt, dữ liệu được trả/xóa theo mốc nào? |

### Data minimization khi tích hợp

Chỉ gửi field cần thiết; không chuyển toàn bộ customer record cho analytics/email nếu chỉ cần recipient address và template variables. Tokenize/pseudonymize identifier khi processor không cần danh tính trực tiếp. Tránh đưa PII vào URL, metric label hoặc log payload.

### Deletion cascade

Khi xóa dữ liệu nguồn, cần xác định processor nào nhận deletion request, ai chịu trách nhiệm theo dõi xác nhận và cách xử lý khi processor chỉ purge theo batch/backup expiry. Lưu trạng thái và bằng chứng trong deletion operation; không chỉ ghi “đã gửi API”.

### Contract và kỹ thuật phải khớp

Hợp đồng có thể cam kết xóa trong một khoảng thời gian, nhưng nếu API chỉ hỗ trợ soft delete, cần ghi nhận khoảng còn tồn tại và kiểm soát truy cập. SLA deletion, backup lifecycle, subprocessor và incident notification phải được đối chiếu với technical design.

## 17. Audit, evidence và accountability

Một chính sách không có evidence khó chứng minh đã được thực thi. Audit trail cần trả lời ai đã quyết định, dữ liệu nào bị tác động, policy nào được áp dụng, khi nào thực thi và kết quả ra sao.

### Deletion evidence

Một deletion operation có thể lưu:

- Operation ID, request/ticket ID.
- Subject reference pseudonymous.
- Dataset/entity/resource scope.
- Policy version và reason code.
- Initiator, approver, execution identity.
- Thời điểm nhận, xác minh, phê duyệt, thực thi.
- Kết quả từng system/processor: completed, deferred, exception, failed.
- Backup expiry date hoặc điều kiện hoàn tất còn lại.
- Manifest/hash và kiểm tra xác minh.

Không lưu bản copy PII đầy đủ vào evidence nếu không cần; evidence cũng có retention, access control và data minimization riêng.

### Audit log phải chống sửa

Log xóa không nên chỉ nằm trong bucket mà cùng deletion worker có quyền xóa. Có thể export sang account/security project riêng, immutable storage, append-only pipeline hoặc dịch vụ audit tập trung. Kiểm soát quyền đọc log vì log có thể chứa identifiers và thông tin nhạy cảm.

### Completion semantics

Phân biệt các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| REQUESTED | Đã nhận request |
| VERIFIED | Xác minh danh tính/authority và scope xong |
| REVIEW_REQUIRED | Cần xem legal hold/retention/ngoại lệ |
| APPROVED | Kế hoạch đã được phê duyệt |
| ACTIVE_STORES_PURGED | Đã xử lý các active system được liệt kê |
| PROCESSOR_PENDING | Đang chờ third-party xác nhận |
| BACKUP_EXPIRY_PENDING | Bản backup cũ còn tới lịch hết hạn |
| EXCEPTION | Một phần dữ liệu phải giữ hoặc không thể xóa ngay |
| COMPLETED | Đạt completion criteria đã công bố |
| FAILED | Có bước lỗi cần retry/điều tra |

Tên trạng thái là ví dụ. Không dùng một trạng thái COMPLETED chung nếu contract không giải thích backup và processor exception. Đặt SLA riêng cho từng loại request và gửi thông tin rõ ràng cho người yêu cầu theo quy trình.

## 18. Case study: nền tảng đặt chỗ xử lý yêu cầu xóa dữ liệu khách hàng

Một nền tảng cloud lưu:

- Hồ sơ khách hàng và thông tin liên hệ trong database.
- Booking, invoice và payment reference trong database giao dịch.
- File hợp đồng/biên bản trong object storage có versioning.
- Search index để tra cứu booking.
- Cache hồ sơ và trạng thái booking.
- Event trong broker để cập nhật analytics.
- Data warehouse và backup theo lịch.
- Dịch vụ email và support SaaS bên ngoài.

Khách hàng yêu cầu xóa tài khoản và dữ liệu cá nhân. Một số invoice còn trong thời hạn lưu giữ đã được pháp chế phê duyệt; một hợp đồng đang legal hold do tranh chấp.

### Bước 1 — Xác minh và phân loại request

Support tiếp nhận request, xác minh chủ thể và quyền đại diện. Privacy workflow tạo operation ID, liên kết account/customer ID cùng các alias đã xác minh. Không sử dụng email người gửi làm tiêu chí duy nhất để xóa.

### Bước 2 — Xác định dữ liệu và ngoại lệ

Inventory cho biết dữ liệu ở các hệ thống. Business owner và compliance xác định:

- Dữ liệu hồ sơ không còn mục đích có thể xóa hoặc ẩn danh.
- Invoice cần giữ theo retention rule, nhưng chỉ các field cần thiết.
- Hợp đồng đang legal hold cần bảo toàn và hạn chế truy cập.
- Search/cache phải được invalidate.
- Event analytics cần tombstone hoặc xử lý downstream theo chính sách.
- Processor email/support cần nhận deletion/rectification tương ứng.
- Backup sẽ tiếp tục giữ bản cũ tới ngày hết retention backup; mọi restore phải áp lại deletion ledger.

### Bước 3 — Lập deletion plan

| Hệ thống | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| Customer DB | Xóa/ẩn danh field đủ điều kiện | Hồ sơ active không còn dữ liệu ngoài mục đích |
| Booking DB | Giữ record cần thiết, xóa field không cần | Transaction evidence được bảo toàn theo policy |
| Invoice DB | Giữ trong retention được phê duyệt | Chỉ quyền hợp lệ mới truy cập |
| Contract object | Legal hold, restrict access | Không xóa trong thời gian hold |
| Search | Delete/tombstone các document đủ điều kiện | Search không hiển thị dữ liệu đã xóa |
| Cache | Invalidate key theo customer/tenant | Không trả bản cũ |
| Broker | Tombstone event hoặc deletion command | Consumer nhận được scope cần xử lý |
| Analytics | Xóa/ẩn danh record theo pipeline policy | Không còn dữ liệu nhận dạng ngoài mục đích |
| Email/support processor | Submit request và track acknowledgment | Có trạng thái xử lý/bằng chứng |
| Backup | Theo dõi expiry; áp deletion ledger sau restore | Dữ liệu không tái xuất hiện khi khôi phục |

### Bước 4 — Phê duyệt và thực thi

Deletion orchestrator tạo manifest versioned. Các bước có thể thực hiện song song nếu không phụ thuộc nhau; legal hold/retention được áp trước mọi hành động xóa. Execution role chỉ có quyền xóa đúng dataset/scope được giao, không sửa policy hoặc gỡ hold.

### Bước 5 — Xác minh

- Query API và database active không còn field đã xóa.
- Search count/document không còn record thuộc scope.
- Cache key đã bị invalidated hoặc hết hạn theo SLA.
- Object version đang hold vẫn tồn tại và bị giới hạn truy cập.
- Analytics consumer đã xử lý tombstone.
- Processor đã xác nhận hoặc còn trạng thái pending theo SLA.
- Deletion ledger và evidence được ghi vào audit store độc lập.

### Bước 6 — Phản hồi và theo dõi

Trả lời rõ dữ liệu nào đã xóa/ẩn danh, dữ liệu nào được giữ theo retention/legal hold và khi nào bản backup hết hạn theo lịch. Không công bố rằng mọi bản sao vật lý đã bị ghi đè ngay nếu storage provider không cung cấp bằng chứng đó.

## 19. Case study: retention cho log, telemetry và backup

Một hệ thống SaaS có log application, security audit, trace, metrics và backup. Log có thể chứa account ID, IP, URL path, error payload hoặc dữ liệu người dùng nếu developer vô tình ghi nội dung request.

### Phân loại theo mục đích

- Security audit dùng điều tra truy cập và thay đổi quyền.
- Application log hỗ trợ debug lỗi.
- Trace phục vụ latency/dependency analysis.
- Metrics hỗ trợ SLO và capacity planning.
- Backup phục vụ disaster recovery.

Không cần mọi loại telemetry giữ cùng thời hạn hoặc cùng mức chi tiết. Metrics aggregate có thể ít rủi ro nhận diện hơn logs chứa payload; trace sampling và redaction có thể giảm dữ liệu thu thập.

### Thiết kế

1. Structured logging với allowlist field; không log token, password, signed URL hoặc request body mặc định.
2. Pseudonymous subject/tenant identifier khi cần điều tra.
3. Security audit lưu ở project/account riêng với quyền append/read tách biệt.
4. Application logs/traces có retention ngắn hơn audit nếu mục đích cho phép.
5. Export/archive theo policy và xóa tự động khi hết hạn.
6. Backup có retention theo RPO/RTO, immutable theo tier và có restore test.
7. Data access và export log được audit.

### Xử lý yêu cầu erasure

Nếu log chứa định danh của subject, tìm theo correlation/reference được phép và áp redaction hoặc deletion theo chính sách. Nếu log bất biến theo yêu cầu bảo toàn, đánh giá legal basis và phương án giảm khả năng truy cập; không tự xóa audit evidence cần giữ. Tránh thiết kế log mới có PII để giảm việc phải truy tìm/xóa sau này.

## 20. Quy trình triển khai retention policy trong cloud

1. **Governance:** chỉ định data owner, policy owner, privacy/legal reviewer và system owner.
2. **Inventory:** thống kê datasets, copies, consumers, processor, backup và region.
3. **Classification:** xác định sensitivity, purpose, subject và criticality.
4. **Policy mapping:** xây retention schedule, deletion rule, legal hold và exception.
5. **Architecture mapping:** xác định database, object, cache, search, event, analytics và backup controls.
6. **Automation:** xây retention engine, deletion orchestrator, tombstone/outbox và policy-as-code.
7. **Approval:** dry-run, manifest, sample review và phê duyệt.
8. **Execution:** chạy canary, batch, idempotent retry và theo dõi consumer.
9. **Verification:** kiểm tra active store, residual copy, backup expiry và processor acknowledgment.
10. **Evidence:** ghi audit, report, exception và completion criteria.
11. **Review:** đánh giá định kỳ policy drift, luật/hợp đồng mới, dữ liệu mới và thay đổi kiến trúc.

## 21. Kiểm thử retention và deletion

| Bài thử | Mô phỏng | Kỳ vọng |
| --- | --- | --- |
| Retention expiry | Record vượt retention end date | Được chọn đúng trong dry-run và xử lý theo policy |
| Incorrect trigger | Thiếu/nhầm closedAt/createdAt | Không xóa hàng loạt; đưa vào exception |
| Legal hold | Object/record có hold | Không bị lifecycle/deletion worker xóa |
| Soft delete | Đánh dấu deleted | Không xuất hiện trong API thường nhưng trạng thái purge minh bạch |
| Cross-system deletion | Xóa source và phát tombstone | Cache/search/analytics/processor được theo dõi |
| Duplicate command | Gửi deletion event nhiều lần | Xử lý idempotent, không ảnh hưởng resource khác |
| Out-of-order event | Update tới sau delete | Không tái tạo dữ liệu đã bị xóa theo policy |
| Processor outage | Third-party API không phản hồi | Retry/backoff, trạng thái pending và alert |
| Backup restore | Restore point cũ có record đã xóa | Deletion ledger được áp lại trước khi mở hệ thống |
| Immutable backup | Request xóa khi backup đang lock | Không bypass lock; exception/expiry được ghi rõ |
| Tenant boundary | Request xóa subject của tenant khác | Bị chặn nếu không có authority |
| Anonymization | Thay direct identifiers | Kiểm tra re-identification/linkability |
| Key deletion | Hủy encryption key | Chỉ áp dụng sau dependency/hold/backup review |
| Evidence integrity | Thử sửa/xóa audit record | Bị ngăn hoặc có cảnh báo độc lập |
| Policy change | Giảm retention | Có approval, effective date và impact report |
| Bulk deletion | Hàng triệu record đủ điều kiện | Có quota, checkpoint, canary, pause/resume |

### Test restore là một phần của deletion test

Tạo backup trước yêu cầu xóa, sau đó xóa source và thực hiện restore vào môi trường cô lập. Kiểm tra deletion ledger có được phát lại trước khi ứng dụng mở read/write hay không. Đây là cách chứng minh dữ liệu đã xóa không tự quay lại sau disaster recovery.

### Test failure giữa chừng

Ngắt deletion worker sau khi source đã xóa nhưng trước khi cache/search xử lý. Khi worker chạy lại, nó phải tiếp tục từ trạng thái từng consumer, không bỏ sót và không mở rộng scope. Test cả broker duplicate, DLQ, policy version thay đổi và tenant suspension.

## 22. Những sai lầm thường gặp

1. **Không có data inventory:** không biết bản sao nằm ở log, export, search, backup hay processor nào.
2. **Retention “vô thời hạn” vì tiện:** tăng rủi ro privacy, chi phí và phạm vi sự cố.
3. **Retention không có trigger:** không xác định được khi nào bắt đầu/kết thúc thời hạn.
4. **Dùng một retention cho mọi dataset:** bỏ qua purpose, classification và nghĩa vụ khác nhau.
5. **Soft delete được xem là erasure:** dữ liệu vẫn còn và có thể truy cập qua đường khác.
6. **Xóa source nhưng quên replica/cache/index:** subject data vẫn hiện ở hệ thống phụ.
7. **Không có tombstone/outbox:** downstream không nhận được deletion event.
8. **Không xử lý duplicate/out-of-order event:** dữ liệu đã xóa có thể được tái tạo.
9. **Restore backup mà không áp deletion ledger:** dữ liệu bị xóa xuất hiện trở lại.
10. **Coi pseudonymization là anonymization:** mapping hoặc quasi-identifier vẫn cho phép nhận diện.
11. **Gọi key deletion là xóa dữ liệu:** vẫn có plaintext copy/key backup hoặc mất dữ liệu ngoài phạm vi.
12. **Lifecycle rule không xét legal hold:** xóa hồ sơ cần bảo toàn.
13. **Một role vừa đổi policy vừa xóa dữ liệu:** thiếu separation of duties.
14. **Không inventory dev/staging/export:** bản sao ngoài production bị bỏ sót.
15. **Không track third-party processor:** chỉ gửi API delete nhưng không xác nhận kết quả.
16. **Metric/log lưu PII quá mức:** tạo thêm dataset phải quản trị và xóa.
17. **Tuyên bố physical deletion tức thời:** vượt quá semantics và bằng chứng của cloud storage.
18. **Không có deletion evidence:** không thể chứng minh ai đã làm gì và ngoại lệ nào còn tồn tại.
19. **Không test failure giữa chừng:** orchestration bị kẹt hoặc hoàn tất sai khi consumer outage.
20. **Không review policy drift:** cấu hình cloud thực tế khác retention schedule đã duyệt.

## 23. Bài tập thực hành và đáp án định hướng

Một nền tảng quản lý thuê tài sản lưu hồ sơ người thuê, hợp đồng, invoice, lịch sử thanh toán, log hỗ trợ và file đính kèm. Dữ liệu được lưu ở shared database, object storage có versioning, search index, event broker, analytics warehouse và backup. Một khách hàng yêu cầu xóa tài khoản. Một invoice còn trong retention đã phê duyệt; một hợp đồng đang có legal hold; một email đã được gửi sang processor bên ngoài.

### Câu 1 — Cần hỏi gì trước khi xóa?

**Đáp án định hướng:** Xác minh danh tính/authority; canonical subject ID và alias; mục đích và phạm vi request; data inventory/lineage; owner của invoice/contract; retention rule/trigger; legal hold; processor/subprocessor; backup policy; dữ liệu chung ảnh hưởng người khác.

### Câu 2 — Có xóa invoice cùng tài khoản không?

**Đáp án:** Không tự động. Invoice còn trong retention được phê duyệt có thể phải giữ. Cần chỉ giữ phần dữ liệu bắt buộc, giới hạn truy cập và audit; phần không còn mục đích có thể xóa/ẩn danh theo policy. Ghi rõ ngoại lệ và thời điểm xem xét lại.

### Câu 3 — Hợp đồng đang legal hold được xử lý thế nào?

**Đáp án:** Giữ đúng object/version trong phạm vi hold, hạn chế quyền đọc và ngăn lifecycle/deletion worker xóa. Việc gỡ hold cần owner, approval và audit theo quy trình.

### Câu 4 — Làm thế nào xử lý search và cache?

**Đáp án:** Phát deletion/tombstone event có scope, consumer invalidate cache key và xóa search document. Dùng event ID/idempotency, theo dõi kết quả từng consumer và xác minh query/count/facet không còn hiển thị record.

### Câu 5 — Backup vẫn chứa hồ sơ thì phản hồi sao?

**Đáp án:** Áp dụng chính sách backup đã công bố: backup bị cô lập, không dùng vận hành thường ngày, giữ tới ngày hết recovery retention; mọi restore phải áp deletion ledger trước khi mở hệ thống. Nêu ngoại lệ/khoảng tồn tại còn lại chính xác, không tuyên bố đã xóa vật lý tức thời.

### Câu 6 — Processor email cần làm gì?

**Đáp án:** Xác định dữ liệu thực sự được gửi và mục đích. Nếu processor lưu contact hoặc event cần xóa, gửi request qua workflow/contract đã thỏa thuận, theo dõi acknowledgment và các subprocessor. Không gửi toàn bộ hồ sơ nếu chỉ cần xóa một recipient/profile.

### Câu 7 — Làm sao kiểm tra deletion worker không xóa nhầm tenant?

**Đáp án:** Deletion plan lấy tenant scope từ trusted identity/subject mapping; worker chỉ có quyền trong scope được cấp. Test tenant A yêu cầu xóa ID của tenant B, xác minh bị từ chối và không có side effect ở database/object/search.

### Câu 8 — Có thể dùng pseudonymization cho analytics và đánh dấu đã anonymize không?

**Đáp án:** Chưa đủ. Nếu mapping hoặc quasi-identifiers còn cho phép re-identification, dữ liệu vẫn có thể liên kết tới cá nhân. Cần đánh giá dataset combination, small groups, free text và access tới mapping; chỉ gọi anonymous khi đánh giá cho thấy không còn khả năng nhận diện hợp lý trong bối cảnh áp dụng.

## 24. Checklist review chính sách lưu giữ và quyền riêng tư

- Có data inventory với owner, purpose, subject, location và lineage không?
- Dữ liệu production, dev/test, log, export, backup và third-party copies đã nằm trong inventory chưa?
- Classification và data minimization có được thực hiện ở thời điểm thiết kế không?
- Retention schedule có trigger, duration, scope, exception, owner và action không?
- Legal hold có registry, role, approval và audit riêng không?
- Soft delete, hard delete và physical deletion được mô tả đúng semantics của từng storage không?
- Data subject request có identity/authority verification và workflow tracking không?
- Deletion plan có dry-run, manifest, approval, canary và idempotent execution không?
- Database, cache, search, event, object, analytics, export và processor có consumer/deletion path không?
- Backup có retention và quy trình áp lại deletion ledger khi restore không?
- Immutable backup/retention có xử lý conflict với erasure theo policy không?
- Anonymization có đánh giá linkability, quasi-identifiers và re-identification risk không?
- Encryption/key lifecycle có hỗ trợ recovery và crypto-erasure theo phạm vi hợp lệ không?
- Region, replication, telemetry, support access và subprocessor có trong data flow map không?
- IAM, separation of duties, approval và audit bảo vệ thao tác xóa/policy change chưa?
- IaC/policy-as-code có guardrail và drift detection không?
- Evidence có operation ID, policy version, result từng system và exception không?
- Có SLA deletion, processor confirmation và backup expiry được truyền đạt rõ không?
- Có test restore sau deletion, failure giữa chừng, duplicate/out-of-order và cross-tenant không?
- Có owner/runbook để xử lý legal hold, request, processor outage và policy drift không?

## 25. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Retention/deletion workflow có hoàn tất đúng, retry được và không làm dữ liệu cần giữ bị mất không? | State machine, outbox, idempotency, backup restore drill |
| **Bảo mật** | Dữ liệu được giữ tối thiểu, truy cập theo least privilege và deletion/audit được bảo vệ không? | Classification, IAM, encryption, immutable audit, approval |
| **Hiệu năng** | Search subject, export, deletion batch và reconcile có đáp ứng SLA mà không gây tải đột biến không? | Index, batch size, queue lag, rate limit, execution metrics |
| **Tối ưu chi phí** | Có bản sao/retention không cần thiết, log quá chi tiết hoặc backup giữ quá lâu không? | Inventory, storage lifecycle, cost per dataset, processor usage |
| **Vận hành xuất sắc** | Đội ngũ có biết dữ liệu ở đâu, policy nào áp dụng và chứng minh kết quả không? | Data catalog, retention engine, runbook, evidence, audit |
| **Tính bền vững** | Dữ liệu có được thu thập tối thiểu, giữ đúng mục đích và xóa đúng thời điểm không? | Purpose mapping, minimization, retention schedule, deletion proof |

Chính sách lưu giữ, xóa dữ liệu và quyền riêng tư cần được thiết kế cùng nhau. **Inventory cho biết dữ liệu nằm ở đâu; classification và purpose xác định dữ liệu cần được bảo vệ thế nào; retention xác định khi nào được giữ; deletion orchestration bảo đảm xử lý các bản sao; audit evidence chứng minh kết quả và ngoại lệ.** Một kiến trúc cloud đáng tin phải phục hồi được khi có sự cố, nhưng cũng phải biết ngừng lưu dữ liệu khi mục đích và nghĩa vụ giữ đã kết thúc.

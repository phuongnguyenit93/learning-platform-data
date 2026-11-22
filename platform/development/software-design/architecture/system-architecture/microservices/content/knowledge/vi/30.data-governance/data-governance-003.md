# Thời gian lưu, xóa dữ liệu và xử lý các bản sao dẫn xuất trong Microservices

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **data retention** (thời gian lưu), **data deletion/erasure** (xóa dữ liệu) và **derived data** (dữ liệu dẫn xuất) trong kiến trúc microservices.
2. Xây dựng danh mục dữ liệu và quy tắc vòng đời theo **loại dữ liệu, mục đích sử dụng, quyền sở hữu và yêu cầu nghiệp vụ/pháp lý**.
3. Thiết kế việc xóa dữ liệu xuyên nhiều service mà không cần distributed transaction toàn hệ thống.
4. Phân biệt soft delete, hard delete, anonymization, pseudonymization, tombstone, TTL và crypto-erasure cùng giới hạn từng cách.
5. Quản lý bản sao trong cache, search index, event stream, data warehouse, object storage, log, bản sao lưu và hệ thống bên thứ ba.
6. Thiết kế quy trình đáng tin cậy dựa trên deletion request, outbox/event, idempotent consumer, retry, đối soát và bằng chứng hoàn tất.
7. Giám sát **deletion lag**, retention violations, các yêu cầu đang mắc kẹt, cũng như phục hồi an toàn khi backup/restore hoặc service lỗi.

Bối cảnh: trong microservices, một thông tin có thể tồn tại ở nhiều nơi với nhiều hình thức. Xóa một hàng trong database của service gốc **không đồng nghĩa** dữ liệu ấy đã biến mất khỏi toàn bộ hệ sinh thái.

## 1. Vì sao quản lý vòng đời dữ liệu khó hơn khi dùng microservices?

Giả sử Customer Service sở hữu hồ sơ khách hàng: tên, email và địa chỉ. Khi khách mua hàng, các microservice khác có thể tạo những bản dữ liệu phục vụ mục đích riêng:

~~~text
                           Customer Service
                              Customer DB
                                  |
                    +-------------+-------------+
                    |             |             |
                    v             v             v
              API response   Customer event   CDC / Outbox
                    |             |             |
                    v             v             v
             Gateway cache   Order Service   Data Platform
                    |         snapshot DB       |
                    v             |             +--> Warehouse
              Browser cache       +--> Search   +--> BI reports
                                  |             +--> ML features
                                  v
                              Notification
                              provider
~~~

Một record khách hàng có thể xuất hiện trong:
- **Dữ liệu chuẩn (source of truth)** của Customer Service.
- **Snapshot nghiệp vụ** trong Order Service để hiển thị lịch sử giao dịch.
- **Redis/Caffeine cache**, API gateway/CDN và thiết bị client.
- **Search index** chứa document phi chuẩn hóa.
- **Event broker**, outbox, CDC log, dead-letter queue và kho replay.
- **Object storage** chứa file đính kèm, ảnh, báo cáo xuất hoặc tài liệu.
- **Data warehouse, data lake, analytical mart** và tập dữ liệu thử nghiệm.
- **Feature store, embedding/vector index, bản tổng hợp** hoặc mô hình được huấn luyện trên dữ liệu.
- **Logs/traces, bản dump, snapshot, backup và hệ thống bên thứ ba**.

Các nơi này có owner, thời hạn lưu, cơ chế xóa và mức nhất quán khác nhau. Do đó, nhu cầu “xóa khách hàng X” là một **quy trình phân tán có trạng thái**, không phải một câu lệnh SQL DELETE duy nhất.

### Các câu hỏi phải trả lời

1. Dữ liệu nào đang được lưu, ở đâu, do service nào chịu trách nhiệm?
2. Mục đích lưu từng loại dữ liệu là gì và giữ trong bao lâu?
3. Khi nào dữ liệu đủ điều kiện xóa, khi nào cần giữ do nghĩa vụ hợp lệ?
4. Những bản sao có thể tìm và xóa bằng định danh nào?
5. Nếu event bị trễ, một service down, cache mất kết nối hoặc backup được restore thì dữ liệu cũ có tái xuất hiện không?
6. Làm sao chứng minh các hành động đã hoàn tất, không chỉ “đã gửi lệnh xóa”?

Không nhất thiết mọi dữ liệu mang cùng hạn lưu. Ví dụ thông tin marketing có thể phải xóa sớm hơn một hồ sơ giao dịch cần giữ để đối soát hoặc tuân thủ. **Chính sách cụ thể phải được xác định từ yêu cầu áp dụng cho tổ chức và khu vực pháp lý liên quan**, không được tự suy luận một thời hạn cố định cho mọi hệ thống.

## 2. Thuật ngữ và ranh giới quan trọng

| Khái niệm | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| Retention policy | Quy tắc giữ dữ liệu bao lâu và vì mục đích gì | Có thể khác theo loại bản ghi hoặc khu vực |
| Retention period | Khoảng thời gian được phép/cần lưu | Phải định nghĩa mốc bắt đầu và điều kiện kết thúc |
| Deletion | Loại bỏ dữ liệu khỏi một hệ thống | Không bảo đảm mọi bản sao khác cũng đã xóa |
| Erasure | Làm dữ liệu không còn khả dụng theo nghĩa được yêu cầu | Phạm vi và bằng chứng phụ thuộc công nghệ/chính sách |
| Soft delete | Đánh dấu bản ghi là đã xóa | Dữ liệu vật lý thường vẫn còn |
| Hard delete | Xóa bản ghi/đối tượng khỏi lưu trữ hoạt động | Có thể vẫn hiện diện trong snapshot và backup |
| Anonymization | Biến đổi để không thể xác định cá nhân theo tiêu chuẩn áp dụng | Phải đánh giá nguy cơ tái định danh thực tế |
| Pseudonymization | Thay định danh bằng mã thay thế | Vẫn có thể liên kết lại nếu còn khóa/bảng ánh xạ |
| Tombstone | Dấu hiệu một đối tượng/khóa đã bị xóa | Thường dùng cho đồng bộ, CDC hoặc log compacted |
| Data lineage | Mối quan hệ nguồn → bản sao/biến đổi | Giúp xác định tác động của một lệnh xóa |
| Legal hold | Tạm ngừng xóa khi có căn cứ giữ dữ liệu hợp lệ | Cần phê duyệt, phạm vi và thời hạn xem xét |
| Deletion SLA/SLO | Mục tiêu xử lý xóa trong một khoảng thời gian | Nên phân biệt xóa online với backup |
| Data minimization | Chỉ thu thập và lưu dữ liệu cần thiết | Giảm chi phí và rủi ro trước cả khi phải xóa |

### Không coi soft delete là xóa hoàn tất

~~~sql
UPDATE customer
SET deleted_at = now()
WHERE customer_id = :id;
~~~

Lệnh này có thể hữu ích để ngăn sử dụng dữ liệu hoặc bắt đầu một workflow. Tuy nhiên, email, địa chỉ và các trường nhạy cảm **vẫn còn trong bảng**, có thể còn trong index, audit log, backup và quyền truy cập của những tác nhân khác. Nếu nghĩa vụ yêu cầu xóa thực sự, chỉ đặt deleted_at thường chưa đủ.

### Anonymization không phải mã hóa/đổi ID đơn giản

Thay email bằng một hash có thể vẫn cho phép xác định lại qua từ điển giá trị hoặc liên kết với bảng khác. Pseudonymization giảm mức tiếp xúc nhưng dữ liệu có thể vẫn là thông tin cá nhân theo khuôn khổ áp dụng. Anonymization cần xét khả năng kết hợp nhiều thuộc tính, tần suất cập nhật, dữ liệu phụ trợ và khả năng tái định danh.

## 3. Tạo danh mục dữ liệu trước khi viết chức năng xóa

Bước nền tảng là **data inventory**: một danh sách đủ dùng về nơi dữ liệu được tạo, lưu, truyền, biến đổi và cung cấp cho bên thứ ba.

Một bản ghi inventory nên có:

~~~text
data_asset_id
data_category
system_or_service_owner
physical_location
data_subject_or_business_key
purpose
source_of_truth
derived_from
retention_basis
retention_trigger
retention_period
legal_hold_rule
deletion_mechanism
downstream_consumers
backup_policy
evidence_owner
~~~

Ví dụ:

| Data asset | Owner | Nguồn gốc | Mục đích | Hướng xử lý khi hết hạn |
| --- | --- | --- | --- | --- |
| customer.profile | Customer Service | Người dùng cung cấp | Quản lý tài khoản | Xóa/ẩn danh theo chính sách sau khi kiểm tra hold |
| order.customer_snapshot | Order Service | Snapshot từ profile lúc đặt hàng | Lịch sử giao dịch | Giữ phần cần thiết hoặc xóa trường không còn cần |
| search.customer_document | Search Service | Event từ Customer | Tra cứu nội bộ | Xóa document và ngăn tái lập từ event cũ |
| cache.customer:key | Customer Service | Bản sao từ DB | Tăng tốc truy vấn | Evict và TTL dự phòng |
| analytics.customer_dimension | Data Platform | CDC/ETL | Phân tích | Xóa/ẩn danh trên các bảng, partition và view liên quan |
| export.customer.csv | Reporting | Truy vấn xuất | Phục vụ nghiệp vụ cụ thể | Đặt expiry, kiểm soát chia sẻ và xóa file |
| customer-backup | Platform/SRE | Snapshot hệ thống | Phục hồi sự cố | Hết hạn theo lịch backup, kiểm soát restore |

Bảng chỉ minh họa. Cần xác định chính sách retention thực tế của mỗi asset từ dữ liệu và nghĩa vụ nghiệp vụ, không áp dụng ngầm cùng một thời gian lưu cho tất cả.

### Quyền sở hữu dữ liệu không đồng nghĩa quyền xóa tùy ý

Mỗi service sở hữu schema của mình, nhưng quyết định một dữ liệu có được xóa hay phải giữ có thể thuộc chính sách chung, người quản trị dữ liệu, pháp chế, bảo mật hoặc người được ủy quyền. Service **thực thi chính sách trong ranh giới dữ liệu mà nó sở hữu**, còn một bộ điều phối theo dõi yêu cầu xuyên nhiều owner.

Nếu service khác đang đọc trực tiếp database của Customer Service, cơ chế xóa khó kiểm soát vì dependency không hiển thị qua API/event. Cần đưa các đường chia sẻ dữ liệu vào inventory và dần thay bằng hợp đồng tích hợp được quản lý.

## 4. Retention policy cần mô tả đầy đủ vòng đời

Một retention policy hữu ích có thể được đọc như:

> Với nhóm dữ liệu X, phục vụ mục đích Y, được lưu tối đa hoặc ít nhất theo chính sách P tính từ sự kiện T; khi hết thời hạn và không có hold hợp lệ, thực hiện hành động A trong thời hạn vận hành D, đồng thời xử lý các bản sao B và lưu bằng chứng E.

Một số điều kiện phải được ghi rõ:
- **Retention trigger:** ngày thu thập, ngày giao dịch kết thúc, ngày tài khoản đóng, ngày hợp đồng chấm dứt, ngày hết hiệu lực hay thời điểm có yêu cầu xóa.
- **Retention duration:** khoảng lưu tối thiểu/tối đa áp dụng cho dữ liệu ấy.
- **Timezone và độ chính xác:** lịch theo ngày nghiệp vụ hay timestamp UTC; tránh sai khi DST thay đổi.
- **Eligibility predicate:** điều kiện xóa: hết hạn, không còn hold, không nằm trong một giao dịch chưa kết thúc.
- **Action:** hard delete, redaction, anonymization, aggregate-only, archive được kiểm soát hoặc chặn truy cập.
- **Derivative propagation:** các hệ thống nhận bản sao cần thực hiện hành động gì.
- **Evidence:** lưu ID yêu cầu, trạng thái, phiên bản policy và thời điểm hoàn tất, tránh lưu lại chính nội dung đã xóa.
- **Exception:** trường hợp tạm hoãn, phê duyệt và lịch xét lại.

Không dùng một cột “retention_days” mà không biết **đếm từ thời điểm nào**. Ví dụ 365 ngày từ ngày tạo đơn và 365 ngày từ ngày đơn hoàn tất là hai chính sách rất khác nhau nếu một đơn được xử lý kéo dài.

## 5. Phân loại dữ liệu theo mục đích và mức rủi ro

Trước khi tính thời gian lưu, nên nhóm dữ liệu theo mục đích. Một sơ đồ minh họa:

1. **Dữ liệu giao dịch cần tính toàn vẹn:** hóa đơn, ledger, thanh toán. Có thể có nghĩa vụ lưu và yêu cầu kiểm toán; xóa nhầm sẽ làm sai sổ sách.
2. **Dữ liệu hồ sơ và định danh:** tên, email, địa chỉ, số điện thoại. Nhiều trường có thể không còn cần sau khi tài khoản bị đóng.
3. **Dữ liệu vận hành ngắn hạn:** session, access logs, traces, request bodies. Nên có TTL phù hợp để hạn chế dữ liệu nhạy cảm tồn tại ngoài mục đích.
4. **Dữ liệu phân tích:** aggregate, cohort, raw event, feature. Cần chứng minh mục đích, thời hạn và khả năng xóa các bản sao chứa định danh.
5. **Dữ liệu lưu trữ và phục hồi:** snapshot, backup, object versions. Cần vòng đời riêng, giới hạn truy cập và quy trình không tái lộ sau restore.

**Một thực thể nghiệp vụ không đồng nghĩa một chính sách xóa duy nhất.** Khi người dùng yêu cầu xóa tài khoản, có thể cần loại bỏ hồ sơ liên hệ trong Customer Service nhưng giữ lại một phần hồ sơ giao dịch đã được tối thiểu hóa hoặc ẩn danh nếu có căn cứ lưu phù hợp. Ngược lại, việc “giữ tất cả dữ liệu vì có hóa đơn” cũng không tự động hợp lệ. Từng trường và mục đích phải được phân tích riêng.

## 6. Mô hình vòng đời dữ liệu

~~~text
COLLECT / GENERATE
       |
       v
ACTIVE --update--> ACTIVE
       |
       +--> REPLICATED / DERIVED
       |           |
       |           +--> CACHE / INDEX / WAREHOUSE / EXPORT / BACKUP
       |
       v
RETAINED (được dùng theo mục đích)
       |
       +--> HOLD (tạm hoãn hành động đủ điều kiện)
       |
       v
ELIGIBLE_FOR_DELETION
       |
       v
RESTRICTED / TOMBSTONED
       |
       v
DELETION_IN_PROGRESS
       |
       +--> RETRY / RECONCILE
       |
       v
ACTIVE_COPIES_REMOVED
       |
       v
BACKUP_EXPIRY / RESTORE_GUARD
       |
       v
VERIFIED_CLOSED
~~~

Đây là state machine khái niệm, không phải tất cả dữ liệu đều phải đi qua từng trạng thái. **Tombstone** có thể được giữ để ngăn một event cũ tạo lại dữ liệu đã xóa. **Verified closed** cần nêu rõ phạm vi: bản sao online đã xóa, các hệ thống bên thứ ba đã xác nhận, và backup còn đợi hết chu kỳ theo chính sách.

Không ghi “mọi byte bị xóa vĩnh viễn” nếu hệ thống không thể chứng minh điều đó; mức cam kết phải tương ứng năng lực công nghệ và nghĩa vụ đang áp dụng.

## 7. Hai nguyên nhân kích hoạt xóa: hết hạn và yêu cầu cụ thể

### 7.1 Retention expiration

Một tác vụ định kỳ kiểm tra dữ liệu đã vượt thời hạn theo policy và đưa vào pipeline xóa.

Ví dụ một bản ghi tạm có expires_at:

~~~sql
SELECT id
FROM temporary_upload
WHERE expires_at <= now()
  AND deleted_at IS NULL
ORDER BY expires_at
LIMIT 1000;
~~~

Sau khi chọn, job cần xử lý xung đột và tính đúng đắn, ví dụ dữ liệu vừa được gia hạn, đang có một giao dịch cập nhật hoặc yêu cầu legal hold phát sinh. Điều kiện hợp lệ phải được kiểm tra trong bước thay đổi trạng thái thực tế.

### 7.2 Deletion request

Một yêu cầu cụ thể có thể tới từ người dùng, bộ phận vận hành, hệ thống quyền riêng tư hoặc quyết định nội bộ hợp lệ. Quy trình cần xác thực danh tính, quyền yêu cầu, phạm vi dữ liệu, căn cứ giữ dữ liệu còn hiệu lực và kỳ hạn trả lời theo quy định áp dụng.

Yêu cầu có thể đi qua API:

~~~http
POST /internal/data-lifecycle/deletion-requests
Content-Type: application/json
Idempotency-Key: delete-customer-123-request-456

{
  "subjectType": "CUSTOMER",
  "subjectId": "123",
  "reason": "ACCOUNT_CLOSURE",
  "policyVersion": "2026.11"
}
~~~

Ví dụ endpoint trên dành cho hệ thống nội bộ đã xác thực và phân quyền. Không nên công khai một API xóa theo ID đơn giản cho mọi người dùng mà không có xác thực yêu cầu, audit và chống lạm dụng.

**Một yêu cầu có thể được gửi lại.** Idempotency key hoặc khóa business logic phải giúp trả cùng trạng thái, không tạo nhiều workflow xóa gây tranh chấp hoặc đưa dữ liệu vào trạng thái không xác định.

## 8. Thiết kế bộ điều phối xóa dữ liệu phân tán

Trong microservices, không nên mở một database transaction kéo dài giữa Customer, Order, Search, Analytics và Notification. Thay vào đó, dùng một **deletion coordinator** giữ trạng thái yêu cầu, phát lệnh cho từng owner và tổng hợp kết quả.

~~~text
Authenticated Request / Retention Scheduler
                    |
                    v
             Deletion Coordinator
          (request ID, scope, status)
                    |
                    v
           Transactional Outbox
                    |
                    v
          Durable Event / Command Bus
             /        |         \
            v         v          v
      Customer     Search      Analytics
      Service      Service      Pipeline
          |          |             |
          v          v             v
      Delete DB  Delete docs  Purge / redact
          |          |             |
          +----------+-------------+
                     |
                     v
                ACK / STATUS
                     |
                     v
             Reconcile / Close
~~~

**Coordinator** không được tự truy cập và xóa trực tiếp mọi database nếu điều đó làm vi phạm ownership hoặc khiến logic nghiệp vụ của service bị bỏ qua. Tốt hơn là gửi command/event đã định nghĩa và để mỗi service xử lý phần dữ liệu mình sở hữu.

### Các giai đoạn minh họa

1. **Validate:** xác định request hợp lệ, quyền, phạm vi, chính sách và các hold cần áp dụng.
2. **Register:** tạo deletion_request bền vững theo khóa duy nhất.
3. **Restrict:** đánh dấu hoặc chặn sử dụng dữ liệu cần xóa để tránh tiếp tục phát sinh bản sao trong lúc cleanup.
4. **Dispatch:** tạo lệnh theo từng service/asset, phát qua outbox/broker.
5. **Execute:** mỗi owner xóa, ẩn danh hoặc giữ có lý do theo chính sách được phê duyệt.
6. **Acknowledge:** ghi nhận kết quả từng step, lỗi và thời điểm xác nhận.
7. **Reconcile:** truy vấn đối soát định kỳ, xử lý command bị mất hoặc dịch vụ down.
8. **Close:** chỉ kết thúc khi phạm vi đã xác nhận; báo rõ những bản sao còn theo vòng đời backup hoặc ngoại lệ hợp lệ.

Có thể xem workflow này là một **saga** có các bước bất đồng bộ. Khác với đặt hàng, nhiều thao tác xóa không thể “hoàn tác” bằng cách tạo lại dữ liệu; vì thế trạng thái và khả năng phục hồi thường quan trọng hơn compensation theo nghĩa đảo ngược.

## 9. Mô hình dữ liệu cho deletion request

Một cấu trúc PostgreSQL minh họa:

~~~sql
CREATE TABLE deletion_request (
    request_id UUID PRIMARY KEY,
    subject_type VARCHAR(50) NOT NULL,
    subject_ref VARCHAR(200) NOT NULL,
    reason VARCHAR(100) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    deadline_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE deletion_step (
    request_id UUID NOT NULL REFERENCES deletion_request(request_id),
    target_service VARCHAR(100) NOT NULL,
    asset_type VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_code VARCHAR(100),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (request_id, target_service, asset_type)
);
~~~

Trong production, **subject_ref** nên là ID nội bộ tối thiểu, có kiểm soát truy cập; không nên sao chép email, số giấy tờ hoặc địa chỉ vào bảng điều phối chỉ để debug. Bảng điều phối cũng là một data asset cần retention policy riêng.

Các trạng thái ví dụ: RECEIVED, VALIDATED, RESTRICTED, IN_PROGRESS, PARTIALLY_COMPLETED, BLOCKED_BY_HOLD, COMPLETED, FAILED_REQUIRES_REVIEW. Tránh có trạng thái “SUCCESS” chung khi mới gửi event mà chưa có xác nhận từ các consumer liên quan.

### Lưu evidence thay vì lưu lại dữ liệu đã xóa

Có thể lưu:
- Request ID và loại yêu cầu.
- Mốc thời gian các step.
- Phiên bản policy và service version thực thi.
- Kết quả PASS/FAILED/HELD/SKIPPED_WITH_REASON.
- Thông tin artifact và cơ chế đối soát.
- Người hoặc hệ thống phê duyệt ngoại lệ.

Hạn chế lưu payload gốc, trước/sau của trường nhạy cảm hoặc raw request body vào audit log. Nếu evidence cần liên kết ID nhạy cảm, phải có chính sách phân quyền, mã hóa và thời hạn lưu của chính evidence đó.

## 10. Event/command xóa dữ liệu và tính idempotent

Một message có thể biểu diễn yêu cầu xóa dữ liệu với scope rõ ràng:

~~~json
{
  "eventId": "d851b9f0-5bc0-4fd3-b1b6-278ce37cded6",
  "eventType": "CustomerDeletionRequested",
  "schemaVersion": 1,
  "requestId": "be7cae80-2d95-40b5-a13f-7d51132cc958",
  "subjectType": "CUSTOMER",
  "subjectRef": "customer-123",
  "policyVersion": "2026.11",
  "occurredAt": "2026-11-12T02:00:00Z"
}
~~~

Ví dụ thời gian và ID chỉ mang tính minh họa. Event nên chứa **reference tối thiểu** thay vì toàn bộ hồ sơ cần xóa; việc đưa email/địa chỉ vào deletion event có thể vô tình tạo thêm một bản sao PII trong broker, DLQ, monitoring và data lake.

### At-least-once và duplicate message

Message broker thường có thể gửi lại message sau timeout hoặc crash. Consumer phải idempotent: xử lý cùng request/event nhiều lần không gây tác động khác so với một lần xử lý đúng.

Ví dụ ghi marker xử lý trong **cùng transaction** với thao tác DB:

~~~sql
CREATE TABLE processed_deletion (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Consumer thử INSERT marker rồi xóa các bản ghi thuộc phạm vi trong cùng transaction. Nếu event_id đã được xử lý, trả ACK theo chính sách, không chạy lại side effect không cần thiết. Tuy nhiên, chỉ dựa vào event_id không ngăn một yêu cầu xóa logic được gửi với **event_id mới**; cần ổn định theo request_id/subject/action ở tầng nghiệp vụ.

Với việc xóa object storage hay search index ngoài DB transaction, marker trong DB chưa tạo atomicity với hệ thống ngoài. Thiết kế step có thể retry an toàn, ví dụ DELETE một object/document không còn tồn tại được xem là đã đạt postcondition, sau khi xác minh đối tượng và phạm vi đúng.

### Thứ tự sự kiện và nguy cơ tái tạo dữ liệu

~~~text
T1: CustomerUpdated(version=7) được gửi nhưng chậm
T2: CustomerDeletionRequested(version=8) được xử lý
T3: Search index xóa document
T4: CustomerUpdated(version=7) tới muộn
T5: Search consumer tạo lại document từ event cũ
~~~

Nếu không có version/tombstone, dữ liệu đã xóa có thể xuất hiện trở lại. Giải pháp:
- Mỗi entity có lifecycle version/generation hoặc sự kiện xóa có version đủ để xác định ordering.
- Search/derived-data consumer lưu tombstone hoặc kiểm tra trạng thái nguồn khi nhận update cũ.
- Không chấp nhận event version thấp hơn trạng thái đã ghi nhận.
- Có snapshot/replay policy nhận biết dữ liệu đã bị xóa, không tự tái tạo từ log cũ.

Tombstone tự nó cũng cần thời gian lưu phù hợp; dọn tombstone quá sớm trong khi event cũ còn được replay có thể phá ràng buộc chống tái tạo.

## 11. Transactional outbox để không mất lệnh xóa

Nếu coordinator cập nhật deletion_request trong database rồi publish event trực tiếp, có thể xảy ra:

~~~text
DB COMMIT deletion_request = IN_PROGRESS
               |
               X Broker publish thất bại
               |
        Không service nào nhận lệnh
~~~

**Transactional outbox** ghi trạng thái và outbox event trong cùng database transaction. Một dispatcher đọc outbox, gửi sang broker và đánh dấu đã phát. Dispatcher vẫn có thể gửi trùng nếu crash sau publish nhưng trước khi đánh dấu, do đó consumer cần idempotency.

Ví dụ schema tối giản:

~~~sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
~~~

Trong transaction tạo deletion_request, đồng thời thêm outbox_event chứa reference tối thiểu. Sau khi commit, dispatcher publish. Với hệ thống lớn, có thể dùng CDC/outbox relay để chuyển tiếp. Dù chọn công nghệ nào, cần metric outbox lag và đối soát message chưa phát.

Đừng giữ payload nhạy cảm dài hạn trong outbox chỉ vì “đã publish”. Bản thân outbox, CDC stream và DLQ phải có policy retention, access control và cleanup.

## 12. Thiết kế xóa dữ liệu trong database chính

Khi xóa dữ liệu ở PostgreSQL/MySQL hoặc một RDBMS tương tự, cần chú ý khóa ngoại, transaction, index, lock và chi phí xóa khối lượng lớn.

### Xóa một customer đơn lẻ

Ví dụ policy cho phép xóa bản ghi profile:

~~~sql
DELETE FROM customer_profile
WHERE customer_id = :customer_id;
~~~

Lệnh trên chỉ an toàn về nghiệp vụ nếu:
- Đã xử lý quan hệ dữ liệu được bảo vệ bằng foreign key.
- Không có legal hold hoặc trạng thái nghiệp vụ chặn xóa.
- Các writer khác không tiếp tục tạo profile cho cùng customer.
- Có kế hoạch xử lý cache, search và dữ liệu downstream.
- Các bảng audit/outbox không còn lưu payload cần xóa ngoài phạm vi cho phép.

Nếu có bảng dependent, **ON DELETE CASCADE** có thể hữu ích cho những bản ghi thực sự thuộc vòng đời parent. Nhưng bật cascade mù quáng có thể xóa nhầm giao dịch cần giữ; cần kiểm soát domain ownership và ràng buộc retention riêng.

### Xóa theo lô để tránh transaction khổng lồ

Ví dụ bảng temporary_token đã hết hạn:

~~~sql
WITH expired AS (
    SELECT id
    FROM temporary_token
    WHERE expires_at < now()
      AND legal_hold = false
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
DELETE FROM temporary_token t
USING expired e
WHERE t.id = e.id;
~~~

Đây là mẫu PostgreSQL minh họa:
- Chọn một batch nhỏ.
- Đảm bảo điều kiện hết hạn/hold được xác định tại thời điểm xử lý.
- Giữ transaction ngắn, commit giữa các batch.
- Theo dõi lock, WAL/transaction log, replication lag và thời gian hoàn thành.
- Resume sau crash thay vì dựa vào một lần DELETE hàng triệu dòng.

Nếu policy thay đổi trong khi job chạy, cần định nghĩa cách cập nhật eligibility hoặc dùng policy version được chốt. Với dữ liệu thuộc giao dịch, không đưa mọi bản ghi quá một mốc timestamp vào câu lệnh DELETE mà thiếu điều kiện nghiệp vụ.

### Partition expiration

Bảng log/event lớn có thể được phân vùng theo thời gian. Khi cả partition có cùng chính sách và không có ngoại lệ, xử lý theo partition có thể hiệu quả hơn việc xóa từng hàng. Tuy nhiên không thể drop một partition nếu một phần dữ liệu còn retention khác hoặc hold hợp lệ. Cần thiết kế partition key bám vào tiêu chí retention thực tế.

### Không nhầm DELETE với xóa byte vật lý ngay

Trong nhiều database, DELETE thay đổi trạng thái logic của bản ghi và cần thêm quá trình vacuum/compaction/page reuse để tái sử dụng không gian; backup và transaction log có vòng đời riêng. Không tuyên bố dữ liệu đã bị ghi đè vật lý ngay sau khi lệnh DELETE thành công. Mức bảo đảm xóa phải được xác định theo công nghệ, encryption và chính sách storage.

## 13. Soft delete, tombstone và chặn tạo lại dữ liệu

**Soft delete** có thể dùng như bước tạm thời để ngăn ứng dụng phục vụ dữ liệu:

~~~sql
ALTER TABLE customer_profile
ADD COLUMN deleted_at TIMESTAMPTZ;
~~~

~~~sql
UPDATE customer_profile
SET deleted_at = now()
WHERE customer_id = :customer_id
  AND deleted_at IS NULL;
~~~

Mọi query nghiệp vụ phải loại trừ bản ghi đã xóa khi thích hợp. Nhưng nếu còn một code path quên điều kiện deleted_at IS NULL, soft delete có thể vẫn lộ thông tin. Trong ORM, filter mặc định cũng không bảo vệ truy vấn raw SQL hoặc ETL đọc trực tiếp.

Một **tombstone** có thể chỉ giữ identifier và deletion generation tối thiểu để hệ thống biết dữ liệu này không được khôi phục bởi event cũ. Phải thiết kế:
- Ai được tạo hoặc cập nhật tombstone?
- Tombstone được lưu bao lâu so với retention của event, backup và replay?
- Dữ liệu còn lại trong tombstone có thể nhận diện cá nhân không?
- Khi business ID được tái sử dụng, lifecycle generation nào phân biệt thực thể cũ/mới?
- Khi hệ thống restore snapshot cũ, tombstone có được áp dụng trước khi mở traffic không?

Tombstone nên tối thiểu hóa thông tin; không cần copy lại email hoặc tên người dùng để chứng minh đã xóa.

## 14. Cache và dữ liệu dẫn xuất trong microservices

Xóa database gốc không xóa các cache đang phục vụ. Ví dụ Customer Service có ba replica, mỗi pod giữ Caffeine L1 và cùng dùng Redis L2. Khi xóa customer trong DB:
- Redis key cần bị xóa hoặc đổi version.
- Local cache trên mọi pod cần evict hoặc có TTL ngắn.
- API gateway/CDN có thể giữ response cũ.
- Frontend/mobile có thể giữ bản riêng trong memory hoặc offline storage.

~~~text
Delete customer in DB
         |
         +--> Redis invalidation
         +--> Local cache invalidation event / bounded TTL
         +--> Gateway/CDN purge where applicable
         +--> Client cache policy / session invalidation
         +--> Reconciliation to detect stale replies
~~~

### TTL là giới hạn dự phòng, không phải bảo đảm xóa tức thời

Nếu chính sách yêu cầu dữ liệu không còn được phục vụ sau thời điểm T, một TTL Redis 24 giờ không đáp ứng yêu cầu ấy khi invalidation có thể bị mất. Cần đặt giới hạn freshness, cách phát invalidation đáng tin cậy và/hoặc kiểm tra deletion status ở điểm đọc.

Với Caffeine/local cache, publish một event không bảo đảm mọi pod nhận được nếu một pod đang mất kết nối. Giải pháp có thể là versioned key, TTL ngắn, pull phiên bản hiện hành hoặc một cơ chế invalidation có khả năng bắt kịp sau reconnect.

### Race giữa xóa và cache loader

~~~text
T1 Request A cache miss, đọc DB trước khi customer bị xóa
T2 Deletion coordinator xóa customer và Redis key
T3 Request A hoàn thành đọc dữ liệu cũ
T4 Request A ghi lại dữ liệu cũ vào Redis
~~~

Để giảm rủi ro:
- Dùng version/generation và compare-and-set trước khi ghi cache.
- Kiểm tra marker đã xóa trước khi return dữ liệu nhạy cảm.
- Áp dụng invalidation sau commit kết hợp kiểm tra phiên bản.
- Có TTL hữu hạn và một job đối soát nếu cần.
- Chặn các writer/loader cũ tái nạp sau khi dữ liệu đã tombstoned.

Chỉ gọi redis.del một lần sau DELETE không tạo bảo đảm tuyệt đối nếu còn request đang bay.

## 15. Search index, read model và projection

Search Service thường dùng document chứa tên, email, địa chỉ hoặc metadata lấy từ Customer events. Một document có thể không còn trong Customer DB nhưng vẫn xuất hiện trong kết quả tìm kiếm.

Khi xử lý deletion event:
1. Tìm tất cả document theo **stable subject ID** hoặc mapping đã lưu.
2. Delete hoặc redact các trường theo policy.
3. Xác nhận thay đổi đã được index/refresh ở mức mà API tìm kiếm thực sự không trả lại bản cũ.
4. Lưu version/tombstone để chống event cũ reindex document.
5. Quét lại bằng truy vấn đối soát với quyền và phạm vi phù hợp.
6. Cập nhật trạng thái step trong deletion_request.

Trong một số search engine, lệnh DELETE/UPDATE thành công có thể cần thời gian refresh/merge trước khi kết quả truy vấn thay đổi; công nghệ lưu trữ còn có snapshot hoặc replica. Phải định nghĩa **điều kiện đã hoàn tất theo hành vi đọc thực tế**, không chỉ HTTP 200 của API xóa.

### CQRS/read model cần vòng đời riêng

Một service khác có thể lưu bản sao hồ sơ để tránh đồng bộ call. Đó là dữ liệu dẫn xuất có owner, chứ không phải “cache vô hại”. Nếu read model được rebuild từ event store, dữ liệu đã xóa có thể quay lại nếu rebuild không áp dụng deletion marker hoặc không lọc event cũ.

Mọi luồng tái tạo projection phải hỗ trợ deletion policy, bao gồm replay từ đầu, reindex toàn bộ và disaster recovery.

## 16. Event broker, outbox, CDC và dead-letter queue

Một event có payload nhạy cảm được phát tới broker có thể tồn tại trong:
- Topic chính theo retention.
- Replicas, transaction/segment files và snapshot.
- Dead-letter topic/queue sau xử lý lỗi.
- CDC connector buffers hoặc outbox table.
- Kho lưu event lịch sử hoặc data lake ingest.
- Consumer-local debug files và log.

Nếu dữ liệu cần xóa, hãy phân biệt:
- **Ngăn phát PII vào event ngay từ thiết kế**: event chỉ chứa ID tối thiểu, consumer lấy dữ liệu cần từ source có kiểm soát.
- **Xóa hoặc giảm thiểu payload mới**: thay đổi event schema, tránh tiếp tục lan truyền thông tin nhạy cảm.
- **Policy cho event đã có**: có thể cần retention expiry, tombstone, rewrite, compaction hoặc encryption/key management tùy công nghệ và yêu cầu.
- **Chặn replay tái tạo dữ liệu**: deletion generation, consumer safeguards và đối soát.
- **Dọn DLQ**: không quên message nằm ở nơi ít giám sát.

### Kafka compacted topic và tombstone

Trong log-compacted Kafka topic, một record cùng key với value null thường được dùng làm **tombstone** để báo xóa key. Nhưng quá trình compaction là bất đồng bộ; segment, retention và consumer khác có ngữ nghĩa riêng. Không tuyên bố phát một tombstone là đảm bảo xóa tức thời mọi bản sao vật lý.

Nếu topic dùng retention theo thời gian, cần thiết kế giới hạn lưu và các snapshot bên ngoài. Consumer có thể vẫn đọc một message cũ trước khi compaction xảy ra, nên xử lý sự kiện cần kiểm tra deletion state/version thay vì dựa hoàn toàn vào trạng thái topic.

## 17. Object storage, file đính kèm và phiên bản đối tượng

File PDF, ảnh, CSV xuất, tài liệu hoặc backup trên object storage cần chính sách vòng đời riêng. Một request xóa khách hàng có thể yêu cầu tìm những object theo owner/subject reference, dù tên file không chứa ID người dùng.

Nên lưu metadata ánh xạ:

~~~text
object_id
bucket / container
object_key
object_version_id
owner_service
subject_ref
purpose
created_at
expires_at
retention_class
deletion_state
~~~

Dữ liệu object_key có thể chứa PII nếu thiết kế sai; nên dùng opaque key/ID và giữ ánh xạ trong một metadata store có kiểm soát.

**Versioning:** trong bucket bật object versioning, xóa key mà không chỉ định version có thể chỉ tạo delete marker hoặc ẩn phiên bản hiện hành, còn các version cũ tiếp tục tồn tại. Cần xử lý version/non-current versions, lifecycle rule, replication destination và quy tắc giữ bản bất biến.

**Retention/immutability:** object lock hoặc cơ chế WORM có thể ngăn xóa đến hết hạn. Workflow phải ghi nhận ngoại lệ/hold và thời điểm đủ điều kiện, không cố lách kiểm soát hoặc báo hoàn tất sai.

**Pre-signed URL và CDN:** khi xóa object, các URL đã cấp có thể còn hạn, response có thể còn trong edge cache; cần xét revoke, TTL và chính sách token khi nội dung nhạy cảm.

### File export và chia sẻ ra ngoài

Một báo cáo được export ra CSV rồi gửi qua email hoặc đối tác có thể nằm ngoài hệ thống quản lý chính. Data inventory phải bao phủ đường chia sẻ này. Cần quyết định vòng đời của file export, quyền tải lại, thời hạn link, yêu cầu nhà cung cấp xóa, và bằng chứng xác nhận. Không hứa có thể thu hồi mọi bản copy người nhận đã tải về nếu công nghệ và hợp đồng không hỗ trợ.

## 18. Data warehouse, data lake và dữ liệu phân tích

Data platform thường nhận dữ liệu qua CDC, ETL/ELT hoặc event rồi tạo thêm nhiều lớp:

~~~text
Operational DB
     |
     v
Raw landing zone
     |
     v
Cleaned / curated tables
     |
     +--> BI marts
     +--> Aggregations
     +--> Feature store
     +--> Exports
     +--> Model training datasets
~~~

Xóa một customer ở operational DB **không tự xóa** record trong warehouse. Ngay cả khi xóa raw, các bảng đã join, aggregate hoặc materialized view có thể còn dấu vết.

Các phương án cần thiết:
1. Mỗi bảng/asset có owner và lineage tới nguồn dữ liệu.
2. Dùng subject reference ổn định trong những nơi có thể cần xóa theo người.
3. Event xóa được pipeline xử lý như một cập nhật có thứ tự/version.
4. Xử lý cả raw, transformed, mart, materialized views, snapshots và exports theo phạm vi.
5. Job backfill/reprocessing không được hồi sinh record đã tombstoned.
6. Có đối soát xác minh không còn record thuộc phạm vi trong các bảng cần xóa.
7. Aggregate đã được ẩn danh hợp lệ có thể có chính sách khác, nhưng phải đánh giá khả năng tái định danh và nguồn gốc.
8. Các dataset test/dev được tạo từ production cần vòng đời tương ứng hoặc khử định danh trước khi sao chép.

Không được dùng câu “đã aggregate nên chắc chắn không còn dữ liệu cá nhân” nếu nhóm nhỏ hoặc thuộc tính kết hợp vẫn có thể nhận diện cá nhân.

### ML feature store và mô hình học máy

Nếu dữ liệu liên quan có trong feature store, embedding index hoặc dataset huấn luyện, workflow phải xác định cần xóa feature row, vector/document hay cập nhật training set. Việc một mô hình đã được huấn luyện từ dữ liệu không có nghĩa có thể xóa ảnh hưởng đó bằng cách DELETE một hàng; khả năng đáp ứng có thể cần unlearning, retraining, đánh giá định danh hoặc quy trình riêng theo chính sách.

Không hứa “xóa khỏi model ngay” nếu công nghệ không hỗ trợ chứng minh. Ghi nhận rõ những thành phần thực hiện được, thời hạn và cách xác minh.

## 19. Logs, traces, metrics và dữ liệu chẩn đoán

Một trong những nguồn bản sao khó thấy nhất là log. Ví dụ:

~~~text
INFO CustomerUpdated email=user@example.com fullName=...
DEBUG HTTP request body={...}
ERROR request failed, payload={...}
~~~

Các dòng này vô tình đưa PII vào log aggregation, alert, monitoring, tracing, incident export hoặc ticket. Một lệnh xóa customer ở DB không sửa những bản ghi đó.

**Ngăn dữ liệu nhạy cảm đi vào log từ đầu** là giải pháp tốt hơn phải xóa log theo người sau này:
- Dùng correlation ID hoặc opaque subject reference thay vì email/tên.
- Mask/redact trường nhạy cảm trong structured logging và exception.
- Không log toàn bộ HTTP request/response body theo mặc định.
- Kiểm soát sampling và retention của traces, spans, exception stack context.
- Không đưa user ID, email hoặc giá trị key tùy ý vào label metrics gây cardinality lớn và lộ thông tin.
- Quy định retention của log, cold archive, incident artifacts và quyền export.

Một log store có thể không hỗ trợ xóa từng record theo subject một cách nhanh chóng. Khi đó, phải giảm thiểu PII tại nguồn, chọn retention tương ứng và xử lý trường hợp đặc biệt bằng khả năng có thật của công cụ. Không báo xóa triệt để khi dữ liệu vẫn còn trong log archive.

## 20. Backup, snapshot và vấn đề dữ liệu xuất hiện lại

Backup là thành phần đặc biệt: đôi khi được giữ bất biến để phục hồi sau ransomware/sự cố. Việc xóa riêng một subject trong backup có thể rất khó hoặc phá tính toàn vẹn của bản sao lưu.

Vì thế cần tách hai mục tiêu:
- **Xóa khỏi hệ thống hoạt động** trong thời hạn áp dụng.
- **Quản lý backup theo chu kỳ giữ đã xác định**, có kiểm soát truy cập, mã hóa và quy trình xử lý khi restore.

### Restore guard là bắt buộc

~~~text
T1 Customer deleted in production
T2 Deletion ledger records customer-123 as deleted
T3 Incident: restore old database snapshot from T0
T4 Restored DB now contains customer-123 again
T5 Restore procedure reapplies deletion ledger / tombstones
T6 Verification before opening traffic
~~~

Nếu backup/restore khôi phục cả coordinator về thời điểm cũ, ledger có thể bị mất. Cần lưu bằng chứng deletion và những marker cần thiết ở một ranh giới phục hồi phù hợp hoặc có cơ chế replay đáng tin, không cùng bị rollback mà không được phát hiện.

Một runbook restore nên gồm:
1. Dừng hoặc cô lập những producer/consumer có thể dùng dữ liệu cũ.
2. Khôi phục dữ liệu vào môi trường kiểm soát truy cập.
3. Xác định snapshot time và các deletion requests hoàn tất sau thời điểm đó.
4. Áp dụng lại lệnh xóa/tombstone theo thứ tự phù hợp.
5. Rebuild/index/replay có nhận biết deletion state.
6. Đối soát những subject phải không còn trong dữ liệu hoạt động.
7. Mở dịch vụ trở lại sau khi các guard được thỏa.

**Không cố xóa backup bất biến trái policy.** Phải phân biệt rõ trường hợp có nghĩa vụ giữ, thời hạn hết hạn và biện pháp hạn chế truy cập. Các yêu cầu pháp lý có thể thay đổi theo khu vực; bộ phận có trách nhiệm cần phê duyệt chính sách trước khi áp dụng.

### Crypto-erasure

Mã hóa từng tập dữ liệu/subject bằng khóa quản lý riêng, sau đó hủy khóa, có thể làm dữ liệu còn nằm trên storage trở nên không thể giải mã nếu thiết kế bảo đảm đúng. Nhưng đây không phải giải pháp tự động:
- Khóa có còn trong backup, cache, HSM replica hoặc hệ thống khác không?
- Dữ liệu đã từng được giải mã và lưu bản rõ ở search/log/warehouse chưa?
- Có dữ liệu dùng chung một khóa khiến hủy khóa ảnh hưởng subject khác không?
- Có thể chứng minh mọi đường lấy lại plaintext đều mất khả năng không?

Chỉ coi crypto-erasure là đáp ứng yêu cầu khi có thiết kế khóa, vận hành và xác nhận tương ứng.

## 21. Legal hold và các ngoại lệ hợp lệ

Có tình huống yêu cầu xóa phải được hoãn hoặc chỉ xóa một phần vì nghĩa vụ giữ tài liệu, tranh chấp, kiểm toán hoặc quy tắc khác. Một workflow đáng tin cần:
- Kiểm tra hold trước khi chuyển trạng thái xóa.
- Xác định hold áp dụng cho **data asset/field nào**, không mặc định giữ mọi dữ liệu của một subject.
- Lưu lý do, owner phê duyệt, thời điểm rà soát và tiêu chí giải phóng hold.
- Hạn chế quyền truy cập dữ liệu đang hold theo mục đích.
- Khi hold được giải phóng, tự đánh giá lại retention eligibility.
- Trả lời yêu cầu xóa đúng thực trạng, không đánh dấu COMPLETED nếu vẫn còn bước bắt buộc bị chặn.

Ví dụ retention engine:

~~~text
eligible = now >= expiry_at
           AND no_active_legal_hold_for_asset
           AND no_business_constraint_preventing_deletion
~~~

Điều kiện và căn cứ giữ dữ liệu phải được xác định bởi chính sách của tổ chức theo phạm vi pháp lý áp dụng. Tài liệu kỹ thuật không thay thế ý kiến pháp lý về thời hạn lưu hoặc quyền được xóa.

### Chống “giữ mãi vì có ngoại lệ”

Hold phải có phạm vi và quy trình rà soát. Nếu một cờ hold tồn tại vĩnh viễn mà không có owner, toàn bộ data retention có thể bị vô hiệu hóa trên thực tế. Cần cảnh báo hold quá hạn rà soát và kiểm toán những thay đổi quyền.

## 22. Tách nghiệp vụ xóa và cơ sở dữ liệu: ví dụ Java/Spring Boot

Ví dụ một Customer Service cung cấp phương thức xử lý lệnh xóa profile:

~~~java
@Service
public class CustomerDeletionHandler {
    private final CustomerRepository customers;
    private final ProcessedDeletionRepository processed;
    private final OutboxRepository outbox;

    public CustomerDeletionHandler(
            CustomerRepository customers,
            ProcessedDeletionRepository processed,
            OutboxRepository outbox) {
        this.customers = customers;
        this.processed = processed;
        this.outbox = outbox;
    }

    @Transactional
    public void handle(DeleteCustomerCommand command) {
        if (processed.existsByRequestId(command.requestId())) {
            return; // command đã hoàn thành trong DB của service
        }

        CustomerProfile profile =
            customers.findByIdForUpdate(command.subjectRef())
                .orElse(null);

        if (profile != null) {
            if (profile.hasActiveHold()) {
                throw new DeletionBlockedByHoldException();
            }
            customers.delete(profile);
        }

        processed.save(new ProcessedDeletion(command.requestId()));
        outbox.save(DeletionStepCompleted.of(
            command.requestId(), "customer-service"
        ));
    }
}
~~~

**Lưu ý:** code là pseudocode Java hướng dẫn, không phải một module hoàn chỉnh. Các repository, record, transaction và exception cần được xây dựng đúng theo ứng dụng. Việc kiểm tra existsByRequestId rồi save một marker vẫn có race nếu hai consumer cùng chạy; phải có **UNIQUE constraint trên request_id** và xử lý xung đột transaction một cách phù hợp.

Nếu deletion task có thao tác ngoài DB như xóa object, nên dùng state machine và work item riêng: commit bước DB, phát outbox command cho object cleanup, retry, chỉ ACK sau khi xác minh postcondition. Không trói một DB transaction vào lời gọi network kéo dài.

### Tại sao không chỉ dùng @Transactional cho toàn bộ quy trình?

@Transactional của Spring thông thường kiểm soát transaction trên những resource tham gia phù hợp, không tự bảo đảm atomicity với Redis, Kafka, Elasticsearch, S3, warehouse và API bên thứ ba. Các bước ngoài DB cần idempotency, outbox, retry, timeout và đối soát.

## 23. Retention jobs và batch deletion an toàn

Một retention scheduler có thể chạy mỗi giờ/ngày, nhưng không nên giữ một transaction khổng lồ để xóa hàng triệu bản ghi.

Mô hình:

~~~text
Retention Scheduler
     |
     v
Find eligible asset IDs (bounded batch)
     |
     v
Persist deletion requests / work items
     |
     v
Distributed workers (claim/lease)
     |
     v
Owner service executes idempotent deletion
     |
     v
Checkpoint + metrics + reconciliation
~~~

Những biện pháp vận hành:
- Sắp xếp theo expiry_at/ID, chia batch vừa khả năng DB.
- Index các trường dùng để tìm expired records, bao gồm trạng thái/hold nếu phù hợp.
- Chỉ định batch size, rate limit và max concurrency theo capacity thực.
- Dùng claim atomic, lease và retry để tránh hai worker tranh cùng một item.
- Retry với exponential backoff + jitter cho lỗi tạm; báo và cách ly lỗi nghiệp vụ.
- Không spam request đến dependency đang 429/503.
- Theo dõi lock wait, WAL, replication lag, I/O và số bản ghi đã xóa/phút.
- Lưu checkpoint, có thể tạm dừng trong đợt tải cao và resume sau sự cố.
- Không dùng thời gian trên nhiều node với timezone không nhất quán; lưu UTC và định nghĩa ngày nghiệp vụ nếu cần.

Nếu chính sách cho phép một retention job chỉ chạy trong khung thấp tải, phải bảo đảm cửa sổ đó đủ để hoàn thành trước deadline. Nếu không, cần tăng hiệu quả qua partition, giới hạn tốc độ và hạ tầng phù hợp.

## 24. Các vấn đề race condition khi xóa phân tán

### 24.1 Một writer cũ tạo lại dữ liệu

~~~text
T1 Deletion marker created
T2 Customer DB deleted
T3 Old request still running writes customer profile again
~~~

Cần chặn write mới bằng lifecycle state/version, unique generation hoặc kiểm tra tombstone; việc chỉ xóa record mà không kiểm soát writer đang bay có thể tạo lại dữ liệu.

### 24.2 Event đến sai thứ tự

Một event CustomerUpdated cũ có thể tới sau CustomerDeleted và reindex dữ liệu. Bảo vệ bằng monotonic version và tombstone; xác định ordering trên mỗi key, không chỉ dựa vào timestamp đồng hồ node.

### 24.3 Retry sau side effect thành công

Worker xóa file ở S3 thành công nhưng timeout trước khi ghi ACK. Retry phải chấp nhận kết quả “object already absent” khi đúng phạm vi và không coi đó là lỗi cần khôi phục dữ liệu.

### 24.4 Một request mới xuất hiện khi request cũ đang chạy

Hai deletion requests khác nhau cho cùng subject có thể chồng nhau. Cần policy về idempotency key/biz key, ưu tiên status và gộp yêu cầu hoặc tách phạm vi đúng nếu mục đích khác. Đừng để kết quả của request cũ vô tình đặt lại trạng thái request mới.

### 24.5 Retention policy đổi giữa quá trình

Một loại dữ liệu có thể được gia hạn retention hoặc bị áp dụng hold mới trong khi batch chạy. Trước điểm xóa không thể đảo ngược, worker cần kiểm tra lại điều kiện hợp lệ và policy version đã được quyết định, theo quy tắc quản trị đã thiết kế.

### 24.6 Restore tạo lại dữ liệu

Restore backup cũ có thể quay lại trạng thái trước khi xóa. Phải có ledger/tombstone độc lập tương ứng và áp dụng lại trước khi cho phép traffic hoặc replay tạo derived copies.

## 25. Dữ liệu trong hệ thống bên thứ ba

Nếu dữ liệu đã được chia sẻ với email gateway, fraud vendor, marketing platform, analytics SaaS hoặc đối tác, việc xóa dữ liệu nội bộ không tự xóa bản copy của họ.

Cần lưu register:
- Provider/processor nhận dữ liệu nào, vì mục đích gì.
- Phương thức xóa: API, dashboard, support request, batch export hoặc hợp đồng.
- Thời gian phản hồi, retry và bằng chứng xác nhận.
- Khả năng xóa ở backup của nhà cung cấp, nếu có thông tin hợp lệ.
- Trường hợp không thể xóa trực tiếp và cơ chế escalation.

Có thể dùng adapter xử lý deletion step riêng cho từng vendor; khi trả ACK, phân biệt “API request accepted”, “processing” và “deletion confirmed”. Trạng thái 202 Accepted từ một API bất đồng bộ chưa đồng nghĩa mọi dữ liệu đã xóa.

Đối với dữ liệu đã xuất ra file cho người nhận bên ngoài, có thể không có phương tiện kỹ thuật để thu hồi mọi bản copy. Cần thể hiện hạn chế và cam kết theo hợp đồng/thực tế, không tuyên bố độ bao phủ tuyệt đối.

## 26. Quan sát và SLO cho data deletion

Một dashboard phải trả lời được:
- Có bao nhiêu deletion request được nhận, đang chạy, hoàn thành hoặc bị hold?
- Service/asset nào đang chậm?
- Yêu cầu gần/đã vượt deadline nào?
- Bao nhiêu derived copies còn chưa xác nhận?
- Có command bị treo trong outbox, broker, DLQ hoặc bước vendor không?
- Có dữ liệu đã xóa nào bị xuất hiện lại sau replay/restore?
- Retention job có hoàn tất trước kỳ hạn chính sách không?

Các metric gợi ý:

| Metric | Ý nghĩa |
| --- | --- |
| deletion_requests_total | Tổng yêu cầu theo trạng thái/loại (cardinality thấp) |
| deletion_steps_pending | Số step còn chờ xác nhận |
| deletion_end_to_end_duration_seconds | Phân phối thời gian xử lý toàn yêu cầu |
| deletion_oldest_pending_age_seconds | Tuổi yêu cầu chờ lâu nhất |
| retention_expired_records_count | Số bản ghi đã đủ điều kiện nhưng chưa xử lý |
| retention_backlog_age_seconds | Độ trễ so với thời điểm hết hạn |
| deletion_events_retry_total | Số lần retry theo service/nhóm lỗi |
| deletion_dlq_count | Công việc bị đưa vào DLQ |
| deletion_reconciliation_mismatch | Số bản sao đáng lẽ đã xóa nhưng còn được tìm thấy |
| deletion_restore_replay_pending | Số marker cần áp dụng lại sau restore |

**Không đưa subject ID/email hoặc request ID ngẫu nhiên vào labels metrics** vì cardinality cao và nguy cơ lộ dữ liệu. Dùng logs/traces có kiểm soát quyền để điều tra chi tiết theo request ID, nhưng cũng tối thiểu hóa nội dung nhạy cảm.

### SLO phải có phạm vi

Một SLO ví dụ:
- 99% deletion requests hợp lệ hoàn thành việc xóa dữ liệu **trên các hệ thống hoạt động được quản lý** trước thời hạn X sau khi được xác nhận đủ điều kiện.
- 100% requests không được đóng COMPLETED khi còn step bắt buộc chưa ACK hoặc chưa có exception hợp lệ.
- Retention backlog không vượt quá giới hạn đã định.
- Dữ liệu xóa không được tái xuất hiện qua replay/restore theo các test của hệ thống.

Số X, phạm vi và tiêu chí phải lấy từ yêu cầu nghiệp vụ/pháp lý thực tế. Không đánh tráo một SLO “xóa DB trong 1 giờ” thành lời cam kết “xóa mọi bản sao, bao gồm backup và thiết bị người dùng, trong 1 giờ”.

## 27. Kiểm thử tính đúng đắn của quy trình xóa

Không chỉ kiểm thử happy path “DELETE database trả về 204”. Các tình huống tối thiểu:

| Kịch bản | Điều phải chứng minh |
| --- | --- |
| Xóa hồ sơ thông thường | Record gốc bị xử lý đúng, workflow có kết quả rõ |
| Search index còn bản sao | Document bị xóa/redact, API search không còn trả dữ liệu |
| Redis/L1 vẫn có dữ liệu | Không trả bản nhạy cảm stale sau điều kiện xóa |
| CustomerUpdated cũ tới sau Deleted | Version/tombstone ngăn tái tạo |
| Duplicate deletion command | Consumer idempotent, không tạo side effect sai |
| Outbox publish lỗi | Command không bị mất, dispatcher có thể phát lại |
| Service downstream down | Step tiếp tục retry và deadline được giám sát |
| Xóa S3 object có version | Đúng version/replica và chính sách được xử lý |
| DLQ giữ message cũ | Có policy làm sạch hoặc ngăn replay phục hồi dữ liệu |
| Backup restore từ trước khi xóa | Deletion ledger/tombstone được reapply trước khi mở traffic |
| Legal hold hiện hành | Không xóa asset bị hold, trạng thái báo chính xác |
| Hold được giải phóng | Workflow tiếp tục đánh giá retention và xóa đúng |
| Người dùng đổi email/ID | Tìm được các asset qua stable subject reference/lineage |
| Warehouse refresh/rebuild | Dữ liệu bị xóa không quay lại read model |
| Một vendor trả 202 Processing | Không báo hoàn tất cho đến khi có điều kiện xác nhận |
| Retention job chạy đồng thời với update | Không xóa nhầm dữ liệu vừa được gia hạn |
| High-volume batch | Không gây lock/lag vượt ngưỡng chấp nhận |
| Yêu cầu xóa nhiều lần | Idempotency business key được duy trì |

Ở tầng integration, nên dùng database/broker/cache tương thích để kiểm thử transaction và idempotency. Ở tầng E2E, chọn một luồng xóa xuyên service quan trọng: tạo dữ liệu, phát sinh bản sao, gửi lệnh xóa, đợi trạng thái hoàn tất theo polling có deadline, truy vấn cả nguồn và derived endpoints để xác nhận.

Không dùng Thread.sleep cố định như bằng chứng hệ phân tán đã đồng bộ. Hãy kiểm tra một postcondition rõ ràng với deadline hợp lý và ghi lại step nào vẫn chưa hoàn thành khi timeout.

## 28. Quy trình xử lý sự cố và khôi phục

Khi một deletion workflow bị mắc kẹt:
1. Xác định request_id, policy_version, deadline và step đang pending.
2. Kiểm tra owner service, message lag, outbox, retries và DLQ.
3. Kiểm tra tình trạng thực tế tại target bằng phương thức chỉ đọc phù hợp; đừng gửi DELETE mù đến nhiều bản ghi khi mapping chưa rõ.
4. Nếu lệnh retry idempotent và điều kiện nghiệp vụ không thay đổi, phát lại từ trạng thái đã lưu.
5. Nếu không có mapping hoặc có hold xung đột, chuyển sang trạng thái cần điều tra, giữ bằng chứng tối thiểu.
6. Khi sửa, chạy reconciliation và xác minh dữ liệu không tái xuất hiện từ event cũ.
7. Đóng incident với tác động, thời hạn xử lý, nguyên nhân và cải tiến phòng ngừa.

**Không dùng backup restore để “undo” việc xóa đã xác nhận** nếu điều đó phục hồi dữ liệu không còn được phép dùng. Khi phải restore vì thảm họa, cần áp dụng lại deletion ledger trước khi hệ thống phục vụ.

## 29. Ví dụ hoàn chỉnh: đóng tài khoản khách hàng

### Bối cảnh

Customer Service sở hữu hồ sơ cá nhân. Order Service giữ thông tin cần cho giao dịch. Search Service có document tra cứu. Notification Service có địa chỉ liên hệ. Analytics giữ events và mart. Object Storage chứa ảnh đại diện và các file export. Redis là cache dùng chung.

Yêu cầu: khi một tài khoản đủ điều kiện đóng và xử lý xóa, hệ thống phải ngừng sử dụng dữ liệu không còn cần thiết, xử lý bản sao và không làm sai lịch sử giao dịch cần giữ hợp lệ.

### Bước A — Phân loại phạm vi

| Asset | Hành động minh họa | Điều kiện |
| --- | --- | --- |
| Customer profile | Xóa thông tin hồ sơ hoặc bản ghi | Sau kiểm tra nghĩa vụ/hold |
| Order customer snapshot | Xóa trường liên hệ không cần, giữ phần giao dịch hợp lệ | Theo policy của Order |
| Search customer document | Delete document hoặc redact | Không reindex từ event cũ |
| Notification contact | Xóa subscriber/contact | Ngăn chiến dịch mới tiếp tục gửi |
| Redis/L1 cache | Evict/invalidate/version bump | Không phục vụ bản stale |
| Avatar / export files | Xóa các object/version phù hợp | Xem versioning/retention |
| Analytics raw và marts | Xóa/ẩn danh những phần trong scope | Có lineage và backfill guard |
| Backup | Hết hạn theo lịch và restore guard | Không báo đã xóa vật lý trước khi có bằng chứng |
| Vendor records | Gửi yêu cầu và theo dõi xác nhận | Theo contract/capability |

Các quyết định cụ thể không thể được suy ra chỉ từ tên asset; cần policy và căn cứ giữ có hiệu lực.

### Bước B — Orchestration

~~~text
User authorized deletion request
     |
     v
Coordinator creates request + outbox
     |
     v
Account status = RESTRICTED
     |
     +--> Customer delete/redact
     +--> Order policy-specific redaction
     +--> Search delete + tombstone
     +--> Notification delete + suppress future use
     +--> Redis/cache invalidation
     +--> Object-store version cleanup
     +--> Warehouse deletion propagation
     +--> Vendor erasure request
     |
     v
Every required step ACK or documented hold
     |
     v
Reconciliation: no active copy within scope
     |
     v
Close request with explicit backup/exception status
~~~

### Bước C — Đo và đối soát

Những kiểm tra cơ bản:
- Customer API không còn trả hồ sơ đã bị xóa.
- Search và cache không còn phục vụ cùng dữ liệu.
- Order Service chỉ còn các trường được phép theo retention.
- Warehouse/query phục vụ nghiệp vụ không trả record thuộc phạm vi.
- File/object và vendor có confirmation tương ứng.
- Replay event cũ không tạo lại hồ sơ.
- Restore snapshot từ thời điểm trước deletion có bước reapply marker.
- Deletion request không bị đóng nếu một step cần thiết còn pending.

### Bước D — Trả kết quả có giới hạn chính xác

Nên phân biệt:
- **REQUEST_ACCEPTED:** đã nhận và xác thực yêu cầu.
- **ONLINE_DELETION_COMPLETED:** các active stores trong phạm vi đã xử lý và đối soát.
- **EXCEPTIONS/RETENTION_REMAINING:** những dữ liệu phải giữ hợp lệ hoặc backup chờ hết hạn, kèm thời hạn/quy trình.
- **REQUEST_CLOSED:** các điều kiện policy-defined đã đạt và có evidence.

Không thay tất cả bằng một thông báo “đã xóa hoàn toàn mọi dữ liệu” khi thực tế còn bản sao chưa kiểm soát.

## 30. Sai lầm phổ biến

**Chỉ xóa bản ghi ở service gốc.** Cache, index, event, analytics, file và vendor có thể còn bản sao. Cần inventory và workflow theo asset.

**Coi soft delete là erasure.** deleted_at chỉ chặn logic nếu mọi query tuân thủ; dữ liệu vật lý vẫn có thể đọc. Cần thiết kế hành động cuối theo policy.

**Cho rằng TTL luôn đủ.** TTL không bảo đảm xóa ngay, nhất là khi có yêu cầu thu hồi hoặc dữ liệu nhạy cảm. Cần invalidation, versioning và guard ở điểm đọc.

**Đưa PII vào deletion event và audit.** Quy trình xóa vô tình tạo thêm bản sao dữ liệu cần xóa. Truyền reference tối thiểu, giữ evidence đã tối thiểu hóa.

**Không quản lý event ordering.** Một CustomerUpdated cũ có thể re-create document sau deletion. Dùng lifecycle generation/tombstone và kiểm tra version.

**Chỉ kiểm tra broker đã publish.** Publish không chứng minh consumer đã xóa. Cần ACK từng step và reconciliation.

**Không tính DLQ và outbox.** Message lỗi bị giữ lại hoặc replay có thể chứa PII và tạo lại bản sao. Áp retention/cleanup cho chính những nơi này.

**Đánh dấu hoàn tất khi API bên thứ ba trả 202.** Accepted/processing khác với confirmed completion. Theo dõi trạng thái thực tế hoặc hạn chế rõ cam kết.

**Xóa backup bất biến tùy tiện.** Có thể phá khả năng khôi phục hoặc vi phạm lưu trữ bắt buộc. Cần lịch backup, mã hóa, quyền và restore guard.

**Không áp dụng lại deletion khi restore.** Snapshot cũ làm dữ liệu đã xóa xuất hiện lại. Dùng ledger độc lập/replay và verification trước traffic.

**Xóa hàng triệu dòng trong một transaction.** Dễ tạo lock, WAL/replication lag và downtime. Batch, partition và rate limit.

**Dùng email làm khóa xóa xuyên service.** Email có thể thay đổi, được tái sử dụng và chứa PII. Dùng opaque stable ID và data lineage.

**Không xét legal hold.** Xóa dữ liệu cần giữ có thể gây hậu quả nghiêm trọng; giữ mọi dữ liệu vô hạn cũng không đúng. Áp chính sách theo asset với phê duyệt.

**Bỏ quên dữ liệu dev/test và bản export.** Dữ liệu sao chép từ production có thể nằm ở môi trường ít kiểm soát hơn. Hạn chế tạo bản sao và áp lifecycle tương ứng.

**Báo “100% erasure” khi chưa có bằng chứng.** Phải mô tả phạm vi đã xử lý, ngoại lệ và những bản sao còn theo retention.

## 31. Checklist thiết kế và triển khai

- [ ] Có data inventory và lineage đủ để biết nơi giữ bản gốc, bản sao và dữ liệu dẫn xuất.
- [ ] Mỗi data asset có owner, mục đích, retention trigger, duration, action và policy version.
- [ ] Chính sách được xác nhận theo nghĩa vụ áp dụng; ngoại lệ/legal hold có phạm vi và owner.
- [ ] Có cơ chế xác thực và phân quyền đối với yêu cầu xóa.
- [ ] Deletion request có ID ổn định, idempotency và durable state.
- [ ] Các service sở hữu dữ liệu thực thi lệnh trong ranh giới của mình.
- [ ] Outbox/broker có retry, idempotent consumer, dead-letter và reconciliation.
- [ ] Có state/version/tombstone ngăn update cũ hoặc replay tái tạo dữ liệu.
- [ ] Cache L1, Redis, gateway/CDN và client được xử lý đúng với mức stale cho phép.
- [ ] Search index/read model/warehouse/feature store có lộ trình xóa hoặc redaction.
- [ ] Object storage có quy trình cho versions, lifecycle, replication và export.
- [ ] Event payload, log, traces và audit đã được tối thiểu hóa, có retention riêng.
- [ ] Backup có retention, kiểm soát truy cập và restore procedure tái áp dụng deletion.
- [ ] Hệ thống bên thứ ba được kiểm kê, có yêu cầu/xác nhận và escalation.
- [ ] Batch deletion có checkpoint, giới hạn tốc độ, xử lý lock và resume.
- [ ] Mỗi step có ACK/postcondition, không đóng sớm workflow.
- [ ] Có metric deletion lag, backlog, retry, DLQ, hold và violation alerts.
- [ ] Đã kiểm thử race, duplicate, out-of-order, restore, cold cache và failure.
- [ ] Evidence được lưu đủ cho kiểm toán nhưng không giữ lại payload nhạy cảm không cần thiết.
- [ ] Tuyên bố hoàn tất nêu đúng phạm vi, ngoại lệ và tình trạng backup.

## 32. Bài tập thực hành

Một hệ thống SaaS đa tenant có Customer Service, Billing Service, Search Service, Notification Service, Analytics Service, PostgreSQL, Redis, Kafka, object storage và một dịch vụ gửi email bên ngoài. Một khách hàng yêu cầu đóng tài khoản trong khi:
- Search index vẫn chứa email cũ.
- Kafka có một message CustomerUpdated bị trễ.
- Redis của một pod đang giữ profile trong local cache.
- Analytics warehouse đã tạo bảng dimension từ CDC.
- Object storage bật versioning và còn file export.
- Billing phải giữ một phần dữ liệu giao dịch theo chính sách đang áp dụng.
- Có backup được tạo trước yêu cầu xóa.
- Email provider xác nhận chỉ mới nhận request xóa bất đồng bộ.

Hãy thiết kế:
1. Data inventory và lineage cho những bản sao nêu trên.
2. Retention policy phân biệt profile, giao dịch, log, event, export và backup.
3. Deletion request schema cùng trạng thái và idempotency key.
4. Outbox/command flow tới các service owner.
5. Cách Search ngăn CustomerUpdated cũ tạo lại document.
6. Cách cache invalidation tránh cache loader ghi lại profile sau khi xóa.
7. Hành động với các object version và email provider chưa xác nhận.
8. Quy trình áp dụng lại deletion sau backup restore.
9. Reconciliation query và bằng chứng cần thiết để đóng request.
10. Các metric và alerts để phát hiện vi phạm thời hạn xóa.

Giải thích vì sao một câu lệnh SQL DELETE và một thông báo “đã hoàn tất” ngay sau khi publish event không đáp ứng đầy đủ bài toán quản trị dữ liệu xuyên microservices.

## Kết luận

Trong microservices, **thời gian lưu và việc xóa dữ liệu là trách nhiệm xuyên toàn bộ vòng đời và toàn bộ bản sao**. Một hồ sơ đã bị xóa ở nguồn vẫn có thể sống trong cache, search, event, analytics, file export, backup hoặc hệ thống bên ngoài. Giải pháp đáng tin cậy bắt đầu từ inventory, lineage và retention policy theo loại dữ liệu; tiếp theo là workflow xóa có trạng thái, owner rõ, event/outbox, idempotency, version/tombstone và đối soát; cuối cùng là quản trị backup, ngoại lệ và bằng chứng thực thi. Mục tiêu là đáp ứng đúng nghĩa vụ và mục đích dữ liệu với phạm vi và mức bảo đảm được mô tả trung thực, thay vì chỉ thực thi một lệnh DELETE.

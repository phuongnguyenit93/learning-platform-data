# Runbook sự cố

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi hệ thống chạy production, sự cố có thể xuất hiện ở publisher, transaction, listener, Event Publication Registry, broker, consumer, database hoặc dependency bên ngoài. **Runbook sự cố** là hướng dẫn vận hành có trình tự để xác định phạm vi ảnh hưởng, bảo vệ dữ liệu, khôi phục luồng event và xác nhận hệ thống trở lại trạng thái ổn định.

Runbook cần giúp người trực vận hành biết phải kiểm tra gì, thu thập bằng chứng nào, hành động nào an toàn và điều kiện nào cho phép tiếp tục. Không nên bắt đầu bằng việc restart toàn bộ service, xóa backlog hoặc reset offset khi chưa hiểu nguyên nhân. Những hành động đó có thể che dấu dấu vết, làm mất event hoặc tạo side effect trùng.

## 1. Mục tiêu và phạm vi

Runbook này áp dụng cho các luồng application events trong Spring Modulith và các tích hợp broker như Kafka. Tùy kiến trúc, một ứng dụng có thể dùng Event Publication Registry cho transactional listener nội bộ, outbox/inbox cho giao tiếp bền vững, Kafka cho giao tiếp liên dịch vụ hoặc kết hợp nhiều cơ chế.

Các mục tiêu vận hành:

- Phát hiện publisher không phát được event hoặc transaction thất bại.
- Phát hiện publication incomplete tăng bất thường hoặc listener không hoàn tất.
- Xác định consumer bị dừng, lag tăng, rebalance liên tục hoặc không commit offset.
- Phân biệt lỗi tạm thời, lỗi dữ liệu, lỗi hợp đồng và kết quả nghiệp vụ.
- Khôi phục xử lý mà không bỏ sót event hoặc lặp side effect.
- Bảo toàn offset, publication record, inbox, outbox và dead-letter record.
- Ghi lại quyết định, thời điểm, người thực hiện và kết quả của từng hành động.

Runbook không thay thế quy trình xử lý sự cố hạ tầng chung, database disaster recovery, bảo mật hoặc incident communication của tổ chức. Khi nguyên nhân nằm ngoài event pipeline, chuyển sang runbook của hệ thống phụ trách và giữ liên kết correlation để điều tra xuyên suốt.

## 2. Chuẩn bị trước khi có sự cố

Một runbook chỉ hữu ích khi người trực có sẵn quyền truy cập và thông tin cần thiết. Trước production, cần xác nhận:

| Hạng mục | Thông tin cần có |
| --- | --- |
| Service và module owner | Tên service, module, nhóm chịu trách nhiệm và kênh escalation nội bộ. |
| Event catalog | Event type, schema version, producer, consumer và mức độ quan trọng. |
| Transaction flow | Publisher transaction, listener phase, transaction của listener và persistence boundary. |
| Publication registry | Cách xem publication incomplete/completed theo phiên bản Spring Modulith đang dùng. |
| Broker topology | Cluster, topic, partition, consumer group, retry topic và DLT. |
| Database | Datasource, migration version, bảng inbox/outbox và quy trình backup/PITR. |
| Observability | Dashboard, alert, log search, trace và metric labels. |
| Recovery procedure | Cách resubmit publication, replay record, xử lý DLT và kiểm tra idempotency. |
| Quyền vận hành | Quyền đọc trạng thái, quyền pause/resume consumer và quy trình phê duyệt thao tác nhạy cảm. |
| Business invariant | Điều kiện dữ liệu phải đúng sau recovery, ví dụ một order chỉ có một reservation đang hiệu lực. |

Điền các giá trị môi trường thực tế vào bản runbook triển khai của tổ chức. Không giả định tên topic, bảng registry, group ID, endpoint, namespace hoặc lệnh quản trị giống nhau giữa staging và production.

## 3. Phân loại mức độ nghiêm trọng

Phân loại severity dựa trên ảnh hưởng nghiệp vụ, phạm vi event và thời gian tồn đọng, không chỉ dựa trên số exception.

| Mức | Dấu hiệu điển hình | Hành động |
| --- | --- | --- |
| SEV-1 | Mất hoặc nhân đôi giao dịch quan trọng; nhiều luồng nghiệp vụ dừng; dữ liệu không nhất quán diện rộng. | Kích hoạt incident response ngay, dừng thay đổi rủi ro, bảo toàn bằng chứng và điều phối owner liên quan. |
| SEV-2 | Một luồng trọng yếu bị gián đoạn; backlog tăng nhanh hoặc vượt SLA; DLT tăng đáng kể. | Gọi nhóm service/broker/database liên quan, khoanh vùng và phục hồi có kiểm soát. |
| SEV-3 | Một consumer hoặc một loại event bị lỗi có phạm vi giới hạn; có workaround hoặc backlog còn trong SLA. | Theo dõi, xử lý theo runbook và đặt thời hạn khắc phục. |
| SEV-4 | Cảnh báo đơn lẻ, lỗi tự phục hồi hoặc ảnh hưởng thấp. | Ghi nhận, kiểm tra xu hướng và tạo công việc phòng ngừa nếu cần. |

Severity có thể được nâng lên khi backlog tiếp tục tăng, retention sắp hết, event có thời hạn nghiệp vụ hoặc sự cố lan sang module khác. Không hạ severity chỉ vì metric tạm thời trở lại bình thường; cần xác minh backlog, side effect và dữ liệu đã nhất quán.

## 4. Quy trình phản ứng ban đầu

Khi nhận alert hoặc báo cáo sự cố, thực hiện theo trình tự:

1. Xác nhận alert, thời điểm bắt đầu và service/module bị ảnh hưởng.
2. Xác định event type, producer, listener hoặc consumer group liên quan.
3. Đánh giá số lượng event bị ảnh hưởng, tuổi event lâu nhất và SLA nghiệp vụ.
4. Kiểm tra deploy, cấu hình, schema migration hoặc thay đổi broker gần thời điểm phát sinh.
5. Thu thập eventId, correlationId, topic/partition/offset, publication identifier và exception category.
6. Xác định có nguy cơ mất dữ liệu, duplicate hoặc side effect chưa rõ hay không.
7. Chọn hành động giảm ảnh hưởng nhỏ nhất và có thể đảo ngược.
8. Ghi lại người thực hiện, thời gian, phạm vi và kết quả.

Trước khi thao tác recovery, lưu snapshot metric, log truy vấn, offset và trạng thái publication. Khi cần pause consumer hoặc tắt publisher, ghi rõ phạm vi và cách bật lại. Không thay đổi đồng thời nhiều thành phần nếu chưa cần thiết vì sẽ khó xác định hành động nào đã giải quyết vấn đề.

## 5. Cây chẩn đoán tổng quát

~~~mermaid
flowchart TD
    A[Alert: event flow bất thường] --> B{Publisher có commit?}
    B -->|Không| C[Kiểm tra request, transaction và database]
    B -->|Có| D{Publication/record đã được tạo?}
    D -->|Không| E[Kiểm tra registry, outbox hoặc publish path]
    D -->|Có| F{Listener/consumer có nhận?}
    F -->|Không| G[Kiểm tra broker, subscription, group và ACL]
    F -->|Có| H{Handler hoàn tất?}
    H -->|Có| I[Đối chiếu side effect và trạng thái nghiệp vụ]
    H -->|Không| J[Phân loại exception và kiểm tra dependency]
    J --> K{Retry an toàn?}
    K -->|Có| L[Recovery có giới hạn và idempotency]
    K -->|Không hoặc chưa rõ| M[Quarantine, đối soát hoặc escalation]
    L --> N[Theo dõi backlog và xác nhận phục hồi]
    C --> N
    E --> N
    G --> N
    I --> N
    M --> N
~~~

Sơ đồ là khung định hướng. Với một event có nhiều listener, mỗi publication có thể có kết quả riêng; không kết luận toàn bộ event đã xử lý xong chỉ vì một listener thành công.

## 6. Sự cố publisher hoặc transaction

**Triệu chứng:** API tạo nghiệp vụ trả lỗi, publisher không phát event, transaction rollback hoặc số lượng event phát ra thấp bất thường so với giao dịch đã commit.

**Kiểm tra:**

- Tỷ lệ lỗi request và transaction theo service.
- Database availability, connection pool, lock wait, deadlock và transaction timeout.
- Exception tại nơi gọi ApplicationEventPublisher.
- Event có được publish trong đúng transaction boundary không.
- Có listener đồng bộ làm exception truyền ngược về publisher không.
- Có thay đổi code/config khiến event type hoặc payload không được tạo không.

**Hành động:**

1. Nếu database hoặc dependency đang lỗi, khôi phục dependency theo runbook tương ứng.
2. Xác minh giao dịch nghiệp vụ có commit hay rollback.
3. Nếu transaction rollback, kiểm tra dữ liệu và publication record có cùng rollback như thiết kế không.
4. Nếu transaction commit nhưng event không được ghi nhận ở nơi mong đợi, kiểm tra publish path, registry hoặc outbox.
5. Chỉ phát bù event khi xác minh giao dịch gốc đã commit và chưa có event tương đương.

Không phát lại event chỉ dựa trên việc client nhận HTTP timeout. Request có thể đã commit trước khi response bị mất. Tra cứu bằng business key/idempotency key để xác định trạng thái trước khi thử lại.

## 7. Sự cố Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication đến transactional listener. Publication thường được đăng ký trong transaction phát event và được đánh dấu completed khi listener xử lý thành công theo cơ chế transaction. Publication incomplete tăng có thể chỉ ra listener lỗi, process dừng giữa xử lý hoặc dependency không sẵn sàng.

**Triệu chứng:**

- Incomplete publication tăng liên tục.
- Một listener có publication tồn tại lâu hơn SLA.
- Recovery/resubmit không làm giảm backlog.
- Database chứa publication store không truy cập được.
- Sau deploy, listener không còn khớp event type hoặc không được khởi tạo.

**Kiểm tra:**

- Xác định listener identifier và event type có incomplete publication.
- Xem tuổi publication lâu nhất, tốc độ phát sinh và số lần recovery.
- Đối chiếu log của listener theo eventId/correlationId.
- Kiểm tra database publication store và transaction commit.
- Kiểm tra listener có bắt exception rồi nuốt lỗi hay không.
- Kiểm tra thay đổi class/package, event type hoặc cấu hình khiến listener không được đăng ký.

**Hành động:**

1. Khắc phục nguyên nhân listener hoặc dependency trước.
2. Xác minh handler idempotent và side effect của các publication đang tồn tại.
3. Dùng API recovery/resubmit được hỗ trợ bởi phiên bản Spring Modulith đang triển khai.
4. Thử một publication đại diện hoặc phạm vi nhỏ trước khi xử lý backlog lớn.
5. Theo dõi publication completed và side effect nghiệp vụ sau recovery.

Không sửa trực tiếp bảng nội bộ của registry hoặc xóa publication incomplete để làm metric giảm. Không giả định registry là event store hoặc lưu trạng thái Kafka offset; mỗi cơ chế có nguồn dữ liệu và quy trình recovery riêng.

## 8. Sự cố listener hoặc handler

**Triệu chứng:** publication chưa hoàn tất, log có exception, projection không cập nhật, một event type thất bại trong khi các loại khác vẫn hoạt động.

**Phân loại lỗi trước khi retry:**

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Tạm thời | Timeout, connection reset, database tạm unavailable. | Retry có backoff và giới hạn nếu thao tác idempotent. |
| Hợp đồng/dữ liệu | Payload sai schema, thiếu field bắt buộc, deserialize failure. | Dừng retry tự động; quarantine/DLT và điều tra producer contract. |
| Nghiệp vụ | Không đủ hàng, đơn đã hủy, điều kiện không hợp lệ. | Xử lý theo nhánh domain, phát event kết quả phù hợp. |
| Cạnh tranh | Optimistic lock conflict, deadlock. | Kiểm tra transaction và retry có giới hạn theo chính sách. |
| Lập trình | NullPointerException, invariant bị vi phạm. | Giữ bằng chứng, khắc phục code và tránh retry mù quáng. |
| Không xác định | Timeout sau khi hệ thống ngoài có thể đã thực hiện side effect. | Đối soát trạng thái trước khi gửi lại hoặc compensation. |

**Hành động:**

1. Lấy một eventId lỗi đại diện và xác định handler cụ thể.
2. Đọc exception type, cause chain, failure category và thời điểm.
3. Xác minh transaction listener đã commit side effect nào.
4. Sửa dependency, dữ liệu hoặc code tùy nguyên nhân.
5. Kiểm tra bằng một event thử hoặc một publication nhỏ trong môi trường phù hợp.
6. Recovery theo lô có giới hạn, theo dõi duplicate và failure rate.

Không bắt exception rồi chỉ log nếu cơ chế registry cần biết listener thất bại. Nếu handler kết thúc bình thường sau khi nuốt lỗi, publication có thể được đánh dấu completed dù nghiệp vụ chưa hoàn tất.

## 9. Sự cố Kafka broker hoặc consumer

**Triệu chứng:** consumer không nhận message, group không join được, partition không được assign, lag tăng, offset không commit hoặc rebalance liên tục.

**Kiểm tra:**

- Broker connectivity, broker health và network latency.
- Authentication, ACL topic và quyền consumer group.
- Topic tồn tại, partition count và leader availability.
- Consumer group state, member count và partition assignment.
- Lag theo từng partition và tuổi record lâu nhất.
- Consumer exception, deserializer failure và commit error.
- CPU, memory, thread pool, poll interval và thời gian xử lý record.

**Hành động:**

1. Nếu broker hoặc network lỗi, phối hợp nhóm nền tảng để khôi phục kết nối.
2. Nếu ACL sai, cấp đúng quyền tối thiểu cho principal và group cần thiết.
3. Nếu consumer bị quá tải, kiểm tra thời gian xử lý, pool và partition assignment trước khi scale.
4. Nếu rebalance liên tục, kiểm tra heartbeat, poll interval, xử lý record quá lâu và restart không ổn định.
5. Nếu lag tăng do dependency downstream, cân nhắc giảm tốc độ hoặc pause consumer theo policy để tránh tạo thêm lỗi.
6. Sau khi khắc phục, theo dõi commit progress và lag giảm ổn định.

Không reset offset chỉ để làm lag về 0. Reset có thể bỏ qua record chưa xử lý hoặc giao lại record đã tạo side effect. Lưu offset hiện tại và xác minh trạng thái nghiệp vụ trước mọi thao tác thay đổi offset.

## 10. Sự cố retry topic và dead-letter topic

**Triệu chứng:** retry backlog tăng, message lặp qua nhiều stage, DLT tăng nhanh hoặc DLT consumer không xử lý được record.

**Kiểm tra:**

- Exception nào đang tạo retry.
- Retry stage, số lần giao và backoff có đúng cấu hình không.
- Retry topic có consumer hoạt động và partition được assign không.
- DLT có nhận đúng eventId, key và metadata gốc không.
- DLT publisher/consumer có lỗi authorization, serialization hoặc broker không.
- Có lỗi cố định như schema mismatch đang bị retry liên tục không.

**Hành động:**

1. Tách retryable khỏi non-retryable error.
2. Sửa dependency hoặc contract gây lỗi.
3. Dừng tự động replay nếu event có thể gây side effect trùng hoặc dữ liệu không hợp lệ.
4. Lưu record DLT và metadata; xác định cách sửa/replay theo từng loại lỗi.
5. Replay một nhóm nhỏ sau khi xác minh idempotency.
6. Theo dõi DLT count và retry backlog sau thao tác.

DLT không đồng nghĩa event đã được xử lý. Nó là nơi lưu record cần điều tra hoặc can thiệp. Không xóa DLT sau khi sửa code nếu chưa có kế hoạch replay hoặc quyết định nghiệp vụ về việc bỏ record.

## 11. Sự cố database, outbox hoặc inbox

**Triệu chứng:** publisher không ghi được publication/outbox, listener không lưu inbox/projection, connection pool cạn hoặc backlog không giảm dù broker hoạt động.

**Kiểm tra:**

- Database connectivity và trạng thái primary/replica.
- Connection pool active/idle/waiting.
- Slow query, lock wait, deadlock và transaction timeout.
- Dung lượng disk, WAL/log growth và replication lag.
- Migration/schema version có tương thích code hiện tại không.
- Outbox record chưa gửi, inbox duplicate và lỗi unique constraint.

**Hành động:**

1. Khôi phục database theo runbook database và bảo đảm primary/replica nhất quán.
2. Xác minh schema/migration trước khi rollback code.
3. Kiểm tra outbox publisher có tiếp tục lấy record chưa gửi sau khi database phục hồi không.
4. Kiểm tra inbox/deduplication để tránh áp dụng lại event đã xử lý.
5. Không xóa record để giải phóng dung lượng nếu chưa xác định retention và trạng thái nghiệp vụ.
6. Theo dõi connection pool, transaction latency và backlog sau phục hồi.

Nếu database có lỗi ghi, không cố tăng connection pool vô hạn. Việc đó có thể làm database quá tải hơn. Điều chỉnh concurrency và khôi phục nguyên nhân gốc theo năng lực database.

## 12. Thu thập bằng chứng cho một event cụ thể

Mỗi lần điều tra nên bắt đầu từ định danh ổn định. Thu thập:

| Trường | Dùng để |
| --- | --- |
| eventId | Theo dõi cùng một event qua retry, DLT và replay. |
| correlationId/traceId | Nối các bước trong một nghiệp vụ hoặc request. |
| eventType/schemaVersion | Xác định hợp đồng và parser đang dùng. |
| producer/service version | Xác định code phát event. |
| listener/consumer group | Xác định nơi nhận và xử lý. |
| topic/partition/offset | Tìm record trên broker. |
| publication identifier/status | Tra cứu registry nội bộ nếu có. |
| attemptCount/firstFailedAt | Hiểu retry và tuổi lỗi. |
| business key/aggregate version | Đối chiếu trạng thái nghiệp vụ và thứ tự event. |
| exception type/category | Chọn chính sách xử lý. |

Không log toàn bộ payload nếu chứa dữ liệu nhạy cảm. Dùng eventId và metadata để truy vấn dữ liệu trong hệ thống có quyền. Bảo toàn timestamp và timezone để so sánh log từ nhiều service.

## 13. Hành động an toàn và hành động cần kiểm soát

| Hành động | Mức kiểm soát | Điều kiện |
| --- | --- | --- |
| Đọc dashboard, log và metric | Thấp | Dùng quyền read-only phù hợp. |
| Tra cứu publication hoặc consumer group | Thấp | Không thay đổi trạng thái. |
| Tăng log level có thời hạn | Trung bình | Giới hạn phạm vi, tránh log payload/secret và có thời điểm hoàn nguyên. |
| Pause một consumer group | Cao | Đánh giá backlog, retention, SLA và owner phê duyệt theo quy trình. |
| Resubmit publication | Cao | Xác minh listener idempotent và side effect. |
| Replay DLT hoặc Kafka record | Cao | Lưu offset/record, xác minh eventId, key, ordering và duplicate. |
| Reset offset | Rất cao | Có checkpoint, kế hoạch replay và đánh giá dữ liệu đã commit. |
| Xóa publication/inbox/outbox/DLT | Rất cao | Chỉ khi có quyết định được phê duyệt và bằng chứng phục hồi. |
| Rollback schema hoặc restore database | Rất cao | Có backup/PITR, compatibility plan và owner database. |

Ưu tiên thao tác read-only để khoanh vùng. Với hành động có thể làm mất hoặc nhân đôi dữ liệu, cần người chịu trách nhiệm nghiệp vụ và kỹ thuật xác nhận phạm vi trước khi thực hiện.

## 14. Recovery publication và replay an toàn

Trước khi resubmit hoặc replay, trả lời bốn câu hỏi:

1. Event có được lưu bền vững và đúng payload không?
2. Side effect lần trước đã commit hay chưa?
3. Handler có idempotency theo eventId/business key không?
4. Replay có ảnh hưởng ordering hoặc aggregate version không?

Quy trình:

- Lưu danh sách eventId và vị trí nguồn.
- Phân loại lỗi và sửa nguyên nhân trước.
- Chọn một event đại diện hoặc batch nhỏ.
- Chạy recovery qua API/tool được hỗ trợ, không sửa trực tiếp bảng nội bộ.
- Xác minh side effect, publication status, offset và metric.
- Mở rộng batch khi kết quả đúng và backlog giảm theo dự kiến.
- Dừng ngay nếu duplicate, thứ tự sai hoặc lỗi tăng.

Với projection có thể tái tạo, cân nhắc rebuild vào storage riêng rồi chuyển traffic sau khi so sánh dữ liệu. Với side effect bên ngoài như payment hoặc shipment, cần tra cứu trạng thái provider và dùng idempotency key trước khi replay.

## 15. Rollback release hoặc cấu hình

Khi sự cố bắt đầu ngay sau deploy:

1. Ghi nhận release version, config revision và migration đã chạy.
2. Tạm dừng rollout hoặc tắt feature flag phát event mới nếu có.
3. Kiểm tra code cũ có đọc được schema/event đã được ghi bởi code mới không.
4. Nếu tương thích, rollback artifact theo quy trình deploy.
5. Nếu không tương thích, giữ bridge consumer hoặc forward-fix; không ép code cũ đọc payload mới.
6. Bảo toàn event đã phát, offset, publication, inbox/outbox và DLT.
7. Xác minh backlog và business invariant sau khi rollback.

Không tự động chạy down migration khi code mới đã ghi dữ liệu vào cột/schema mới. Nếu migration mất dữ liệu, cần restore/PITR hoặc forward-fix; down migration tạo lại cột rỗng không phục hồi dữ liệu đã mất.

## 16. Escalation và phối hợp

Chuyển sự cố đến nhóm phù hợp khi cần:

| Dấu hiệu | Nhóm cần phối hợp |
| --- | --- |
| Transaction, query, lock hoặc database unavailable | Database/platform team |
| Broker, partition, ACL hoặc consumer group lỗi | Messaging/platform team |
| Event schema, listener hoặc module boundary lỗi | Owner của module producer/consumer |
| Payment, shipment hoặc dịch vụ ngoài lỗi | Owner dependency tương ứng |
| Mất/nhân đôi dữ liệu hoặc side effect chưa rõ | Business owner, incident lead và nhóm kỹ thuật liên quan |
| Credential hoặc truy cập bất thường | Security/identity team |

Khi escalation, cung cấp severity, thời điểm, eventId/correlationId mẫu, event type, producer/consumer version, topic/group, số lượng/tuổi backlog, hành động đã thực hiện và rủi ro còn lại. Không gửi secret hoặc payload nhạy cảm qua kênh không được phép.

## 17. Điều kiện xác nhận phục hồi

Không kết thúc incident chỉ vì alert đã hết. Cần xác minh:

- Publisher tạo event đúng với giao dịch đã commit.
- Listener/consumer xử lý thành công theo SLA.
- Publication incomplete giảm về mức bình thường hoặc có danh sách ngoại lệ đã được chấp nhận.
- Consumer lag và tuổi record giảm ổn định.
- Retry topic và DLT không tiếp tục tăng bất thường.
- Outbox/inbox và offset phản ánh đúng tiến độ.
- Side effect không bị duplicate hoặc bỏ sót.
- Projection và dữ liệu nghiệp vụ thỏa invariant.
- Error rate, latency, dependency và health trở lại ngưỡng chấp nhận.
- Không còn thao tác pause, feature flag hoặc log level tạm thời bị bỏ quên.

Giữ quan sát tăng cường trong một khoảng thời gian phù hợp với traffic và SLA. Nếu backlog cần nhiều giờ để xử lý hết, incident chỉ có thể đóng khi có kế hoạch theo dõi và owner rõ ràng cho phần tồn đọng.

## 18. Post-incident review

Sau khi phục hồi, ghi nhận:

- Timeline từ alert đầu tiên đến lúc khôi phục.
- Phạm vi event, module, tenant và nghiệp vụ bị ảnh hưởng.
- Root cause và các yếu tố làm sự cố lan rộng.
- Event nào bị retry, đưa DLT, replay hoặc compensation.
- Dữ liệu nào được phục hồi hoặc đối soát.
- Hành động nào đã hiệu quả và hành động nào gây thêm rủi ro.
- Alert/runbook nào thiếu hoặc phát hiện quá muộn.
- Việc cần làm, owner và deadline.

Không chỉ ghi “consumer bị lỗi” hoặc “Kafka chậm”. Cần chỉ ra nguyên nhân cụ thể, ví dụ dependency timeout làm listener rollback, publication incomplete tăng, retry consumer bị thiếu capacity và lag vượt SLA. Nếu chưa xác định được root cause, ghi rõ giả thuyết và việc cần điều tra tiếp.

## 19. Diễn tập runbook

Runbook cần được diễn tập định kỳ trong môi trường staging hoặc game day có kiểm soát:

| Kịch bản diễn tập | Kết quả cần đạt |
| --- | --- |
| Dừng listener | Phát hiện incomplete publication hoặc consumer lag và phục hồi được. |
| Làm dependency timeout | Retry có giới hạn, không lặp side effect. |
| Gửi payload sai schema | Record được quarantine/DLT, có metadata điều tra. |
| Broker tạm mất kết nối | Publisher/consumer phục hồi theo policy và không mất record. |
| Database read/write failure | Xác định transaction đã commit hay rollback và khôi phục đúng. |
| DLT tăng nhanh | Khoanh vùng lỗi, dừng replay không an toàn và xử lý có kiểm soát. |
| Duplicate delivery | Inbox/idempotency ngăn tác động nghiệp vụ trùng. |
| Rollback release | Code cũ tương thích dữ liệu hoặc bridge/forward-fix được kích hoạt. |

Sau mỗi lần diễn tập, cập nhật runbook bằng kết quả thực tế: thời gian phát hiện, thời gian phục hồi, lệnh/công cụ đã dùng, quyền còn thiếu và bước gây nhầm lẫn. Chỉ ghi các lệnh đã xác minh trên đúng môi trường; không sao chép lệnh production vào tài liệu như thể dùng được ở mọi cluster.

## 20. Mẫu ghi nhận sự cố

Sử dụng mẫu sau trong incident ticket hoặc hệ thống quản lý sự cố:

~~~text
Incident ID:
Severity:
Service / Module:
Start time / Timezone:
Detected by:
Producer version:
Consumer / Listener:
Event type / Schema version:
Event ID / Correlation ID:
Topic / Partition / Offset:
Publication status / Consumer group:
Backlog count / Oldest age:
DLT count:
Business impact:
Suspected cause:
Evidence links:
Actions taken (who / when / scope):
Replay / Resubmit / Compensation details:
Data reconciliation result:
Current risk:
Recovery criteria:
Next update / Owner:
Post-incident actions:
~~~

Mẫu này giúp ca trực tiếp theo tiếp tục điều tra mà không phải suy luận lại những gì đã xảy ra. Ghi rõ timezone, đơn vị đo, môi trường và phạm vi để tránh nhầm lẫn giữa các dashboard.

## 21. Checklist nhanh cho người trực

- Xác định severity và business impact.
- Tìm eventId, correlationId, event type và producer/consumer version.
- Kiểm tra publisher transaction đã commit hay rollback.
- Kiểm tra publication registry, outbox hoặc broker record.
- Kiểm tra listener, consumer group, partition, offset và lag.
- Phân loại exception trước khi retry.
- Bảo toàn publication, inbox, outbox, DLT và offset.
- Xác minh side effect và idempotency trước resubmit/replay.
- Dùng thao tác nhỏ, có thể quan sát và dừng được.
- Escalate đúng owner khi có nguy cơ mất hoặc nhân đôi dữ liệu.
- Xác minh business invariant và backlog sau phục hồi.
- Ghi timeline, quyết định và hành động follow-up.

Runbook sự cố giúp đội vận hành xử lý event pipeline theo bằng chứng và theo đúng ranh giới transaction, publication, broker và nghiệp vụ. Khi sự cố được phân loại trước, dữ liệu và offset được bảo toàn, recovery có idempotency và kết quả được xác minh bằng business invariant, hệ thống có thể phục hồi có kiểm soát mà không làm mất event hoặc tạo thêm tác động ngoài ý muốn.

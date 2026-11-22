# Cảnh báo theo tác động tới nghiệp vụ

Một đêm, CPU của PostgreSQL tăng lên 88% trong mười phút nhưng mọi đơn hàng vẫn được tiếp nhận, thanh toán và xác nhận đúng hạn. Hệ thống gửi hàng chục cảnh báo “CPU cao”, khiến người trực phải kiểm tra một đợt tổng hợp báo cáo vốn đã được lên lịch. Vài ngày sau, CPU chỉ 25%, API vẫn trả HTTP 200, nhưng **outbox ngừng phát sự kiện `OrderPlaced`**: hàng nghìn đơn đã được lưu mà kho vận không nhận được yêu cầu xử lý. Không có cảnh báo nào xuất hiện vì biểu đồ database nhìn vẫn “xanh”.

Hai tình huống cho thấy sự khác biệt giữa **cảnh báo theo trạng thái hạ tầng** và **cảnh báo theo tác động tới nghiệp vụ** (*business-impact-based alerting*). CPU, bộ nhớ, kết nối và lock rất hữu ích để chẩn đoán, nhưng câu hỏi đầu tiên cần trả lời là: **Khách hàng hoặc quy trình nghiệp vụ đang không nhận được kết quả nào, trong bao lâu, và hậu quả là gì?**

Bài thuộc chương **Quan sát và vận hành** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Nội dung kết nối các chủ đề lưu trữ bền vững trong Java: ranh giới transaction, JDBC pool, SQL, concurrency, consistency, cache, outbox, replication, backup và kiểm soát lỗi. Mục tiêu là xây dựng hệ thống cảnh báo có thể **phát hiện mất dữ liệu, ghi trùng, kết quả sai hoặc quá chậm**, giúp người trực hành động được, và giảm cảnh báo không tạo ra quyết định.

**Nguyên tắc xuyên suốt:** Cảnh báo cần xuất phát từ **lời hứa nghiệp vụ có thể đo được**, gắn với một trạng thái lỗi hoặc rủi ro đã định nghĩa, rồi mới chỉ ra các tín hiệu kỹ thuật hỗ trợ chẩn đoán. Một biểu đồ đẹp hay một SLO “xanh” không được coi là bằng chứng không có sai lệch dữ liệu nghiêm trọng.

## 1. Phân biệt triệu chứng nghiệp vụ, nguyên nhân kỹ thuật và tín hiệu dự báo

Giả sử khách hàng đặt hàng và nhận được thông báo “Đặt hàng thành công”:

~~~mermaid
flowchart LR
    A[Khách gửi checkout] --> B[Java API]
    B --> C[(Orders DB)]
    C --> D[Outbox relay]
    D --> E[(Message broker)]
    E --> F[Kho vận / thanh toán]
    F --> G[Hoàn tất xử lý nghiệp vụ]
~~~

Một sự cố có thể được mô tả ở ba mức:

| Mức tín hiệu | Ví dụ | Giá trị vận hành |
| --- | --- | --- |
| **Triệu chứng người dùng/nghiệp vụ** | 8% checkout thất bại; đơn đã nhận không chuyển sang xử lý trong 15 phút | Xác định **tác động**, ưu tiên xử lý và đánh giá SLO |
| **Nguyên nhân hoặc điểm nghẽn** | Đợi row lock, connection pool hết slot, outbox relay dừng | Chỉ đường điều tra và biện pháp khôi phục |
| **Tín hiệu dự báo / sức khỏe hệ thống** | WAL archive lag tăng, disk sắp đầy, backup sắp hết cửa sổ PITR | Phát hiện rủi ro trước khi thành mất dữ liệu/sự cố |

Không nên cấm cảnh báo hạ tầng: **disk còn quá ít dung lượng hoặc archive WAL ngừng liên tục** có thể đe dọa trực tiếp độ bền dữ liệu trước khi người dùng thấy lỗi. Nhưng loại cảnh báo này phải có **mô hình tác động dự kiến, thời gian còn lại để hành động và runbook rõ**, thay vì chỉ dựa vào một ngưỡng tùy tiện.

### Ba câu hỏi trước khi tạo alert

1. **Điều gì đã hoặc sắp xảy ra với nghiệp vụ?** Ví dụ đơn được xác nhận mà không có bản ghi bền vững, số dư sai, yêu cầu đồng bộ quá hạn.
2. **Tín hiệu này chứng minh điều đó đến mức nào?** Một transaction bị deadlock không đồng nghĩa người dùng đã thất bại nếu ứng dụng retry thành công trong ngân sách thời gian.
3. **Người nhận có thể làm gì?** Nếu không có hành động phù hợp và cảnh báo chỉ lặp lại trên một dashboard, hãy cân nhắc đổi thành metric, ticket hoặc báo cáo định kỳ.

## 2. Định nghĩa kết quả nghiệp vụ tại ranh giới persistence

Mỗi operation nên có một **hợp đồng kết quả**: lúc nào coi là tiếp nhận, thành công, thất bại, đang xử lý và chưa rõ kết quả.

Ví dụ `POST /orders` với mục tiêu tạo đơn:

| Trạng thái | Ý nghĩa | Có được trả “thành công” không? |
| --- | --- | --- |
| `REJECTED_VALIDATION` | Input sai, không tiếp nhận | Không; thường không phải lỗi độ tin cậy của dịch vụ |
| `REJECTED_POLICY` | Quyền hoặc ràng buộc nghiệp vụ từ chối hợp lệ | Không; không tự tính là service failure |
| `ACCEPTED_PENDING` | Yêu cầu hợp lệ đã được ghi bền vững để xử lý tiếp | Có thể trả `202` nếu API cam kết xử lý bất đồng bộ |
| `COMMITTED` | Đơn và yêu cầu phát event đã commit theo hợp đồng | Có thể xác nhận bước tạo đơn thành công |
| `FAILED_INTERNAL` | Lỗi hệ thống khiến yêu cầu hợp lệ không đạt kết quả | Lỗi cần tính vào SLI phù hợp |
| `UNKNOWN_OUTCOME` | Mất phản hồi lúc commit/gọi provider, chưa biết đã thực thi chưa | Không tự coi là rollback hoặc thành công |
| `COMPLETED_DOWNSTREAM` | Payment/kho vận hoàn tất theo mốc cam kết | Thành công của **một hành trình nghiệp vụ khác** |

Một API trả HTTP 200 không chứng minh kho vận đã nhận event; một HTTP timeout không chứng minh đơn chưa commit. Cần theo dõi cả **kết quả tại ranh giới đồng bộ** và **tiến trình sau đó**.

Một invariant quan trọng hơn HTTP status:

> Mỗi yêu cầu tạo đơn hợp lệ với một idempotency key được chấp nhận phải dẫn tới **tối đa một đơn đúng**, và yêu cầu đã được xác nhận bền vững phải có khả năng tìm lại/tiếp tục xử lý sau crash.

Nếu phát hiện **hai khoản thu tiền cho một yêu cầu**, dù tổng số request thất bại chỉ 0,01%, đây vẫn có thể là sự cố mức nghiêm trọng cao. Không nên để tỷ lệ thành công trung bình che lấp vi phạm bất biến hiếm nhưng có hậu quả lớn.

## 3. SLI, SLO, SLA và error budget

**SLI** (*Service Level Indicator*) là phép đo cụ thể về một thuộc tính dịch vụ, như tỷ lệ checkout hợp lệ thành công hoặc thời gian đơn chuyển sang xử lý.

**SLO** (*Service Level Objective*) là mục tiêu nội bộ áp dụng cho SLI trong một cửa sổ xác định, ví dụ “99,9% checkout hợp lệ hoàn tất trong 2 giây trong 30 ngày”.

**SLA** (*Service Level Agreement*) là thỏa thuận dịch vụ có thể bao gồm cam kết, điều khoản và hệ quả khi vi phạm; không tự đồng nghĩa với metric SLO.

**Error budget** là lượng thất bại/không đạt yêu cầu được cho phép bởi SLO, trong **cùng mẫu số và cùng cửa sổ**.

Với SLO dạng tỷ lệ 99,9%, tỷ lệ không đạt cho phép là:

\[
1 - 0{,}999 = 0{,}001 = 0{,}1\%
\]

Nếu có 1.000.000 lượt checkout **đủ điều kiện** trong 30 ngày, ngân sách là khoảng **1.000 lượt không đạt** theo định nghĩa SLI. Nếu SLO là availability theo **thời gian** trong đúng 30 ngày, ngân sách tương ứng khoảng **43,2 phút**. Hai cách diễn giải **không hoán đổi tùy tiện**: một sự cố 5 phút vào giờ cao điểm có thể làm thất bại nhiều request hơn 5 phút vào ban đêm.

### Ví dụ một SLI được định nghĩa đủ cụ thể

~~~text
Tên: checkout_valid_completion_ratio
Đơn vị quan sát: Một ý định checkout hợp lệ, nhận diện bằng request_id
Denominator: Tất cả ý định checkout hợp lệ đã được nhận trong cửa sổ
Numerator: Những ý định đạt trạng thái COMMITTED trong tối đa 2 giây
Loại trừ: Request sai format và các trường hợp từ chối hợp lệ bởi business rule
Không loại trừ: Lỗi database, pool timeout, commit không rõ kéo dài quá deadline
Cửa sổ: 30 ngày rolling
Mục tiêu: >= 99,9%
Owner: Nhóm Order Platform
~~~

Phải quy định rõ **đơn vị tính** và **thời điểm chốt outcome**. Đếm HTTP retry thành 3 yêu cầu mới khi user chỉ có một idempotency key sẽ làm sai mẫu số; bỏ qua request timeout vì “không có response” cũng làm SLI đẹp giả tạo.

Nếu SLA đòi trạng thái xử lý cuối cùng sau nhiều phút, nên có **SLI workflow hoàn tất** khác với SLI xác nhận tức thời ở API.

## 4. Chọn SLI gắn với tính đúng đắn của dữ liệu

Với persistence, chỉ đo request success rate và latency là chưa đủ. Cần xem cả khả năng **ghi bền vững, đọc đúng, không trùng và dữ liệu được truyền tới thành phần phụ thuộc**.

| Mục tiêu nghiệp vụ | SLI gợi ý | Mẫu lỗi cần bắt |
| --- | --- | --- |
| Tạo đơn hàng | Tỷ lệ yêu cầu hợp lệ commit trong deadline | DB timeout, pool cạn, rollback |
| Thanh toán đúng số lần | Số vi phạm duplicate charge trên mỗi ý định/đơn | Retry không idempotent, consumer chạy lặp |
| Không thất lạc dữ liệu | Số giao dịch đã ACK nhưng không tìm lại được sau lỗi | Durability/recovery/replication sai |
| Dữ liệu đúng chủ sở hữu | Số lần lộ dữ liệu cross-tenant được phát hiện | Lỗi authorization/cache key/RLS |
| Không bán âm tồn kho | Số invariant violation khi commit | Race, lost update, bỏ constraint |
| Đơn được giao downstream | Tỷ lệ order quá hạn không có sự kiện/ack xử lý | Outbox backlog, broker/consumer lag |
| Người dùng xem dữ liệu mới | Tỷ lệ read-your-writes không đạt ở đường đọc yêu cầu | Replica lag, cache stale |
| Phục hồi khi hỏng | Cửa sổ restorable thực so với RPO, thời gian restore test so với RTO | WAL archive thiếu, backup chain lỗi |

Các chỉ số như **không mất dữ liệu** hoặc **không lộ dữ liệu** thường rất khó quan sát trực tiếp theo thời gian thực. Chúng cần **nhiều lớp phát hiện**: invariant checks trong DB, đối soát theo batch, audit, kiểm thử khôi phục và cảnh báo tức thời khi xuất hiện bất kỳ vi phạm có bằng chứng đáng tin cậy.

**Không báo cáo “0 data loss incidents” chỉ vì chưa có metric nào đếm được data loss.** Cần ghi mức độ bao phủ của hệ thống phát hiện.

## 5. Từ “four golden signals” tới tín hiệu nghiệp vụ

Bốn nhóm tín hiệu thường dùng trong vận hành dịch vụ là **latency, traffic, errors và saturation**. Đối với persistence, cần mở rộng bằng **correctness, durability và consistency lag**.

~~~mermaid
flowchart TD
    A[Hành trình nghiệp vụ] --> B[SLI end-to-end]
    B --> C[Latency]
    B --> D[Errors / outcome]
    B --> E[Correctness]
    B --> F[Durability & completion lag]
    C --> G[JDBC / DB / cache spans]
    D --> H[SQLSTATE / timeout / pool]
    E --> I[Constraints / reconciliation]
    F --> J[Outbox / replication / backup]
    K[Traffic & saturation] --> G
    K --> H
~~~

| Nhóm | Ví dụ metric | Chú ý |
| --- | --- | --- |
| Latency | p95/p99 checkout theo end-to-end request | Không cộng riêng các percentile thành p99 tổng |
| Traffic | Số checkout đủ điều kiện/giây, orders/giây | Sụt traffic có thể là lỗi; cũng có thể theo lịch tự nhiên |
| Errors | Failed/internal/unknown outcomes; deadlock sau khi retry | Phân biệt từ chối hợp lệ với lỗi dịch vụ |
| Saturation | Pool pending, CPU, lock wait, WAL/disk, queue depth | Thường là **nguyên nhân hoặc dự báo**, không phải kết quả nghiệp vụ |
| Correctness | Duplicate order, âm tồn kho, mismatched ledger | Sự kiện ít nhưng độ nghiêm trọng lớn |
| Durability | Backup chain restorable, WAL archive lag | Đe dọa khả năng khôi phục khi hỏng |
| Consistency/completion | Tuổi order pending, outbox age, read-model version lag | Phải có deadline gắn với hành trình nghiệp vụ |

**Một thiết kế tốt có cả metric để paging và metric để debug**, nhưng không gửi tất cả metric lên cùng kênh cảnh báo khẩn cấp.

## 6. Vẽ bản đồ hành trình nghiệp vụ và điểm đo

Ví dụ flow đặt hàng:

~~~mermaid
sequenceDiagram
    participant U as Khách hàng
    participant API as Java Order API
    participant DB as PostgreSQL
    participant O as Outbox relay
    participant B as Broker
    participant W as Fulfillment
    U->>API: Checkout (request_id=R1)
    API->>DB: BEGIN; order + outbox; COMMIT
    DB-->>API: Commit acknowledged
    API-->>U: Order accepted
    O->>DB: Claim outbox event
    O->>B: Publish OrderPlaced(E1)
    B-->>O: Acknowledged
    B->>W: Deliver E1
    W->>W: Deduplicate + persist task
    W-->>B: Ack after commit
    Note over U,W: Từng chặng có deadline và dấu mốc riêng
~~~

Để cảnh báo có ý nghĩa, cần định nghĩa:

- **Bắt đầu**: thời điểm server chấp nhận `request_id`, không chỉ thời điểm người dùng nhấn nút.
- **Đã ghi**: order và outbox cùng commit trong một transaction.
- **Đã gửi**: broker xác nhận theo hợp đồng delivery đã chọn.
- **Đã nhận xử lý**: fulfillment ghi bền vững tác vụ (không chỉ đã đọc packet).
- **Hoàn tất**: trạng thái nghiệp vụ cuối cùng theo business definition.

Mỗi chặng có thể có SLO riêng, nhưng **việc đạt SLO ở chặng trước không chứng minh chặng sau đã đạt**. Nếu API trả 201 trong 50 ms mà fulfillment không có đơn trong 20 phút, SLO API vẫn có thể xanh trong khi trải nghiệm khách hàng không đạt.

### “Accepted” không được đồng nhất với “completed”

Một endpoint `202 Accepted` có thể đúng hợp đồng nếu lưu công việc bền vững rồi xử lý sau. Định nghĩa cảnh báo phải tách:

1. **Acceptance failures:** không lưu được ý định xử lý.
2. **Completion misses:** yêu cầu đã nhận nhưng vượt deadline xử lý.
3. **Correctness failures:** xử lý hai lần, sai số tiền, sai tenant, mất sự kiện.

Đếm completion misses phải truy được những request đã được accept từ một nguồn **bền vững**, tránh dựa hoàn toàn vào một counter in-memory có thể mất khi process crash.

## 7. Xử lý tín hiệu lỗi: kết quả hợp lệ khác lỗi hệ thống

Không phải mọi HTTP 4xx, constraint violation hoặc SQL exception đều là vấn đề độ tin cậy.

| Outcome | Có tính vào lỗi service theo SLI checkout thông thường? | Lý do |
| --- | --- | --- |
| Input sai định dạng và bị trả 400 đúng | Thường không | User input không đạt hợp đồng |
| Người dùng không có quyền và bị trả 403 đúng | Thường không | Authorization hoạt động |
| Tồn kho đã hết, từ chối theo quy tắc | Thường không | Quyết định nghiệp vụ đúng |
| Database unavailable, yêu cầu hợp lệ trả 503 | Có | Dịch vụ không thực hiện được |
| Connection pool timeout gây checkout thất bại | Có | Lỗi hạ tầng ảnh hưởng hành trình |
| Deadlock được retry thành công dưới deadline | Không nhất thiết | Người dùng vẫn nhận kết quả đúng/hạn |
| Deadlock retry hết lần, yêu cầu hợp lệ thất bại | Có | Mất khả dụng |
| SQLState 23505 do retry cùng idempotency key hợp lệ | Có thể là duplicate-safe replay | Cần kiểm tra fingerprint và trả kết quả cũ |
| Một order bị tạo hai lần do retry | **Lỗi correctness nghiêm trọng** | Dù API đều trả 200 |
| Commit outcome không rõ trong nhiều phút | Có nếu vượt deadline resolution | Không thể coi là rollback chắc chắn |

Việc phân loại lỗi cần tương thích hợp đồng của từng endpoint. Ví dụ nhiều yêu cầu hết hàng hợp lệ có thể là **tín hiệu sản phẩm/tồn kho** cần thông báo vận hành kinh doanh, nhưng không phải một incident “database hỏng”.

Không gom mọi trường hợp `SQLException` vào “DB error rate” và paging, vì một số exception phản ánh input hoặc constraint hoạt động đúng. Cũng không nuốt exception dưới dạng `Optional.empty()` làm hệ quan sát không thấy lỗi thật.

## 8. Latency: đo độ trễ thấy được và độ trễ từng chặng

Một request mất 2 giây có thể do:

~~~text
API parse/validate      10 ms
JDBC pool acquisition  700 ms
SQL execute/fetch       80 ms
DB transaction commit   20 ms
HTTP serialization       5 ms
Hàng đợi/khác          1185 ms
-----------------------------
Tổng                  2000 ms
~~~

Ví dụ này chỉ minh họa việc phân rã **trên cùng một request**; mỗi đoạn phải được instrument tại ranh giới rõ ràng. Không cộng p95 pool + p95 SQL + p95 HTTP để tuyên bố đó là p95 end-to-end; percentile không cộng tuyến tính như vậy.

Hệ thống nên có:

- Histogram latency end-to-end theo operation đã phê duyệt, bao gồm timeout.
- Connection acquisition/hold time của pool (ví dụ HikariCP hoặc provider đang dùng).
- SQL elapsed/fetch/commit theo loại operation, không gắn full SQL có dữ liệu nhạy cảm làm label.
- DB waits (lock, I/O, client, v.v.), query plan và số câu SQL trên request.
- Async queue age từ mốc commit/accept đến lúc consumer hoàn tất.

Khi p99 vượt SLO, alert theo **tỷ lệ request vượt deadline** thường phù hợp hơn một p99 lẻ vì nó gắn với error budget. p99 vẫn rất hữu ích ở dashboard và trong chẩn đoán.

### Cẩn trọng ở lưu lượng thấp

Nếu một endpoint chỉ có 5 request trong 5 phút, một lỗi làm error rate thành 20%. Tỷ lệ này có thể đáng điều tra, nhưng paging tự động theo ngưỡng 1% sẽ rất nhiễu nếu không xét **số lượng, giá trị nghiệp vụ và độ tin cậy thống kê**. Đối với đường cực kỳ quan trọng nhưng ít gọi, có thể dùng **synthetic transaction, kiểm tra trạng thái bền vững hoặc alert tuyệt đối trên một lỗi đã xác minh**, thay vì chỉ rate.

## 9. Lỗi im lặng: dữ liệu sai nhưng HTTP vẫn 200

Một cảnh báo theo nghiệp vụ phải phát hiện những sự cố mà latency và 5xx không thấy:

- Hai giao dịch thanh toán có cùng business request nhưng tạo hai charge.
- Số dư tài khoản hoặc tồn kho trở thành âm do lost update.
- Một event được đánh dấu đã xử lý nhưng business side effect chưa commit.
- Dữ liệu cross-tenant được trả qua cache hit dù DB có RLS.
- Projection chứa revision cũ và được dùng để chốt giá.
- Đơn hàng được ACK nhưng không thể tìm lại sau failover.

Các phép đo hữu ích:

~~~text
duplicate_business_effects_total
inventory_negative_rows
ledger_reconciliation_mismatches
confirmed_orders_missing_outbox_event
orders_without_required_downstream_task
tenant_scope_violation_confirmed_total
~~~

Các tên trên là **minh họa**, không phải metric tự có của PostgreSQL/Java. Chúng phải được xây dựng bằng phép kiểm tra có chứng cứ: unique key, constraints, transaction logic, outbox/inbox reconciliation, scheduled consistency checks hoặc audit.

**Lưu ý:** một counter bằng 0 không chứng minh tuyệt đối không có sai lệch nếu luồng đối soát đang dừng. Vì vậy cần thêm **freshness/coverage của job kiểm tra**, như `reconciliation_last_success_timestamp_seconds` và phần dữ liệu đã được đối soát.

### Lúc nào nên page ngay cả với một lỗi?

Khi đã có bằng chứng **rò rỉ dữ liệu nhạy cảm, duplicate charge, mất giao dịch đã ACK hoặc invariant tài chính bị phá**, một trường hợp có thể đủ kích hoạt mức nghiêm trọng cao. Không chờ lỗi vượt 1% vì “sample size chưa đủ”. Quy trình phải giảm false positive bằng cách kiểm chứng tín hiệu, deduplicate incident và có runbook điều tra/khắc phục an toàn.

## 10. Theo dõi workflow bất đồng bộ: backlog chưa chắc là tác động

Outbox và consumer đều có thể tích tụ công việc mà **chưa** ảnh hưởng cam kết nếu vẫn trong deadline.

| Tín hiệu | Phản ánh | Hạn chế |
| --- | --- | --- |
| `outbox_pending_count` | Có bao nhiêu event chưa phát | Đợt traffic tăng có thể làm backlog tăng hợp lệ |
| `oldest_outbox_age_seconds` | Event lâu nhất đang chờ bao lâu | Cần phân loại event, retry, poison |
| `consumer_lag` | Độ lệch offset/hàng đợi consumer | Không trực tiếp bằng thời gian trễ nghiệp vụ |
| `orders_over_processing_deadline` | Số đơn chưa có tác vụ xử lý quá hạn | Trực tiếp hơn với cam kết cho khách |
| `event_publish_failure_rate` | Gửi broker gặp lỗi ra sao | Retry có thể phục hồi trước hạn |
| `reconciliation_gap` | DB gốc khác projection/side effect | Tín hiệu correctness, cần dữ liệu đủ tin cậy |

Ví dụ một đợt flash sale tạo 50.000 đơn trong 2 phút. Outbox pending tăng từ 0 lên 8.000, rồi về 0 trong 90 giây. Nếu SLO cho phép sự kiện đến fulfillment trong 5 phút, không nhất thiết phải page vì queue length > 5.000. Ngược lại, chỉ có 3 đơn ở trạng thái `PENDING_FULFILLMENT` quá 30 phút cũng có thể là sự cố cần xử lý.

### Định nghĩa age dựa vào sự kiện bền vững

Để đo thời gian “đã accept nhưng chưa hoàn tất”, dùng timestamp được ghi cùng transaction/record nguồn thay vì một stopwatch chỉ tồn tại trong RAM:

~~~sql
-- PostgreSQL: ví dụ đếm đơn quá hạn chưa được fulfillment xác nhận.
-- Các trạng thái/cột chỉ là một lược đồ minh họa.
SELECT COUNT(*) AS overdue_orders
FROM orders
WHERE status = 'ACCEPTED'
  AND accepted_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes';
~~~

Câu SQL này đúng chỉ nếu `status='ACCEPTED'` vẫn phản ánh “chưa được downstream xử lý”, được cập nhật bền vững từ một sự kiện xác nhận đáng tin cậy. Nếu trạng thái đang cập nhật bất đồng bộ hoặc có trạng thái lỗi riêng, query phải tính đủ tất cả trạng thái **chưa hoàn tất**, không lấy một giá trị đơn giản rồi bỏ sót.

Không quét bảng lớn mỗi vài giây để lấy metric nếu làm tăng tải DB đáng kể; dùng index, bảng theo dõi workflow hoặc bộ tổng hợp đáng tin và kiểm soát tần suất đo.

## 11. Độ bền dữ liệu và khả năng khôi phục cần cảnh báo chủ động

Một hệ có thể chưa có lỗi API nhưng đã mất khả năng đạt RPO/RTO vì WAL archiving dừng hoặc bản backup gần nhất không giải mã/restore được.

| Rủi ro | Tín hiệu | Tác động nếu không can thiệp |
| --- | --- | --- |
| WAL archiver liên tục lỗi | Archive failures tăng, log coverage bị thiếu | PITR có thể không đạt target khi primary hỏng |
| Backup chain bị hỏng | Restore rehearsal/checksum thất bại | Backup tồn tại nhưng không dùng được |
| Backup quá cũ | Tuổi bản backup usable vượt chính sách | RPO hoặc cửa sổ restorable co lại |
| Replica lag tăng | Commit-to-visible lag, ứng dụng cần read-your-writes thất bại | Người dùng không thấy thay đổi vừa ghi |
| Disk/WAL sắp đầy | Dự báo hết dung lượng theo growth, không chỉ % hiện tại | Transaction mới có thể bị chặn/lỗi |
| Connection leak | Pool pending/hold time tăng kéo dài | API timeout dù DB CPU thấp |

**RPO** là lượng mất dữ liệu chấp nhận theo kịch bản phục hồi; **RTO** là thời gian khôi phục dịch vụ. Một dòng `last_archived_time` không tiến không tự chứng minh archive hỏng nếu không có WAL mới được tạo. Cần kết hợp **WAL generation rate, archive lag, số lần lỗi và actual restorable window**.

Những cảnh báo chủ động phải thể hiện **thời gian còn lại trước khi vi phạm một cam kết**. Ví dụ “archive lag tăng 10 phút và SLO RPO yêu cầu 15 phút; nếu primary mất ngay bây giờ, dữ liệu có nguy cơ vượt mức mất cho phép” có giá trị hơn “archive_command có một lỗi”.

### Không coi backup success là restore success

Chỉ báo “backup job exit 0” chưa chứng minh có thể phục hồi. Cần test restore độc lập định kỳ, xác minh checksum, khóa giải mã, WAL continuity và thời gian hoàn tất so với RTO. Khi diễn tập thất bại, cảnh báo phải được phân loại theo **sự mất khả năng khôi phục** chứ không chỉ “cron job warning”.

## 12. Xác định phạm vi tác động, mức độ nghiêm trọng và người chịu trách nhiệm

Một alert tốt nên nêu **bị ảnh hưởng đến đâu**:

| Mức ví dụ | Khi nào áp dụng | Phản ứng |
| --- | --- | --- |
| **SEV1 / critical** | Mất dữ liệu đã ACK, sai số tiền, duplicate charge, lộ dữ liệu, nhiều khách không giao dịch được | Page người trực ngay, mở incident, bảo toàn bằng chứng và giới hạn side effect |
| **SEV2 / high** | SLO checkout tiêu hao ngân sách nhanh, backlog quá hạn ảnh hưởng số đơn đáng kể | Page nhóm chịu trách nhiệm, triage trong ca trực |
| **SEV3 / warning** | Rủi ro sắp vượt RPO, backup test quá hạn, độ trễ tăng nhưng chưa gây vi phạm | Ticket/notification trong thời gian xử lý phù hợp; escalations nếu tiếp diễn |
| **Info** | CPU tăng trong đợt batch đã biết, deadlock retry thành công, thay đổi latency nhỏ | Dashboard/log, không page |

Tên SEV và tiêu chí ở đây chỉ **minh họa**, không phải chuẩn chung bắt buộc. Một vi phạm RPO thực tế có thể xứng đáng SEV1 dù chưa có lỗi khách hàng; một lỗi dữ liệu chỉ ảnh hưởng một khách VIP hoặc thanh toán giá trị lớn có thể nghiêm trọng hơn lỗi nhiều request thấp giá trị.

Trong alert routing, ít nhất cần:

- **Service và hành trình**: ví dụ `order-checkout`, `fulfillment-ack`, `payment-reconciliation`.
- **Ảnh hưởng**: tỷ lệ request, số đơn quá hạn, tenant tier hoặc nhóm khách bị ảnh hưởng.
- **Mức chứng cứ**: xác minh được data corruption hay chỉ là leading indicator.
- **Owner**: đội chịu trách nhiệm chính, backup owner và escalation.
- **Runbook/dashboard/trace**: vị trí tra cứu và bước khôi phục đầu tiên.

Không đưa raw customer ID, email, order ID, token hoặc payload nhạy cảm vào alert label/pager. Khi cần điều tra ca cụ thể, dẫn tới hệ thống audit có phân quyền thay vì đẩy dữ liệu cá nhân vào notification công khai.

## 13. Error-budget burn rate: phát hiện vi phạm SLO đang tăng nhanh

Nếu SLO trong 30 ngày là 99,9% yêu cầu đạt chuẩn, error budget là **0,1%**. Một hệ đang có tỷ lệ không đạt **1,44%** đã tiêu hao ngân sách nhanh hơn tốc độ cho phép:

\[
\text{Burn rate}
=\frac{\text{Tỷ lệ request không đạt quan sát}}{1-\text{SLO}}
=\frac{0{,}0144}{0{,}001}=14{,}4
\]

Burn rate không trực tiếp là số người dùng bị lỗi; nó là **tốc độ tiêu hao ngân sách tương đối với mục tiêu**. Một sự cố kéo dài một giờ với burn rate 14,4 tiêu hao lượng ngân sách tương đương khoảng 14,4 giờ ở tốc độ 1×, trong cùng mô hình tỷ lệ và điều kiện tải. Nếu cửa sổ SLO 30 ngày, đó xấp xỉ **2% error budget của cửa sổ**, không phải 14,4% số request của cả tháng.

### Dùng nhiều cửa sổ thay vì một ngưỡng tức thời

Một mẫu cảnh báo thường có:

- **Cửa sổ dài:** xác nhận ảnh hưởng đáng kể, tránh phản ứng theo một spike rất ngắn.
- **Cửa sổ ngắn:** xác nhận lỗi **vẫn đang diễn ra**, tránh page vì sự cố đã kết thúc.
- **Ngưỡng burn rate:** gắn mức ưu tiên với tốc độ tiêu hao ngân sách.

Ví dụ minh họa cho SLO 99,9%, cửa sổ rolling 30 ngày:

| Mức | Burn rate | Hai cửa sổ cùng vượt | Ý nghĩa |
| --- | ---: | --- | --- |
| Fast burn | 14,4× | 1 giờ và 5 phút | Có khả năng tiêu hao ngân sách nhanh; cân nhắc page |
| Medium burn | 6× | 6 giờ và 30 phút | Sự cố kéo dài có ảnh hưởng tích lũy |
| Slow burn | 1× hoặc ngưỡng được chọn theo chính sách | 1–3 ngày hoặc báo cáo định kỳ | Cần kế hoạch cải thiện, không nhất thiết đánh thức người trực |

Các giá trị ở đây là **ví dụ thiết kế**, không phải ngưỡng bắt buộc cho mọi SLO hay công cụ. Phải hiệu chỉnh theo số request, độ nghiêm trọng, múi giờ vận hành và thời gian đáp ứng thực tế.

### Giới hạn quan trọng

1. Burn rate cho SLI request-based **không đo trực tiếp** sự cố correctness hiếm nhưng rất nặng. Một duplicate charge có thể phải page ngay.
2. Ở lưu lượng thấp, tỷ lệ nhảy rất mạnh. Cần số lượng tối thiểu, tín hiệu tuyệt đối hoặc synthetic check phù hợp.
3. Ở lưu lượng rất cao, một tỷ lệ nhỏ có thể tương đương nhiều khách hàng; phải báo kèm số lượng bị ảnh hưởng.
4. Nếu metric thiếu dữ liệu do exporter chết, không được tự diễn giải error rate bằng 0.
5. Một SLI nghiệp vụ không có **đơn vị quan sát ổn định** sẽ cho burn rate sai: retry nhân mẫu số hoặc request unknown bị bỏ qua là hai lỗi phổ biến.

## 14. Ví dụ PromQL: tỷ lệ yêu cầu không đạt và tuổi công việc quá hạn

Giả sử hệ thống xuất metric minh họa:

~~~text
business_checkout_slo_decisions_total{outcome="good"}
business_checkout_slo_decisions_total{outcome="bad"}
business_outbox_oldest_unpublished_age_seconds{service="orders"}
business_reconciliation_last_success_timestamp_seconds{job="ledger"}
~~~

Quy ước:

- Mỗi **ý định checkout đủ điều kiện** được chốt outcome một lần sau deadline đánh giá; `good` nếu đạt yêu cầu, `bad` nếu không đạt.
- Không tạo label có `order_id`, `request_id` hoặc một event ID riêng.
- `business_outbox_oldest_unpublished_age_seconds` là gauge đo từ timestamp lưu bền vững; khi không còn pending, exporter theo quy ước trả `0`.
- `business_reconciliation_last_success_timestamp_seconds` là Unix timestamp của lần đối soát thành công gần nhất, không phải thời gian scrape.

**PromQL cho tỷ lệ không đạt trong một giờ** (minh họa metric của riêng service này):

~~~promql
sum(increase(business_checkout_slo_decisions_total{outcome="bad"}[1h]))
/
clamp_min(
  sum(increase(business_checkout_slo_decisions_total[1h])),
  1
)
~~~

Giá trị khoảng `0.0144` tương đương tỷ lệ không đạt `1.44%`. `clamp_min(..., 1)` ở đây tránh chia cho 0 trong phép tính **count trong cửa sổ**, nhưng **không** chứng minh “không request = hệ thống khỏe”; cần kiểm tra no-data/low-traffic riêng. Nếu một series chưa từng được tạo, kết quả có thể là **empty/no data**, không phải 0; triển khai thực tế phải xác định rõ hành vi.

Ví dụ điều kiện **hai cửa sổ cùng vượt 14,4× budget**:

~~~promql
(
  sum(increase(business_checkout_slo_decisions_total{outcome="bad"}[1h]))
  /
  clamp_min(sum(increase(business_checkout_slo_decisions_total[1h])), 1)
  > 0.0144
)
and
(
  sum(increase(business_checkout_slo_decisions_total{outcome="bad"}[5m]))
  /
  clamp_min(sum(increase(business_checkout_slo_decisions_total[5m])), 1)
  > 0.0144
)
~~~

Trong cấu hình production, có thể thêm kiểm tra mẫu số tối thiểu và đường cảnh báo riêng cho **một lỗi đặc biệt nghiêm trọng**. Đồng thời nên đặt tên recording rule, owner và routing; không dùng một query tổng hợp mọi tenant/service nếu mức ảnh hưởng của từng nhóm khác xa nhau.

**Cảnh báo tuổi outbox**:

~~~promql
max by (service) (
  business_outbox_oldest_unpublished_age_seconds
) > 300
~~~

Ngưỡng 300 giây chỉ phù hợp nếu workflow thực sự phải publish trong 5 phút. Nếu outbox đang trống mà exporter dừng, gauge cũ có thể biến mất: cần alert về exporter/scrape hoặc đo lần update thành công.

**Cảnh báo đối soát không chạy được trong một giờ**:

~~~promql
time() - max by (job) (
  business_reconciliation_last_success_timestamp_seconds
) > 3600
~~~

Đây là cách kiểm tra **độ mới của bằng chứng**, không phải so kết quả đối soát. Cần thêm cảnh báo khi **có mismatch thực tế** và khi series mất hoàn toàn, vì một metric biến mất có thể khiến biểu thức trên không tạo alert nào. Nếu reconciliation theo lịch hai giờ/lần, ngưỡng một giờ là sai thiết kế; hãy gắn ngưỡng với lịch và SLO của job.

### Cảnh báo histogram latency

Nếu Micrometer/Prometheus xuất histogram `checkout_latency_seconds_bucket` và có label phù hợp, có thể tính p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(checkout_latency_seconds_bucket[5m])
  )
)
~~~

Query này chỉ đúng khi histogram metric tồn tại, bucket và cấu hình quan sát phù hợp. Không cần tự tạo p95 “giả” bằng cách lấy trung bình của các p95 theo pod. Với SLO “95% request dưới 2 giây”, **tỷ lệ vượt ngưỡng/không đạt** thường giúp đốt ngân sách chính xác hơn một cảnh báo p95 đơn lẻ.

## 15. Java/Micrometer: ghi metric theo kết quả có ý nghĩa

Một service Java có thể dùng Micrometer để phát các metric theo tên operation và outcome **có tập giá trị hữu hạn**. Đoạn ví dụ sau chỉ trình bày instrumentation, không thay thế nơi lưu trạng thái nghiệp vụ bền vững:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.util.EnumMap;
import java.util.Objects;

public final class CheckoutTelemetry {
    public enum Outcome {
        GOOD, BAD, UNKNOWN
    }

    private final EnumMap<Outcome, Counter> counters =
            new EnumMap<>(Outcome.class);
    private final EnumMap<Outcome, Timer> timers =
            new EnumMap<>(Outcome.class);

    public CheckoutTelemetry(MeterRegistry registry) {
        Objects.requireNonNull(registry);
        for (Outcome outcome : Outcome.values()) {
            String label = outcome.name().toLowerCase(
                    java.util.Locale.ROOT);

            counters.put(outcome,
                    Counter.builder("business.checkout.slo.decisions")
                            .tag("outcome", label)
                            .description("SLO decisions by outcome")
                            .register(registry));

            timers.put(outcome,
                    Timer.builder("checkout.latency")
                            .tag("outcome", label)
                            .publishPercentileHistogram()
                            .register(registry));
        }
    }

    public void recordDecision(
            Outcome outcome, Duration elapsed) {
        Objects.requireNonNull(outcome);
        Objects.requireNonNull(elapsed);
        if (elapsed.isNegative()) {
            throw new IllegalArgumentException(
                    "elapsed phải không âm");
        }
        counters.get(outcome).increment();
        timers.get(outcome).record(elapsed);
    }
}
~~~

**Lưu ý về tên metric:** mã Micrometer dùng tên dạng dấu chấm và backend Prometheus thường chuẩn hóa thành tên có dấu gạch dưới/suffix `_total` cho counter, `_seconds` cho timer; **xác minh tên metric thực được exporter xuất ra** trước khi sao chép PromQL ở phần trước. Mẫu trên dùng `unknown` để minh họa trạng thái chưa rõ nhưng cách tính SLI phải xác định nó thành `good` hoặc `bad` sau deadline; **không đếm cùng một ý định hai lần**.

**Các giới hạn rất quan trọng:**

1. **Không gọi `recordDecision()` tại mọi HTTP retry** nếu SLI tính theo một business intent: các retry có thể làm mẫu số tăng sai. Hãy có cơ chế xác định outcome duy nhất theo `request_id` ở nguồn bền vững rồi đưa ra metric tổng hợp phù hợp.
2. **Metric counter trong RAM không phải sổ cái nghiệp vụ**. DB có thể commit rồi process chết trước khi tăng counter, hoặc counter có thể reset lúc restart. Với kiểm tra correctness/accepted-vs-completed, nguồn đáng tin là trạng thái DB/event/audit được đối soát.
3. Label phải giới hạn: `outcome`, `service`, `operation` thuộc tập giá trị được kiểm soát. Không dùng user ID, order ID, SQL text nguyên văn hoặc request path chứa ID làm label.
4. Đo duration bằng đồng hồ đo thời gian trôi qua thích hợp (`System.nanoTime()` hoặc cơ chế timing của framework), không lấy hai mốc wall clock có thể bị chỉnh để đo elapsed.
5. Những lời gọi metric phải có overhead được kiểm soát; telemetry gặp lỗi không được làm transaction nghiệp vụ ghi trùng hoặc bị đánh dấu thành công giả.

Với Spring Boot/Micrometer, thư viện có thể đã instrument HTTP, HikariCP và JDBC; tránh nhân đôi metric không cần thiết. **Business outcome metric** vẫn cần định nghĩa và triển khai có chủ đích vì HTTP 200 không biết order đã giao downstream hay chưa.

## 16. Chẩn đoán sau alert: Java, connection pool và PostgreSQL

Khi một SLI checkout bắt đầu burn nhanh, dashboard hỗ trợ nên trả lời:

1. **API:** lỗi phát sinh ở endpoint nào, tenant/operation tier nào, có deployment mới không?
2. **Pool:** `active/idle/pending`, acquisition time và connection hold time có bất thường?
3. **DB:** wait event thuộc nhóm Lock, I/O, Client, LWLock hay không có wait? SQL có tăng calls/rows?
4. **Transaction:** có nhiều transaction dài hoặc `idle in transaction` giữ khóa?
5. **External dependencies:** broker, payment provider, cache hoặc replica có trễ?
6. **Correctness:** có record `UNKNOWN_OUTCOME`, giao dịch đã ACK chưa được tìm thấy hoặc event quá hạn?

Một truy vấn PostgreSQL **chỉ đọc** hữu ích cho triage:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    NOW() - xact_start AS transaction_age,
    NOW() - query_start AS query_age,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST
LIMIT 100;
~~~

**Không suy diễn quá mức:**

- `state='active'` vẫn có thể đang **đợi** một tài nguyên; không đồng nghĩa dùng CPU.
- `wait_event_type='Lock'` là bằng chứng backend tại thời điểm lấy mẫu đang chờ một loại khóa, nhưng snapshot không chứng minh toàn bộ sự cố chỉ do lock.
- `query_age` khi session idle có thể không phải thời gian một query đang chạy; đọc cùng `state`.
- Backend PostgreSQL không thấy request **đang đợi mượn pool connection** ở Java, vì SQL chưa được gửi đến DB.
- Một deadlock được retry thành công có thể không làm khách hàng thất bại; xem kết quả cuối và deadline.

Nếu dùng PostgreSQL `pg_stat_statements` (khi extension đã bật) để tìm truy vấn có tổng thời gian lớn, cần kiểm tra **calls, total time, row count, buffers và cửa sổ đo**; không chỉ tìm câu SQL có mean lớn nhất. Với query plan, dùng `EXPLAIN` có kiểm soát, vì `EXPLAIN ANALYZE` thật sự chạy statement và có thể gây tác động ghi.

### Không alert dựa duy nhất vào một ngưỡng connection count

Pool có 20/20 connection active là bình thường nếu load ổn định, thời gian giữ ngắn và không có pending request. Ngược lại, pending requests kéo dài hơn deadline checkout là tín hiệu tác động đáng quan tâm. Kết nối nhiều chỉ là một **dấu hiệu**; đừng tự tăng pool từ 20 lên 200 khi database đang bị hot-row lock hoặc I/O saturation.

## 17. Dashboard, trace và log: điều tra một incident theo chiều dọc

Metric cho biết **bao nhiêu và từ khi nào**; distributed trace chỉ ra **yêu cầu đi qua đâu**; log/audit cung cấp bằng chứng cho **trạng thái và lỗi cụ thể**.

~~~mermaid
flowchart TD
    A[Alert: đơn quá hạn 5 phút] --> B[Dashboard: số đơn + phân nhóm]
    B --> C[Trace: Order API → DB → outbox → broker]
    C --> D[Log theo correlation ID]
    D --> E[DB / event audit: trạng thái authoritative]
    E --> F[Runbook + biện pháp an toàn]
~~~

Ví dụ trace có các span:

~~~text
HTTP POST /orders                120 ms
  OrderService.validate           10 ms
  JDBC pool acquire                7 ms
  PostgreSQL transaction          75 ms
    INSERT order                  25 ms
    INSERT outbox                 10 ms
    COMMIT                        40 ms
  Serialize response              11 ms

Sau đó (khác trace/worker nếu cần):
  Outbox publish delay           600 s
  Broker consumer lag           300 s
~~~

Không được cộng những số trên thành một “HTTP latency” chung; phần worker là **workflow bất đồng bộ** có timestamp, correlation và SLO riêng.

### Correlation và bảo mật

- Gắn `trace_id`, `correlation_id` và `event_id` ở log/tracing **có phân quyền**.
- Sử dụng span attributes có cardinality kiểm soát và không chứa raw SQL parameter, JWT, số thẻ, mật khẩu hay thông tin cá nhân.
- Không dùng `event_id` làm Prometheus metric label: một event khác nhau tạo một time series, làm tăng chi phí lưu/CPU.
- Khi tracing sampling bỏ qua một request, **metric SLI vẫn phải bao phủ toàn lưu lượng** hoặc có phương pháp ước lượng hợp lệ; không lấy số trace được sampling làm mẫu số SLO.
- Nếu log/trace exporter bị lỗi, incident không được tự trở thành “zero errors”; giám sát độ sẵn sàng của pipeline observability.

Một trường hợp thiếu dữ liệu do sampling phải được ghi nhận là **hạn chế bằng chứng**, không tự xác minh rằng giao dịch đã được xử lý.

## 18. Chống alert fatigue: nhóm, khử trùng lặp và giảm nhiễu

Nếu cùng một lỗi database làm 30 pod checkout báo pool timeout, không nên page 30 lần với 30 người trực. Tổ chức cảnh báo có thể:

1. **Group theo service/region/operation/incident class**, không theo instance ID hoặc request ID.
2. **Deduplicate** các symptom cùng nguyên nhân khi có bằng chứng đáng tin; giữ thông tin phạm vi ảnh hưởng.
3. **Inhibit** cảnh báo nguyên nhân phụ ở tầng dưới khi một cảnh báo chính đã bao phủ, nhưng không giấu **data loss/correctness** vì nó quan trọng riêng.
4. Dùng cửa sổ xác nhận và điều kiện “for” phù hợp cho leading indicators có dao động.
5. Dùng **maintenance window có phê duyệt** cho batch đã lên lịch; không tắt toàn bộ alert business-impact trong thời gian bảo trì.
6. Phân biệt **page cần hành động ngay**, **ticket cần xử lý giờ làm việc** và **metric để xem trong dashboard**.
7. Theo dõi chất lượng cảnh báo sau mỗi incident: thời gian phát hiện, false positives, duplicated pages, alerts thiếu runbook.

Một cấu hình silence quá rộng có thể làm mất tín hiệu về rò dữ liệu, nghiệp vụ thất bại hoặc nguy cơ mất khả năng restore. Silence phải có **owner, lý do, phạm vi và thời hạn**, cùng đường escalation khi phát hiện tác động ngoài dự kiến.

### Không thiết kế một alert cho mỗi metric

Một vận hành viên không thể xử lý “CPU > 80%”, “heap > 75%”, “connections > 90%”, “lock waits > 20” và “latency > 500ms” như năm incident độc lập khi tất cả là một chuỗi nhân quả. Ưu tiên alert **hành trình đang hỏng**, còn các metric kỹ thuật được đính kèm để điều tra.

Ngược lại, các rủi ro **trước tác động** như WAL archive không đạt RPO có thể cần cảnh báo độc lập dù checkout hiện tại vẫn tốt.

## 19. Runbook: mỗi cảnh báo phải dẫn tới quyết định an toàn

Mẫu runbook:

~~~text
Alert: OrdersNotHandedToFulfillmentWithin5m
Mục tiêu: >= 99.9% đơn ACCEPTED có fulfillment task trong <= 5 phút
Phạm vi: Order Platform / region / tenant tier
Triệu chứng: số đơn quá hạn tăng; có thể đã ACK đơn cho khách
Owner: Order Platform on-call
Escalation: Messaging team, Fulfillment team, Incident Commander
Dashboard: business order completion + outbox + broker lag
Không làm: gửi lại payment charge, xóa pending outbox, restart bừa
~~~

Quy trình ứng cứu gợi ý:

1. **Xác nhận tác động:** bao nhiêu đơn đã quá hạn, từ khi nào, tenant/region nào, có trùng giao dịch không? Đối chiếu một mẫu với nguồn DB bền vững.
2. **Bảo vệ correctness:** nếu có nguy cơ xử lý trùng, tạm dừng side effect nguy hiểm theo runbook; không dùng retry vô hạn.
3. **Khoanh vùng chặng lỗi:** DB có order+outbox chưa? Relay còn chạy không? Broker ACK? Consumer offset/lag? Fulfillment có ghi task?
4. **Phục hồi có kiểm soát:** restart/redeploy relay nếu phù hợp, sửa kết nối hoặc quota, tăng worker từ từ nếu bottleneck cho phép; theo dõi backlog, DB và duplicate.
5. **Đối soát:** so order đã accept với task thật, replay event với **event ID ổn định**, consumer inbox phải idempotent. Các trường hợp kết quả payment unknown phải hỏi provider trước khi retry.
6. **Đóng incident:** số đơn quá hạn giảm, không thêm duplicate, SLI hồi phục, backlog xử lý đúng, còn bao nhiêu ngoại lệ cần giải quyết thủ công?
7. **Hậu kiểm:** ghi nguyên nhân gốc, khoảng thời gian ảnh hưởng, số đơn/người dùng, dữ liệu mất/trùng (nếu có), cách ngăn tái diễn và cải thiện alert.

**Cảnh báo không nên có “biện pháp một nút” quá nguy hiểm.** Ví dụ tự động chạy `TRUNCATE outbox_events` để giảm backlog sẽ làm mất ý định phát event; tự động `pg_terminate_backend` trên mọi blocker có thể làm rollback transaction nghiệp vụ quan trọng. Biện pháp tự động phải có tiền điều kiện, giới hạn và khả năng quan sát rõ.

## 20. Tình huống: API xanh nhưng 420 đơn không được xử lý

Giả định trong 15 phút:

~~~text
Checkout HTTP success rate:       99.98%
Checkout p95:                     90 ms
PostgreSQL CPU:                   30%
Outbox oldest unpublished age:    18 phút
Outbox pending:                   1.800 event
Orders ACCEPTED overdue > 5 phút: 420 đơn
Broker publish errors:            tăng do credential hết hạn
Duplicate payment charge:         chưa phát hiện, đang đối soát
~~~

**Vấn đề nghiệp vụ:** 420 đơn đã được tiếp nhận nhưng chưa được chuyển thành tác vụ kho vận đúng hạn, dù API nhanh. Cảnh báo thích hợp là **completion deadline miss** (và có thể alert riêng về outbox coverage), không phải CPU database.

**Điều tra:** kiểm tra credential của producer/relay, log authentication errors, retry behavior, quyền broker; đếm outbox pending và đối chiếu trạng thái order với consumer. Nếu credential thay đổi, xác minh kết nối mới, vòng đời secret và cơ chế reconnect; đừng tăng JDBC pool vì PostgreSQL không phải nút thắt.

**Khôi phục:** cấp lại credential bằng quy trình phê duyệt, cho relay resume, giới hạn throughput để không gây stampede, giữ nguyên `event_id` khi retry. Consumer dùng inbox/unique constraint để không tạo hai fulfillment task cho một event. Đo tuổi backlog giảm và số order quá hạn được giải quyết.

**Sau sự cố:** bổ sung alert “relay authentication failure kéo dài và outbox deadline có nguy cơ vi phạm”, đồng thời giữ completion SLI làm tín hiệu chính. Cảnh báo credential có thể là dự báo sớm, nhưng **tác động cuối cùng** cần được đo bằng đơn hàng.

## 21. Tình huống: CPU cao có phải page không?

Giả sử một backfill schema đã được phê duyệt chạy trong cửa sổ bảo trì:

~~~text
PostgreSQL CPU:              87% trong 12 phút
API checkout error rate:    không tăng
API checkout p95/p99:       trong SLO
Connection pool pending:    thấp
Replication lag:           trong ngân sách
WAL archive / disk:        đủ an toàn
Backfill progress:         tăng đều
~~~

Đây có thể là tình trạng **sử dụng tài nguyên cao nhưng được kiểm soát**. Không nhất thiết page nhóm checkout chỉ vì CPU vượt 80%. Tuy nhiên cần **guardrail**:

- Nếu p99 API bắt đầu vượt deadline hoặc error budget burn tăng, giảm/tạm dừng backfill.
- Nếu WAL/disk sắp đầy hoặc replication/archive lag đe dọa RPO, dừng job trước khi tạo sự cố dữ liệu.
- Nếu lock wait/connection hold tăng bất thường, giảm batch size/concurrency hoặc dừng worker.
- Nếu có dấu hiệu sai dữ liệu, không chờ KPI latency vượt ngưỡng.

Một **leading indicator** như “disk sẽ hết trong 20 phút theo tốc độ ghi hiện tại” có thể xứng đáng paging trước khi có lỗi người dùng. Giá trị nằm ở **thời gian còn lại và hành động** chứ không phải ngưỡng phần trăm cố định.

## 22. Kiểm thử chính hệ thống cảnh báo

Không được coi việc tạo rule là kết thúc. Cần xác minh alert phát hiện được sự cố và đưa thông tin đúng đến người có trách nhiệm.

| Kịch bản kiểm thử | Điều cần xác nhận |
| --- | --- |
| Checkout timeout khi DB mất kết nối | SLI ghi nhận không đạt, không bị lọc thành lỗi người dùng |
| Request bị từ chối vì hết hàng hợp lệ | Không làm bẩn service error budget |
| Outbox relay dừng 10 phút | Tuổi event/đơn quá hạn tăng, alert đúng owner |
| Broker ACK bị mất, event được gửi lại | Duplicate delivery không bị nhầm thành duplicate business effect |
| Counter reset khi pod restart | Cách tính dùng rate/increase phù hợp và không xem reset là lỗi âm |
| Metric exporter chết | Có cảnh báo telemetry missing/stale, không mặc định “0 lỗi” |
| Một checkout lỗi ở endpoint lưu lượng thấp | Chính sách low-volume đúng, không bỏ sót lỗi critical |
| Duplicate charge được phát hiện bởi reconciliation | Alert correctness kích hoạt dù HTTP success cao |
| Backup archive mất một WAL segment | Restore rehearsal/coverage báo không thể đạt target |
| Backfill làm CPU cao nhưng SLO không ảnh hưởng | Không tạo bão page; guardrail vẫn hoạt động |
| Maintenance silence hết hạn | Alert quan trọng được bật lại đúng lúc |
| Một sự cố chung gây lỗi ở nhiều pod | Notification được group/dedupe; owner vẫn thấy phạm vi |

### Diễn tập fault-injection an toàn

Trong môi trường test có DB/broker gần production:

1. Tạo yêu cầu/record mẫu với business ID ổn định.
2. Dừng relay hoặc giả lập broker auth failure để tạo outbox lag.
3. Xác nhận metric và alert chuyển trạng thái sau đúng cửa sổ; ghi thời gian **detect**, **notify** và **acknowledge**.
4. Khôi phục relay, kiểm tra duplicate-safe replay và completion SLI.
5. Kiểm tra alert tự resolve khi tác động hết; còn lại các trường hợp ngoại lệ có ticket/đối soát.

Không cố tình xóa dữ liệu hay chặn broker production chỉ để thử alert nếu chưa có quy trình an toàn và phê duyệt. Với cảnh báo liên quan data loss, dùng kiểm tra mô phỏng hoặc môi trường cách ly; tránh tạo side effect thật tới khách hàng.

## 23. Sai lầm phổ biến trong cảnh báo persistence

| Sai lầm | Vì sao sai | Thiết kế tốt hơn |
| --- | --- | --- |
| Page khi CPU DB > 80% trong mọi tình huống | CPU cao không đồng nghĩa người dùng thất bại | Cảnh báo SLI, dùng CPU để chẩn đoán và guardrail |
| Chỉ nhìn HTTP 200/500 | Không thấy đơn quá hạn, duplicate charge, dữ liệu sai | Đo lifecycle/invariants từ nguồn bền vững |
| Lấy outbox pending count làm SLO | Backlog tăng trong đợt peak có thể hợp lệ | Đo tuổi quá hạn/độ trễ hoàn tất so với deadline |
| Dùng toàn bộ 4xx làm lỗi hạ tầng | Từ chối hợp lệ bị tính sai | Tách validation/policy rejection khỏi failures |
| Mỗi HTTP retry là một checkout mới trong mẫu số | SLO đẹp/xấu giả tùy retry rate | Định nghĩa đơn vị business intent và idempotency key |
| Bỏ qua commit unknown khi tính lỗi | SLO thành công giả | Có trạng thái unknown và deadline resolution |
| Chỉ báo lỗi khi tỷ lệ > 1% | Một sự cố mất tiền/dữ liệu hiếm vẫn nghiêm trọng | Alert correctness theo bất biến, có xác minh |
| Chỉ số dữ liệu sai bằng 0 vì reconciliation dừng | “Không đo” bị hiểu thành “không lỗi” | Alert cả freshness/coverage của kiểm tra |
| Dùng p95 pool + p95 query làm p95 API | Percentile không cộng được như vậy | Trace/measure end-to-end cùng request |
| Metric label là order ID/user ID/full SQL | Cardinality cao, rò PII | Label tập cố định; ID chỉ trong audit/tracing có kiểm soát |
| Không có runbook/owner | Người trực không biết làm gì | Gắn tác động, dashboard, quyền xử lý, escalation |
| Tự động restart hoặc tăng pool cho mọi timeout | Có thể khuếch đại lock/retry storm | Xác định bottleneck và giới hạn biện pháp |
| Alert tự resolve là coi dữ liệu đã đúng | Những đơn quá hạn/duplicate có thể tồn tại | Reconciliation và xác nhận hậu quả |
| Silence rộng trong maintenance | Mất tín hiệu data loss/RPO | Silence hẹp, có thời hạn, giữ guardrail critical |
| Chỉ kiểm tra backup job thành công | Không chứng minh restore được | Diễn tập PITR/RTO, kiểm tra archive chain |
| Chỉ dùng metrics của một service | Không thấy workflow đa service | Hành trình end-to-end và correlation |

## 24. Bài tập: thiết kế cảnh báo cho hệ đặt hàng Java

Một hệ có các thành phần `Order API → PostgreSQL → Outbox → Kafka → Payment/Fulfillment`, mục tiêu:

~~~text
SLO A: 99,9% ý định checkout hợp lệ được commit trong 2 giây (30 ngày).
SLO B: 99,5% order ACCEPTED có fulfillment task trong 5 phút.
Invariant C: Mỗi idempotency key chỉ tạo tối đa một charge và một order.
Durability D: Trong sự cố primary, RPO mục tiêu không vượt 15 phút.
~~~

Hôm nay xuất hiện:

| Tín hiệu | Trạng thái |
| --- | --- |
| Checkout p95 | 120 ms |
| Checkout success rate | 99,96% |
| PostgreSQL CPU | 28% |
| Connection pool pending | 0–2 |
| Kafka consumer lag | 25.000 message |
| Order quá hạn trên 5 phút | 780 |
| Outbox oldest pending | 19 phút |
| Đối soát duplicate charge | 1 trường hợp có bằng chứng |
| WAL archive lag | 12 phút và còn tăng |

**Câu hỏi:**

1. Những tín hiệu nào là **tác động nghiệp vụ đã có**, tín hiệu nào là **dự báo rủi ro** và tín hiệu nào chỉ hỗ trợ chẩn đoán?
2. Nếu checkout API vẫn đạt SLO A, bạn có đóng incident không? Vì sao?
3. Cần page ngay khi thấy một duplicate charge đã xác minh không, dù chỉ 1/100.000 giao dịch?
4. Với WAL archive lag 12 phút và RPO 15 phút, cần quan sát thêm điều gì để đánh giá nguy cơ khi primary mất?
5. Cho SLO A 99,9%, tỷ lệ không đạt quan sát 1,44% tương đương burn rate bao nhiêu?
6. Nếu Kafka lag 25.000 nhưng không đơn nào vượt 5 phút, có nhất thiết page không?
7. Nếu reconciliation metric dừng cập nhật nhưng gauge mismatch vẫn bằng 0, có thể tuyên bố không có sai dữ liệu không?
8. Hãy đề xuất một trang runbook gồm owner, dashboard, bước bảo vệ side effect và tiêu chí kết thúc incident.

### Hướng giải

- (1) **780 order quá hạn** và **một duplicate charge đã xác minh** là ảnh hưởng/nguy cơ correctness thực tế. WAL archive lag 12 phút tăng dần là rủi ro durability/RPO cần đánh giá ngay. Consumer lag, outbox age gợi ý nơi điều tra. CPU thấp không phủ nhận incident.
- (2) **Không**. SLO B và invariant C đang bị ảnh hưởng; SLO A chỉ đo bước tạo đơn.
- (3) Có thể cần mức nghiêm trọng cao ngay, vì duplicate charge là vi phạm bất biến tài chính. Phải xác minh và xử lý theo quy trình payment an toàn.
- (4) Đo **latest verified restorable position/time**, WAL generation, archive failure, storage và tình huống failover; 12 phút lag không tự đồng nghĩa chính xác 12 phút mất dữ liệu nhưng đã gần ngân sách.
- (5) `14,4×`, vì `0,0144 / 0,001 = 14,4`.
- (6) Không tự động. Nếu workflow vẫn hoàn tất trong deadline, queue có thể được xử lý kịp; vẫn cần dự báo drain time/capacity.
- (7) Không. Kiểm tra stale/missing metrics và lần đối soát thành công trước khi kết luận.
- (8) Runbook cần số order ảnh hưởng, owner/escalation, lệnh/query **chỉ đọc** an toàn, chiến lược retry với cùng event ID và consumer dedupe, kiểm tra provider trước khi charge lại, tiêu chí hoàn tất và đối soát hậu sự cố.

## 25. Checklist đưa cảnh báo nghiệp vụ vào vận hành

1. **Business contract:** outcome nào được hứa, commit/ACK/completion được định nghĩa ở đâu?
2. **SLI/SLO:** đơn vị quan sát, mẫu số/tử số, deadline, exclusions, cửa sổ và owner đã rõ chưa?
3. **Correctness:** có alert riêng cho mất dữ liệu, duplicate, cross-tenant leak, invariant violation?
4. **Asynchronous flow:** có đo accepted-to-completed, outbox age, consumer lag và reconciliation?
5. **Durability:** có cảnh báo WAL/archive coverage, backup validity, latest restorable time, RPO/RTO?
6. **Diagnostic context:** có trace, pool metrics, DB waits, query patterns và deploy timeline?
7. **Error budget:** có burn-rate windows, low-traffic policy và biện pháp khi thiếu metric?
8. **Cardinality & privacy:** label chỉ dùng danh mục kiểm soát; ID/PII nằm trong audit có phân quyền?
9. **Severity:** biết tác động thực tế, mức rủi ro và khi nào page/ticket/info?
10. **Routing:** owner, người dự phòng, escalation, runbook và dashboard có thể truy cập?
11. **Noise control:** grouping, deduplication, inhibition, maintenance silence hẹp và có thời hạn?
12. **Safe remediation:** không khuyến nghị thao tác phá dữ liệu, retry không idempotent hoặc mở transaction dài không cần thiết?
13. **Observation coverage:** exporter/scrape/reconciliation job mất dữ liệu có được phát hiện?
14. **Testing:** alert đã được diễn tập khi DB/broker lỗi, counter reset, thấp lưu lượng và dữ liệu sai chưa?
15. **Aftercare:** có đối soát dữ liệu sau incident, đánh giá missed/false alerts và cập nhật runbook?

**Kết luận:** Cảnh báo persistence tốt không bắt đầu từ câu hỏi **“CPU có cao không?”**, mà bắt đầu từ **“Điều gì khách hàng và nghiệp vụ đã hoặc sắp không nhận được?”**. Hãy định nghĩa SLI/SLO theo kết quả **commit, hoàn tất workflow và tính đúng đắn**, dùng error-budget burn rate cho lỗi phổ biến, cảnh báo riêng cho vi phạm bất biến nghiêm trọng, và theo dõi khả năng phục hồi dữ liệu ngay cả trước khi có lỗi API. Sau đó dùng metrics JDBC/PostgreSQL, traces, logs và runbook để tìm nguyên nhân và khôi phục **mà không tạo thêm lỗi ghi trùng hoặc mất dữ liệu**. Một cảnh báo đáng giá là cảnh báo giúp người trực đưa ra quyết định đúng, kịp thời và có thể kiểm chứng.

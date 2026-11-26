# Bước học tiếp theo

Hoàn thành module **SPRING_MODULITH_APPLICATION_EVENTS** giúp bạn biết cách tổ chức giao tiếp giữa các module bằng application events, phát và nhận event, xử lý sau commit, theo dõi publication, retry, kiểm thử và quan sát luồng sự kiện. Bước tiếp theo nên đưa những kỹ năng này vào một quy trình nghiệp vụ hoàn chỉnh, nơi nhiều module cùng phối hợp và một phần xử lý có thể chạy qua message broker hoặc dịch vụ độc lập.

Lộ trình phù hợp là đi từ **modular monolith có event đáng tin cậy** tới **hệ thống event-driven phân tán có khả năng phục hồi**. Bạn không cần chuyển mọi event sang Kafka ngay. Trước tiên hãy chứng minh ranh giới module và transaction đúng; sau đó bổ sung lưu trữ bền vững, broker, điều phối quy trình, schema governance và vận hành production.

## 1. Xác định năng lực đã có và khoảng trống tiếp theo

Trước khi chọn chủ đề mới, tự kiểm tra xem bạn có thể giải thích và thực hành được các việc sau không:

- Xác định khi nào dùng event, khi nào dùng service call hoặc command.
- Đặt event contract trong module sở hữu sự thật nghiệp vụ.
- Phát event trong transaction phù hợp và phân biệt xử lý đồng bộ với after-commit.
- Giải thích publication lifecycle và cách phục hồi publication chưa hoàn tất.
- Thiết kế listener idempotent, retry có giới hạn và quarantine lỗi không thể tự phục hồi.
- Kiểm thử transaction rollback, listener failure, duplicate và event sai thứ tự.
- Đọc trace, log, metric để tìm event bị chậm hoặc thất bại.
- Triển khai phiên bản mới mà vẫn xử lý được event cũ trong giai đoạn chuyển tiếp.

Nếu còn điểm nào chưa vững, hãy quay lại bài tương ứng và tạo một ví dụ nhỏ có thể chạy, kiểm thử và giải thích. Không nên mở rộng sang hệ thống phân tán khi một listener nội bộ vẫn có thể đánh dấu thành công dù side effect chưa được lưu.

## 2. Chọn hướng học theo mục tiêu

Sau nền tảng application events, có ba hướng phát triển chính. Chúng có thể kết hợp, nhưng nên chọn một mục tiêu ưu tiên cho mỗi chặng.

| Hướng | Học sâu điều gì? | Khi nào nên chọn? |
|---|---|---|
| Modular monolith đáng tin cậy | Module boundary, transaction, publication registry, inbox/outbox, retry và test | Khi ứng dụng vẫn triển khai như một đơn vị |
| Messaging phân tán | Kafka, partition, consumer group, schema registry, delivery và replay | Khi cần giao tiếp giữa process hoặc service độc lập |
| Workflow nhiều bước | Saga, process manager, timeout, compensation và reconciliation | Khi nghiệp vụ cần phối hợp nhiều module/service và có trạng thái kéo dài |

Một hệ thống tốt có thể giữ phần lớn event nội bộ trong Spring Modulith, chỉ externalize những contract thực sự cần chia sẻ. Việc tách service nên xuất phát từ yêu cầu ownership, scale, deployment hoặc fault isolation, không chỉ vì đã có Kafka.

## 3. Lộ trình khuyến nghị

Thứ tự dưới đây giúp tăng dần độ phức tạp mà vẫn giữ được khả năng kiểm chứng ở từng bước:

| Chặng | Chủ đề tiếp theo | Kết quả cần đạt |
|---:|---|---|
| 1 | Transactional outbox và inbox | Không mất ý định phát event và xử lý duplicate an toàn |
| 2 | Kafka producer/consumer nâng cao | Hiểu partition, key, group, offset, retry và DLT |
| 3 | Event schema governance | Thay đổi contract mà producer/consumer vẫn tương thích |
| 4 | Saga và process manager | Điều phối workflow nhiều bước, timeout và compensation |
| 5 | Distributed tracing và reliability | Theo dõi event xuyên service và xử lý backlog |
| 6 | Resilience và production operations | Deploy, drain, replay, rollback và khôi phục sự cố |
| 7 | Architecture fitness và contract testing | Ngăn dependency sai và phát hiện breaking change sớm |

Không cần học tất cả cùng lúc. Mỗi chặng nên kết thúc bằng một thay đổi có kiểm thử, một sơ đồ luồng và một quyết định kiến trúc được ghi lại.

## 4. Chặng 1 — Transactional outbox và inbox

Đây là bước nên học trước khi externalize event ra broker. Vấn đề cốt lõi là database transaction và thao tác gửi message tới broker thường không cùng một transaction nguyên tử.

Nếu ứng dụng commit đơn hàng rồi process dừng trước khi gửi message, hệ thống có thể mất event. Nếu broker đã nhận message nhưng producer không nhận được phản hồi, producer có thể gửi lại và tạo duplicate.

Transactional outbox giải quyết phần producer bằng cách ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng database transaction:

~~~text
Begin database transaction
        |
        +---- Update business aggregate
        |
        +---- Insert outbox record
        |
        v
      Commit
        |
        v
Outbox publisher / CDC
        |
        v
      Broker
~~~

Inbox giải quyết phần consumer bằng cách ghi nhận event ID đã xử lý cùng với thay đổi nghiệp vụ trong một transaction:

~~~text
Receive event
     |
     v
Begin transaction
     |
     +---- Insert inbox key (consumer, eventId)
     |
     +---- Apply business/projection change
     |
     v
   Commit
~~~

Khi học chặng này, hãy làm rõ:

- Outbox record được tạo cùng transaction nào?
- Publisher claim record bằng lock hay lease?
- Khi broker acknowledgment không rõ, làm sao retry an toàn?
- Inbox có unique constraint theo consumer và event ID không?
- Inbox state và projection update có cùng transaction không?
- Khi event bị quarantine hoặc replay, ai chịu trách nhiệm?

Kết quả cần có là một producer không mất ý định phát event và một consumer có thể nhận cùng event nhiều lần mà không lặp side effect.

## 5. Chặng 2 — Kafka và messaging phân tán

Sau khi hiểu outbox/inbox, hãy học Kafka ở mức vận hành và semantics, không chỉ cách gọi API gửi message.

Các chủ đề nên nắm:

- Topic, partition, replica, leader và retention.
- Message key và ordering trong phạm vi partition.
- Consumer group, assignment, rebalance và committed offset.
- Producer acknowledgment, idempotence và retry.
- Consumer acknowledgment, at-least-once và redelivery.
- Batch processing, backpressure và consumer lag.
- Retry topic, dead-letter topic và replay.
- ACL, TLS và credential management.

Bài tập nhỏ: externalize một event như OrderConfirmed sang topic riêng. Dùng order ID làm key nếu thứ tự theo đơn hàng là yêu cầu. Consumer ghi projection vào database qua inbox; sau đó cố ý dừng consumer ở giữa xử lý và xác minh event được giao lại nhưng dữ liệu chỉ thay đổi một lần.

Không đồng nhất producer idempotence của Kafka với idempotency của nghiệp vụ. Producer idempotence giúp hạn chế duplicate do retry ở phạm vi producer protocol; consumer vẫn cần bảo vệ side effect của chính nó.

## 6. Chặng 3 — Quản trị schema và compatibility

Khi producer và consumer deploy độc lập, event payload trở thành hợp đồng phiên bản hóa. Hãy học cách:

- Phân biệt schema compatibility với business semantic compatibility.
- Đánh giá backward, forward và full compatibility.
- Thêm trường optional có default đúng nghĩa.
- Đổi tên hoặc đổi kiểu bằng dual-read/dual-write.
- Xử lý enum value mới và unknown fields.
- Dùng schema registry nếu hệ thống cần quản lý schema tập trung.
- Upcast event lịch sử sang model nội bộ mới.
- Quản lý topic version và thời hạn hỗ trợ contract cũ.

Bài tập: thay đổi event OrderConfirmed từ payload chỉ có order ID sang payload có amount và currency. Triển khai consumer tolerant trước, sau đó mới triển khai producer phát trường mới. Giữ fixture của schema cũ để chứng minh consumer mới vẫn đọc được dữ liệu lịch sử.

Không xóa trường cũ ngay khi producer mới đã deploy. Consumer theo lịch, replay job hoặc data pipeline có thể vẫn cần đọc event cũ.

## 7. Chặng 4 — Saga và process manager

Khi một nghiệp vụ cần nhiều module hoặc service phối hợp, event đơn lẻ không đủ để mô tả toàn bộ tiến trình. Ví dụ quy trình hoàn tất đơn hàng có thể gồm:

~~~text
OrderPlaced
    |
    v
ReserveInventory
    |
    v
InventoryReserved
    |
    v
CapturePayment
    |
    v
PaymentCaptured
    |
    v
CreateShipment
    |
    v
OrderFulfilled
~~~

Nếu giữ chỗ hàng thất bại, quy trình có thể từ chối đơn. Nếu thanh toán thất bại sau khi đã giữ hàng, cần phát hành hành động giải phóng hàng. Đây là compensation có ý nghĩa nghiệp vụ, không phải rollback database xuyên nhiều service.

Học hai cách tổ chức:

- **Orchestration:** process manager giữ trạng thái workflow và gửi command tới từng participant.
- **Choreography:** participant phản ứng với event của nhau, không có một bộ điều phối trung tâm.

Orchestration giúp nhìn rõ trạng thái, timeout và nhánh xử lý; choreography giảm điều phối trực tiếp nhưng có thể làm luồng phản ứng khó lần theo khi số participant tăng. Chọn theo độ phức tạp của quy trình và nhu cầu vận hành.

Bài tập: xây dựng workflow đặt hàng với trạng thái PENDING, INVENTORY_RESERVED, PAYMENT_CAPTURED, COMPLETED và COMPENSATING. Xác định timeout, retry, compensation, reconciliation và hành động khi nhận event trùng hoặc sai thứ tự.

## 8. Chặng 5 — Observability xuyên producer và consumer

Khi event đi qua nhiều process, log riêng từng service không đủ để thấy toàn bộ hành trình. Hãy kết hợp:

- Trace context được truyền qua message headers.
- Event ID ổn định để deduplicate và tìm lịch sử.
- Correlation ID để nối các bước trong một workflow.
- Causation ID để xác định event hoặc command tạo ra bước tiếp theo.
- Metrics có cardinality thấp cho throughput, failure, lag và backlog.
- Log có cấu trúc để truy vấn từng event.
- Dashboard và alert gắn với SLA của từng consumer.

Thực hành một tình huống: một đơn hàng bị treo sau khi Inventory đã giữ hàng nhưng Payment chưa hoàn tất. Dùng correlation ID để tìm các event liên quan, trace để xác định bước chậm, metric để xem backlog và log để biết policy retry đã chọn.

Không dùng trace ID hoặc event ID làm metric label. Giữ chúng trong trace/log; metrics nên dùng event type, topic, consumer group và outcome.

## 9. Chặng 6 — Reliability và vận hành production

Sau khi pipeline hoạt động trong môi trường test, hãy học cách vận hành nó khi dependency chậm, broker gián đoạn hoặc một phiên bản mới được triển khai.

Các năng lực cần có:

- Retry có giới hạn, exponential backoff, jitter và deadline.
- Quarantine/DLT cùng runbook replay.
- Circuit breaker và concurrency limit cho dependency quá tải.
- Consumer pause/resume và backpressure.
- Graceful shutdown và draining handler đang chạy.
- Rolling/blue-green/canary với event contract tương thích.
- Database expand-migrate-contract.
- Rollback binary mà không làm mất event đã phát.
- Theo dõi publication incomplete, outbox age, consumer lag và DLT growth.

Bài tập: mô phỏng broker ngừng hoạt động trong vài phút, tiếp tục nhận request bằng cách lưu outbox, khôi phục broker và xác minh backlog được gửi lại. Sau đó mô phỏng một consumer lỗi liên tục và chứng minh event được quarantine thay vì retry vô hạn.

## 10. Chặng 7 — Architecture fitness và contract testing

Khi số module tăng, cần tự động hóa các quy tắc kiến trúc để thay đổi mới không làm suy yếu ranh giới.

Hãy thực hành:

- Kiểm tra module dependency và named interface.
- Ngăn module truy cập package nội bộ của module khác.
- Phát hiện chu trình dependency.
- Kiểm thử event contract bằng fixture versioned.
- Consumer-driven contract test cho hệ thống tích hợp độc lập.
- Kiểm thử schema compatibility trong CI.
- Kiểm thử failure và recovery bằng database/broker thật hoặc Testcontainers.
- Giữ test bất đồng bộ xác định bằng clock, condition và timeout.

Mục tiêu là biến quyết định kiến trúc thành kiểm tra có thể lặp lại. Một test chỉ xác nhận method được gọi chưa đủ để chứng minh publication, broker acknowledgment hoặc side effect đã commit.

## 11. Dự án tổng hợp nên thực hiện

Một dự án tốt để nối các chặng là **Order Fulfillment** với các module:

| Module | Trách nhiệm | Event/command tiêu biểu |
|---|---|---|
| Orders | Tạo và quản lý vòng đời đơn | OrderPlaced, OrderConfirmed |
| Inventory | Giữ và giải phóng hàng | ReserveInventory, InventoryReserved, InventoryReleased |
| Payments | Thu tiền và hoàn tiền | CapturePayment, PaymentCaptured, PaymentFailed |
| Shipping | Tạo và theo dõi giao hàng | CreateShipment, ShipmentCreated |
| Notifications | Gửi thông báo | OrderStatusChanged |
| Operations | Theo dõi lỗi và replay | EventQuarantined, ReplayRequested |

Thực hiện theo từng phiên bản:

1. Bắt đầu bằng modular monolith và kiểm tra module boundary.
2. Dùng application events cho các sự kiện nội bộ đã commit.
3. Thêm publication tracking và listener idempotent.
4. Thêm outbox/inbox trước khi externalize.
5. Externalize một hoặc hai contract sang Kafka.
6. Thêm schema version và consumer compatibility.
7. Dùng process manager cho workflow có timeout/compensation.
8. Thêm tracing, metrics, alert và dashboard.
9. Kiểm thử restart, duplicate, out-of-order, broker outage và replay.
10. Thực hiện rolling deployment với phiên bản cũ và mới cùng tồn tại.

Giữ phạm vi nhỏ ở mỗi lần triển khai. Không cần tách tất cả module thành microservice để hoàn thành dự án; có thể giữ Orders và Inventory trong cùng ứng dụng, chỉ externalize một contract để học ranh giới phân tán.

## 12. Các sản phẩm cần tạo sau mỗi chặng

Mỗi chặng nên để lại artefact cụ thể để có thể review:

| Artefact | Nội dung |
|---|---|
| Event catalog | Event type, owner, producer, consumer và contract version |
| Architecture diagram | Module, broker, topic, workflow và dependency |
| ADR | Lý do chọn event, command, outbox, saga hoặc topic version |
| Contract fixtures | Payload mẫu của từng schema version |
| Failure matrix | Điểm lỗi, trạng thái cần giữ và cách phục hồi |
| Runbook | Retry, quarantine, replay, pause/resume và rollback |
| Dashboard | Throughput, latency, incomplete publication, lag và DLT |
| Test suite | Unit, integration, contract, recovery và failure tests |

Các artefact này giúp người khác hiểu hệ thống mà không phải lần theo toàn bộ source code. Cập nhật chúng cùng pull request khi contract hoặc subscription thay đổi.

## 13. Kế hoạch học tập 6 tuần

Nếu muốn một nhịp học có giới hạn, có thể chia thành sáu tuần:

| Tuần | Trọng tâm | Bài thực hành cuối tuần |
|---:|---|---|
| 1 | Transactional outbox/inbox | Producer lưu outbox và consumer deduplicate |
| 2 | Kafka partition, group, offset | Gửi và nhận event có key, kiểm tra redelivery |
| 3 | Schema compatibility | Thay đổi payload mà consumer cũ/mới cùng hoạt động |
| 4 | Saga/process manager | Hoàn tất đơn hàng với timeout và compensation |
| 5 | Tracing và reliability | Tìm một event lỗi xuyên producer-consumer |
| 6 | Production rollout và recovery | Deploy hai phiên bản, drain, rollback và replay |

Mỗi tuần nên có một phiên review: giải thích trade-off, chạy failure scenario và cập nhật ADR/runbook. Nếu thời gian ít, kéo dài mỗi chặng; không bỏ qua kiểm thử phục hồi chỉ để hoàn thành đúng lịch.

## 14. Tiêu chí tự đánh giá đã sẵn sàng

Bạn có thể chuyển sang một chủ đề tiếp theo khi có thể tự thực hiện và giải thích các việc sau:

- Chọn đúng event, command hoặc query dựa trên semantics.
- Chứng minh event không phát side effect khi transaction nguồn rollback.
- Giải thích publication registry, outbox và inbox khác nhau thế nào.
- Xử lý duplicate mà không tạo side effect trùng.
- Giữ ordering theo aggregate khi nghiệp vụ yêu cầu.
- Triển khai producer/consumer version mới mà vẫn đọc được event cũ.
- Điều phối workflow nhiều bước với timeout và compensation.
- Tìm một event bị treo bằng event ID, correlation ID, trace và metrics.
- Phục hồi sau broker outage hoặc process restart.
- Triển khai thay đổi không làm gián đoạn consumer đang hoạt động.

Nếu chưa đạt một tiêu chí, chọn đúng chặng tương ứng để luyện thêm thay vì mở rộng toàn bộ hệ thống.

## 15. Chọn bài tiếp theo ngay sau module này

Một thứ tự thực tế để bắt đầu:

1. **Transactional outbox/inbox:** củng cố tính bền vững và idempotency trước khi đưa event qua network.
2. **Kafka consumer reliability:** hiểu offset, rebalance, retry, DLT và replay trong môi trường có broker.
3. **Saga/process manager:** học điều phối nghiệp vụ nhiều bước và compensation.
4. **Schema evolution:** bảo vệ contract khi producer/consumer deploy độc lập.
5. **Distributed observability:** trace và đo lường event xuyên service.
6. **Production operations:** triển khai, draining, rollback và phục hồi backlog.

Nếu mục tiêu của bạn là phát triển một modular monolith, hãy đi sâu vào outbox/inbox, module boundary, transaction và architecture tests trước. Nếu mục tiêu là tích hợp nhiều hệ thống, ưu tiên Kafka, schema governance và consumer reliability. Nếu nghiệp vụ có nhiều bước kéo dài, ưu tiên saga/process manager trước khi tách thêm service.

Bước học tiếp theo không phải là thêm thật nhiều công nghệ vào ứng dụng. Hãy chọn một quy trình nghiệp vụ có thể kiểm chứng, mở rộng nó từ event nội bộ tới giao tiếp phân tán khi cần, rồi chứng minh hệ thống vẫn đúng khi lỗi, duplicate, restart và deploy xảy ra. Đó là cách chuyển kiến thức application events thành năng lực thiết kế và vận hành một hệ thống event-driven đáng tin cậy.


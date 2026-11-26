# Triển khai không gián đoạn

Triển khai không gián đoạn là cách đưa phiên bản mới của ứng dụng vào production mà vẫn duy trì khả năng tiếp nhận request và xử lý application events. Với hệ thống Spring Modulith, việc rollout còn phải bảo đảm event được phát, publication được theo dõi, listener có thể xử lý event cũ và mới, consumer không mất offset, đồng thời các instance đang chạy song song không diễn giải cùng một contract theo hai cách mâu thuẫn.

Không thể chỉ dựa vào rolling deployment của nền tảng để đạt mục tiêu này. Ứng dụng cần tương thích giữa các phiên bản trong thời gian chuyển tiếp, database cần được migration theo nhiều bước, event phải có khả năng xử lý lặp an toàn và quy trình shutdown phải cho phép công việc đang chạy hoàn tất hoặc được phục hồi sau đó.

## 1. Mục tiêu và phạm vi của triển khai không gián đoạn

Một lần triển khai được xem là không gián đoạn khi người dùng và hệ thống tích hợp tiếp tục nhận được dịch vụ trong giới hạn SLA đã định. Điều đó không có nghĩa mọi request đều không có lỗi hoặc mọi event được xử lý tức thời. Mục tiêu thực tế gồm:

- Không làm mất dữ liệu nghiệp vụ đã commit.
- Không làm mất application event hoặc message đã được broker xác nhận.
- Không để consumer xử lý một event bằng contract không tương thích.
- Giữ khả năng phục hồi khi instance bị dừng giữa lúc xử lý.
- Hạn chế thời gian lỗi, độ trễ và backlog trong giai đoạn rollout.
- Có thể dừng rollout hoặc rollback khi chỉ số vượt ngưỡng.
- Duy trì khả năng quan sát từ producer tới listener và consumer.

Cần phân biệt hai lớp:

| Lớp | Điều cần duy trì |
|---|---|
| Availability của ứng dụng | Instance còn phục vụ request, health check và dependency cần thiết |
| Continuity của event | Publication, broker record, offset, retry state và listener processing có thể tiếp tục chính xác |

Một API vẫn trả HTTP 200 không chứng minh event pipeline đang khỏe. Ngược lại, consumer lag tăng trong vài phút có thể chấp nhận được nếu event vẫn được lưu bền vững, backlog có thể bắt kịp và SLA cho phép.

## 2. Chọn chiến lược triển khai

Các chiến lược phổ biến có đặc điểm khác nhau:

| Chiến lược | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Rolling deployment | Thay từng nhóm instance cũ bằng instance mới | Ứng dụng stateless và hai phiên bản tương thích trong thời gian chạy song song |
| Blue-green | Dựng môi trường mới, kiểm tra rồi chuyển traffic | Cần chuyển traffic nhanh và có khả năng duy trì hai môi trường |
| Canary | Chuyển một phần traffic hoặc workload sang phiên bản mới trước | Muốn giới hạn phạm vi ảnh hưởng và quan sát hành vi thực tế |
| Recreate | Dừng phiên bản cũ rồi khởi chạy phiên bản mới | Có maintenance window hoặc không thể chạy hai phiên bản cùng lúc |

Rolling thường là lựa chọn đơn giản cho ứng dụng Spring Boot nhiều instance, nhưng chỉ an toàn nếu phiên bản cũ và mới có thể cùng đọc/ghi database và xử lý event trong khoảng overlap.

Blue-green giúp chuyển traffic nhanh nhưng không tự giải quyết xung đột khi hai môi trường cùng consume một topic hoặc cùng chạy scheduled worker. Cần quyết định rõ môi trường nào được phép phát và tiêu thụ event trước và sau cutover.

Canary cần phân chia workload có chủ đích. Nếu cả phiên bản cũ và mới cùng nhận event, phải bảo đảm chúng không tạo side effect trùng hoặc ghi projection theo hai semantics khác nhau. Canary theo HTTP traffic không nhất thiết đồng nghĩa canary cho consumer group.

## 3. Kiểm tra khả năng tương thích giữa phiên bản cũ và mới

Trong rolling deployment, hai phiên bản có thể chạy đồng thời. Vì vậy, mọi thay đổi cần được đánh giá theo các cặp:

- Producer cũ với consumer mới.
- Producer mới với consumer cũ.
- Listener cũ với event đang tồn tại trong publication registry.
- Consumer mới với message cũ còn trong Kafka retention.
- Ứng dụng mới với schema database đang ở trạng thái mở rộng.
- Ứng dụng cũ với schema database đã được migration nhưng chưa contract.

Trước khi rollout, lập bảng tương thích:

| Thành phần | Phiên bản cũ | Phiên bản mới | Điều kiện |
|---|---|---|---|
| Producer | Phát event v1 | Phát v1 hoặc v2 tương thích | Không buộc consumer cũ đọc payload không hỗ trợ |
| Consumer | Đọc v1 | Đọc v1 và v2 | Consumer mới phải xử lý dữ liệu cũ còn tồn tại |
| Database | Dùng cột cũ | Có thể đọc/ghi cột cũ và mới | Chưa xóa cột cũ trong giai đoạn overlap |
| Projection | Schema hiện tại | Schema mở rộng | Handler có version guard hoặc migration rõ |
| Retry/replay | Có event pending | Có thể xử lý event cũ | Giữ event ID và upcaster cần thiết |

Nếu không thể tạo một khoảng tương thích, không rollout trực tiếp theo kiểu rolling. Hãy dùng topic/schema version mới, chuyển consumer theo kế hoạch hoặc chọn maintenance window có kiểm soát.

## 4. Expand-migrate-contract cho database

Database migration là một trong những nguyên nhân phổ biến khiến phiên bản cũ không thể chạy cùng phiên bản mới. Không nên xóa hoặc đổi tên cột trong cùng lần deploy mà code mới bắt đầu sử dụng nó.

Dùng chiến lược ba giai đoạn:

1. **Expand:** thêm cột, bảng hoặc index mới mà code cũ vẫn hoạt động được.
2. **Migrate:** triển khai code có thể đọc/ghi cả cấu trúc cũ và mới, backfill dữ liệu và xác minh kết quả.
3. **Contract:** sau khi mọi instance cũ đã dừng và không còn consumer phụ thuộc, mới xóa cấu trúc cũ.

Ví dụ đổi cột customer_name thành customer_display_name:

~~~text
Release A — Expand
- Thêm customer_display_name nullable.
- Code cũ vẫn dùng customer_name.

Release B — Migrate
- Code mới đọc customer_display_name, fallback customer_name.
- Ghi đồng thời hai cột trong thời gian chuyển tiếp.
- Backfill dữ liệu cũ theo batch.
- Đo số bản ghi còn thiếu giá trị mới.

Release C — Contract
- Xác nhận mọi instance và job đã dùng cột mới.
- Ngừng ghi customer_name.
- Sau thời gian rollback, xóa cột cũ.
~~~

Backfill cần có checkpoint, giới hạn batch và khả năng tiếp tục sau lỗi. Không chạy một transaction khổng lồ trên bảng lớn nếu điều đó tạo lock kéo dài hoặc ảnh hưởng workload production.

Index lớn có thể cần tạo theo cách online/concurrently tùy database. Cú pháp và giới hạn phụ thuộc hệ quản trị; cần kiểm tra khả năng migration trên đúng database production.

## 5. Di trú event contract theo nhiều bước

Event đã được phát có thể còn nằm trong Kafka, archive hoặc publication chưa hoàn tất. Do đó, đổi class Java không làm thay đổi các event cũ.

Khi thêm trường, thường triển khai consumer tolerant trước rồi mới phát trường mới. Khi đổi tên hoặc kiểu dữ liệu, dùng trường mới và duy trì trường cũ trong giai đoạn chuyển tiếp.

Ví dụ:

~~~json
{
  "eventId": "event-123",
  "schemaVersion": 2,
  "orderId": "order-456",
  "totalAmountMinor": 125000,
  "totalAmount": "1250.00",
  "currency": "VND"
}
~~~

Trong giai đoạn migration:

- Consumer mới đọc được cả payload cũ và mới.
- Producer mới có thể ghi cả trường cũ và trường mới.
- Consumer cũ tiếp tục nhận dạng trường cũ.
- Metric theo dõi số lần consumer phải fallback.
- Chỉ bỏ trường cũ sau khi mọi consumer đã chuyển và replay window đã hết.

Đối với thay đổi không tương thích, tạo event type hoặc topic version mới. Dual-publish cần giữ một event identity ổn định để downstream không xử lý hai bản phát như hai nghiệp vụ độc lập.

## 6. Thứ tự rollout producer và consumer

Thứ tự triển khai phải dựa trên compatibility:

| Thay đổi | Thứ tự khuyến nghị |
|---|---|
| Thêm trường optional | Triển khai consumer tolerant trước, producer phát trường sau |
| Đổi tên trường | Consumer dual-read trước, producer dual-write sau |
| Ngừng trường cũ | Xác minh consumer không còn đọc, rồi ngừng ghi và cuối cùng xóa |
| Thêm enum value | Consumer hỗ trợ unknown/new value trước producer |
| Topic/schema không tương thích | Consumer mới sẵn sàng trước, sau đó chuyển producer |
| Thay đổi semantics | Công bố contract mới, rollout consumer theo version và có kế hoạch replay |

Không triển khai producer mới trước khi biết consumer cũ sẽ phản ứng thế nào với payload mới. Một consumer không hoạt động thường xuyên vẫn có thể đọc lại event cũ khi được bật lại; hãy tính cả replay job, analytics và batch consumer vào thứ tự rollout.

Với Spring Modulith nội bộ, listener là một phần của cùng artifact nhưng các instance cũ và mới vẫn có thể cùng tồn tại trong rolling deployment. Event phát từ instance mới có thể được xử lý bởi listener ở instance cũ nếu kiến trúc và registry cho phép. Vì vậy, listener cần tương thích với event trong giai đoạn overlap.

## 7. Triển khai listener Spring Modulith an toàn

Listener nội bộ cần xử lý được event đã phát trước lần deploy. Khi thay đổi signature hoặc semantics:

- Giữ listener cũ hoạt động cho tới khi publication pending của contract cũ đã được xử lý.
- Nếu event class thay đổi không tương thích, dùng adapter/upcaster hoặc hỗ trợ đồng thời phiên bản cũ và mới.
- Giữ idempotency key ổn định qua retry và resubmit.
- Tránh đổi tên handler/listener một cách tùy tiện khi còn publication incomplete cần phục hồi.
- Kiểm tra transaction semantics và executor được dùng bởi listener.
- Không đánh dấu event thành công khi chỉ mới đưa vào một queue trong bộ nhớ.

Ví dụ listener có thể ủy quyền việc xử lý sang service:

~~~java
@Component
class OrderPaidListener {

    private final OrderProjectionService projectionService;

    OrderPaidListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        projectionService.apply(event);
    }
}
~~~

Trong rollout, phiên bản service mới phải hiểu event được phát bởi phiên bản cũ. Nếu thay đổi projection schema, dùng migration mở rộng và version guard để event cũ không ghi đè trạng thái mới.

## 8. Event Publication Registry và publication pending

Spring Modulith Event Publication Registry theo dõi publication của application event tới listener và trạng thái hoàn tất hoặc incomplete. Khi triển khai phiên bản mới, cần kiểm tra publication chưa hoàn tất trước khi thay đổi listener contract.

Một quy trình an toàn:

1. Theo dõi số lượng và tuổi publication incomplete trước deploy.
2. Xác định listener nào có backlog hoặc lỗi kéo dài.
3. Triển khai phiên bản mới có khả năng xử lý event cũ.
4. Giữ persistence của registry qua lần restart/deploy.
5. Sau deploy, theo dõi publication mới và publication được resubmit.
6. Chỉ loại bỏ khả năng đọc event cũ khi đã xác nhận không còn publication cần xử lý.

Registry hỗ trợ phục hồi publication chưa hoàn tất nhưng không phải event store chứa toàn bộ lịch sử nghiệp vụ. Không dựa vào registry để replay mọi event đã hoàn tất từ đầu.

Nếu nhiều phiên bản ứng dụng cùng dùng chung database registry, cần xác minh cấu hình listener và cách nhận diện publication trong đúng phiên bản Spring Modulith đang chạy. Không giả định mọi thay đổi handler hoặc deployment topology đều tương thích tự động.

## 9. Rolling deployment với Kafka consumer

Kafka consumer có thể bị rebalance khi instance cũ dừng và instance mới tham gia group. Điều này là bình thường nhưng có thể làm tăng độ trễ hoặc khiến record được giao lại.

Để giảm ảnh hưởng:

- Cấu hình shutdown grace period đủ để xử lý record đang chạy.
- Dừng nhận thêm công việc khi instance chuẩn bị shutdown.
- Hoàn tất hoặc rollback transaction đang xử lý trước khi dừng.
- Chỉ commit offset sau khi xử lý hoặc bàn giao bền vững.
- Dùng idempotency để chịu được redelivery.
- Theo dõi rebalance, consumer lag và processing latency.
- Đảm bảo phiên bản mới đọc được mọi schema còn trong retention.

Không commit offset trước khi database commit nếu không có cơ chế bảo đảm tương đương; nếu process dừng sau commit offset nhưng trước database write, record có thể bị mất khỏi xử lý. Với at-least-once, chấp nhận redelivery và bảo vệ side effect bằng inbox hoặc khóa duy nhất.

Nếu dùng retry topic hoặc dead-letter topic, cần bảo đảm consumer mới giữ được metadata nguồn, event ID và ordering semantics cần thiết.

## 10. Graceful shutdown và draining

Khi instance nhận tín hiệu shutdown, cần ngừng nhận công việc mới và cho phép công việc đang chạy hoàn tất trong thời gian cho phép.

Một trình tự tổng quát:

~~~text
Instance receives termination signal
              |
              v
Mark instance unready
              |
              v
Stop accepting new HTTP traffic
              |
              v
Pause/stop new event consumption
              |
              v
Wait for in-flight handlers
              |
        +-----+------+
        |            |
     Completed    Deadline reached
        |            |
        v            v
 Commit/ack       Rollback or leave
 safely           work recoverable
        |            |
        +-----+------+
              |
              v
Close connections and exit
~~~

Readiness nên chuyển sang trạng thái không nhận traffic trước khi process thoát. Liveness và readiness có mục đích khác nhau; không dùng liveness để đánh dấu instance đang drain vì orchestrator có thể restart nó liên tục.

Nếu handler không thể hoàn tất trước deadline, transaction phải rollback hoặc message không được acknowledge để broker giao lại. Không dùng shutdown hook để đánh dấu mọi event đang chạy thành công chỉ nhằm rút ngắn thời gian dừng.

Thời gian graceful shutdown cần phối hợp với termination grace period của nền tảng, timeout của load balancer và max processing time của consumer.

## 11. Blue-green và canary cho event consumer

Blue-green cần xác định môi trường nào sở hữu consumer group. Nếu cả blue và green cùng dùng một group ID, Kafka sẽ chia partition giữa hai môi trường; điều này có thể không phù hợp nếu mục tiêu là kiểm tra green độc lập trước cutover.

Nếu dùng group ID riêng cho green để kiểm thử, green có thể đọc lại toàn bộ dữ liệu hoặc tạo side effect trùng. Vì vậy, cần chọn một trong các cách:

- Chạy green ở chế độ shadow chỉ đọc và không tạo side effect.
- Dùng topic hoặc dữ liệu test riêng.
- Chỉ chuyển quyền consume sau khi green đã sẵn sàng.
- Dùng consumer group riêng với checkpoint và quy trình cutover rõ.
- Dùng dual processing có deduplication và so sánh kết quả nếu kiến trúc hỗ trợ.

Canary theo consumer cần phân chia partition hoặc subscription có chủ đích. Không để hai phiên bản cùng ghi vào một projection nếu chúng dùng logic tính toán khác nhau mà không có generation/version isolation.

## 12. Transactional outbox và ranh giới ghi dữ liệu

Nếu ứng dụng vừa ghi dữ liệu nghiệp vụ vừa phát event tới broker, cần tránh trạng thái database commit nhưng message không được gửi, hoặc message được gửi khi transaction nghiệp vụ rollback.

Transactional outbox ghi business state và outbox record trong cùng database transaction. Worker hoặc CDC publisher gửi outbox record tới broker sau đó.

~~~text
Business transaction
      |
      +---- Update business tables
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

Outbox giúp duy trì ý định phát event bền vững qua restart. Publisher vẫn có thể gửi lại nếu không biết chắc broker đã nhận record trước khi process dừng. Consumer cần idempotency để xử lý redelivery.

Spring Modulith có Event Publication Registry cho publication tới listener; khi dùng externalization adapter, cần hiểu rõ transaction và acknowledgment semantics của integration. Không tự động coi registry và transactional outbox là cùng một cơ chế.

Khi rollout, không thay đổi schema outbox hoặc payload trong một bước phá vỡ worker publisher đang chạy. Dùng expand-migrate-contract và duy trì khả năng đọc record cũ.

## 13. Health check và readiness cho event pipeline

Health endpoint cần phản ánh trạng thái phục vụ và khả năng xử lý event theo mức phù hợp. Một số tín hiệu nên quan sát:

- Database sẵn sàng và registry/inbox có thể ghi.
- Broker kết nối được nếu service cần publish hoặc consume.
- Consumer group có assignment hợp lệ.
- Consumer lag không vượt ngưỡng vận hành.
- Publication incomplete không tăng bất thường.
- Outbox/inbox backlog nằm trong giới hạn.
- Retry/DLT có thể ghi bền vững.
- Dependency quan trọng không ở trạng thái circuit open kéo dài.

Không nhất thiết biến mọi lỗi downstream thành readiness failure. Nếu broker tạm thời không sẵn sàng nhưng ứng dụng vẫn có thể nhận request và ghi outbox bền vững, có thể tiếp tục phục vụ trong giới hạn backlog. Ngược lại, nếu không thể ghi dữ liệu hoặc lưu ý định event, cần đánh giá readiness theo SLA và nguy cơ mất dữ liệu.

Tách health của ứng dụng khỏi health của từng pipeline giúp người vận hành biết nên loại instance khỏi traffic, dừng consumer hay chỉ cảnh báo dependency.

## 14. Quan sát trong và sau rollout

Theo dõi baseline trước deploy và so sánh trong rollout:

| Chỉ số | Điều cần quan sát |
|---|---|
| HTTP error rate | Tăng lỗi request hoặc timeout |
| Request latency | p95/p99 so với baseline |
| Instance readiness | Số instance ready và thời gian drain |
| Event publish failures | Lỗi gửi event hoặc outbox publisher |
| Incomplete publications | Số lượng và tuổi publication chưa hoàn tất |
| Consumer lag | Backlog theo topic, partition và group |
| Event processing latency | Thời gian từ publish tới hoàn tất |
| Retry/DLT count | Lỗi lặp hoặc poison event |
| Database pool/locks | Connection saturation, lock wait và deadlock |
| Rebalance count | Mức độ dao động consumer group |

Log cần có release version, instance ID, event ID, listener/consumer ID, correlation ID và trace ID khi phù hợp. Không dùng các ID có cardinality cao làm metric label.

Đặt ngưỡng dừng rollout trước khi bắt đầu. Ví dụ: error rate tăng vượt ngưỡng, publication age vượt SLA, consumer lag không giảm, DLT tăng đột biến hoặc database connection pool bão hòa. Ngưỡng cụ thể phải dựa trên baseline và SLO của hệ thống.

## 15. Rollback khi phiên bản mới có vấn đề

Rollback binary không tự đảo ngược database migration, event đã phát hoặc message đã ghi vào broker. Vì vậy, cần thiết kế rollback trước deploy.

Một rollback an toàn thường gồm:

1. Dừng rollout và giữ nguyên instance còn khỏe.
2. Chuyển traffic hoặc consumer assignment về phiên bản tương thích.
3. Không xóa schema mới nếu phiên bản cũ vẫn có thể chạy với schema mở rộng.
4. Xác định event mới đã được phát và consumer cũ có đọc được không.
5. Giữ event pending và offset để phiên bản phục hồi có thể xử lý tiếp.
6. Nếu cần, tạm dừng producer hoặc consumer theo policy để tránh tạo thêm dữ liệu không tương thích.
7. Đối soát projection và trạng thái nghiệp vụ sau khi rollback.
8. Chỉ contract database/schema sau khi hết cửa sổ rollback.

Nếu event mới không tương thích với phiên bản cũ, không đơn giản bật lại binary cũ. Có thể cần forward-fix, adapter chuyển đổi hoặc consumer tương thích trung gian. Không xóa message đã phát để làm cho phiên bản cũ hoạt động.

## 16. Runbook cho một lần triển khai

Một runbook có thể chia thành bốn giai đoạn:

**Trước deploy**

- Xác nhận phiên bản producer/consumer tương thích.
- Kiểm tra schema database đã expand.
- Kiểm tra publication incomplete, outbox/inbox và consumer lag.
- Xác nhận backup, rollback plan và người trực vận hành.
- Ghi baseline metric và ngưỡng dừng.

**Trong deploy**

- Triển khai theo rolling, canary hoặc blue-green đã chọn.
- Theo dõi readiness và graceful shutdown.
- Xác minh instance mới khởi động và kết nối dependency.
- Theo dõi event publish, listener failure, rebalance và lag.
- Không contract schema trong giai đoạn overlap.

**Sau deploy**

- Xác minh request và event pipeline hoạt động.
- Kiểm tra publication pending và backlog đang giảm.
- Kiểm tra DLT, retry và lỗi deserialization.
- So sánh metric với baseline.
- Xác nhận consumer version đã chuyển đủ.

**Sau cửa sổ ổn định**

- Ngừng dual-write/dual-read khi đủ điều kiện.
- Chạy contract migration và dọn cấu trúc cũ.
- Thu hồi ACL, topic hoặc compatibility code không còn dùng.
- Cập nhật runbook, event catalog và release record.

## 17. Kiểm thử trước triển khai production

Kiểm thử cần mô phỏng cả phiên bản cũ và mới cùng tồn tại:

1. Producer cũ phát event, consumer mới đọc được.
2. Producer mới phát event, consumer cũ xử lý được trong giai đoạn tương thích.
3. Database schema mở rộng cho cả binary cũ và mới.
4. Backfill chạy theo batch trong khi request và event vẫn phát sinh.
5. Listener thất bại trước commit và publication có thể phục hồi.
6. Process dừng giữa handler và event được giao lại mà không tạo side effect trùng.
7. Kafka consumer rebalance trong rolling deployment.
8. Consumer mới xử lý event cũ còn trong retention.
9. Retry/DLT vẫn hoạt động khi broker hoặc dependency lỗi.
10. Rollback binary vẫn chạy với database schema đã expand.
11. Readiness và graceful shutdown phản ánh đúng trạng thái drain.
12. Canary không tạo side effect trùng với phiên bản stable.

Dùng integration test với database và broker phù hợp để kiểm tra offset, transaction, publication registry và idempotency. Chỉ kiểm thử unit không thể chứng minh toàn bộ quá trình rollout giữa nhiều instance.

## 18. Các nguyên nhân thường làm triển khai gián đoạn

| Nguyên nhân | Hậu quả | Biện pháp |
|---|---|---|
| Xóa cột trước khi instance cũ dừng | Binary cũ lỗi truy vấn | Expand-migrate-contract |
| Producer phát schema mới quá sớm | Consumer cũ deserialize thất bại | Rollout consumer tolerant trước |
| Shutdown ngay khi còn handler chạy | Event bị giao lại hoặc xử lý dang dở | Graceful drain và idempotency |
| Commit offset trước database | Có thể mất side effect khi process dừng | Commit sau xử lý/bàn giao bền vững |
| Hai phiên bản cùng xử lý một event | Side effect trùng hoặc projection xung đột | Consumer ownership, inbox và version guard |
| Dùng chung group cho blue/green không chủ đích | Partition bị chia ngoài dự kiến | Thiết kế group và cutover rõ |
| Retry không giới hạn | Backlog và tải dependency tăng | Backoff, max attempts và quarantine |
| Rollback code nhưng không xét event đã phát | Consumer cũ không đọc được message mới | Contract compatibility và forward-fix plan |

## 19. Checklist triển khai không gián đoạn

Trước khi bắt đầu rollout, xác nhận:

- Có chiến lược rolling, blue-green hoặc canary phù hợp với topology.
- Hai phiên bản có thể cùng hoạt động trong cửa sổ chuyển tiếp.
- Database migration dùng expand-migrate-contract.
- Event contract tương thích hoặc đã có version/topic migration.
- Consumer mới đọc được event cũ và consumer cũ không bị buộc đọc payload mới không hỗ trợ.
- Listener nội bộ và externalized consumer có kế hoạch xử lý publication pending.
- Kafka consumer có graceful shutdown, offset policy và idempotency.
- Consumer group/partition ownership trong blue-green hoặc canary đã rõ.
- Outbox/inbox/registry persistence có thể phục hồi sau restart.
- Readiness, liveness và drain behavior được cấu hình đúng.
- Có metric, baseline, alert và ngưỡng dừng rollout.
- Rollback không phụ thuộc vào việc đảo ngược dữ liệu hoặc xóa event đã phát.
- Có kiểm thử hai phiên bản cùng chạy và kiểm thử restart/rebalance.
- Chỉ contract schema và xóa cấu trúc cũ sau khi hết cửa sổ tương thích.

Triển khai không gián đoạn cho hệ thống Spring Modulith đòi hỏi phối hợp vòng đời ứng dụng, database và event pipeline. Khi duy trì tương thích giữa phiên bản, migration theo nhiều giai đoạn, drain listener/consumer đúng cách và giữ publication cùng message có thể phục hồi, nhóm vận hành có thể đưa phiên bản mới vào production mà không làm đứt luồng nghiệp vụ.


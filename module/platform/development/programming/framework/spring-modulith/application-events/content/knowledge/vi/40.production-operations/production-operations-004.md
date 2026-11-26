# Mở rộng consumer trong production

Khi lưu lượng application event tăng, consumer có thể không xử lý kịp tốc độ producer phát message. Queue bắt đầu dài ra, tuổi event tăng, listener chiếm nhiều thread và database hoặc dịch vụ downstream bị quá tải. Trong hệ thống Spring Modulith, mở rộng consumer cần được thiết kế cùng với publisher, listener, transaction, Event Publication Registry và broker để tăng throughput mà vẫn giữ được thứ tự nghiệp vụ, idempotency và khả năng phục hồi.

Module `SPRING_MODULITH_APPLICATION_EVENTS` tổ chức giao tiếp giữa các module bằng application event nhằm giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Trong production, cần phân biệt listener nội bộ chạy trong application context với consumer phân tán đọc từ Kafka hoặc RabbitMQ. Hai mô hình có cách mở rộng khác nhau: tăng executor concurrency trong một process không tương đương với thêm consumer instance trong một broker consumer group.

## 1. Khi nào cần mở rộng consumer?

Không nên tăng số thread hoặc replica chỉ vì CPU đang cao. Cần xác định dấu hiệu cho thấy năng lực xử lý event thấp hơn nhu cầu thực tế.

Các dấu hiệu thường gặp:

- Queue depth hoặc consumer lag tăng liên tục trong giờ tải bình thường.
- Tuổi message cũ nhất vượt SLO xử lý.
- Tốc độ event đến cao hơn tốc độ consumer hoàn tất.
- Thread pool của listener thường xuyên bão hòa hoặc queue nội bộ đầy.
- Thời gian chờ connection database tăng.
- Retry làm tăng số lần xử lý và kéo dài backlog.
- Một consumer hoặc partition trở thành điểm nghẽn trong khi các consumer khác nhàn rỗi.
- Consumer hoàn thành event chậm dù CPU còn thấp, thường do I/O hoặc dependency bên ngoài.

Backlog tăng trong một đợt ngắn chưa chắc là sự cố. Nếu consumer vẫn xử lý đều và backlog giảm sau khi đợt tải kết thúc, có thể hệ thống đã có đủ năng lực dự phòng. Hãy xem xu hướng trong một cửa sổ đủ dài, tuổi event và SLO trước khi quyết định scale.

## 2. Phân biệt listener nội bộ với consumer qua broker

Đây là quyết định đầu tiên vì nó xác định cơ chế scale.

| Mô hình | Cách nhận event | Cách mở rộng chính |
| --- | --- | --- |
| Spring application listener nội bộ | `ApplicationEventPublisher` dispatch trong application context của process phát event | Điều chỉnh executor/concurrency và tài nguyên của process |
| `@ApplicationModuleListener` | Listener theo cơ chế Spring Modulith, thường bất đồng bộ và gắn với transaction semantics | Điều chỉnh executor thực tế được async infrastructure sử dụng; giới hạn concurrency |
| Consumer Kafka | Đọc record từ topic trong một consumer group | Tăng consumer instance, phân bổ partition và tối ưu xử lý theo partition |
| Consumer RabbitMQ | Đọc message từ queue | Tăng số consumer cạnh tranh trên queue, điều chỉnh prefetch và concurrency |
| Consumer service độc lập | Nhận externalized event qua adapter/broker | Scale service theo lag, queue age và năng lực downstream |

Event nội bộ được dispatch trong process không tự trở thành một hàng đợi phân tán dùng chung giữa các replica. Nếu một ứng dụng có nhiều instance, mỗi instance có application context và event dispatch cục bộ của nó. Thêm replica không tự động phân phối một event nội bộ đang chờ trong executor của instance A sang instance B.

Nếu cần nhiều service hoặc nhiều instance cùng chia sẻ một luồng công việc, hãy externalize event qua broker phù hợp và thiết kế consumer group/queue rõ ràng. Event Publication Registry giúp theo dõi publication tới listener và phục hồi publication chưa hoàn tất theo cơ chế hỗ trợ; không nên xem registry là một distributed work queue tổng quát hoặc giả định nó tự cân bằng tải giữa mọi replica.

## 3. Đo tải trước khi tăng concurrency

Mở rộng cần dựa trên tốc độ event đến và thời gian xử lý thực tế. Gọi:

- \(\lambda\): tốc độ event đến, tính bằng event/giây.
- \(\mu\): tốc độ xử lý trung bình của một consumer instance khi chạy ở concurrency đã chọn.
- \(n\): số consumer instance hoạt động.
- \(B\): số event đang chờ trong backlog.

Trong mô hình đơn giản, hệ thống chỉ có thể duy trì backlog ổn định khi tổng năng lực xử lý lớn hơn tốc độ event đến:

\[
n\mu > \lambda
\]

Nếu tổng năng lực chỉ vừa bằng tốc độ đến, hệ thống không có dư địa cho burst, retry hoặc dao động thời gian xử lý. Cần một khoảng dự phòng phù hợp với SLO và đặc điểm tải thực tế.

Nếu backlog đang có và năng lực xử lý lớn hơn tốc độ đến, thời gian gần đúng để xóa backlog là:

\[
T_{drain} \approx \frac{B}{n\mu - \lambda}
\]

Đây chỉ là ước lượng khi tốc độ đến và xử lý tương đối ổn định. Nó không tính phân phối tải lệch, partition nóng, retry, batch, thời gian khởi động consumer hoặc giới hạn downstream.

Định luật Little cũng giúp liên hệ số lượng event đang nằm trong hệ thống với throughput và thời gian chờ:

\[
L = \lambda W
\]

Trong đó \(L\) là số công việc trung bình trong hệ thống và \(W\) là thời gian trung bình một công việc ở trong hệ thống. Nếu throughput không đổi nhưng số event tồn đọng tăng, thời gian chờ thường cũng tăng.

### Ví dụ tính năng lực

Giả sử một consumer instance xử lý ổn định 40 event/giây. Producer phát trung bình 120 event/giây và có burst cao hơn. Ba instance chỉ đạt khoảng 120 event/giây trong điều kiện lý tưởng, không có dự phòng. Bốn instance tạo thêm khoảng trống năng lực, nhưng chỉ hữu ích nếu broker có đủ partition/queue throughput và database cùng dependency chịu được concurrency bổ sung.

Không lấy throughput trong unit test làm số liệu capacity. Hãy đo bằng tải gần với payload, transaction, database, network và dependency thật của production.

## 4. Tăng concurrency trong listener nội bộ

`@ApplicationModuleListener` phù hợp với listener cần xử lý theo cơ chế module và transaction riêng. Khi listener được thực thi bất đồng bộ, executor quyết định số tác vụ có thể chạy đồng thời và số tác vụ có thể chờ.

Một executor cần được cấu hình có giới hạn:

```java
@Configuration
class EventListenerExecutionConfiguration {

    @Bean("taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("modulith-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

Các con số trên chỉ minh họa. Tên bean và cách chọn executor phải phù hợp với async infrastructure thực tế của ứng dụng. `@ApplicationModuleListener` sử dụng cơ chế bất đồng bộ của Spring; hãy xác nhận executor nào đang được chọn trong cấu hình hiện tại, tránh tạo thêm một bean nhưng listener vẫn chạy trên executor khác.

Ví dụ listener:

```java
@Component
class InventoryOnOrderPlaced {

    private final InventoryService inventory;

    InventoryOnOrderPlaced(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        inventory.reserve(event.orderId(), event.items());
    }
}
```

Tăng pool size giúp nhiều listener chạy đồng thời, nhưng cũng làm tăng số transaction, connection database và lời gọi dependency ngoài. Nếu một listener giữ transaction trong thời gian dài, tăng thread có thể khiến connection pool cạn nhanh hơn. Hãy tăng từng bước và quan sát thời gian chờ database cùng downstream.

### Chọn queue capacity có chủ đích

Executor queue là một buffer trong process. Queue quá nhỏ có thể từ chối tác vụ khi burst ngắn; queue quá lớn có thể giữ nhiều event trong RAM và làm tuổi xử lý tăng mà không tạo thêm throughput.

Nên chọn queue capacity dựa trên:

- Burst có thể chấp nhận và thời gian cần để consumer hấp thụ burst.
- Kích thước object/event và bộ nhớ heap.
- Thời gian chờ tối đa trước khi event phải được xử lý.
- Hành vi khi executor bão hòa: reject, retry hoặc cơ chế lưu bền vững.
- Khả năng phục hồi publication khi việc submit tác vụ thất bại.

Không dùng queue vô hạn để che giấu thiếu capacity. Khi buffer tăng không giới hạn, ứng dụng có thể dùng hết heap và bị dừng trước khi backlog được xử lý.

## 5. Tăng số consumer instance cho Kafka

Kafka phân chia topic thành partition. Trong cùng một consumer group, mỗi partition tại một thời điểm được gán cho tối đa một consumer trong group. Vì vậy, số partition giới hạn mức song song đọc của một group.

Ví dụ topic có 6 partition:

```text
Topic: order-events
Partitions: P0 P1 P2 P3 P4 P5

Consumer group: analytics
  instance A -> P0, P1
  instance B -> P2, P3
  instance C -> P4, P5
```

Nếu tăng lên 8 instance nhưng topic vẫn có 6 partition, ít nhất 2 instance không được gán partition trong trạng thái ổn định. Thêm replica không tự tăng throughput khi số partition là giới hạn.

Trước khi tăng partition, hãy đánh giá:

- Throughput cần đạt và mức song song mong muốn.
- Key strategy và thứ tự cần giữ theo aggregate.
- Số lượng consumer group đang đọc topic.
- Tác động tới phân phối dữ liệu và tải broker.
- Khả năng thay đổi partition count trong vòng đời topic.

### Chọn message key để giữ thứ tự

Nếu cần thứ tự theo đơn hàng, dùng `orderId` làm key để các event của cùng aggregate được route vào cùng partition. Khi đó Kafka bảo đảm thứ tự record trong partition. Không có thứ tự toàn cục giữa nhiều partition.

Nếu key phân phối không đều, một partition có thể nóng trong khi partition khác ít tải. Hãy theo dõi lag theo partition, không chỉ tổng lag của consumer group. Một aggregate có lưu lượng rất cao có thể trở thành điểm nghẽn do yêu cầu giữ thứ tự theo key.

### Consumer group và offset

Mỗi nhóm consumer có group ID riêng nếu cần nhận toàn bộ bản sao event độc lập. Các instance trong cùng group chia partition và cùng tiến offset. Nếu nhiều ứng dụng cần nhận cùng event, không cho chúng dùng chung một group ID trừ khi mục tiêu là chia tải giữa chúng.

Offset chỉ có ý nghĩa trong một partition. Khi xử lý database, thường cần commit database trước rồi mới commit offset để tránh mất thay đổi nếu tiến trình dừng. Điều này có thể tạo redelivery nếu database commit xong nhưng offset chưa commit; consumer phải idempotent.

## 6. Tăng consumer concurrency cho RabbitMQ

Với RabbitMQ, nhiều consumer có thể cùng consume một queue theo mô hình competing consumers. Broker phân phối message cho các consumer đang đăng ký; throughput phụ thuộc số consumer, thời gian xử lý, prefetch, loại queue, tốc độ acknowledgement và tài nguyên broker.

```text
Exchange: orders.events
       |
       v
Queue: analytics.order-completed
       |
       +----> Consumer instance A
       +----> Consumer instance B
       +----> Consumer instance C
```

Mỗi message trong queue được giao cho một consumer theo cơ chế phân phối của queue; các consumer không phải mỗi người nhận một bản sao. Nếu nhiều hệ thống cần bản sao độc lập, tạo queue riêng cho từng nhóm consumer và bind các queue đó vào exchange.

### Điều chỉnh prefetch

Prefetch giới hạn số message chưa được acknowledge mà broker có thể giao trước cho consumer/channel theo cấu hình. Prefetch quá thấp có thể làm consumer thường xuyên chờ round trip; quá cao có thể giữ nhiều message chưa xử lý trong một instance, tăng bộ nhớ và làm phân phối tải lệch.

Hãy đo thời gian xử lý, số message unacked, memory và phân phối giữa consumer khi thay đổi prefetch. Nếu listener xử lý lâu hoặc có side effect nặng, mức prefetch thấp hơn có thể giúp kiểm soát lượng công việc đang giữ. Nếu xử lý nhanh và ổn định, có thể tăng dần để giảm overhead giao nhận.

### Ordering với nhiều consumer

Một queue có thể giữ thứ tự message được enqueue, nhưng khi nhiều consumer xử lý song song, thứ tự hoàn tất xử lý không được bảo đảm. Requeue, retry và acknowledgement cũng có thể làm thứ tự quan sát thay đổi. Nếu nghiệp vụ cần thứ tự theo aggregate, cân nhắc phân vùng queue, serialize xử lý theo key hoặc dùng sequence/version để từ chối event cũ.

## 7. Chọn concurrency theo bottleneck

Concurrency nên được giới hạn bởi tài nguyên chậm nhất trong đường xử lý, không chỉ bởi số core CPU.

| Bottleneck | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| CPU | CPU cao, processing time tăng dù dependency nhanh | Tối ưu xử lý, batch phù hợp hoặc tăng CPU/instance |
| Database | Connection pool chờ, query latency cao, lock contention | Tối ưu query/index/transaction; giới hạn listener concurrency |
| HTTP dependency | Timeout, rate limit, connection saturation | Bulkhead, connection pool, rate limit và concurrency cap |
| Broker | Publish/deliver latency, disk/network hoặc queue throughput cao | Kiểm tra broker capacity, partition/queue topology và payload size |
| Serialization | CPU cao, payload lớn, GC nhiều | Giảm payload, tối ưu schema/converter và tránh serialize thừa |
| Executor | Active threads đạt max, queue tăng, task bị reject | Điều chỉnh pool/queue sau khi kiểm tra downstream |
| Partition nóng | Lag một vài partition cao hơn hẳn | Xem lại key distribution và workload theo aggregate |

Tăng concurrency khi database đang quá tải thường làm hệ thống tệ hơn. Trong trường hợp đó, giới hạn số listener chạy đồng thời có thể giúp giảm contention và làm throughput ổn định hơn.

## 8. Backpressure và giới hạn hàng đợi

Backpressure là cách hệ thống phản ứng khi tốc độ event đến vượt năng lực xử lý. Mục tiêu là giữ lượng công việc trong giới hạn kiểm soát được và tránh để producer, executor, broker hoặc database sụp đổ do backlog vô hạn.

Các lớp kiểm soát có thể gồm:

- Giới hạn queue của executor nội bộ.
- Broker queue/topic retention và quota phù hợp.
- Prefetch/maximum poll records và số tác vụ in-flight.
- Giới hạn concurrency của consumer.
- Rate limit khi gọi dependency ngoài.
- Giảm tốc producer hoặc tạm hoãn loại công việc ít quan trọng khi có cơ chế nghiệp vụ cho phép.
- Tách luồng quan trọng và không quan trọng bằng destination/queue riêng.

Không nên tự ý drop event nghiệp vụ quan trọng để giảm backlog. Nếu cần bỏ hoặc gộp event, phải có quy tắc nghiệp vụ rõ ràng, ví dụ event snapshot mới thay thế event cập nhật trạng thái trung gian. Với event tài chính hoặc tồn kho, bỏ message có thể làm sai dữ liệu.

### Bounded queue và overload policy

Khi executor queue đầy, ứng dụng cần hành vi xác định: từ chối submit, chạy trên caller thread hoặc dùng một cơ chế lưu bền vững khác. Mỗi lựa chọn có hệ quả:

- Reject có thể làm lộ tình trạng quá tải sớm; cần bảo đảm lỗi được quan sát và publication còn khả năng phục hồi.
- Caller-runs có thể tạo backpressure lên thread phát event nhưng làm thay đổi latency và ngữ cảnh xử lý của publisher.
- Queue vô hạn che giấu quá tải và có nguy cơ hết bộ nhớ.

Chọn policy theo transaction semantics và cách Spring Modulith ghi nhận publication. Không cấu hình rejection policy chỉ để tránh log lỗi mà chưa xác nhận event vẫn được xử lý hoặc có thể resubmit.

## 9. Tách luồng theo mức độ quan trọng

Nếu consumer báo cáo có thể chậm nhưng consumer thanh toán phải xử lý nhanh, không nên để cả hai tranh cùng một executor hoặc queue mà không có giới hạn. Có thể tách destination, executor hoặc service theo mức độ quan trọng và đặc tính xử lý.

Ví dụ:

| Luồng | Đặc điểm | Chiến lược |
| --- | --- | --- |
| Payment events | Tác động trực tiếp tới giao dịch | SLO nghiêm, concurrency và alert riêng |
| Inventory events | Cần đúng thứ tự theo aggregate ở một số thao tác | Partition/key hoặc serialization theo aggregate |
| Analytics events | Có thể xử lý trễ và theo batch | Consumer pool riêng, batch và backlog dài hơn có kiểm soát |
| Notifications | Phụ thuộc provider bên ngoài | Rate limit, retry và DLQ riêng |

Bulkhead giúp lỗi hoặc tải cao ở một nhóm consumer không làm cạn toàn bộ thread, connection hoặc queue của nhóm khác. Tuy nhiên, tách luồng làm tăng số thành phần cần quan sát và vận hành; chỉ tách khi có khác biệt thật về SLO, tải hoặc failure mode.

## 10. Batch processing và hiệu quả mỗi lần gọi

Nếu event độc lập và thao tác lưu trữ hỗ trợ batch, xử lý theo lô có thể giảm số lần round trip tới database hoặc broker. Ví dụ consumer nhận một nhóm event rồi ghi nhiều bản ghi projection trong một transaction.

Batch cần giới hạn:

- Kích thước tối đa của batch.
- Thời gian chờ gom batch.
- Kích thước payload và bộ nhớ.
- Thời gian transaction và lock duration.
- Cách xác định event lỗi trong batch.
- Cách retry phần thành công và phần thất bại.

Batch quá lớn có thể tăng latency và khiến một lỗi nhỏ làm rollback nhiều event. Batch quá nhỏ có thể không giảm overhead. Cần đo throughput và p95/p99 latency khi thay đổi kích thước.

Nếu event có quan hệ thứ tự, không gom batch theo cách đảo thứ tự. Với thao tác delta, cần idempotency theo event hoặc sequence để retry batch không cộng dồn hai lần.

## 11. Idempotency khi tăng số consumer

Tăng concurrency làm tăng khả năng hai instance nhận các event liên quan gần nhau hoặc một event được giao lại sau timeout. Consumer phải idempotent trước khi scale mạnh.

Một inbox table có thể dùng khóa `(consumer_name, event_id)`:

```sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    event_id       VARCHAR(100) NOT NULL,
    processed_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong transaction:

1. Thử insert inbox entry bằng thao tác nguyên tử.
2. Nếu khóa đã tồn tại, bỏ qua lần giao lặp.
3. Nếu insert thành công, cập nhật dữ liệu nghiệp vụ/read model.
4. Commit inbox và dữ liệu cùng nhau.

Unique constraint bảo vệ race condition khi nhiều instance xử lý cùng một event. Không chỉ `SELECT` kiểm tra rồi `INSERT` ở hai bước không có khóa.

Nếu hai event khác `eventId` cùng đại diện cho một hành động nghiệp vụ, cần business operation key. Ví dụ, hai `PaymentRequested` có event ID khác nhau nhưng cùng `paymentAttemptId` chỉ được tạo một lần thu tiền.

Đối với side effect bên ngoài, sử dụng idempotency key do provider hỗ trợ nếu có. Database transaction nội bộ không thể rollback một email đã gửi hoặc một khoản thanh toán đã được provider ghi nhận.

## 12. Giữ thứ tự khi tăng concurrency

Tăng số consumer có thể làm thứ tự hoàn tất xử lý khác thứ tự nhận message. Trước khi scale, hãy xác định thứ tự nào là invariant:

- Thứ tự publish trong một transaction.
- Thứ tự event theo một aggregate.
- Thứ tự message trong một partition/queue.
- Thứ tự hoàn tất side effect.
- Thứ tự cập nhật read model.

Nếu chỉ cần thứ tự theo aggregate, hãy dùng aggregate ID làm partition key hoặc phân vùng xử lý theo aggregate. Consumer có thể xử lý các aggregate khác nhau song song nhưng serialize event của cùng aggregate.

Nếu event mang version, projector có thể từ chối event cũ và phát hiện gap. Không dùng timestamp làm sequence duy nhất vì đồng hồ có thể lệch và nhiều event có cùng timestamp.

Với workflow nhiều nhánh độc lập, không áp đặt thứ tự toàn cục. Hãy mô hình hóa dependency giữa các bước và chỉ đồng bộ tại điểm hội tụ thực sự cần thiết.

## 13. Retry, poison event và dead-letter queue

Retry làm tăng tải. Khi consumer chậm vì dependency đang lỗi, retry quá nhanh có thể tạo retry storm và làm backlog lớn hơn.

Một chính sách retry nên phân loại lỗi:

- **Transient:** timeout ngắn, kết nối tạm mất, rate limit có thể phục hồi; retry có exponential backoff và jitter.
- **Permanent:** schema không hợp lệ, dữ liệu thiếu trường bắt buộc, vi phạm invariant; không retry vô hạn.
- **Unknown outcome:** side effect ngoài có thể đã xảy ra nhưng response bị mất; đối soát hoặc dùng cùng idempotency key trước khi retry.

Sau số lần retry hữu hạn, poison event có thể được chuyển sang DLQ/quarantine để các event khác tiếp tục tiến triển. DLQ cần có owner, alert, retention và quy trình replay có kiểm soát.

Khi tăng số consumer, hãy kiểm tra retry traffic riêng. Nếu mỗi event lỗi được thử lại nhiều lần, tốc độ xử lý hữu ích có thể thấp hơn nhiều so với số lần handler được gọi.

## 14. Giới hạn tải lên database và dependency ngoài

Consumer thường dùng database connection trong transaction và có thể gọi dịch vụ HTTP. Tổng concurrency của tất cả replica phải nằm trong giới hạn các dependency đó.

Ví dụ, nếu mỗi instance chạy 16 listener đồng thời và có 8 replica, hệ thống có thể tạo tới 128 tác vụ xử lý song song, chưa tính request HTTP và background job khác. Nếu mỗi tác vụ giữ một connection database, connection pool và database server phải chịu được tải này cùng các workload khác.

Hãy tính tổng theo toàn hệ thống:

\[
\text{Potential concurrency} = \text{replica count} \times \text{per-instance concurrency}
\]

Đây là giới hạn lý thuyết; số thực tế còn phụ thuộc executor, số listener, partition/queue và thời gian chờ. Tuy nhiên, nó giúp tránh việc mỗi nhóm tự tăng pool mà không xem tổng tải.

Các biện pháp bảo vệ:

- Giới hạn listener concurrency theo connection pool và năng lực database.
- Giữ transaction ngắn; không gọi HTTP chậm trong khi giữ database lock nếu có thể tách bước.
- Đặt timeout cho HTTP/database và connection pool.
- Dùng bulkhead riêng cho dependency dễ quá tải.
- Dùng rate limit theo quota của provider.
- Theo dõi connection acquisition time, lock wait và downstream latency.
- Không tăng replica nếu database đã là bottleneck.

## 15. Autoscaling theo tín hiệu event

CPU không phải tín hiệu đủ tốt cho mọi consumer. Consumer bị chờ I/O có thể có CPU thấp nhưng backlog vẫn tăng. Ngược lại, CPU cao ngắn hạn có thể không ảnh hưởng SLO nếu queue vẫn được xử lý kịp.

Các tín hiệu autoscaling phù hợp:

- Kafka consumer lag theo group và partition.
- RabbitMQ queue depth và tuổi message cũ nhất.
- Tốc độ event đến so với tốc độ xử lý thành công.
- Backlog growth rate trong một cửa sổ thời gian.
- Processing duration p95/p99.
- Mức sử dụng thread pool và queue executor.
- Giới hạn concurrency của database/dependency ngoài.

Autoscaler phải biết giới hạn song song của nguồn. Với Kafka, số replica consumer hữu ích trong group thường không vượt số partition có thể xử lý song song. Với RabbitMQ, thêm consumer có thể tăng throughput nhưng phải giới hạn theo broker, prefetch và downstream.

### Tránh scale dao động

Scale up/down quá nhanh có thể gây rebalance liên tục, tạo thêm connection và làm consumer mất thời gian khởi động. Dùng cooldown, stabilization window và mức tăng/giảm có giới hạn. Scale down nên chậm hơn scale up nếu event đang có backlog hoặc consumer cần hoàn tất công việc đang nhận.

Không đặt autoscaling target chỉ dựa trên tổng backlog mà bỏ qua tuổi event. Một backlog lớn nhưng đang giảm nhanh có thể không cần thêm replica; backlog nhỏ nhưng event cũ nhất đã vượt SLO vẫn cần điều tra.

## 16. Graceful shutdown và rolling deployment

Khi scale down hoặc deploy phiên bản mới, consumer cần dừng nhận công việc mới và hoàn tất hoặc trả lại công việc đang xử lý theo semantics của broker.

Một trình tự shutdown an toàn thường là:

1. Đánh dấu instance không nhận thêm traffic/công việc mới.
2. Ngừng poll hoặc ngừng đăng ký consumer mới.
3. Chờ tác vụ in-flight hoàn tất trong thời gian shutdown cho phép.
4. Commit database trước acknowledgement/offset theo thiết kế.
5. Nếu không hoàn tất kịp, để message có thể được giao lại và dựa vào idempotency.
6. Đóng connection và executor sau khi xử lý xong hoặc timeout có kiểm soát.

Với Kafka, shutdown và rebalance cần bảo đảm offset chỉ được commit cho record đã xử lý an toàn. Với RabbitMQ, message chưa acknowledge có thể được redeliver khi channel/connection đóng; consumer phải chịu được duplicate.

Với listener nội bộ, executor nên có chính sách chờ tác vụ đang chạy trong giới hạn thời gian shutdown. Persistent Event Publication Registry giúp theo dõi publication chưa hoàn tất theo cấu hình, nhưng không thay thế việc thiết kế shutdown cho executor và transaction.

Khi triển khai rolling update, consumer mới nên đọc được payload do producer cũ phát và ngược lại trong khoảng thời gian triển khai hỗn hợp. Thay đổi schema breaking cần quy trình migration riêng.

## 17. Health, readiness và liveness

Health check cần phản ánh khả năng nhận và xử lý công việc, nhưng không nên restart consumer chỉ vì backlog cao. Backlog là tín hiệu tải; restart liên tục có thể làm giảm throughput hơn nữa.

Nên phân biệt:

- **Liveness:** process còn hoạt động và không bị treo nghiêm trọng.
- **Readiness:** instance đã sẵn sàng tham gia nhận công việc, connection và cấu hình cần thiết đã được thiết lập.
- **Consumer progress:** consumer có đang xử lý hoặc tiến offset/checkpoint hay không.
- **Backlog/SLO alert:** event có đang chờ quá lâu hoặc lag tăng hay không.

Nếu broker tạm mất kết nối, readiness có thể chuyển trạng thái theo chiến lược của ứng dụng; liveness không nhất thiết phải thất bại ngay. Tránh cấu hình liveness khiến orchestrator liên tục restart mọi replica trong lúc broker outage.

## 18. Observability khi mở rộng consumer

Cần quan sát cả năng lực, độ trễ và lỗi. Một dashboard hữu ích có thể gồm:

| Nhóm | Metric/tín hiệu | Dùng để trả lời |
| --- | --- | --- |
| Arrival | Event publish rate | Producer phát nhanh tới mức nào? |
| Throughput | Event processed/acknowledged rate | Consumer hoàn tất được bao nhiêu? |
| Backlog | Queue depth, incomplete publication count | Có bao nhiêu việc đang chờ? |
| Age/lag | Oldest message age, consumer lag | Event cũ nhất đang chờ bao lâu? |
| Latency | Processing duration p50/p95/p99 | Một event mất bao lâu để xử lý? |
| Executor | Active threads, queue size, rejected tasks | Listener pool có bị bão hòa không? |
| Database | Pool active/idle, acquisition time, lock wait | Database có là bottleneck không? |
| Retry/DLQ | Retry count, failure rate, DLQ depth | Có lỗi lặp hoặc poison event không? |
| Resource | CPU, memory, GC, network | Instance còn dư tài nguyên không? |
| Progress | Last successful completion/checkpoint | Consumer có tiếp tục tiến triển không? |

Metric nên có label hữu hạn như `consumer`, `event_type`, `destination`, `partition` và `result` khi tập giá trị được kiểm soát. Không đưa `eventId`, `aggregateId`, email hoặc payload vào label metric vì cardinality sẽ tăng nhanh. Định danh cụ thể nên nằm trong log/trace có quyền truy cập phù hợp.

Log nên có event ID, correlation ID, consumer name, destination và kết quả xử lý. Không ghi toàn bộ payload chứa dữ liệu cá nhân. Trace có thể giúp xác định thời gian ở publisher, broker, consumer, database và dependency ngoài nếu context propagation được cấu hình đúng.

## 19. Alert và SLO cho consumer

Một consumer có thể có SLO về độ trễ xử lý, tỷ lệ thành công hoặc thời gian backlog được xóa sau burst. Ví dụ:

- 99% event `OrderCompleted` được consumer billing xử lý trong một khoảng thời gian nghiệp vụ đã thống nhất.
- Consumer analytics bắt kịp nguồn trong thời gian cho phép sau một đợt replay.
- DLQ không tăng liên tục mà không có người chịu trách nhiệm.
- Publication incomplete lâu nhất không vượt ngưỡng vận hành.

Alert nên kết hợp nhiều tín hiệu:

- Lag/queue age vượt SLO trong một khoảng thời gian liên tục.
- Backlog tăng và completion rate thấp hơn arrival rate.
- Consumer count bằng 0 hoặc partition không có owner.
- Thread pool queue đầy hoặc reject tăng.
- Database connection wait và downstream latency tăng.
- Retry/DLQ tăng nhanh.

Không tạo paging chỉ vì CPU hoặc queue depth tăng trong vài giây. Cần có thời gian `for`, ngưỡng theo event criticality và runbook chỉ ra bước điều tra đầu tiên.

## 20. Kiểm thử capacity và scale trước production

Một cấu hình concurrency có thể chạy tốt trong test nhỏ nhưng thất bại khi payload lớn, dependency chậm hoặc có burst. Nên kiểm thử nhiều kiểu tải:

| Kiểu test | Mục tiêu |
| --- | --- |
| Baseline | Đo throughput/latency với cấu hình hiện tại |
| Load test | Đo hành vi ở tải mục tiêu ổn định |
| Stress test | Tìm giới hạn và cách hệ thống suy giảm khi quá tải |
| Burst test | Xác nhận khả năng hấp thụ đợt tăng event ngắn |
| Soak test | Phát hiện memory leak, queue tăng dần và connection rò rỉ |
| Dependency degradation | Xác nhận backpressure khi database/provider chậm |
| Redelivery/retry | Kiểm tra idempotency và retry storm |
| Rebalance/shutdown | Kiểm tra Kafka rebalance, RabbitMQ redelivery và graceful shutdown |
| Scale up/down | Đo thời gian bắt kịp và tác động khi thay đổi replica |

Đo throughput hữu ích, không chỉ số lần handler được gọi. Một consumer có thể có throughput cao nhưng phần lớn là retry hoặc duplicate. Hãy theo dõi số event nghiệp vụ hoàn tất, độ trễ và sai lệch dữ liệu.

## 21. Rollout thay đổi concurrency an toàn

Không nên tăng pool size hoặc replica hàng loạt mà không có baseline. Có thể triển khai theo từng bước:

1. Ghi nhận arrival rate, processing rate, lag/queue age và bottleneck hiện tại.
2. Xác định mô hình consumer: listener nội bộ, Kafka hay RabbitMQ.
3. Xác định SLO, thứ tự cần giữ, idempotency và giới hạn downstream.
4. Thay đổi một tham số mỗi lần: pool size, prefetch, partition, batch hoặc replica.
5. Theo dõi throughput, p95/p99, DB pool, retry và error rate.
6. Giữ cấu hình nếu throughput tăng mà SLO và dependency vẫn ổn định.
7. Rollback tham số nếu database, broker hoặc dependency bị quá tải.
8. Ghi lại capacity thực tế và giới hạn đã xác định để làm cơ sở autoscaling.

Với thay đổi partition hoặc topology broker, cần kế hoạch riêng vì có thể ảnh hưởng key distribution, ordering và consumer assignment. Không coi thay đổi partition count là thao tác scale không có tác động.

## 22. Runbook khi consumer không theo kịp

Khi queue age hoặc consumer lag vượt ngưỡng, người vận hành có thể điều tra theo trình tự:

1. Xác định event type, consumer group/queue, partition và thời điểm backlog bắt đầu tăng.
2. So sánh arrival rate với completion/acknowledgement rate.
3. Kiểm tra consumer instance còn hoạt động và có được gán partition/queue không.
4. Xem processing time, thread pool, executor queue và rejected task.
5. Kiểm tra database connection pool, lock wait, query latency và downstream timeout.
6. Kiểm tra retry rate, poison event và DLQ để xác định tải lặp.
7. Nếu bottleneck là consumer compute, tăng concurrency/replica trong giới hạn partition và tài nguyên.
8. Nếu bottleneck là database hoặc provider, giới hạn concurrency và xử lý dependency trước.
9. Nếu một partition/key nóng, kiểm tra phân phối key và workload của aggregate.
10. Theo dõi backlog drain, tuổi event và SLO cho tới khi phục hồi.
11. Chỉ resubmit/replay event sau khi xác định lỗi và bảo đảm idempotency.

Không xóa queue hoặc publication incomplete để giảm số liệu. Không tăng replica vô hạn khi downstream đã quá tải. Nếu backlog đến từ poison event, cách ly event lỗi theo chính sách để phần còn lại có thể tiến triển.

## 23. Những lỗi thường gặp khi mở rộng consumer

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tăng replica cho listener nội bộ nhưng mong event được chia giữa các instance | Event dispatch cục bộ không trở thành distributed queue | Externalize qua broker nếu cần scale-out phân tán |
| Tăng Kafka consumer vượt số partition | Instance dư không nhận partition | Thiết kế partition count và key strategy phù hợp |
| Dùng chung Kafka group cho hai ứng dụng cần nhận bản sao | Hai ứng dụng chia nhau message thay vì mỗi ứng dụng nhận đủ | Dùng group riêng cho từng consumer độc lập |
| Tăng RabbitMQ prefetch quá cao | Nhiều message unacked, tải lệch và memory tăng | Đo và điều chỉnh prefetch |
| Dùng queue executor vô hạn | Heap tăng và event chờ lâu không giới hạn | Bounded queue và overload policy rõ ràng |
| Tăng concurrency khi database đã bão hòa | Connection wait và lock contention tăng | Giới hạn consumer, tối ưu database trước |
| Không idempotent khi scale | Duplicate/redelivery tạo side effect trùng | Inbox, business key và unique constraint |
| Không xét thứ tự khi xử lý song song | Event cũ ghi đè trạng thái mới | Partition/key, sequence và checkpoint |
| Retry quá nhanh | Retry storm làm backlog nặng hơn | Backoff, jitter, retry cap và DLQ |
| Autoscale chỉ theo CPU | Không phát hiện consumer bị chờ I/O | Dùng lag, queue age và completion rate |
| Scale down đột ngột | Message bị redeliver hoặc offset không an toàn | Graceful shutdown và commit/ack đúng thứ tự |
| Chỉ đo handler invocation | Throughput có thể bị thổi phồng bởi retry/duplicate | Đo business completion và latency |

## 24. Quy trình mở rộng consumer trong production

Khi cần tăng năng lực xử lý event, hãy thực hiện theo thứ tự:

1. Phân biệt listener nội bộ với consumer qua broker.
2. Đo arrival rate, completion rate, backlog, age/lag và processing duration.
3. Xác định bottleneck thực tế: CPU, executor, database, broker hay dependency ngoài.
4. Chọn cách scale phù hợp: pool concurrency, Kafka partitions/instances hoặc RabbitMQ consumers/prefetch.
5. Giới hạn queue, in-flight messages và concurrency theo tài nguyên downstream.
6. Bảo đảm idempotency, thứ tự theo aggregate và retry/DLQ trước khi tăng song song.
7. Thiết kế autoscaling theo lag/queue age và stabilization window.
8. Cấu hình graceful shutdown, readiness và rolling deployment.
9. Load/stress/soak test với dependency degradation và redelivery.
10. Rollout từng bước, theo dõi SLO và ghi lại capacity đã xác nhận.

Mở rộng consumer là bài toán cân bằng giữa tốc độ event đến, khả năng xử lý và giới hạn của các dependency. Khi phân biệt đúng listener nội bộ với consumer phân tán, đo backlog và latency, chọn concurrency theo bottleneck, đồng thời bảo vệ idempotency, ordering và graceful shutdown, hệ thống Spring Modulith có thể tăng throughput mà vẫn duy trì tính đúng đắn của giao tiếp nghiệp vụ trong production.

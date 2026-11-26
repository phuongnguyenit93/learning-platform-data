# Backpressure

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp qua publisher, listener và các adapter đến broker. Khi tốc độ phát sự kiện cao hơn tốc độ xử lý, công việc tồn đọng sẽ tích tụ ở executor, publication registry, broker hoặc consumer. **Backpressure** là cách hệ thống điều tiết tốc độ tiếp nhận và xử lý để tải không vượt quá năng lực của các thành phần phía sau.

Backpressure không làm hệ thống nhanh hơn. Nó giúp hệ thống phản ứng có kiểm soát khi tải tăng, downstream chậm hoặc broker tạm thời không sẵn sàng. Mục tiêu là giữ độ trễ và backlog trong giới hạn vận hành, bảo vệ tài nguyên, đồng thời duy trì các cam kết giao sự kiện của nghiệp vụ.

## 1. Hiểu vấn đề backpressure

Một luồng event thường có nhiều chặng:

1. Request hoặc tác vụ nghiệp vụ tạo event.
2. Publisher phát application event.
3. Listener nội bộ nhận và xử lý, hoặc publication được lưu để xử lý sau.
4. Adapter externalization chuyển event đến broker.
5. Broker lưu và phân phối message.
6. Consumer nhận, xử lý và xác nhận message.
7. Consumer có thể phát event tiếp theo hoặc gọi dịch vụ khác.

Mỗi chặng có một năng lực xử lý hữu hạn. Nếu publisher tạo 1.000 event mỗi giây trong khi consumer chỉ xử lý được 600 event mỗi giây, backlog tăng khoảng 400 event mỗi giây trong thời gian tải đó. Nếu tình trạng kéo dài, queue, database, bộ nhớ hoặc dung lượng broker cuối cùng sẽ cạn.

Có thể hình dung quan hệ giữa tốc độ đến, tốc độ xử lý và backlog:

```
Tốc độ backlog thay đổi ≈ tốc độ event đến - tốc độ event xử lý
```

- Nếu tốc độ đến thấp hơn tốc độ xử lý, backlog có xu hướng giảm.
- Nếu hai tốc độ xấp xỉ nhau, backlog có thể ổn định nhưng không còn nhiều dư địa cho đột biến.
- Nếu tốc độ đến cao hơn tốc độ xử lý trong thời gian dài, backlog tiếp tục tăng.
- Nếu consumer dừng hoàn toàn, broker hoặc publication store phải giữ công việc cho đến khi có thể phục hồi, trong giới hạn dung lượng và retention.

Backpressure là tập hợp cơ chế để điều tiết quan hệ này. Nó có thể làm chậm producer, giới hạn số công việc đang chạy, điều chỉnh lượng message được consumer lấy về, tạm dừng nhận message, từ chối tải mới hoặc chuyển công việc sang hàng đợi bền vững.

## 2. Phân biệt backpressure, buffering và load shedding

Các cơ chế này có liên quan nhưng giải quyết vấn đề khác nhau:

| Cơ chế | Hành vi | Khi phù hợp |
|---|---|---|
| Backpressure | Điều chỉnh tốc độ hoặc lượng công việc được phép đi tiếp | Consumer còn khả năng xử lý nhưng cần giới hạn tải |
| Buffering | Giữ công việc để xử lý sau | Có đột biến ngắn hạn và có đủ dung lượng lưu trữ |
| Load shedding | Từ chối hoặc loại bỏ một phần tải | Hệ thống phải bảo vệ tài nguyên khi không thể tiếp nhận thêm |
| Retry | Thử lại công việc thất bại | Lỗi có khả năng tạm thời và chính sách retry được giới hạn |
| Scaling | Tăng năng lực xử lý bằng thêm tài nguyên hoặc instance | Nút thắt có thể mở rộng và downstream còn dư năng lực |

Buffering chỉ trì hoãn thời điểm xử lý. Một queue không giới hạn có thể che giấu quá tải trong một khoảng thời gian rồi gây ra sự cố bộ nhớ hoặc dung lượng. Retry tức thì cũng có thể làm tải tăng cao hơn. Scaling consumer không giúp ích nếu database, API bên ngoài hoặc partition của broker đã là nút thắt.

Hệ thống đáng tin cậy thường kết hợp các cơ chế: buffer có giới hạn, backpressure, retry có backoff, admission control và cảnh báo backlog.

## 3. Tìm đúng nơi tích tụ backlog

Không nên chỉ quan sát số message trên broker. Với Spring Modulith, tải có thể tích tụ ở nhiều tầng:

| Tầng | Dấu hiệu | Tài nguyên có thể bị ảnh hưởng |
|---|---|---|
| Request và publisher | Request chậm, nhiều event được phát trong một transaction | Thread request, transaction, connection pool |
| Async executor | Queue task tăng, thread bận lâu, task bị từ chối | Heap, thread, CPU |
| Publication registry | Publication chưa hoàn tất tăng và ngày càng cũ | Database, index, dung lượng lưu trữ |
| Externalization adapter | Gửi message chậm, lỗi kết nối hoặc xác nhận chậm | Connection, buffer, publication backlog |
| Broker | Consumer lag, queue depth hoặc disk tăng | Dung lượng broker, I/O, retention |
| Consumer | Thời gian xử lý tăng, số message đang xử lý tăng | Thread pool, database pool, downstream API |
| Dịch vụ được gọi tiếp | Timeout, rate limit, circuit breaker mở | Connection, quota và năng lực dịch vụ ngoài |

Hãy đo backlog tại từng chặng và xác định nơi có tốc độ xử lý thấp nhất. Ví dụ, broker có thể nhận message rất nhanh nhưng consumer ghi database chậm. Tăng tốc producer hoặc tăng số lần publish chỉ làm backlog ở broker lớn hơn.

## 4. Đo tải trước khi chọn giới hạn

Trước khi đặt queue size hoặc concurrency, cần hiểu workload thực tế:

- Tốc độ event trung bình và tốc độ đỉnh trong từng khoảng thời gian.
- Số listener hoặc consumer nhận mỗi event.
- Kích thước payload trung bình và trường hợp lớn nhất.
- Thời gian xử lý trung bình, p95 và p99.
- Tỷ lệ lỗi, retry và thời gian downstream gián đoạn.
- Số instance, thread, partition và connection có thể sử dụng.
- Mức backlog tối đa và độ trễ xử lý mà nghiệp vụ chấp nhận.

Một phép tính đơn giản giúp ước lượng năng lực. Nếu một consumer xử lý trung bình 50 event mỗi giây và có 8 consumer độc lập với tải phân bổ đều, năng lực lý thuyết là khoảng 400 event mỗi giây. Năng lực thực tế thường thấp hơn vì transaction, lock, network, GC, retry và các tác vụ khác cùng sử dụng tài nguyên.

Theo dõi cả throughput và latency. Throughput có thể vẫn cao trong khi độ trễ tăng vì message chờ lâu trước khi được xử lý. Với event nghiệp vụ, tuổi của publication hoặc message cũ nhất thường là tín hiệu quan trọng hơn tổng số message.

## 5. Giới hạn hàng đợi trong ứng dụng

Listener bất đồng bộ giúp publisher không phải chờ toàn bộ công việc của listener. Tuy nhiên, async chỉ chuyển nơi chờ từ request thread sang executor. Nếu executor dùng queue không giới hạn, hệ thống vẫn có thể tích tụ vô hạn task.

Hãy cấu hình executor với:

- Số thread tối thiểu và tối đa phù hợp CPU, I/O và downstream.
- Queue có giới hạn để đặt trần cho số task chờ.
- Chính sách từ chối task khi queue đầy.
- Metric cho active thread, queue size, task hoàn tất và task bị từ chối.
- Quy tắc shutdown để công việc đang chờ được xử lý hoặc được lưu bền vững theo thiết kế.

Ví dụ cấu hình executor có queue giới hạn:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

@Configuration
@EnableAsync
class EventExecutorConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("event-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy()
        );
        return executor;
    }
}
~~~

Đây là giá trị minh họa, không phải cấu hình mặc định hay khuyến nghị cố định cho mọi ứng dụng. Cần import `java.util.concurrent.ThreadPoolExecutor` khi sử dụng `AbortPolicy`, và cần lựa chọn executor phù hợp với listener thực tế.

Khi queue đầy, `AbortPolicy` báo từ chối task. Hành vi tiếp theo phải được xử lý phù hợp với hợp đồng giao sự kiện. Không được nuốt exception hoặc đánh dấu publication hoàn tất nếu listener chưa xử lý thành công.

Một số chính sách khác có trade-off riêng:

- **CallerRunsPolicy:** thread gọi sẽ chạy task, qua đó làm chậm producer. Điều này có thể tạo backpressure tự nhiên, nhưng nếu thread gọi là request thread hoặc đang giữ transaction, thời gian request và tải transaction có thể tăng.
- **DiscardPolicy / DiscardOldestPolicy:** loại bỏ task. Chỉ phù hợp với dữ liệu có thể mất theo một chính sách nghiệp vụ rõ ràng, ví dụ một số cập nhật telemetry có thể bỏ qua. Không dùng tùy tiện cho event nghiệp vụ cần giao đáng tin cậy.
- **AbortPolicy:** từ chối rõ ràng. Ứng dụng phải để lỗi lan đến nơi có thể retry hoặc xử lý; cần bảo đảm publication registry và transaction phản ánh đúng kết quả.

Với event nghiệp vụ quan trọng, một queue trong bộ nhớ không phải nơi lưu trữ bền vững. Nếu process dừng, task đang chờ có thể mất. Hãy dùng publication registry hoặc broker làm nơi giữ công việc bền vững theo kiến trúc đã chọn.

## 6. Giới hạn concurrency của listener

Tăng số thread không đồng nghĩa tăng thông lượng vô hạn. Listener có thể bị giới hạn bởi connection pool, row lock, API bên ngoài hoặc một aggregate cần xử lý tuần tự.

Chọn concurrency theo năng lực của tài nguyên phía sau:

- Nếu listener đọc/ghi database, số tác vụ đồng thời cần phù hợp với connection pool và khả năng chịu tải của database.
- Nếu listener gọi API có quota, giới hạn concurrency và tốc độ gọi theo quota của dịch vụ.
- Nếu xử lý CPU-bound, tăng thread vượt số core có thể làm tăng context switching thay vì tăng thông lượng.
- Nếu event cùng aggregate cần giữ thứ tự, tránh xử lý đồng thời các event đó theo cách làm sai thứ tự nghiệp vụ.
- Nếu một loại event chậm hơn nhiều loại khác, cân nhắc tách executor hoặc queue để tránh một nhóm công việc chiếm hết năng lực.

Có thể dùng semaphore hoặc bulkhead để giới hạn số lời gọi đến một downstream. Circuit breaker giúp ngừng gọi khi downstream lỗi kéo dài; sau đó hệ thống có thể tạm dừng consumer, retry có backoff hoặc giữ message trong broker.

## 7. Backpressure ở broker và consumer

Broker thường cung cấp cơ chế điều tiết ở phía consumer. Tên và cấu hình cụ thể phụ thuộc transport.

### Kafka

Với Kafka, consumer đọc message theo batch và quản lý offset. Các yếu tố cần xem xét:

- Số partition giới hạn mức song song tối đa trong một consumer group theo cách phân phối partition.
- Số consumer lớn hơn số partition không tự tạo thêm năng lực xử lý song song.
- Kích thước batch và số record được lấy về cần phù hợp với bộ nhớ và thời gian xử lý.
- Chỉ commit offset sau khi message đã được xử lý theo bảo đảm giao nhận mà ứng dụng yêu cầu.
- Khi consumer chậm, lag tăng; có thể tạm dừng partition hoặc giảm tốc độ poll theo thiết kế adapter.
- Hot partition hoặc key phân bố không đều có thể khiến một consumer bị quá tải trong khi consumer khác còn rảnh.

Nếu thứ tự theo aggregate là quan trọng, key thường dựa trên aggregate ID. Nhưng key phân vùng cần được chọn cùng với yêu cầu thứ tự và phân bố tải.

### RabbitMQ

Với RabbitMQ, consumer prefetch giới hạn số message chưa được acknowledge mà broker giao cho consumer. Prefetch quá lớn có thể làm message tập trung trong một consumer chậm; quá nhỏ có thể làm giảm throughput khi xử lý có độ trễ cao.

Cần chọn prefetch theo thời gian xử lý, số consumer, kích thước message và năng lực downstream. Dùng acknowledgement phù hợp để broker chỉ loại message khỏi queue sau khi consumer hoàn tất theo chính sách. Nếu consumer lỗi, xác định rõ requeue, retry queue hoặc dead-letter; requeue liên tục có thể tạo vòng lặp nóng.

### Các transport khác

Với JMS hoặc adapter khác, hãy tìm cơ chế tương đương như receive timeout, batch size, prefetch, concurrent consumers, acknowledgement và pause/resume. Không giả định mọi broker có cùng semantics hoặc một tham số cấu hình có cùng ý nghĩa.

## 8. Điều tiết tốc độ producer

Nếu consumer đã đạt giới hạn, producer cần biết hệ thống không thể tiếp nhận thêm vô hạn. Có một số cách:

**Admission control ở request boundary.** Giới hạn số request hoặc tác vụ có thể tạo event trong một khoảng thời gian. Khi quá tải, trả về phản hồi có thể thử lại như 429 hoặc 503, kèm hướng dẫn retry phù hợp nếu đó là API công khai.

**Rate limiting.** Giới hạn tốc độ theo tenant, loại event hoặc nguồn phát. Cách này hữu ích khi một nguồn tạo tải đột biến ảnh hưởng các nguồn khác.

**Batching và coalescing.** Gom nhiều cập nhật nhỏ thành một event tổng hợp nếu ngữ nghĩa nghiệp vụ cho phép. Với dữ liệu trạng thái có thể ghi đè, đôi khi chỉ cần công bố trạng thái mới nhất thay vì mọi trạng thái trung gian. Không gom các event mà mỗi lần chuyển trạng thái đều có ý nghĩa nghiệp vụ.

**Tách tải theo mức ưu tiên.** Event phục vụ giao dịch cốt lõi có thể cần queue và quota riêng so với event phân tích hoặc telemetry. Cần tránh để tải ưu tiên thấp chiếm hết tài nguyên của luồng quan trọng.

**Tạm dừng hoặc giảm tốc nguồn phát.** Với job nền, scheduler hoặc batch importer, có thể giảm batch size, tăng khoảng nghỉ hoặc dừng nhận công việc mới khi backlog vượt ngưỡng.

Không áp dụng load shedding cho event quan trọng mà không có quy tắc nghiệp vụ. Nếu buộc phải từ chối, hãy xác định caller sẽ retry thế nào và publication có được lưu bền vững hay không.

## 9. Publication registry và backlog bền vững

Spring Modulith Event Publication Registry theo dõi publication đến listener. Khi listener bất đồng bộ hoặc lỗi, publication chưa hoàn tất có thể tồn tại để quan sát và phục hồi theo cấu hình.

Registry giúp bảo vệ việc giao event giữa các module, nhưng nó không phải một bộ điều tốc tự động cho toàn hệ thống. Nếu listener xử lý chậm hơn tốc độ event được tạo, số publication chưa hoàn tất sẽ tăng. Cần đặt giới hạn tài nguyên, theo dõi tuổi backlog và xác định chính sách phục hồi.

Các điểm cần quản lý:

- Dung lượng database dành cho publication.
- Tốc độ ghi publication và cập nhật trạng thái hoàn tất.
- Index và truy vấn tìm publication chưa hoàn tất.
- Retention cho publication đã hoàn tất.
- Cảnh báo khi tuổi publication cũ nhất vượt SLO.
- Chính sách resubmit có backoff và giới hạn.
- Cách xử lý publication lỗi vĩnh viễn hoặc payload không thể đọc.

Không xóa publication chưa hoàn tất chỉ để làm giảm backlog. Trước khi cleanup, phải xác định event đã được xử lý, có thể phục hồi, hay cần quy trình xử lý ngoại lệ.

## 10. Retry có backoff và tránh retry storm

Khi downstream chậm hoặc ngừng hoạt động, retry ngay lập tức có thể làm tình hình tệ hơn. Hàng nghìn message cùng thử lại liên tục tạo retry storm, chiếm thread, connection và quota.

Một chính sách retry nên có:

- Số lần retry tối đa hoặc thời hạn retry.
- Exponential backoff để tăng khoảng chờ giữa các lần thử.
- Jitter để tránh nhiều consumer retry cùng một thời điểm.
- Phân loại lỗi có thể retry và lỗi không thể retry.
- Dead-letter hoặc khu vực cách ly cho message cần điều tra.
- Quy trình phát lại sau khi khắc phục nguyên nhân.

Ví dụ backoff tăng dần có giới hạn:

```
delay(n) = min(maxDelay, initialDelay × 2^n) + jitter
```

Các giá trị thực tế cần được giới hạn và chọn theo SLO. Retry không được che giấu lỗi vĩnh viễn hoặc khiến message bị giữ vô thời hạn mà không có cảnh báo.

Nếu consumer xử lý một tác dụng phụ rồi lỗi trước khi acknowledgement, message có thể được gửi lại. Consumer cần idempotent để lần xử lý lặp không tạo tác dụng phụ thứ hai. Nếu lỗi là do downstream quá tải, circuit breaker hoặc tạm dừng consumer có thể hữu ích hơn việc tiếp tục retry.

## 11. Tách luồng và cô lập lỗi

Một consumer chậm có thể làm ảnh hưởng các event khác nếu tất cả dùng chung executor, queue hoặc partition. Có thể giảm ảnh hưởng bằng:

- Tách queue theo nhóm event có đặc tính tải khác nhau.
- Dùng executor riêng cho listener CPU-bound và I/O-bound.
- Giới hạn concurrency theo downstream.
- Dùng bulkhead để một dịch vụ lỗi không chiếm hết thread.
- Đặt quota theo tenant hoặc nguồn phát.
- Ưu tiên xử lý event có SLO nghiêm ngặt hơn.

Tuy nhiên, tách queue tạo thêm vận hành: cấu hình, ACL, dashboard, retention và dead-letter. Chỉ tách khi có khác biệt về mức ưu tiên, tải, thứ tự hoặc độ tin cậy đủ rõ.

## 12. Đo lường và cảnh báo backpressure

Theo dõi cả tốc độ đến và tốc độ xử lý. Chỉ nhìn số message trong queue không cho biết backlog có đang được giải quyết hay không.

| Metric | Ý nghĩa |
|---|---|
| Event ingress rate | Tốc độ publisher tạo event |
| Event completion rate | Tốc độ listener hoặc consumer hoàn tất |
| Queue depth / publication backlog | Khối lượng công việc đang chờ |
| Age of oldest message/publication | Tuổi của công việc cũ nhất |
| Consumer lag | Khoảng cách giữa vị trí message mới nhất và vị trí consumer đã xử lý |
| Processing latency p95/p99 | Thời gian xử lý ở các phân vị cao |
| In-flight messages | Số message đang được xử lý hoặc chưa ack |
| Executor active threads / queue size | Mức sử dụng và áp lực trên executor |
| Rejected task count | Số task bị từ chối do hết năng lực |
| Retry và dead-letter rate | Tần suất lỗi và message cần điều tra |
| Database pool wait / lock wait | Nút thắt tại database phía consumer |

Đặt ngưỡng cảnh báo theo SLO, ví dụ tuổi publication cũ nhất, độ trễ event đến consumer hoặc thời gian backlog cần để xử lý hết. Một queue lớn nhưng đang giảm có thể ít nguy hiểm hơn queue nhỏ nhưng liên tục tăng.

Dashboard nên cho phép lọc theo event type, listener, consumer group, destination và tenant. Dùng event ID hoặc correlation ID để lần theo một event qua publisher, registry, broker và consumer.

## 13. Quy trình phản ứng khi backlog tăng

Khi backlog vượt ngưỡng, xử lý theo thứ tự:

1. Xác định tầng đang tích tụ backlog: executor, publication registry, adapter, broker hay consumer.
2. So sánh ingress rate và completion rate để biết tải mới có vượt năng lực hay không.
3. Xem processing latency, lỗi, retry, connection pool và tài nguyên downstream.
4. Nếu downstream đang quá tải, giảm concurrency hoặc tạm dừng consumer có kiểm soát.
5. Nếu producer có thể điều tiết, giảm batch size, rate hoặc tạm dừng job nền.
6. Khắc phục lỗi gốc trước khi tăng retry hoặc phát lại hàng loạt.
7. Chỉ tăng consumer khi partition, database, API và quota phía sau còn dư năng lực.
8. Theo dõi backlog có giảm và tuổi message cũ nhất có trở lại trong SLO hay không.
9. Sau sự cố, điều chỉnh giới hạn và kiểm thử lại tình huống tải đỉnh.

Không tăng đồng thời số producer, consumer, thread và retry khi chưa xác định bottleneck. Điều đó có thể chuyển áp lực sang database hoặc dịch vụ ngoài và tạo thêm sự cố.

## 14. Sơ đồ điều tiết tải

~~~mermaid
flowchart TD
    A[Publisher phát event] --> B[Admission control]
    B --> C{Có thể tiếp nhận?}
    C -- Không --> D[Tạm hoãn hoặc từ chối tải mới]
    C -- Có --> E[Publication registry hoặc outbox]
    E --> F[Adapter gửi đến broker]
    F --> G[Broker có giới hạn lưu trữ]
    G --> H[Consumer lấy message theo năng lực]
    H --> I{Downstream còn năng lực?}
    I -- Không --> J[Giảm tốc hoặc pause consumer]
    J --> G
    I -- Có --> K[Xử lý event]
    K --> L{Thành công?}
    L -- Có --> M[Acknowledge hoặc hoàn tất publication]
    L -- Không --> N[Retry có backoff hoặc dead-letter]
    N --> G
    M --> O[Đo throughput, lag và latency]
    O --> B
~~~

Sơ đồ thể hiện các điểm có thể điều tiết. Cơ chế cụ thể phụ thuộc việc listener chạy trong ứng dụng, adapter gửi message và loại broker đang sử dụng.

## 15. Ví dụ: listener chậm khi gọi dịch vụ kho

Giả sử module Đơn hàng phát 300 event OrderConfirmed mỗi giây. Listener externalization gửi message tới broker, còn consumer Kho gọi API để giữ hàng. API kho chỉ xử lý ổn định 180 request mỗi giây.

Nếu consumer tiếp tục nhận 300 message mỗi giây, backlog tăng khoảng 120 message mỗi giây. Trong 10 phút, backlog có thể tăng khoảng 72.000 message nếu không có thay đổi về tải hoặc năng lực xử lý.

Cách xử lý:

- Đặt concurrency và rate limit của consumer phù hợp với quota API kho.
- Dùng prefetch hoặc batch size vừa đủ để consumer không giữ quá nhiều message đang xử lý.
- Khi API kho quá tải, pause hoặc giảm tốc consumer và dùng retry có backoff.
- Giữ message trong broker theo retention đủ cho thời gian gián đoạn dự kiến.
- Theo dõi tuổi message cũ nhất và dead-letter.
- Nếu nguồn phát có thể điều tiết, giảm tốc các job tạo đơn hàng hàng loạt.
- Chỉ tăng consumer khi API kho, database và partition còn khả năng mở rộng.

Consumer cần idempotent. Nếu API kho đã giữ hàng nhưng acknowledgement bị mất, message có thể được gửi lại. Dùng event ID hoặc order ID làm idempotency key theo hợp đồng của API kho để tránh giữ hàng hai lần.

## 16. Kiểm thử backpressure

Kiểm thử cần mô phỏng tải và sự cố ở các chặng, không chỉ đo một listener trong điều kiện lý tưởng.

Các tình huống nên kiểm tra:

- Producer phát nhanh hơn consumer trong một khoảng thời gian.
- Consumer chậm dần do database hoặc API tăng latency.
- Broker tạm ngừng hoặc mất kết nối.
- Executor queue đầy và task bị từ chối.
- Một consumer bị lỗi kéo dài trong khi consumer khác vẫn khỏe.
- Một partition hoặc tenant có tải nóng bất thường.
- Message bị gửi lại sau khi consumer đã thực hiện tác dụng phụ.
- Process dừng khi có task đang chờ hoặc publication chưa hoàn tất.
- Backlog lớn được xử lý sau khi downstream phục hồi.
- Dead-letter được phát lại sau khi nguyên nhân đã được khắc phục.

Đánh giá các kết quả:

- Bộ nhớ, thread và connection không tăng vô hạn.
- Producer hoặc consumer bị điều tiết theo chính sách dự kiến.
- Event nghiệp vụ quan trọng không bị mất âm thầm.
- Retry không tạo vòng lặp nóng.
- Consumer xử lý trùng an toàn.
- Backlog có thể giảm sau khi tải trở lại bình thường.
- Độ trễ và tuổi message trở lại trong SLO.
- Metric và cảnh báo chỉ ra đúng tầng bị nghẽn.

## 17. Checklist thiết kế backpressure

- [ ] Đã xác định năng lực và bottleneck của từng chặng.
- [ ] Đã đo ingress rate, completion rate và processing latency.
- [ ] Queue trong bộ nhớ có giới hạn.
- [ ] Executor có concurrency và rejection policy rõ ràng.
- [ ] Không loại bỏ event nghiệp vụ quan trọng khi queue đầy.
- [ ] Consumer concurrency phù hợp với database và downstream quota.
- [ ] Broker prefetch, batch size hoặc poll được cấu hình theo năng lực.
- [ ] Có cơ chế pause/resume hoặc giảm tốc khi downstream quá tải.
- [ ] Retry có backoff, jitter và giới hạn.
- [ ] Có dead-letter hoặc quy trình cách ly lỗi vĩnh viễn.
- [ ] Listener và consumer idempotent.
- [ ] Publication registry và broker có retention/dung lượng được giám sát.
- [ ] Có metric backlog, tuổi message, rejection, retry và throughput.
- [ ] Có ngưỡng cảnh báo dựa trên SLO.
- [ ] Đã kiểm thử tải đỉnh, downstream chậm và phục hồi backlog.

## 18. Nguyên tắc vận hành

Backpressure cần được thiết kế xuyên suốt từ publisher, listener, publication registry, adapter đến broker và consumer. Hãy giới hạn queue, điều chỉnh concurrency theo năng lực downstream, điều tiết tốc độ producer khi có thể và giữ các event nghiệp vụ quan trọng trong cơ chế lưu trữ bền vững.

Spring Modulith giúp tổ chức việc phát, theo dõi và phục hồi application event theo ranh giới module. Broker cung cấp cơ chế lưu và phân phối message, còn consumer quyết định tốc độ xử lý thực tế. Khi các tầng phối hợp bằng giới hạn rõ ràng, retry có kiểm soát, idempotency và quan sát backlog, hệ thống có thể hấp thụ đột biến tải mà vẫn giữ được độ tin cậy của giao sự kiện.

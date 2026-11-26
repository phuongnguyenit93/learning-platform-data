# Thông lượng event

## Mục tiêu

Một ứng dụng Spring Modulith có thể phát nhiều application event trong một transaction và có nhiều module cùng lắng nghe. Khi lưu lượng tăng, thời gian xử lý listener, executor, database, Event Publication Registry và broker có thể trở thành nút thắt. Nếu chỉ tăng số thread mà không đo toàn bộ luồng, hệ thống có thể tạo thêm contention, backlog và retry.

**Thông lượng event (event throughput)** là số event được xử lý hoàn tất trong một đơn vị thời gian. Muốn tăng thông lượng bền vững, cần xác định giới hạn của từng thành phần, kiểm soát mức song song và bảo đảm hệ thống không nhận tải nhanh hơn khả năng xử lý trong thời gian dài.

Sau bài học, bạn có thể:

- Phân biệt throughput, latency, arrival rate và backlog.
- Đo thông lượng end-to-end và tìm bottleneck trong luồng application event.
- Điều chỉnh executor, concurrency, transaction và database phù hợp.
- Tối ưu payload, batching và partitioning khi externalize event.
- Áp dụng backpressure, giới hạn retry và mở rộng theo tải.
- Thiết kế load test, capacity plan và cảnh báo vận hành.

## 1. Thông lượng khác độ trễ

Thông lượng và độ trễ liên quan nhưng không phải cùng một chỉ số:

- **Arrival rate:** số event đến trong một giây, thường ký hiệu là \(\lambda\).
- **Throughput:** số event hoàn tất thành công trong một giây.
- **Latency:** thời gian từ một mốc bắt đầu tới khi event hoàn tất.
- **Backlog:** số event đang chờ xử lý hoặc chưa được xác nhận hoàn tất.
- **Error rate:** tỷ lệ event lỗi, bị retry hoặc bị đưa vào dead-letter/quarantine.

Một hệ thống có thể đạt throughput cao nhưng latency vẫn lớn nếu xử lý theo batch. Ngược lại, latency thấp ở tải nhỏ không chứng minh hệ thống chịu được tải cao. Cần đo cả throughput và latency theo percentile như p50, p95, p99.

Thông lượng hoàn tất trong một cửa sổ đo:

\[
  Throughput = \frac{Số\ event\ hoàn\ tất\ thành\ công}{Thời\ gian\ đo}
\]

Ví dụ, nếu 120.000 event hoàn tất trong 60 giây thì throughput trung bình là 2.000 event/giây. Cần ghi rõ mẫu số là event được nhận, được dispatch hay hoàn tất nghiệp vụ. Các mốc này không thể thay thế cho nhau.

### Arrival rate và khả năng xử lý

Nếu arrival rate thấp hơn khả năng xử lý trong thời gian đủ dài, backlog có thể ổn định. Nếu arrival rate liên tục cao hơn khả năng xử lý, backlog sẽ tăng cho tới khi queue đầy, bộ nhớ cạn hoặc hệ thống bắt đầu từ chối tải.

Ví dụ:

| Arrival rate | Khả năng xử lý | Xu hướng |
| ---: | ---: | --- |
| 500 event/s | 800 event/s | Có dư địa xử lý burst và backlog giảm. |
| 800 event/s | 800 event/s | Hoạt động gần giới hạn; ít dư địa cho burst hoặc lỗi. |
| 1.000 event/s | 800 event/s | Backlog tăng khoảng 200 event mỗi giây nếu tải kéo dài. |

Không nên thiết kế production chạy liên tục sát 100% công suất. Cần headroom cho burst, retry, tác vụ nền, deploy và suy giảm hiệu năng của dependency.

### Little's Law và backlog

Trong một hệ thống ổn định, định luật Little mô tả quan hệ giữa số công việc trung bình trong hệ thống, throughput và thời gian lưu lại:

\[
  L = \lambda \times W
\]

Trong đó \(L\) là số event trung bình đang xử lý/chờ, \(\lambda\) là throughput trung bình qua hệ thống và \(W\) là thời gian trung bình một event ở trong hệ thống. Ví dụ, nếu hệ thống xử lý 400 event/s và thời gian lưu lại trung bình là 0,5 giây thì số event trung bình trong hệ thống xấp xỉ 200. Công thức chỉ hữu ích khi các đại lượng được đo trên cùng một ranh giới và hệ thống ở trạng thái ổn định.

## 2. Đo đúng luồng event

Một event trong Spring Modulith có thể đi qua nhiều bước:

1. Module nghiệp vụ publish application event.
2. Event Publication Registry ghi nhận publication tới listener được quản lý.
3. Listener được dispatch, thường bất đồng bộ khi dùng `@ApplicationModuleListener`.
4. Listener thực hiện logic và transaction của module nhận.
5. Registry ghi nhận publication hoàn tất sau khi listener xử lý thành công.
6. Nếu event được externalize, integration adapter tiếp tục serialize và gửi tới broker.
7. Consumer bên ngoài nhận, xử lý và xác nhận message theo semantics của broker.

Mỗi bước có throughput và latency riêng. Đo số lần gọi `publishEvent` chỉ cho biết tốc độ phát event, không cho biết listener đã xử lý xong bao nhiêu event.

### Chọn mốc đo

| Mốc | Chỉ số nên đo | Ý nghĩa |
| --- | --- | --- |
| Publish | Event được phát mỗi giây | Tốc độ module nguồn tạo event. |
| Dispatch | Publication được giao tới listener mỗi giây | Tốc độ hệ thống đưa công việc vào listener. |
| Listener completion | Listener hoàn tất mỗi giây | Throughput xử lý nội bộ thực tế. |
| Externalization | Message được broker xác nhận mỗi giây | Throughput gửi ra hạ tầng ngoài. |
| Consumer completion | Consumer hoàn tất nghiệp vụ mỗi giây | Throughput end-to-end phía nhận. |

Với một event có nhiều listener, một event được publish có thể tạo nhiều publication cần xử lý. Vì vậy, đếm publication/listener và đếm event nghiệp vụ là hai số liệu khác nhau. Hãy gắn `event_type`, `listener_id` và `event_id` để phân tích mà không nhầm fan-out với duplicate.

### Đo latency theo từng đoạn

Ghi nhận timestamp hoặc span cho các mốc publish, listener start, listener finish, broker acknowledgement và consumer completion. Từ đó có thể phân biệt:

- Thời gian chờ dispatch/executor.
- Thời gian xử lý trong listener.
- Thời gian chờ database connection và transaction.
- Thời gian gọi dependency ngoài.
- Thời gian serialize, publish và chờ broker acknowledgement.
- Thời gian message nằm trong broker trước khi consumer nhận.

Không dùng một histogram latency duy nhất để kết luận bottleneck. Một listener có thể chạy nhanh nhưng phải chờ executor lâu; một transaction có thể ngắn nhưng database pool bị cạn.

## 3. Mô hình năng lực xử lý

Với một nhóm worker xử lý độc lập, throughput lý thuyết gần đúng có thể ước lượng từ số worker và thời gian xử lý trung bình:

\[
  Capacity \approx \frac{Concurrency}{Average\ processing\ time}
\]

Nếu có 20 worker và mỗi event cần trung bình 50 ms xử lý, năng lực lý thuyết là khoảng 400 event/s. Đây chỉ là ước lượng ban đầu: thời gian chờ database, lock, network, GC và dependency có thể làm năng lực thực tế thấp hơn.

Trong pipeline nhiều bước, throughput end-to-end bị giới hạn bởi bước có năng lực thấp nhất:

\[
  Throughput_{system} \leq \min(Capacity_1, Capacity_2, \ldots, Capacity_n)
\]

Tăng concurrency ở listener không giúp ích nếu database chỉ cấp được ít connection, broker không đủ partition hoặc API ngoài đã đạt rate limit.

### Fan-out làm tăng tổng công việc

Nếu một event được gửi tới \(N\) listener, số lần xử lý có thể gần bằng \(N\) cho mỗi event nguồn. Ví dụ 1.000 event/s với 4 listener tạo khoảng 4.000 lượt xử lý listener/s. Một listener nặng có thể trở thành bottleneck dù các listener còn lại rất nhanh.

Hãy đo theo từng listener. Chỉ tăng năng lực ở listener đang nghẽn; tránh tăng thread toàn cục khiến các module khác tranh chấp cùng database hoặc CPU.

## 4. Điều chỉnh executor và mức song song

`@ApplicationModuleListener` là lựa chọn thường dùng để xử lý application event bất đồng bộ sau commit. Listener chạy trên executor; số thread, queue và chính sách từ chối ảnh hưởng trực tiếp tới throughput và khả năng chịu burst.

Ví dụ cấu hình một executor có giới hạn:

```java
@Configuration
class EventExecutionConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("module-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

Đây là cấu hình minh họa, không phải thông số phù hợp cho mọi ứng dụng. Cần xác minh executor thực sự được Spring async infrastructure và listener của phiên bản Spring Modulith đang dùng lựa chọn. Nếu ứng dụng có nhiều executor, hãy cấu hình rõ executor cho listener thay vì dựa vào một bean không xác định.

### Chọn số thread theo tài nguyên

Thread nhiều hơn không đồng nghĩa throughput cao hơn. Với listener chủ yếu chờ I/O, concurrency có thể lớn hơn số core CPU; với listener CPU-bound, tăng thread quá số core có thể làm context switching và GC tăng.

Khi chọn concurrency, cân nhắc:

- Số core và thời gian CPU thực tế của handler.
- Kích thước connection pool của database và số connection dành cho request khác.
- Giới hạn concurrency/rate của dependency ngoài.
- Số partition nếu listener đọc từ Kafka.
- Mức độ tranh chấp trên aggregate, row lock hoặc cache.
- Bộ nhớ cần cho mỗi event và queue đang chờ.

Nếu listener dùng database, không nên để số transaction đồng thời vượt xa connection pool khả dụng. Hãy dành connection cho HTTP request, scheduler, health check và tác vụ vận hành. Khi tăng concurrency mà connection wait time tăng mạnh, throughput có thể giảm thay vì tăng.

### Queue phải có giới hạn

Queue không giới hạn có thể che giấu tình trạng quá tải trong một khoảng thời gian, nhưng backlog sẽ tiêu thụ bộ nhớ và làm latency tăng liên tục. Queue hữu hạn giúp hệ thống phát hiện sớm khi producer nhanh hơn consumer.

Chính sách khi queue đầy cần được lựa chọn có chủ đích:

- Block hoặc tạo backpressure nếu tầng gọi có thể chờ an toàn.
- Từ chối công việc để cơ chế bền vững bên ngoài retry sau.
- Tạm dừng nhận message từ broker nếu consumer container hỗ trợ pause/resume.
- Chuyển sang giới hạn tải hoặc circuit breaker khi dependency suy giảm.

Không dùng chính sách âm thầm discard event cho luồng nghiệp vụ cần độ tin cậy. Nếu dùng `CallerRunsPolicy`, hãy hiểu rằng publisher thread có thể phải chạy listener và làm thay đổi latency/transaction boundary của luồng phát. Chính sách này không phù hợp cho mọi loại event.

### Tách executor theo nhóm công việc

Một listener gửi email chậm không nên chiếm hết thread của listener cập nhật trạng thái đơn. Có thể tách executor theo module hoặc nhóm workload khi cần cách ly tài nguyên. Việc tách cần cân nhắc tổng số thread, connection pool và giới hạn CPU; nhiều pool nhỏ không tự động tốt hơn một pool được quản lý hợp lý.

## 5. Giảm chi phí xử lý trong listener

Listener nên làm phần công việc cần thiết để hoàn tất trách nhiệm của module, tránh kéo dài transaction bằng những thao tác không cần thiết.

Các nguyên tắc:

- Chỉ tải aggregate/field cần thiết; tránh N+1 query khi xử lý một event.
- Không giữ database transaction mở trong lúc gọi HTTP hoặc chờ broker.
- Dùng batch khi nhiều event cập nhật cùng loại dữ liệu và semantics cho phép.
- Tránh serialize/deserialize lặp lại cùng payload qua nhiều lớp.
- Giảm payload tới mức consumer cần, tránh tải cả object graph lớn.
- Cache dữ liệu tham chiếu chỉ khi có chính sách invalidation và độ mới phù hợp.
- Tránh lock toàn cục; dùng khóa theo aggregate hoặc optimistic locking khi phù hợp.

### Transaction ngắn và rõ ràng

Transaction listener nên bao quanh các thay đổi database cần commit nguyên tử. Nếu listener cần gọi hệ thống ngoài, có thể ghi command vào outbox cùng transaction rồi để dispatcher gửi sau. Cách này giảm thời gian giữ connection và lock.

Không nên chia transaction chỉ để tăng throughput nếu điều đó làm mất tính nguyên tử nghiệp vụ. Trước khi tối ưu, xác định chính xác dữ liệu nào phải cùng commit và side effect nào có thể chuyển sang bước bất đồng bộ tiếp theo.

### Tránh công việc thừa

Không phải event nào cũng cần mọi listener. Thiết kế event type và subscription rõ ràng, tránh phát một event tổng quát khiến nhiều listener phải lọc và bỏ qua phần lớn message. Nếu listener cần một projection riêng, phát event có ý nghĩa phù hợp và chỉ chứa dữ liệu cần thiết.

## 6. Database và Event Publication Registry

Với listener được Spring Modulith quản lý, Event Publication Registry lưu dấu vết publication và trạng thái hoàn tất. Điều này hỗ trợ khôi phục publication chưa hoàn tất, nhưng cũng tạo thêm thao tác lưu trữ trong database.

Khi throughput cao, database có thể chịu tải từ:

- Ghi publication khi event được phát.
- Cập nhật publication khi listener hoàn tất.
- Truy vấn publication chưa hoàn tất để resubmit/quan sát.
- Ghi dữ liệu nghiệp vụ của listener.
- Ghi inbox/outbox hoặc failure record nếu ứng dụng sử dụng.

Do đó, database có thể trở thành bottleneck trước CPU hoặc executor.

### Theo dõi database

Đo các chỉ số:

- Connection pool active/idle, pending borrowers và connection wait time.
- Transaction duration, commit latency và rollback rate.
- Query latency, lock wait, deadlock và số lần retry.
- CPU, IOPS, buffer/cache hit và dung lượng storage.
- Tốc độ tăng của bảng publication, inbox/outbox và index.
- Số publication chưa hoàn tất và tuổi publication lâu nhất.

Nếu connection pool thường xuyên cạn, tăng thread listener có thể làm hàng đợi connection dài hơn. Hãy xác định query/lock gây nghẽn, tối ưu index và giảm transaction duration trước khi mở rộng concurrency.

### Retention và dọn dữ liệu hoàn tất

Publication đã hoàn tất có thể tích lũy theo thời gian. Cần chính sách retention/cleanup phù hợp với yêu cầu audit, replay và vận hành của ứng dụng. Dọn dữ liệu quá sớm làm mất dấu vết cần điều tra; giữ vô thời hạn làm bảng/index lớn và truy vấn trạng thái chậm.

Không xóa publication chưa hoàn tất chỉ để giảm backlog. Trước khi cleanup, phân biệt rõ trạng thái hoàn tất, lỗi, đang retry và quarantine. Theo dõi thời gian cleanup và ảnh hưởng tới workload production.

### Tách tải đọc và tải ghi

Nếu dashboard hoặc công cụ vận hành truy vấn publication liên tục trên cùng database đang phục vụ transaction nghiệp vụ, có thể tạo thêm tải đọc. Giới hạn polling, dùng query phù hợp và tránh truy vấn toàn bảng. Chỉ tách read replica hoặc datasource khi đã đo được lợi ích và hiểu độ trễ nhất quán.

## 7. Batching và giảm overhead

Batching gom nhiều thao tác thành một nhóm để giảm round trip và overhead cố định. Ví dụ, ghi nhiều dòng projection trong một batch có thể hiệu quả hơn một câu lệnh cho mỗi event.

Batching phù hợp khi:

- Nhiều event có cùng kiểu thao tác database.
- Có thể cập nhật một nhóm bản ghi trong cùng transaction.
- Hợp đồng cho phép xử lý theo nhóm mà không làm sai thứ tự nghiệp vụ.
- Kích thước batch và thời gian chờ có giới hạn.

Batch quá lớn có thể kéo dài transaction, tăng lock, bộ nhớ và thời gian retry khi một phần thất bại. Batch quá nhỏ lại không giảm được overhead. Hãy đo throughput, p95 latency và kích thước transaction theo nhiều giá trị batch.

### Batch ở broker và batch trong ứng dụng

Kafka consumer có thể poll nhiều record một lần; RabbitMQ consumer có thể điều chỉnh prefetch. Batch nhận từ broker không đồng nghĩa mọi record phải nằm trong một transaction nghiệp vụ duy nhất. Cần chọn semantics ack/commit phù hợp để khi một record lỗi, hệ thống không xác nhận nhầm các record chưa xử lý.

Với Spring Modulith application events nội bộ, không nên tự gom các event nghiệp vụ khác nhau chỉ để giảm số lần listener chạy nếu điều đó làm thay đổi semantics. Có thể batch ở tầng persistence/projection sau khi đã giữ nguyên event identity và quy tắc idempotency.

### Coalescing event

Một số event mô tả trạng thái mới nhất, ví dụ `CustomerProfileSnapshotUpdated`, có thể được coalesce nếu consumer chỉ cần trạng thái cuối. Nhưng event mang ý nghĩa nghiệp vụ như `PaymentCaptured`, `OrderCancelled` hoặc `InventoryReserved` không thể tùy tiện gộp/bỏ vì mỗi event đại diện cho một side effect riêng.

Chỉ coalesce khi hợp đồng xác định rõ event là snapshot có thể thay thế, có version tăng đơn điệu và mọi consumer chấp nhận bỏ qua trạng thái trung gian.

## 8. Partitioning và mở rộng consumer khi dùng Kafka

Khi application event được externalize tới Kafka, throughput consumer phụ thuộc số partition, số consumer đang hoạt động và khả năng xử lý mỗi record.

- Một partition chỉ được một consumer trong cùng consumer group xử lý tại một thời điểm.
- Tăng consumer instance vượt số partition không làm tăng song song đọc của group đó.
- Key quyết định partition theo partitioner; key phân bố lệch có thể tạo hot partition.
- Thứ tự được bảo đảm trong phạm vi partition, không phải toàn topic.
- Tăng số partition có thể thay đổi cách key ánh xạ và ảnh hưởng thứ tự tương lai.

Nếu cần giữ thứ tự event của cùng aggregate, thường dùng aggregate ID làm key. Nhưng nếu một aggregate tạo phần lớn traffic, key đó có thể trở thành hot partition. Cần cân bằng giữa thứ tự nghiệp vụ và phân bố tải; không chia nhỏ key nếu điều đó làm mất thứ tự bắt buộc.

### Consumer concurrency

Số consumer thread/instance nên phù hợp với số partition và năng lực xử lý downstream. Nếu database chỉ chịu được 10 transaction đồng thời, chạy 50 consumer thread có thể chỉ tạo 40 thread chờ connection. Nếu có 30 partition nhưng chỉ chạy 3 consumer, có thể chưa tận dụng hết khả năng song song.

Theo dõi consumer lag theo partition, record processing time, rebalance frequency, poll interval và lỗi commit offset. Lag tăng liên tục cho biết tốc độ xử lý không theo kịp tốc độ ghi, nhưng cần đối chiếu với arrival rate và thời gian xử lý để tìm nguyên nhân.

### Externalization và producer throughput

Producer throughput chịu ảnh hưởng bởi kích thước message, compression, batch size, linger time, acknowledgement level và số partition. Tăng batch/linger có thể tăng hiệu quả mạng nhưng làm tăng latency. Acknowledgement mạnh hơn có thể tăng độ tin cậy nhưng thêm thời gian chờ. Chọn cấu hình theo SLO và semantics dữ liệu, không tối ưu throughput bằng cách giảm bảo đảm durability mà không đánh giá rủi ro.

## 9. Backpressure và bảo vệ hệ thống khi quá tải

Backpressure giúp tốc độ nhận công việc phản ánh khả năng xử lý thực tế. Nếu producer liên tục phát nhanh hơn consumer, chỉ tăng queue sẽ trì hoãn thời điểm quá tải chứ không giải quyết nguyên nhân.

Các cơ chế có thể kết hợp:

- Queue/executor có capacity hữu hạn.
- Giới hạn concurrency và rate ở listener hoặc dependency.
- Pause/resume broker consumer khi downstream quá tải.
- Retry với exponential backoff và jitter.
- Circuit breaker để tránh gọi dependency đang lỗi liên tục.
- Từ chối sớm command mới khi hệ thống không còn khả năng nhận thêm công việc.
- Tách workload quan trọng và workload nền để một nhóm không chiếm hết tài nguyên.

### Ưu tiên và phân loại tải

Nếu event thanh toán và event gửi email dùng chung một executor, email chậm có thể làm thanh toán bị trễ. Có thể tách workload theo mức độ quan trọng hoặc module, nhưng phải giới hạn tổng tài nguyên và tránh starvation của nhóm ưu tiên thấp.

Không dùng priority queue nếu không có chính sách đảm bảo công bằng. Một nhóm ưu tiên cao có lưu lượng liên tục có thể khiến nhóm khác không bao giờ được xử lý.

### Retry có thể khuếch đại tải

Khi dependency chậm, retry làm tăng số request trong lúc hệ thống vốn đã quá tải. Dùng backoff, jitter, retry budget và circuit breaker. Không retry lỗi dữ liệu xác định hoặc lỗi authorization không thể tự phục hồi.

Khi hết retry, chuyển event sang quarantine/DLQ theo policy và giữ khả năng xử lý lại. Không để retry vô hạn chiếm worker và connection pool.

## 10. Payload, serialization và garbage collection

Payload lớn làm tăng chi phí serialize/deserialize, network transfer, broker storage, database I/O và garbage collection. Event chỉ nên chứa dữ liệu consumer cần để thực hiện công việc hoặc cập nhật projection.

Các cách giảm chi phí:

- Tránh gửi toàn bộ aggregate hoặc object graph có nhiều quan hệ lazy.
- Dùng DTO/event contract rõ ràng và kích thước giới hạn.
- Chọn JSON, Avro hoặc Protobuf theo yêu cầu; đo CPU và kích thước thực tế.
- Dùng compression khi message đủ lớn và CPU còn dư địa.
- Tránh encode/decode cùng payload nhiều lần.
- Không nhúng file lớn; dùng object storage reference có quyền truy cập và retention rõ ràng.
- Tránh tạo quá nhiều object tạm trong vòng lặp xử lý nóng.

Compression giảm bytes truyền và lưu trữ nhưng tiêu tốn CPU. Nếu bottleneck là CPU serialization, compression có thể làm throughput thấp hơn. Hãy đo cả CPU, bytes/s, message size và latency.

## 11. Mở rộng ngang và giới hạn tài nguyên

Có thể tăng số instance để mở rộng listener hoặc consumer, nhưng hiệu quả phụ thuộc vào cách phân phối công việc và tài nguyên dùng chung.

Trước khi scale out, kiểm tra:

- Các listener có thể chạy song song mà không vi phạm thứ tự aggregate không?
- Database, broker và dependency có đủ capacity cho số instance mới không?
- Consumer group có đủ partition để phân phối tới instance mới không?
- Có hot key, lock contention hoặc rate limit theo tenant không?
- Event Publication Registry và database có chịu được số transaction tăng thêm không?
- Mỗi instance có executor/queue bounded và shutdown behavior phù hợp không?

Horizontal scaling có thể làm tăng cạnh tranh trên database. Nếu mọi instance cùng cập nhật một row hoặc cùng gọi một API giới hạn 100 request/s, throughput tổng không tăng tuyến tính. Cần đo saturation ở dependency và dùng partitioning/ownership hoặc rate limiter phù hợp.

## 12. Kiểm thử tải và capacity planning

Load test nên mô phỏng phân bố event và dependency gần production. Một bài test chỉ phát các event rỗng vào listener no-op không phản ánh throughput thực tế.

### Thiết kế kịch bản

1. **Baseline:** tải thấp để đo latency và tài nguyên khi hệ thống khỏe.
2. **Ramp-up:** tăng arrival rate từng bước để tìm điểm bắt đầu tăng backlog/latency.
3. **Sustained load:** giữ tải mục tiêu đủ lâu để quan sát connection pool, GC, database và backlog.
4. **Spike:** tạo burst ngắn để xem queue/backpressure có hấp thụ được không.
5. **Dependency degradation:** làm chậm hoặc ngắt dependency để đánh giá retry, circuit breaker và phục hồi.
6. **Recovery:** trả dependency về bình thường và đo thời gian backlog được xử lý hết.
7. **Soak:** chạy lâu để phát hiện memory leak, tăng bảng registry, index bloat hoặc suy giảm theo thời gian.

### Chỉ số cần ghi

| Nhóm | Chỉ số |
| --- | --- |
| Event flow | Arrival rate, completion throughput, backlog, event age. |
| Latency | p50/p95/p99 publish-to-completion và thời gian từng listener. |
| Executor | Active threads, queue depth, rejected tasks, task duration. |
| Database | Pool utilization, wait time, transaction/query latency, lock và deadlock. |
| Broker | Producer rate, consumer lag, partition skew, rebalance, request latency. |
| Runtime | CPU, heap, allocation rate, GC pause, thread count. |
| Reliability | Error rate, retry count, duplicate, incomplete publication, DLQ/quarantine. |

### Xác định capacity mục tiêu

Capacity không chỉ là throughput cao nhất đo được trong vài giây. Hãy xác định throughput duy trì được trong khi p95/p99 latency, error rate và backlog vẫn nằm trong SLO. Giữ headroom cho burst và sự cố một phần.

Một kế hoạch đơn giản có thể đặt:

- Arrival rate bình thường.
- Peak arrival rate và thời lượng peak.
- Throughput tối thiểu cần duy trì.
- Giới hạn latency cho từng loại event.
- Thời gian tối đa cho phép backlog tồn tại.
- Thời gian phục hồi backlog sau khi dependency trở lại.

Khi ước lượng, dùng event size và fan-out thực tế. Nếu một event có 3 listener, hãy tính cả 3 lượt xử lý và chi phí registry tương ứng, thay vì chỉ tính số event nguồn.

## 13. Quan sát và cảnh báo thông lượng

Dashboard hiệu năng nên phân biệt tải đến, tải hoàn tất và công việc tồn đọng. Các metric hữu ích:

- `events_published_total` theo event type/module.
- `event_listener_completed_total` và `event_listener_failed_total` theo listener.
- Histogram thời gian listener và publish-to-completion.
- Executor active thread, queue depth và rejected task.
- Số publication incomplete và tuổi publication lâu nhất.
- Database connection wait, transaction latency và lock wait.
- Broker producer throughput, consumer lag và partition skew.
- Retry rate, DLQ/quarantine count và event age.

Tên metric trên là gợi ý đặt tên, không phải metric mặc định được Spring Modulith tự cung cấp. Có thể instrument bằng Micrometer/observability stack của ứng dụng.

Tránh dùng `event_id`, `aggregate_id` hoặc customer ID làm label metric vì cardinality có thể tăng rất lớn. Các định danh cụ thể phù hợp hơn trong log/trace có kiểm soát. Metric nên dùng dimension giới hạn như event type, listener, module và outcome.

### Đặt cảnh báo theo triệu chứng

- Backlog tăng liên tục trong khi completion throughput thấp hơn arrival rate.
- Tuổi publication chưa hoàn tất vượt SLO.
- Executor queue gần đầy hoặc task bị từ chối.
- Database pool wait time và transaction latency tăng.
- Consumer lag tăng ở một số partition cụ thể.
- Retry/DLQ tăng đột biến hoặc dependency liên tục mở circuit breaker.
- p95/p99 latency tăng dù throughput chưa giảm.

Một metric đơn lẻ hiếm khi đủ để xác định nguyên nhân. Ví dụ consumer lag tăng có thể do partition nóng, database chậm hoặc event payload lớn. Dashboard cần liên kết các metric theo cùng khoảng thời gian.

## 14. Những lỗi tối ưu thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ tăng thread pool | Database/dependency bị quá tải, contention tăng. | Đo bottleneck và giới hạn concurrency theo tài nguyên. |
| Dùng queue không giới hạn | Bộ nhớ tăng và latency kéo dài khi consumer không theo kịp. | Dùng bounded queue và backpressure. |
| Đo số event publish như throughput hoàn tất | Đánh giá sai năng lực xử lý listener. | Đo completion theo từng listener và end-to-end. |
| Chạy sát 100% capacity | Không có headroom cho burst, retry hoặc deploy. | Giữ dự phòng và xác định peak capacity. |
| Giữ transaction trong lúc gọi mạng | Connection/lock bị giữ lâu, throughput giảm. | Tách side effect qua outbox hoặc bước bất đồng bộ. |
| Batch quá lớn | Transaction dài, lock và memory tăng. | Đo batch size và giới hạn thời gian/khối lượng. |
| Tăng consumer vượt số partition | Không tăng khả năng đọc song song của consumer group. | Điều chỉnh partition/concurrency có kiểm soát. |
| Retry không giới hạn | Khuếch đại tải khi dependency lỗi. | Backoff, jitter, retry budget và DLQ. |
| Coalesce event nghiệp vụ | Mất side effect hoặc lịch sử quan trọng. | Chỉ coalesce snapshot có semantics thay thế rõ ràng. |
| Bỏ qua chi phí Event Publication Registry | Database trở thành bottleneck khó giải thích. | Đo publication write/completion/query và cleanup. |

## 15. Quy trình tối ưu thông lượng

Khi cải thiện throughput cho application events trong Spring Modulith:

1. Định nghĩa rõ event nào được đếm và mốc nào là hoàn tất.
2. Đo arrival rate, completion throughput, p95/p99 latency và backlog theo listener.
3. Dùng trace/metric để xác định bottleneck: executor, CPU, database, registry, broker hay dependency.
4. Ước lượng capacity và headroom dựa trên event size, fan-out và thời gian xử lý thực tế.
5. Điều chỉnh executor, queue capacity và concurrency trong giới hạn tài nguyên.
6. Rút ngắn transaction, tối ưu query/index và giảm payload/công việc thừa.
7. Áp dụng batch, partitioning hoặc scale out khi semantics và dependency cho phép.
8. Thiết lập backpressure, retry budget và circuit breaker để kiểm soát quá tải.
9. Chạy load, spike, soak và recovery test bằng workload gần production.
10. Theo dõi SLO, backlog age, publication chưa hoàn tất và chi phí vận hành sau mỗi lần thay đổi.

Thông lượng bền vững đến từ việc cân bằng tốc độ phát, mức song song và năng lực của từng dependency. Khi đo đúng mốc hoàn tất, giới hạn queue/concurrency, tối ưu transaction và có backpressure, ứng dụng Spring Modulith có thể xử lý nhiều event hơn mà vẫn giữ được độ trễ, tính đúng đắn và khả năng phục hồi.

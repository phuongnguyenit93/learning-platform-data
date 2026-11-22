# AsyncAcks và commit lệch thứ tự

Trong Spring Kafka, listener có thể xử lý record bất đồng bộ bằng cách chuyển công việc sang executor hoặc một dịch vụ xử lý nền. Khi nhiều record được xử lý đồng thời, thứ tự hoàn tất thường khác thứ tự Kafka giao record. Ví dụ, consumer nhận các offset 100, 101 và 102 nhưng công việc của offset 102 hoàn tất trước offset 100. Nếu ứng dụng commit offset 103 ngay khi record 102 hoàn tất, Kafka có thể bỏ qua 100 và 101 sau khi consumer gặp sự cố.

`asyncAcks` là cơ chế của Spring Kafka cho phép acknowledgement của các record được trả về trong một lần poll đến theo thứ tự bất kỳ. Container trì hoãn commit cho đến khi nhận đủ acknowledgement của các record thuộc poll đó, rồi mới commit offset theo thứ tự an toàn. Trong thời gian còn acknowledgement bị thiếu, consumer được pause để không nhận thêm record mới từ các partition đang quản lý.

Cơ chế này hỗ trợ xử lý bất đồng bộ nhưng không tự tạo ra exactly-once, không tự chạy công việc song song và không thay thế idempotency. Ứng dụng vẫn phải ack sau khi tác động nghiệp vụ đã hoàn tất bền vững, quản lý lỗi của worker và chấp nhận khả năng record được giao lại sau sự cố.

## 1. Vì sao commit lệch thứ tự có thể làm mất record?

Kafka lưu committed offset cho từng partition và consumer group. Offset đã commit biểu thị vị trí tiếp theo mà consumer group sẽ đọc. Khi record có offset 102 được xử lý xong, commit offset 103 có nghĩa là consumer group đã xác nhận mọi record trước vị trí 103 trong partition đó.

Giả sử một poll trả về ba record của cùng partition:

| Offset | Thời gian xử lý | Thứ tự hoàn tất |
|---:|---:|---:|
| 100 | 900 ms | 3 |
| 101 | 300 ms | 2 |
| 102 | 100 ms | 1 |

Nếu mỗi worker tự commit offset khi hoàn tất, record 102 có thể khiến ứng dụng commit offset 103 trước khi 100 và 101 xong. Nếu process dừng ngay sau đó, lần đọc tiếp theo bắt đầu từ 103; hai record chưa xử lý có thể bị bỏ qua.

~~~text
Kafka poll:       100       101       102
                   |         |         |
Worker:          chậm      vừa       nhanh
                   |         |         |
Hoàn tất:          3         2         1
                   |         |         |
Commit sai:                           103
                   |
          Process gặp sự cố
                   |
          100 và 101 bị bỏ qua
~~~

Vấn đề không phải Kafka tự đảo thứ tự record. Kafka vẫn giao record theo thứ tự offset trong một partition. Sự lệch thứ tự xuất hiện ở tầng ứng dụng khi nhiều công việc chạy đồng thời và hoàn tất theo thời gian khác nhau.

### 1.1. Commit offset là commit vị trí tiếp theo

Khi record có offset 100 được xác nhận thành công, offset được commit thường là 101. Khi record 102 được xác nhận, offset commit là 103. Vì commit offset biểu thị vị trí tiếp theo cần đọc, commit một offset cao hơn cũng xác nhận các offset thấp hơn trong cùng partition.

Offset của các partition độc lập với nhau. Commit offset 103 của partition 0 không có nghĩa record của partition 1 cũng đã hoàn tất. Tuy vậy, trong một poll có thể có record từ nhiều partition; container cần quản lý các acknowledgement và offset theo từng partition.

### 1.2. Vì sao xử lý song song lại tạo ra tình huống này?

Một listener có thể gửi mỗi record vào thread pool:

~~~java
@KafkaListener(topics = "orders", groupId = "billing")
public void listen(OrderCreated event) {
    executor.execute(() -> billingService.process(event));
}
~~~

Phương thức listener trả về ngay sau khi enqueue công việc. Nếu container dùng acknowledgement tự động theo kiểu record, container có thể xem listener đã hoàn tất trong khi công việc nghiệp vụ vẫn đang chạy. Nếu tự commit theo callback hoàn tất mà không giữ thứ tự offset, một record nhanh có thể làm offset tiến qua record chậm hơn.

Không được xem việc đưa công việc vào executor là xử lý nghiệp vụ thành công. Thời điểm ack phải gắn với kết quả bền vững của công việc, không chỉ gắn với việc thread pool đã nhận task.

## 2. AsyncAcks giải quyết vấn đề như thế nào?

`asyncAcks` được Spring Kafka bổ sung từ dòng phiên bản 2.8. Khi bật, ứng dụng có thể acknowledge các record thuộc cùng một poll theo thứ tự hoàn tất bất kỳ. Container theo dõi các acknowledgement còn thiếu và trì hoãn commit cho đến khi đã nhận đủ acknowledgement cần thiết của poll trước.

Ví dụ với offset 100, 101 và 102:

1. Listener nhận record và gửi ba công việc đến worker pool.
2. Worker xử lý offset 102 xong trước và gọi acknowledge.
3. Worker xử lý offset 101 xong và acknowledge.
4. Container vẫn chưa commit vượt qua offset 100 vì acknowledgement của record này còn thiếu.
5. Offset 100 hoàn tất và được acknowledge.
6. Khi đủ acknowledgement cho poll, container có thể commit offset an toàn đến vị trí tiếp theo sau record cuối cùng của partition.

~~~text
Poll trả về:       100       101       102
                    |         |         |
Hoàn tất:            3         2         1
                    |         |         |
Ack đến:            100?      101       102
                    |         |         |
Container giữ các ack đến khi đủ
                    |
Ack offset 100 đến
                    |
Commit offset tiếp theo an toàn: 103
~~~

Điểm quan trọng là container quản lý thứ tự commit, dù acknowledgement đến lệch thứ tự. Ứng dụng không cần tự tính offset lớn nhất rồi commit thủ công cho từng callback.

### 2.1. Consumer được pause trong khi chờ acknowledgement

Khi vẫn còn acknowledgement bị thiếu từ poll trước, container pause consumer để không tiếp tục đưa thêm record mới vào listener. Điều này ngăn một backlog công việc bất đồng bộ không giới hạn và giữ ranh giới rõ giữa các poll đang chờ hoàn tất.

Consumer vẫn cần tiếp tục vòng đời poll/heartbeat theo cách container quản lý để duy trì membership trong group. Pause ở đây có nghĩa tạm dừng nhận record mới để xử lý, không phải đóng consumer hoặc rời group.

Hệ quả vận hành:

- Một worker chậm nhất trong poll có thể giữ consumer ở trạng thái pause lâu hơn các worker khác.
- Tăng số worker không nhất thiết làm tăng throughput nếu một record chậm giữ cả poll batch chưa thể hoàn tất.
- Kích thước poll batch ảnh hưởng số công việc có thể chạy đồng thời và thời gian consumer bị pause.
- Cần theo dõi tuổi của acknowledgement còn thiếu, thời gian xử lý worker và consumer lag.

`asyncAcks` cho phép hoàn tất lệch thứ tự nhưng vẫn duy trì ranh giới commit an toàn. Nó không loại bỏ chi phí của một công việc chậm.

## 3. Điều kiện sử dụng AsyncAcks

Để dùng cơ chế này, listener cần sử dụng manual acknowledgement và container cần bật asynchronous acknowledgements. Ví dụ cấu hình trên listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
orderListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.MANUAL);
    factory.getContainerProperties().setAsyncAcks(true);

    return factory;
}
~~~

Listener dùng factory này:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "billing",
        containerFactory = "orderListenerFactory")
public void listen(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {
    // Chuyển công việc sang worker và acknowledge khi hoàn tất.
}
~~~

Tên bean, kiểu key/value, serializer và cấu hình consumer phải khớp với ứng dụng thực tế. `setAsyncAcks(true)` là API của các phiên bản Spring Kafka có hỗ trợ tính năng này; cần đối chiếu dependency đang dùng.

### 3.1. Manual acknowledgement

`AckMode.MANUAL` cho phép listener chủ động gọi `acknowledge()` sau khi công việc đã hoàn tất. Khi kết hợp với `asyncAcks`, acknowledgement có thể đến từ worker thread theo thứ tự hoàn tất thực tế.

`AckMode.MANUAL_IMMEDIATE` có hành vi commit ngay nếu acknowledge được gọi trên consumer thread. Nếu acknowledge được gọi từ thread khác, yêu cầu commit được chuyển về xử lý trên consumer thread; không nên giả định nó luôn commit ngay tại thời điểm worker gọi phương thức.

Với công việc bất đồng bộ, cần hiểu thread gọi ack và semantics của ack mode. Không xây dựng logic phụ thuộc vào việc offset đã được broker commit ngay khi callback gọi `acknowledge()`.

### 3.2. Các giới hạn quan trọng

- `asyncAcks` được thiết kế cho record listener; không hỗ trợ batch listener theo semantics của tính năng này.
- Khi bật `asyncAcks`, không sử dụng `nack()`. Cơ chế negative acknowledgement không tương thích với việc quản lý acknowledgement lệch thứ tự.
- Listener cần có manual acknowledgement phù hợp; chỉ bật property mà không gọi ack đúng lúc sẽ làm container chờ acknowledgement còn thiếu.
- Một poll phải có đủ acknowledgement trước khi container có thể tiếp tục nhận record mới theo cơ chế này.
- `asyncAcks` không tự chạy record trên thread pool. Ứng dụng phải tự quản lý executor và vòng đời công việc nếu muốn xử lý song song.

Nếu cần dùng batch listener hoặc logic nack để retry một phần batch, hãy chọn một thiết kế xử lý khác phù hợp với listener type và error handling, thay vì bật `asyncAcks`.

## 4. Ví dụ xử lý bất đồng bộ với Acknowledgment

Một cách dùng phổ biến là nhận record trên consumer thread, gửi công việc đến executor và acknowledge khi dịch vụ nghiệp vụ hoàn tất:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "billing",
        containerFactory = "orderListenerFactory")
public void listen(
        ConsumerRecord<String, OrderCreated> record,
        Acknowledgment acknowledgment) {

    CompletableFuture
            .runAsync(
                    () -> billingService.processIdempotently(record.value()),
                    workerExecutor)
            .whenComplete((ignored, error) -> {
                if (error == null) {
                    acknowledgment.acknowledge();
                }
                else {
                    asyncFailureHandler.handle(record, error, acknowledgment);
                }
            });
}
~~~

Đây là cấu trúc minh họa. `workerExecutor` cần là executor có giới hạn thread và queue; `billingService` phải hoàn tất thay đổi nghiệp vụ bền vững trước khi future thành công. `asyncFailureHandler` là thành phần do ứng dụng thiết kế để xử lý lỗi bất đồng bộ.

Không nên dùng executor không giới hạn. Nếu tốc độ nhận task cao hơn tốc độ xử lý, queue có thể tăng vô hạn, tiêu thụ heap và làm thời gian hoàn tất kéo dài. Với `asyncAcks`, consumer pause khi chờ acknowledgement của poll, nhưng một poll vẫn có thể chứa nhiều task đồng thời.

### 4.1. Acknowledge sau khi công việc bền vững

Ví dụ, nếu worker cập nhật database, thứ tự nên là:

1. Bắt đầu database transaction.
2. Kiểm tra hoặc ghi event id vào inbox table.
3. Thực hiện cập nhật nghiệp vụ nếu event chưa được xử lý.
4. Commit database transaction.
5. Chỉ sau khi commit thành công mới gọi `acknowledge()`.

Nếu database commit thành công nhưng ứng dụng chết trước khi offset được commit, Kafka có thể giao lại record. Inbox/idempotency key ngăn cập nhật nghiệp vụ bị lặp.

Không ack ngay sau khi gọi `CompletableFuture.runAsync()`. Thao tác đó chỉ xác nhận task đã được đưa vào executor; task có thể thất bại, process có thể dừng hoặc executor có thể từ chối task.

### 4.2. Quản lý task rejection

Nếu executor từ chối task do queue đầy hoặc đang shutdown, listener không được coi record là đã xử lý. Hãy xử lý rejection ngay trong đường nhận record và đưa record vào cơ chế retry/recovery có kiểm soát. Không ack record chỉ để giải phóng consumer.

Với executor có bounded queue, cần chọn chính sách rejection có thể quan sát. Chính sách âm thầm bỏ task sẽ làm mất công việc trong khi Kafka offset có thể đã được xác nhận nếu ứng dụng ack sai thời điểm.

## 5. Xử lý lỗi trong worker bất đồng bộ

Một điểm khác biệt quan trọng là exception xảy ra trong worker thread sau khi listener đã trả về không tự động đi qua error handler của listener container. Container chỉ quan sát được exception được ném trong luồng listener/container mà nó quản lý.

Do đó, nếu worker thất bại:

- Không acknowledge record như thể công việc đã thành công.
- Không giả định error handler của listener container sẽ tự nhận exception từ thread pool.
- Gửi lỗi đến một failure handler có giới hạn retry và có thể quan sát.
- Chỉ acknowledge sau khi xử lý thành công hoặc sau khi record đã được chuyển bền vững vào luồng recovery như DLT.
- Nếu cả xử lý nghiệp vụ lẫn recovery đều thất bại, cần báo động và dừng/khôi phục consumer theo chính sách rõ ràng; không để acknowledgement bị treo vô thời hạn.

### 5.1. Recovery thành công rồi mới acknowledge

Một hướng thiết kế là failure handler thử lại lỗi tạm thời theo số lần giới hạn. Nếu không thể xử lý, nó publish record sang DLT và chỉ acknowledge sau khi kết quả publish DLT được xác nhận thành công.

~~~text
Worker xử lý record
       |
       +---- Thành công ----> Ack
       |
       +---- Thất bại
                 |
                 v
          Retry có giới hạn
                 |
          +------+------+
          |             |
       Thành công     Hết retry
          |             |
          v             v
         Ack       Publish DLT
                        |
                 +------+------+
                 |             |
              Thành công     Thất bại
                 |             |
                 v             v
                Ack      Không ack; alert
                         và recovery theo runbook
~~~

Đây là luồng logic, không phải cấu hình tự động do `asyncAcks` cung cấp. Việc publish DLT phải chờ xác nhận phù hợp; nếu DLT broker không nhận record, không được ack nguồn và làm mất khả năng phát lại.

### 5.2. Acknowledgement bị thiếu có thể giữ consumer ở trạng thái pause

Nếu worker thất bại và failure handler không bao giờ hoàn tất hoặc không ack sau recovery, container tiếp tục chờ acknowledgement còn thiếu. Vì consumer bị pause cho đến khi poll trước được xác nhận đầy đủ, các record mới có thể ngừng được giao cho listener.

Đây là hành vi bảo vệ thứ tự commit, nhưng nếu không có timeout và alert, nó có thể trông giống consumer bị treo. Hãy ghi nhận event id, topic, partition, offset, thời điểm bắt đầu xử lý, số lần retry và trạng thái recovery.

Không tự ý ack một record chỉ để mở khóa consumer. Trước khi ack, phải có bằng chứng tác động nghiệp vụ đã hoàn tất hoặc record đã được lưu an toàn vào recovery channel.

## 6. Ví dụ offset đến lệch thứ tự trong một poll

Giả sử một poll trả về:

| Partition | Offset | Công việc |
|---|---:|---|
| orders-0 | 40 | Tạo invoice, mất 800 ms |
| orders-0 | 41 | Cập nhật trạng thái, mất 200 ms |
| orders-0 | 42 | Ghi audit, mất 100 ms |
| orders-1 | 15 | Đồng bộ dữ liệu, mất 300 ms |

Thứ tự hoàn tất có thể là offset 42, offset 41, partition 1 offset 15, rồi offset 40. Container cần quản lý acknowledgement riêng theo partition và không được commit vượt qua offset còn thiếu trong partition 0.

Khi offset 40 cuối cùng được acknowledge và mọi record của poll đã được xác nhận, offset commit có thể tiến đến 43 cho partition 0 và 16 cho partition 1. Không có một thứ tự toàn cục giữa offset 43 và 16 vì chúng thuộc hai partition khác nhau.

Điều này cho thấy:

- Kafka bảo đảm thứ tự record trong từng partition, không bảo đảm thứ tự xử lý nghiệp vụ giữa các partition.
- AsyncAcks bảo vệ thứ tự commit offset, không ép worker hoàn tất theo thứ tự nhận.
- Nếu nghiệp vụ yêu cầu thứ tự cho cùng aggregate, các event của aggregate đó cần được thiết kế cùng key/partition và không được thực hiện side effect song song theo cách phá vỡ thứ tự nghiệp vụ.

## 7. AsyncAcks và giới hạn throughput

`asyncAcks` cho phép các record trong một poll được xử lý đồng thời, nhưng container chờ đủ acknowledgement trước khi tiếp tục nhận record ở poll tiếp theo. Vì vậy, thông lượng phụ thuộc vào:

- Số record được trả về trong mỗi poll.
- Số worker thực sự chạy song song.
- Thời gian xử lý của record chậm nhất trong poll.
- Khả năng của database và dịch vụ downstream.
- Số consumer member và số partition được gán.

Một poll có 100 record và executor có 20 thread có thể xử lý tối đa khoảng 20 task cùng lúc, tùy workload. Tuy nhiên, nếu một task kéo dài 30 giây, consumer vẫn phải chờ acknowledgement đó trước khi tiến sang poll mới. Tăng `max.poll.records` có thể tăng số task trong poll và mức song song tiềm năng, nhưng cũng tăng lượng công việc đang chờ và thời gian bị pause nếu có record chậm.

### 7.1. Chọn max.poll.records

`max.poll.records` giới hạn số record trả về trong một lần poll. Khi dùng AsyncAcks, hãy xem nó như giới hạn số acknowledgement cần hoàn tất trước khi consumer có thể tiếp tục.

Batch lớn:

- Có thể tận dụng executor và giảm overhead poll.
- Có thể tạo nhiều task đồng thời.
- Có thể làm một record chậm giữ cả poll lâu hơn.
- Có thể tăng số record bị giao lại sau crash trước commit.

Batch nhỏ:

- Giới hạn lượng task đồng thời và phạm vi công việc đang chờ.
- Có thể giúp consumer tiếp tục poll thường xuyên hơn khi task hoàn tất nhanh.
- Có thể giảm throughput nếu overhead poll và commit chiếm tỷ lệ lớn.

Chọn giá trị dựa trên phân bố thời gian xử lý p95/p99, capacity của worker pool và downstream. Không chỉ dựa trên thời gian trung bình.

### 7.2. Bounded executor và backpressure

Executor nên có giới hạn thread và queue. Khi queue gần đầy, hệ thống cần tạo backpressure hoặc báo lỗi có kiểm soát thay vì tiếp tục nhận vô hạn.

Các lựa chọn:

- Giảm `max.poll.records` để giảm số task được phát ra trong một poll.
- Giảm số worker nếu downstream đang quá tải.
- Tăng năng lực downstream khi đây là bottleneck thực sự.
- Giới hạn thời gian xử lý và số lần retry.
- Dùng nhiều consumer/partition hơn khi cần song song hóa và dữ liệu có thể phân vùng an toàn.

Không dùng `CallerRunsPolicy` một cách thiếu cân nhắc nếu nó khiến consumer thread chạy công việc dài ngay trong callback và làm thay đổi thời gian poll. Mọi rejection policy cần được kiểm tra trong bối cảnh thread nào sẽ thực thi task.

## 8. AsyncAcks không phải exactly-once

AsyncAcks bảo vệ thứ tự commit offset của các record thuộc poll. Nó không tạo transaction nguyên tử giữa Kafka và database, cũng không ngăn một record được giao lại sau crash.

Các kịch bản có thể xảy ra:

| Thời điểm sự cố | Hệ quả |
|---|---|
| Worker chưa xử lý xong, chưa ack | Record có thể được giao lại |
| Database đã commit, worker chưa ack | Record có thể được giao lại; nghiệp vụ phải idempotent |
| Worker ack, container chưa commit offset | Record có thể được giao lại nếu process/broker gặp lỗi trước commit |
| Tất cả ack đã đến và offset đã commit | Consumer group tiếp tục từ offset tiếp theo đã commit |
| Worker ack trước khi database commit | Có nguy cơ mất tác động nghiệp vụ nếu database thất bại sau đó |

Với consumer cập nhật database, hãy dùng inbox table hoặc unique event id trong cùng transaction với thay đổi nghiệp vụ. Với thao tác gọi API ngoài, dùng idempotency key nếu API đích hỗ trợ. Nếu không, cần trạng thái xử lý và đối soát để xử lý kết quả timeout không rõ ràng.

## 9. AsyncAcks và thứ tự nghiệp vụ

Kafka giữ thứ tự record trong một partition, nhưng khi ứng dụng xử lý bất đồng bộ, tác động nghiệp vụ có thể hoàn tất lệch thứ tự.

Ví dụ một partition có:

1. `OrderCreated`
2. `OrderPaid`
3. `OrderShipped`

Nếu ba worker xử lý đồng thời, `OrderShipped` có thể hoàn tất trước `OrderCreated`. AsyncAcks chỉ bảo vệ việc commit offset; nó không tự bảo đảm side effect của các event hoàn tất theo thứ tự.

Nếu nghiệp vụ yêu cầu tuần tự theo aggregate:

- Xử lý tuần tự các record cùng key trong một partition.
- Hoặc phân phối công việc theo key vào các lane tuần tự.
- Hoặc kiểm tra version/sequence của aggregate trong database trước khi áp dụng thay đổi.
- Giữ idempotency và từ chối hoặc trì hoãn event đến sai thứ tự theo quy tắc nghiệp vụ.

Chỉ chạy song song những event độc lập hoặc những bước có thể chịu được việc hoàn tất lệch thứ tự.

## 10. Observability cho acknowledgement và commit

Khi dùng AsyncAcks, consumer lag đơn lẻ chưa đủ để tìm một acknowledgement bị treo. Nên ghi nhận các mốc:

- Thời điểm record được nhận từ listener.
- Thời điểm task được enqueue và bắt đầu chạy.
- Thời điểm tác động nghiệp vụ commit.
- Thời điểm acknowledgment được gọi.
- Kết quả retry hoặc publish DLT nếu có.
- Topic, partition, offset, event id và consumer group.

Metrics nên có:

| Metric | Ý nghĩa |
|---|---|
| Async task in-flight count | Số task đang xử lý |
| Worker queue depth | Số task đang chờ executor |
| Worker processing duration | Thời gian xử lý của worker |
| Oldest unacknowledged age | Tuổi acknowledgement còn thiếu lâu nhất |
| Acknowledgement completion rate | Tốc độ task hoàn tất và ack |
| Consumer pause duration | Thời gian consumer ở trạng thái pause do chờ ack |
| Consumer lag / oldest record age | Backlog và độ trễ của dữ liệu |
| Retry/recovery/DLT rate | Tình trạng lỗi và phục hồi |
| Commit latency/failure | Kết quả commit offset |

Không đưa event id, offset hoặc message key làm metric tag có cardinality cao. Có thể ghi chúng trong log có cấu trúc để điều tra một record cụ thể.

### 10.1. Alert cần thiết

Thiết lập alert khi:

- Có acknowledgement chưa hoàn tất vượt quá thời hạn xử lý dự kiến.
- Consumer pause kéo dài bất thường.
- Worker queue depth tăng liên tục.
- Processing rate thấp hơn incoming rate và lag tăng.
- Retry hoặc DLT tăng đột biến.
- Commit offset thất bại.
- Worker exception tăng sau một lần deploy.

Ngưỡng cần dựa trên SLA và phân bố thời gian xử lý thực tế. Một task lâu 5 giây có thể bình thường với một loại công việc nhưng là sự cố với luồng realtime.

## 11. Runbook khi consumer bị pause vì thiếu ack

### 11.1. Consumer không nhận record mới

1. Kiểm tra trạng thái container và consumer pause.
2. Tìm record đã được dispatch nhưng chưa có acknowledgement.
3. Tra log theo topic, partition, offset và event id.
4. Kiểm tra worker queue, thread pool, database connection và downstream latency.
5. Xác định task đang chạy, bị treo, bị reject hay đã thất bại.
6. Nếu task thất bại, kiểm tra failure handler và trạng thái retry/DLT.
7. Chỉ acknowledge sau khi nghiệp vụ hoàn tất hoặc recovery đã lưu record bền vững.
8. Xác nhận consumer tiếp tục poll và lag bắt đầu giảm.

### 11.2. Worker queue tăng liên tục

1. So sánh tốc độ dispatch với tốc độ hoàn tất.
2. Kiểm tra số worker và CPU.
3. Kiểm tra database/API downstream có chậm hoặc giới hạn concurrency không.
4. Giảm poll batch hoặc giới hạn dispatch.
5. Điều chỉnh worker pool sau khi xác định bottleneck.
6. Theo dõi tuổi acknowledgement cũ nhất đến khi trở lại bình thường.

### 11.3. Record bị giao lại sau restart

1. Xác định offset đã commit cuối cùng của group.
2. Xác định record nào đã hoàn tất nghiệp vụ nhưng chưa được commit.
3. Kiểm tra inbox/idempotency key để ngăn side effect lặp.
4. Đối soát các thao tác ngoài database nếu API đích có kết quả không rõ.
5. Xác nhận record được xử lý lại và ack/commit tiến lên đúng thứ tự.

## 12. Kiểm thử AsyncAcks

Kiểm thử cần xác nhận cả thứ tự hoàn tất, commit offset và tác động nghiệp vụ.

Một kịch bản integration test:

1. Tạo topic test với ít nhất một partition và gửi nhiều record có offset liên tiếp.
2. Cấu hình record listener với manual ack và AsyncAcks.
3. Làm cho record đầu tiên xử lý chậm hơn các record sau.
4. Cho worker hoàn tất và ack theo thứ tự ngược.
5. Xác nhận consumer không commit vượt qua record chưa ack.
6. Cho record chậm nhất ack và xác nhận commit tiến lên sau khi poll đã được xác nhận đầy đủ.
7. Khởi động lại consumer trước khi đủ ack và xác nhận record chưa commit có thể được giao lại.
8. Xác nhận idempotency ngăn tác động nghiệp vụ bị lặp.
9. Làm worker thất bại và kiểm tra failure handler không ack sai.
10. Làm DLT/recovery unavailable và xác nhận nguồn không bị xác nhận mất dữ liệu.

Nên có test riêng cho executor rejection, worker timeout, shutdown trong lúc task đang chạy và commit failure. Test chỉ xác nhận callback `acknowledge()` đã được gọi là chưa đủ; cần kiểm tra offset thực tế và kết quả nghiệp vụ.

## 13. Những lỗi thiết kế thường gặp

**Ack ngay sau khi enqueue:** Task có thể chưa chạy hoặc bị từ chối. Hãy ack sau khi kết quả nghiệp vụ bền vững.

**Tự commit offset lớn nhất từ worker:** Có thể commit vượt qua offset còn thiếu trong cùng partition. Hãy để container quản lý acknowledgement với AsyncAcks.

**Bật AsyncAcks nhưng không dùng manual ack:** Container không nhận được tín hiệu hoàn tất đúng thời điểm. Hãy chọn ack mode và listener signature phù hợp.

**Nuốt exception trong worker:** Listener container không nhìn thấy lỗi bất đồng bộ. Hãy chuyển lỗi đến failure handler có retry/recovery rõ ràng.

**Để một ack treo vô hạn:** Consumer có thể pause và ngừng nhận record mới. Cần timeout, alert và quy trình recovery.

**Cho rằng AsyncAcks giữ thứ tự side effect:** Nó chỉ quản lý offset commit; thứ tự nghiệp vụ cần được bảo vệ ở tầng xử lý.

**Dùng executor không giới hạn:** Queue có thể tăng vô hạn và làm cạn heap. Hãy giới hạn thread, queue và tốc độ dispatch.

**Dùng nack cùng AsyncAcks:** Hai cơ chế không tương thích. Chọn một mô hình retry phù hợp.

## 14. Checklist triển khai

### Cấu hình container

- [ ] Phiên bản Spring Kafka hỗ trợ AsyncAcks.
- [ ] Listener dùng record mode phù hợp.
- [ ] Ack mode được đặt là MANUAL hoặc MANUAL_IMMEDIATE theo semantics cần thiết.
- [ ] AsyncAcks được bật trên đúng listener container.
- [ ] Không dùng nack khi AsyncAcks đang bật.
- [ ] Auto commit của Kafka consumer được tắt khi container quản lý acknowledgement.

### Xử lý bất đồng bộ

- [ ] Executor có giới hạn thread và queue.
- [ ] Task chỉ ack sau khi nghiệp vụ hoàn tất bền vững.
- [ ] Executor rejection và worker exception được xử lý rõ ràng.
- [ ] Failure handler có retry giới hạn và recovery/DLT.
- [ ] Recovery chỉ ack sau khi record đã được lưu bền vững.
- [ ] Có timeout và cảnh báo cho acknowledgement bị thiếu.

### Độ tin cậy và vận hành

- [ ] Consumer idempotent khi record được giao lại.
- [ ] Thứ tự nghiệp vụ theo key được bảo vệ nếu cần.
- [ ] Có metrics cho in-flight task, queue, processing time, pause và lag.
- [ ] Đã kiểm thử crash trước khi commit và duplicate delivery.
- [ ] Đã kiểm thử worker failure, DLT failure và graceful shutdown.
- [ ] Runbook có hướng xử lý consumer pause do ack còn thiếu.

## Kết luận

AsyncAcks cho phép các record trong cùng một poll được acknowledge theo thứ tự hoàn tất bất kỳ, trong khi Spring Kafka trì hoãn commit cho đến khi nhận đủ acknowledgement cần thiết. Điều này giúp ứng dụng xử lý song song mà không commit vượt qua record chưa hoàn tất. Đổi lại, consumer pause khi còn ack bị thiếu, worker chậm có thể giữ cả poll, và lỗi trong thread bất đồng bộ phải được ứng dụng xử lý riêng. Hãy dùng manual acknowledgement, executor có giới hạn, idempotency và recovery có kiểm soát; đo tuổi ack còn thiếu, pause duration, worker queue và commit offset để vận hành an toàn.

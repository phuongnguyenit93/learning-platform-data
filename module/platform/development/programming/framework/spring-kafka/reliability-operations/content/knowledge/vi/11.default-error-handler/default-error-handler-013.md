# BackOffHandler và thời gian chờ dài trong Spring Kafka

Trong Spring Kafka, DefaultErrorHandler dùng một chính sách BackOff để quyết định **khi nào** thử lại record bị lỗi và một BackOffHandler để quyết định **làm thế nào** container chờ đến thời điểm retry. Hai thành phần này có vai trò khác nhau. BackOff tạo ra chuỗi khoảng chờ; BackOffHandler thực thi khoảng chờ đó trong vòng đời listener container.

Sự khác biệt này trở nên quan trọng khi khoảng chờ dài. Nếu consumer thread chỉ sleep trong khi chờ, nó có thể không gọi poll đủ lâu và vượt max.poll.interval.ms. Consumer group khi đó có thể loại consumer khỏi group và phân phối lại partition. ContainerPausingBackOffHandler xử lý tình huống này bằng cách pause container trong thời gian chờ, đồng thời container tiếp tục poll để duy trì hoạt động của consumer.

Với thời gian chờ rất dài hoặc retry kéo dài nhiều phút, nhiều giờ, retry topic hoặc một cơ chế lưu trạng thái retry bền vững thường phù hợp hơn việc giữ một partition trong trạng thái blocking retry.

## 1. BackOff policy và BackOffHandler là hai việc khác nhau

Một lần listener xử lý record thất bại có thể đi qua các bước:

~~~text
Kafka listener nhận record
          |
          v
Listener ném exception
          |
          v
DefaultErrorHandler
          |
          +--> BackOff policy
          |       |
          |       +--> trả về khoảng chờ tiếp theo
          |       |
          |       +--> trả về STOP khi hết retry
          |
          v
BackOffHandler
          |
          +--> thực hiện khoảng chờ
          |
          v
Container retry / giao lại record
          |
          +--> thành công
          |
          +--> thất bại lần nữa
          |
          +--> hết retry: recoverer / DLT
~~~

**BackOff policy** xác định chuỗi thời gian chờ. Ví dụ:

- Chờ 1 giây giữa các lần retry.
- Chờ 1, 2, 4, 8 giây theo exponential backoff.
- Chờ tối đa 30 giây sau khi khoảng chờ tăng dần.
- Dừng sau một số lần retry đã định.

**BackOffHandler** nhận khoảng chờ mà policy trả về rồi thực hiện việc chờ theo cách phù hợp với listener container. Handler không tự quyết định lỗi nào retry được, số lần retry là bao nhiêu hoặc record nào sẽ được gửi DLT.

**DefaultErrorHandler** phối hợp cả hai thành phần với việc xử lý exception, seek/redelivery và recoverer. Vì vậy, chỉ thay đổi BackOff policy không nhất thiết giải quyết được vấn đề consumer thread bị giữ trong một khoảng sleep dài. Muốn thay đổi cách container chờ, cần cấu hình BackOffHandler phù hợp.

## 2. BackOff policy tạo ra chuỗi khoảng chờ

Spring Kafka sử dụng abstraction BackOff của Spring Framework. Mỗi lần listener thất bại, BackOffExecution cung cấp khoảng chờ kế tiếp thông qua nextBackOff(). Khi không còn lần retry, execution trả về BackOffExecution.STOP.

Ví dụ với FixedBackOff:

~~~java
BackOff backOff = new FixedBackOff(1_000L, 3L);
~~~

Với khoảng chờ 1.000 ms và 3 lần retry, listener được gọi lần đầu ngay lập tức; nếu thất bại, error handler cho phép tối đa ba lần retry sau lần đầu, mỗi lần cách nhau khoảng một giây. Khi chuỗi retry kết thúc, recoverer được gọi nếu đã cấu hình.

Bảng diễn giải:

| Lần gọi listener | Kết quả | Hành động |
|---:|---|---|
| 1 | Thất bại | Chờ 1 giây |
| 2 | Thất bại | Chờ 1 giây |
| 3 | Thất bại | Chờ 1 giây |
| 4 | Thất bại | Hết retry, gọi recoverer |

Số lần trong BackOff thường là số lần retry sau lần xử lý ban đầu. Khi thiết kế, hãy ghi rõ tổng số lần listener có thể được gọi để tránh nhầm giữa attempts và retries.

### FixedBackOff

FixedBackOff phù hợp khi dependency thường phục hồi trong một khoảng thời gian tương đối ổn định.

~~~java
BackOff backOff = new FixedBackOff(2_000L, 4L);
~~~

Ví dụ này chờ 2 giây giữa các lần retry và cho phép tối đa bốn lần retry sau lần đầu. Nó dễ dự đoán, nhưng nếu nhiều consumer cùng gặp sự cố, chúng có thể retry đồng loạt theo cùng lịch.

### Exponential backoff

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại. Cách này giúp giảm áp lực lên dependency khi lỗi kéo dài.

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(6);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(30_000L);
~~~

Với initial interval 1 giây, multiplier 2 và max interval 30 giây, các khoảng chờ tăng dần cho tới khi chạm mức tối đa. Constructor trong ví dụ đặt số lần retry tối đa; hãy kiểm tra API theo phiên bản Spring Framework/Spring Kafka của ứng dụng.

Exponential backoff thường phù hợp với lỗi mạng, rate limit hoặc dependency đang phục hồi. Nếu nhiều instance có cùng lịch, có thể cần jitter ở tầng retry phù hợp để tránh tất cả cùng gọi lại tại một thời điểm.

### Khi BackOff trả về STOP

Khi BackOffExecution trả về STOP, DefaultErrorHandler kết thúc chuỗi retry cho record hiện tại và chuyển sang recovery theo cấu hình. Nếu có ConsumerRecordRecoverer, record có thể được chuyển sang DLT hoặc xử lý bởi một recoverer riêng.

Không nên dùng retry vô hạn cho dữ liệu lỗi cố định. Với một record không deserialize được hoặc vi phạm validation, thêm thời gian chờ không làm payload thay đổi. Hãy phân loại exception non-retryable để recovery sớm.

## 3. BackOffHandler thực thi thời gian chờ như thế nào?

Spring Kafka cung cấp BackOffHandler để tách cách chờ khỏi chính sách tính khoảng chờ. Các handler thường gặp:

- **DefaultBackOffHandler:** chờ theo cách blocking trên luồng xử lý container.
- **ContainerPausingBackOffHandler:** pause listener container trong khoảng chờ, cho phép container tiếp tục poll thay vì giữ consumer thread trong một lần sleep dài.

Việc chọn handler không thay đổi chuỗi thời gian do BackOff policy tạo ra. Nó thay đổi cách thời gian đó được thực thi.

### DefaultBackOffHandler

DefaultBackOffHandler là lựa chọn đơn giản cho các khoảng chờ ngắn. Trong thời gian sleep, consumer thread không thực hiện poll mới. Nếu listener xử lý nhanh và backoff ngắn, điều này thường không gây vấn đề.

Với khoảng chờ dài, thread có thể không poll trong thời gian vượt giới hạn max.poll.interval.ms. Khi đó, consumer có thể bị xem là không còn hoạt động trong group, gây rebalance và giao partition cho consumer khác.

Ví dụ, nếu max.poll.interval.ms là 5 phút nhưng error handler sleep 8 phút, consumer có thể vượt poll interval trước khi quay lại xử lý. Tăng max.poll.interval.ms có thể thay đổi ngưỡng này, nhưng không giải quyết mọi vấn đề về thời gian chờ hoặc việc giữ partition quá lâu.

### ContainerPausingBackOffHandler

ContainerPausingBackOffHandler được thiết kế cho khoảng chờ dài hơn. Thay vì giữ consumer thread sleep xuyên suốt, handler pause listener container trong thời gian backoff. Container vẫn tiếp tục poll trong trạng thái pause để duy trì membership của consumer group; record mới không được chuyển cho listener trong thời gian pause.

~~~text
Listener thất bại
      |
      v
DefaultErrorHandler
      |
      v
BackOff trả về 8 phút
      |
      v
ContainerPausingBackOffHandler
      |
      +--> pause container
      |
      +--> container tiếp tục poll
      |       |
      |       +--> duy trì consumer group membership
      |       +--> không giao record mới cho listener
      |
      +--> hết khoảng pause
              |
              v
          resume container
              |
              v
       tiếp tục retry record lỗi
~~~

Cách này giúp tránh việc consumer không poll trong toàn bộ khoảng chờ dài. Tuy nhiên, nó vẫn là blocking retry ở cấp partition/container: record lỗi đang được xử lý và các record sau có thể phải đợi. Pause không làm record lỗi biến mất và cũng không tạo một retry queue độc lập.

## 4. Cấu hình ContainerPausingBackOffHandler với DefaultErrorHandler

Ví dụ cấu hình một record listener với DLT recoverer và khoảng chờ dài:

~~~java
@Configuration
public class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler orderErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        BackOff backOff = new FixedBackOff(
                60_000L, // khoảng chờ 60 giây
                3L       // tối đa 3 lần retry sau lần đầu
        );

        BackOffHandler backOffHandler =
                new ContainerPausingBackOffHandler();

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        backOff,
                        backOffHandler
                );

        handler.addNotRetryableExceptions(
                InvalidOrderException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            DefaultErrorHandler orderErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(orderErrorHandler);

        return factory;
    }
}
~~~

Trong ví dụ:

- BackOff policy đặt khoảng chờ 60 giây và tối đa ba lần retry.
- ContainerPausingBackOffHandler thực hiện các khoảng chờ bằng cách pause container.
- DefaultErrorHandler điều phối retry và recovery.
- InvalidOrderException được đánh dấu non-retryable nên không phải chờ đủ ba lần retry.
- DeadLetterPublishingRecoverer chuyển record không phục hồi được sang DLT theo cấu hình định tuyến.

Các kiểu KafkaTemplate, serializer và factory cần khớp với payload thực tế. Nếu DLT có thể chứa cả object đã deserialize và raw byte[] từ lỗi deserialize, hãy cấu hình serializer có thể xử lý cả hai dạng hoặc dùng template chuyên biệt.

Constructor nhận BackOffHandler có sẵn trong các phiên bản Spring Kafka hỗ trợ API này. Hãy kiểm tra phiên bản dependency trước khi áp dụng; nếu phiên bản cũ không có constructor đó, cần nâng cấp hoặc dùng cơ chế tương ứng mà phiên bản cung cấp.

## 5. Quan hệ với max.poll.interval.ms

max.poll.interval.ms là giới hạn tối đa giữa các lần gọi poll() tiếp theo của consumer trong group management. Nếu consumer không gọi poll trong khoảng này, coordinator có thể xem consumer là không còn hoạt động và bắt đầu rebalance.

Cần phân biệt ba loại thời gian:

| Cấu hình | Điều khiển điều gì |
|---|---|
| max.poll.interval.ms | Khoảng thời gian tối đa giữa các lần poll |
| session.timeout.ms | Thời gian phát hiện consumer mất heartbeat theo cơ chế group |
| pollTimeout | Thời gian container chờ trong một lần poll trước khi vòng lặp tiếp tục |

Khi dùng DefaultBackOffHandler, thời gian sleep cộng với thời gian xử lý listener có thể làm consumer vượt max.poll.interval.ms nếu không poll trong khoảng chờ.

Ví dụ:

~~~text
max.poll.interval.ms = 300000 (5 phút)
listener thất bại
DefaultBackOffHandler sleep = 8 phút
consumer không poll trong thời gian sleep
      |
      v
vượt max.poll.interval.ms
      |
      v
consumer có thể rời group / rebalance
~~~

ContainerPausingBackOffHandler giải quyết tình huống này bằng cách pause container và để vòng lặp container tiếp tục poll trong thời gian pause. Do đó, consumer vẫn có thể duy trì group membership trong khi record chưa được giao lại cho listener.

Tăng max.poll.interval.ms có thể phù hợp nếu thời gian xử lý bình thường của listener thực sự dài. Nhưng không nên chỉ tăng giá trị này để che giấu một retry wait quá dài. Một consumer bị giữ trong trạng thái retry lâu vẫn có thể giữ partition và làm consumer group chậm tiến.

## 6. Pause container không giống stop consumer

Đây là khác biệt quan trọng khi vận hành.

**Pause** tạm ngừng chuyển record mới đến listener trong khi consumer vẫn tiếp tục poll để giữ group membership. Khi resume, container tiếp tục giao record cho listener.

**Stop** dừng container và đóng consumer theo lifecycle. Consumer rời group; partition có thể được phân phối lại cho consumer khác.

~~~text
RUNNING
   |
   | pause()
   v
PAUSED
   |
   | poll tiếp tục, listener không nhận record mới
   |
   | resume()
   v
RUNNING

RUNNING
   |
   | stop()
   v
STOPPING
   |
   | consumer đóng
   v
STOPPED
~~~

ContainerPausingBackOffHandler dùng pause/resume để tạo khoảng chờ. Nó không stop consumer rồi khởi động lại sau mỗi lần retry.

Pause ở cấp container cũng có thể ảnh hưởng đến nhiều partition mà child consumer đang quản lý. Vì vậy, khi một record lỗi trên consumer đang pause, các partition khác được gán cho cùng consumer có thể bị chậm theo. Hãy tính đến partition assignment và concurrency khi chọn blocking retry.

## 7. Thời gian pause có thể không chính xác tuyệt đối

ContainerPausingBackOffHandler dựa trên vòng poll và cơ chế pause/resume của listener container. Khoảng chờ thực tế có thể lệch so với con số trong BackOff policy do pollTimeout và lịch hoạt động của container.

Ví dụ, nếu muốn pause 10 giây nhưng container poll theo chu kỳ 2 giây, thời điểm resume thực tế có thể lệch theo chu kỳ poll và thời điểm container xử lý lệnh pause/resume. Đây không phải bộ hẹn giờ chính xác cho một tác vụ nghiệp vụ cần chạy đúng từng mili giây.

Vì vậy:

- Dùng handler cho retry delay cần chờ dài nhưng không yêu cầu thời điểm chính xác tuyệt đối.
- Đặt pollTimeout phù hợp với yêu cầu latency và hoạt động container.
- Quan sát thời gian pause thực tế trong môi trường tải thật.
- Không dựa vào thời gian pause để thực hiện một deadline nghiệp vụ chính xác.
- Nếu cần lịch retry dài, có thể phục hồi sau restart hoặc cần thời điểm giao lại độc lập, dùng retry topic hoặc lưu lịch retry bền vững.

## 8. Blocking retry có thể giữ partition trong thời gian dài

ContainerPausingBackOffHandler giữ consumer group hoạt động nhưng không loại bỏ ảnh hưởng của blocking retry đến partition.

Giả sử partition 0 có các record:

~~~text
P0:
  offset 100 --> event A (lỗi, retry sau 10 phút)
  offset 101 --> event B
  offset 102 --> event C
~~~

Nếu retry blocking giữ record 100 ở trạng thái chờ, record 101 và 102 có thể không được xử lý cho đến khi record 100 thành công hoặc được recovery. Điều này giữ thứ tự nhưng làm tăng latency cho các record sau.

Trong một consumer đang quản lý nhiều partition, việc pause container có thể ảnh hưởng tới việc giao record từ các partition khác của cùng consumer. Tăng concurrency có thể phân phối partition cho nhiều child consumer hơn, nhưng không giải quyết việc một partition bị giữ bởi poison pill.

Blocking retry phù hợp khi:

- Khoảng chờ ngắn hoặc vừa phải.
- Giữ thứ tự trong partition là yêu cầu.
- Lỗi có khả năng phục hồi trong thời gian dự kiến.
- Số lần retry có giới hạn.
- Việc tạm ngừng partition trong thời gian retry là chấp nhận được.

Nếu record cần chờ nhiều phút hoặc giờ, hãy đánh giá retry topic thay vì giữ partition chờ.

## 9. Retry topic cho thời gian chờ dài

Spring Kafka hỗ trợ non-blocking retry thông qua @RetryableTopic. Khi listener thất bại, framework chuyển record sang retry topic tương ứng với delay đã cấu hình. Consumer của topic chính có thể tiếp tục xử lý record khác trong khi record lỗi chờ tới lần thử tiếp theo.

Ví dụ:

~~~java
@RetryableTopic(
        attempts = "5",
        backoff = @Backoff(
                delay = 60_000,
                multiplier = 2.0,
                maxDelay = 900_000
        ),
        dltTopicSuffix = "-dlt"
)
@KafkaListener(
        topics = "orders",
        groupId = "order-service"
)
public void onOrder(OrderCreated event) {
    orderService.process(event);
}
~~~

Trong ví dụ, retry topic dùng delay tăng dần từ 60 giây, nhân đôi và giới hạn tối đa 15 phút. attempts và cách tạo retry topics cần được kiểm tra theo phiên bản Spring Kafka; cấu hình này minh họa chính sách non-blocking retry.

So sánh:

| Tiêu chí | Blocking retry + ContainerPausingBackOffHandler | Non-blocking retry topic |
|---|---|---|
| Consumer group chính | Container pause nhưng tiếp tục poll | Có thể tiếp tục xử lý record khác |
| Partition bị lỗi | Có thể bị giữ tại record đang retry | Record lỗi được chuyển sang topic retry |
| Thứ tự | Dễ giữ thứ tự trong partition nguồn | Có thể thay đổi thứ tự quan sát |
| Thời gian chờ | Phù hợp delay dài vừa phải | Phù hợp delay dài hơn |
| Hạ tầng | Dùng topic nguồn và container | Cần retry topics và luồng chuyển tiếp |
| Khôi phục sau restart | Dựa vào offset và container lifecycle | Retry record được lưu trong Kafka topic |
| Độ phức tạp | Thấp hơn | Cao hơn, cần quản lý topology retry/DLT |

Non-blocking retry có các giới hạn theo phiên bản và loại listener; đặc biệt cần kiểm tra khả năng kết hợp với batch listener và container transaction. Không giả định mọi cấu hình blocking retry có thể chuyển nguyên trạng sang @RetryableTopic.

Retry topic cũng có thể làm thay đổi thứ tự. Ví dụ event B ở topic chính có thể được xử lý trước event A đang chờ trong retry topic. Nếu thứ tự nghiệp vụ là bắt buộc, cần giữ retry blocking hoặc thiết kế sequence/ordering ở tầng nghiệp vụ.

## 10. Chọn backoff theo loại lỗi

Không nên áp dụng một chuỗi chờ duy nhất cho mọi exception.

| Loại lỗi | Chính sách gợi ý |
|---|---|
| Database/network chập chờn | Exponential backoff ngắn, giới hạn tổng thời gian |
| HTTP 429 hoặc rate limit | Tôn trọng Retry-After nếu có, backoff có jitter |
| HTTP 503 hoặc dependency tạm unavailable | Backoff tăng dần, circuit breaker nếu cần |
| Service bảo trì trong vài phút | Container pause hoặc retry topic tùy yêu cầu thứ tự |
| Dependency có thể mất hàng giờ | Retry topic hoặc lưu trạng thái retry bền vững |
| Payload không hợp lệ | Không retry cùng payload; recover/DLT |
| Authorization bị từ chối | Không retry vô hạn; cảnh báo và quarantine nếu cần |
| Bug code xác định | Giới hạn retry, giữ record để điều tra |

Lỗi retryable phải có điều kiện phục hồi có ý nghĩa. Ví dụ database tạm ngắt kết nối có thể phục hồi, nhưng một event thiếu orderId sẽ không tự sửa sau 10 phút.

### Exponential backoff và jitter

Nếu nhiều consumer cùng retry theo một lịch cố định, chúng có thể đồng loạt gọi lại dependency. Jitter thêm độ lệch ngẫu nhiên để phân tán thời điểm retry.

Một lịch minh họa:

~~~text
baseDelay = 1 second
multiplier = 2
maxDelay = 30 seconds

retry 1: ~1 second + jitter
retry 2: ~2 seconds + jitter
retry 3: ~4 seconds + jitter
retry 4: ~8 seconds + jitter
retry 5: ~16 seconds + jitter
retry 6+: ~30 seconds + jitter
~~~

Nếu BackOff implementation không cung cấp jitter, có thể dùng một BackOff tùy chỉnh hoặc chọn retry mechanism có hỗ trợ jitter phù hợp. Không nên tự sleep ngẫu nhiên trong listener vì việc đó không phối hợp với container pause/poll lifecycle.

## 11. Kết hợp DefaultErrorHandler với recovery và DLT

DefaultErrorHandler điều phối retry và sau khi hết retry gọi recoverer. Với DLT, DeadLetterPublishingRecoverer có thể gửi record lỗi sang topic riêng để điều tra hoặc phát lại sau khi sửa nguyên nhân.

~~~text
orders topic
    |
    v
listener
    |
    +--> exception retryable
    |       |
    |       v
    |    BackOff policy
    |       |
    |       v
    |    BackOffHandler chờ
    |       |
    |       v
    |    retry listener
    |
    +--> hết retry
            |
            v
      DeadLetterPublishingRecoverer
            |
            v
        orders.DLT
~~~

Cần xác định:

- Số lần retry và tổng thời gian retry.
- Exception nào không retry.
- DLT topic và partition routing.
- Serializer cho record gốc và raw bytes.
- Hành vi nếu publish DLT thất bại.
- Retention và quyền truy cập DLT.
- Quy trình sửa dữ liệu và replay.
- Idempotency của consumer khi record được phát lại.

Nếu DLT publish thất bại, không nên xem record nguồn đã được recovery thành công. Cần quan sát exception từ recoverer và đảm bảo offset nguồn không tiến như thể dữ liệu đã được lưu an toàn.

## 12. Dùng BackOffHandler cho consumer nhiều partition và concurrency

ConcurrentMessageListenerContainer tạo các child container, mỗi child có consumer riêng. Khi một child consumer pause vì backoff, các partition được gán cho child đó có thể cùng bị ảnh hưởng.

Ví dụ:

~~~text
Topic orders: 6 partitions
Concurrency: 3

Child 1: P0, P1
Child 2: P2, P3
Child 3: P4, P5

P0 có record lỗi và Child 1 pause:
  P0: record lỗi đang chờ retry
  P1: có thể bị chậm do cùng child container
  P2-P5: do child khác xử lý tiếp
~~~

Đây là lý do concurrency và partition assignment ảnh hưởng đến blast radius của blocking retry. Nếu workload có key ordering, cần phân phối key và partition phù hợp. Không nên tăng concurrency vượt số partition với kỳ vọng giải quyết mọi tình huống retry.

Khi pause container, consumer vẫn poll để duy trì membership nhưng không giao record mới cho listener. Theo dõi consumer lag theo partition để biết partition nào bị giữ và ảnh hưởng lan tới đâu.

## 13. BackOffHandler và shutdown/rebalance

Một khoảng pause dài có thể trùng với thời điểm ứng dụng shutdown hoặc consumer group rebalance.

Khi shutdown:

- Container cần ngừng nhận công việc mới.
- Record đang retry có thể chưa được xử lý lại.
- Offset chưa commit có thể khiến record được giao lại sau khi instance khác tiếp quản.
- DLT/recovery phải có trạng thái rõ ràng nếu đã bắt đầu.
- Không nên chờ retry dài hơn thời gian shutdown được cấp.

Khi rebalance:

- Partition có thể được thu hồi khỏi consumer hiện tại.
- Container cần dừng xử lý theo lifecycle và trạng thái assignment.
- Record chưa commit có thể được giao lại cho consumer mới.
- Idempotency cần bảo vệ side effect đã thực hiện trước lần commit.

ContainerPausingBackOffHandler không đảm bảo record sẽ hoàn tất trước mọi lần shutdown hoặc rebalance. Hãy thiết kế listener có thể phục hồi và không dựa vào một consumer instance duy nhất để giữ trạng thái retry trong bộ nhớ.

## 14. Không dùng sleep trong listener để thay thế BackOffHandler

Một cách triển khai dễ gặp nhưng không phù hợp là tự gọi Thread.sleep trong listener:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(OrderCreated event) throws InterruptedException {
    try {
        orderService.process(event);
    }
    catch (TemporaryDependencyException ex) {
        Thread.sleep(300_000L);
        throw ex;
    }
}
~~~

Cách này giữ consumer thread trong sleep, làm chậm poll và có thể vượt max.poll.interval.ms. Nó cũng trộn lẫn retry scheduling với business logic, khiến test, shutdown và observability khó kiểm soát.

Hãy để listener ném exception và cấu hình DefaultErrorHandler cùng BackOffHandler. Khi cần delay dài, chọn ContainerPausingBackOffHandler hoặc retry topic theo yêu cầu.

## 15. Chọn thời gian chờ và giới hạn retry

Backoff không nên chỉ được chọn theo cảm giác. Hãy xác định:

1. Dependency thường phục hồi trong bao lâu?
2. Bao nhiêu lần retry là hợp lý trước khi recovery?
3. Tổng thời gian xử lý record có vượt deadline nghiệp vụ không?
4. Partition có thể bị giữ trong khoảng thời gian đó không?
5. Consumer group có cần tiếp tục xử lý record phía sau không?
6. Có cần giữ thứ tự trong partition không?
7. Retry có thể phục hồi sau restart không?
8. DLT có thể lưu record an toàn nếu retry hết hạn không?

Ví dụ policy cho lỗi dịch vụ ngoài thường phục hồi trong vài chục giây:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(5);

backOff.setInitialInterval(1_000L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(15_000L);

DefaultErrorHandler handler =
        new DefaultErrorHandler(
                recoverer,
                backOff,
                new ContainerPausingBackOffHandler()
        );
~~~

Ví dụ này tạo các khoảng chờ tăng dần với giới hạn 15 giây và tối đa năm lần retry. Tổng thời gian thực tế phụ thuộc chuỗi backoff, thời gian listener, thời gian poll và recovery.

Nếu tổng thời gian retry có thể lên tới nhiều phút hoặc giờ, hãy cân nhắc retry topic. Nếu retry cần theo lịch nghiệp vụ cụ thể hoặc phải phối hợp với trạng thái database, hãy lưu next_attempt_at và attempt count trong một kho bền vững.

## 16. Quan sát thời gian retry và trạng thái container

Trong production, cần đo cả số lần retry và thời gian thực tế container bị pause.

| Tín hiệu | Điều cần theo dõi |
|---|---|
| Listener error count | Tần suất listener thất bại |
| Retry attempt count | Số lần record được thử lại |
| Backoff duration | Khoảng chờ được yêu cầu |
| Container paused duration | Thời gian pause thực tế |
| Consumer lag theo partition | Partition bị chậm khi retry |
| Rebalance count | Rebalance phát sinh trong thời gian retry |
| DLT publish count | Số record được recovery |
| Recovery failure count | Lỗi khi publish hoặc xử lý DLT |
| Listener processing latency | Thời gian xử lý trước khi lỗi |
| Dependency error rate | Xác định lỗi có thực sự tạm thời |

Tên metric cụ thể phụ thuộc Spring Kafka, Kafka client, Micrometer và exporter. Có thể lắng nghe container events như ConsumerPausedEvent và ConsumerResumedEvent để ghi nhận trạng thái pause/resume, đồng thời dùng metric consumer lag để đo tác động tới partition.

Log nên có topic, partition, offset, key hoặc event ID, exception class, attempt number và thời điểm retry tiếp theo. Không log raw payload nếu có thể chứa thông tin nhạy cảm.

## 17. Các tình huống vận hành thường gặp

### Retry delay dài hơn max.poll.interval.ms

Nếu dùng blocking sleep, consumer có thể không poll đủ lâu và rời group. Dùng ContainerPausingBackOffHandler để pause container trong khi tiếp tục poll, hoặc chuyển sang retry topic nếu partition nguồn không nên bị giữ.

### Container vẫn poll nhưng partition không tiến

ContainerPausingBackOffHandler duy trì poll trong thời gian pause, nhưng record lỗi vẫn đang chờ retry. Nếu cần tiếp tục xử lý record sau, dùng non-blocking retry topic và chấp nhận tác động đến thứ tự.

### Retry đồng loạt gây tải tăng

Dùng exponential backoff, jitter và circuit breaker ở tầng dependency. Giảm concurrency hoặc tốc độ xử lý nếu dependency quá tải. Không để mọi consumer retry ngay sau cùng một khoảng cố định.

### Retry mãi một payload không hợp lệ

Phân loại exception non-retryable và chuyển DLT/quarantine. Không dùng backoff dài để che giấu lỗi dữ liệu cố định.

### DLT publish thất bại

Kiểm tra broker, ACL, serializer, topic và partition routing. Recovery chưa hoàn tất nếu record chưa được lưu an toàn; cần cảnh báo và không commit nguồn như thể recovery thành công.

### Shutdown xảy ra khi container đang pause

Container dừng theo lifecycle. Record chưa commit có thể được giao lại khi consumer khác nhận partition. Listener và side effect phải idempotent để xử lý lại an toàn.

## 18. Checklist cấu hình BackOffHandler

- BackOff policy có số lần retry hữu hạn và tổng thời gian hợp lý.
- FixedBackOff hoặc exponential backoff phù hợp với loại lỗi.
- Exception dữ liệu cố định được phân loại non-retryable.
- BackOffHandler được chọn theo độ dài khoảng chờ.
- Dùng DefaultBackOffHandler cho khoảng chờ ngắn khi blocking sleep phù hợp.
- Dùng ContainerPausingBackOffHandler khi cần pause container và tiếp tục poll trong thời gian chờ.
- Không dùng Thread.sleep trực tiếp trong listener để tự xây retry.
- Đã hiểu quan hệ giữa max.poll.interval.ms, session timeout và pollTimeout.
- Đã tính đến các partition khác cùng child consumer bị ảnh hưởng khi pause.
- Retry delay không giữ partition quá lâu nếu yêu cầu throughput không cho phép.
- Retry topic được cân nhắc cho thời gian chờ dài hoặc cần xử lý record sau.
- Thứ tự nghiệp vụ được đánh giá khi dùng non-blocking retry.
- DLT recoverer và serializer hỗ trợ payload lỗi.
- Recovery publish thất bại được quan sát và xử lý đúng.
- Shutdown/rebalance có thể xảy ra giữa các lần retry mà không làm mất side effect.
- Consumer idempotent để chịu redelivery.
- Có metrics/log cho retry count, pause duration, lag, rebalance và DLT.

BackOff policy trả lời câu hỏi “chờ bao lâu và thử lại bao nhiêu lần”; BackOffHandler trả lời câu hỏi “container chờ bằng cách nào”. Với khoảng chờ dài, ContainerPausingBackOffHandler giúp consumer tiếp tục poll trong khi container pause, tránh giữ consumer thread trong một lần sleep vượt poll interval. Khi delay dài đến mức partition không nên bị giữ, hãy chuyển sang retry topic hoặc cơ chế retry bền vững có lịch riêng.

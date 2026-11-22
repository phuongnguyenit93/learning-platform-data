# NonResponsiveConsumerEvent

Trong Spring Kafka, một consumer bình thường liên tục gọi `poll()` để lấy record, duy trì tiến độ của consumer group và tiếp tục xử lý dữ liệu. Khi consumer **không phản hồi trong thời gian dài**, listener có thể ngừng nhận record mới dù pod vẫn `Running`, JVM chưa crash và kết nối TCP tới Kafka vẫn tồn tại. Đây là một dạng sự cố khó phát hiện nếu hệ thống chỉ dựa vào health check của ứng dụng hoặc việc container chưa bị stop.

Spring Kafka cung cấp application event **`NonResponsiveConsumerEvent`** để phát hiện dấu hiệu consumer thread không trở lại vòng `poll()` trong khoảng thời gian vượt ngưỡng giám sát. Event được phát từ cơ chế monitor của listener container khi thời gian kể từ hoạt động poll vượt ngưỡng tính từ `pollTimeout` và `noPollThreshold`. Nó là **tín hiệu cảnh báo cần điều tra**, không phải bằng chứng chắc chắn Kafka broker đã chết, không phải exception của listener và cũng không tự động sửa sự cố.

Bài học này giải thích thời điểm event xuất hiện, cách cấu hình bộ giám sát, cách nhận event trong ứng dụng Spring Boot, cách phân biệt consumer bị kẹt với xử lý record lâu, cùng quy trình vận hành để khôi phục mà không làm mất dữ liệu hoặc tạo retry/rebalance storm.

## 1. Consumer bình thường và consumer không phản hồi

Một vòng lặp Kafka consumer đơn giản có dạng:

```text
                       +-------------------+
                       | Consumer.poll()   |
                       +---------+---------+
                                 |
                                 v
                       Có record được trả về?
                           /          \
                         Không         Có
                           |            |
                           |            v
                           |       Listener xử lý
                           |            |
                           +------<-----+
                                 |
                                 v
                         Poll vòng kế tiếp
```

Trong Spring Kafka, listener container quản lý consumer thread, gọi `poll()`, đưa record vào listener, xử lý acknowledgment/offset và các công việc của container. Ứng dụng thường không cần tự viết một vòng `while(true)` để poll.

Sự cố có thể khiến consumer không tiến tới poll tiếp theo:

- `poll()` hoặc một thao tác Kafka client đang chờ lâu bất thường do network, broker/coordinator hoặc lỗi thư viện.
- Listener xử lý record quá lâu, ví dụ HTTP timeout kéo dài hoặc database lock không được giải phóng.
- Một callback liên quan commit/transaction/seek/rebalance bị block hoặc gặp deadlock.
- JVM bị stall vì GC pause dài, quá tải CPU hoặc các thread phải tranh tài nguyên.
- Một luồng bị kẹt trong code người dùng và không trả lại quyền điều khiển cho container.

**Điểm tinh tế:** tên event là `NonResponsiveConsumerEvent`, không phải `KafkaBrokerDownEvent`. Monitor quan sát dấu hiệu “consumer không poll đúng tiến độ”, nên nguyên nhân có thể ở client, listener, JVM hoặc hạ tầng Kafka. Cần điều tra bằng thread dump, log, metric và trạng thái group trước khi kết luận.

## 2. NonResponsiveConsumerEvent là gì?

`NonResponsiveConsumerEvent` nằm trong package:

```java
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
```

Đây là một **Spring application event** do Kafka listener container phát khi bộ monitor nhận thấy consumer không đáp ứng ngưỡng poll. Ứng dụng có thể nhận nó qua `@EventListener` hoặc cơ chế `ApplicationListener` của Spring.

Về mặt vận hành, event cho biết:

1. Listener/consumer nào đã bị monitor đánh dấu không phản hồi.
2. Khoảng thời gian kể từ hoạt động poll được container theo dõi.
3. Context topic-partition/consumer tương ứng, theo API của phiên bản.
4. Một thời điểm để ghi log, tăng metric, tạo cảnh báo hoặc kích hoạt hành động khôi phục **có kiểm soát**.

Nó **không** tự:

- Dừng listener container hoặc restart pod.
- Gọi `consumer.wakeup()` hoặc ép `poll()` thoát.
- Commit hoặc rollback offset.
- Chuyển record lỗi sang DLT.
- Thay đổi assignment hoặc chuyển partition sang consumer khác.
- Xác định chính xác nguyên nhân đang chặn consumer thread.

Vì vậy, event nên được xem như một phần của **observability và incident response**. Phải xây dựng chính sách phản ứng riêng nếu muốn hành động tự động.

## 3. Ba tham số quyết định thời điểm phát event

Các cấu hình quan trọng nằm ở `ContainerProperties`:

| Thuộc tính | Ý nghĩa | Đơn vị |
|---|---|---|
| `pollTimeout` | Thời gian tối đa được truyền vào lời gọi consumer `poll()` trong chu kỳ bình thường. | Millisecond. |
| `noPollThreshold` | Hệ số ngưỡng để xác định consumer đã quá lâu không có tiến triển poll theo monitor. | Hệ số không có đơn vị. |
| `monitorInterval` | Khoảng thời gian giữa các lần monitor kiểm tra tình trạng consumer. | Giây. |

Theo các mặc định thường gặp trong Spring Kafka, `pollTimeout` là **5.000 ms**, `noPollThreshold` là **3,0** và `monitorInterval` là **30 giây**. Những giá trị này có thể khác do cấu hình ứng dụng hoặc phiên bản framework; phải đọc giá trị thực tế của listener container khi điều tra.

Ngưỡng thời gian xấp xỉ:

```text
T_threshold ≈ pollTimeout × noPollThreshold
```

Nếu `pollTimeout = 5.000 ms` và `noPollThreshold = 3.0`:

```text
T_threshold ≈ 5.000 × 3 = 15.000 ms = 15 giây
```

Monitor không chạy liên tục mỗi millisecond. Nếu `monitorInterval = 30 giây`, thời điểm phát hiện phụ thuộc vào pha của lần quét monitor; có thể muộn hơn thời điểm vừa vượt ngưỡng. **Không coi ngưỡng 15 giây là cam kết event xuất hiện đúng giây thứ 15.**

### Ví dụ thay đổi ngưỡng

| `pollTimeout` | `noPollThreshold` | Ngưỡng tính toán | `monitorInterval` |
|---:|---:|---:|---:|
| 5.000 ms | 3,0 | 15 giây | 30 giây |
| 5.000 ms | 6,0 | 30 giây | 10 giây |
| 1.000 ms | 5,0 | 5 giây | 5 giây |
| 10.000 ms | 3,0 | 30 giây | 15 giây |

Các hàng là ví dụ minh họa; không phải bảng khuyến nghị cố định. Việc hạ ngưỡng quá thấp có thể tạo cảnh báo liên tục khi listener đôi khi phải xử lý record lâu hơn bình thường.

## 4. Cấu hình monitor trong ConcurrentKafkaListenerContainerFactory

Một cách rõ ràng để cấu hình là thao tác trực tiếp trên `ContainerProperties` của listener container factory:

```java
@Configuration
public class KafkaMonitorConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            monitoredKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        factory.setConsumerFactory(consumerFactory);

        // Timeout mỗi poll: 5 giây.
        factory.getContainerProperties().setPollTimeout(5_000L);

        // Đánh dấu không phản hồi khi thời gian vượt
        // khoảng 3 lần poll timeout.
        factory.getContainerProperties().setNoPollThreshold(3.0f);

        // Monitor kiểm tra theo chu kỳ 10 giây.
        factory.getContainerProperties().setMonitorInterval(10);

        return factory;
    }
}
```

Các import chính:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
```

Listener muốn dùng factory này phải tham chiếu đúng tên:

```java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders",
    groupId = "order-service",
    containerFactory = "monitoredKafkaListenerContainerFactory"
)
public void onOrder(ConsumerRecord<String, String> record) {
    orderService.process(record.value());
}
```

Khi Spring Boot đã tạo factory mặc định hoặc ứng dụng có nhiều factory, phải chắc chắn event phát từ **factory/container thực tế đang chạy listener**. Cấu hình một factory không được listener sử dụng sẽ không thay đổi hành vi của listener đó.

`monitorInterval` là chu kỳ giám sát **tính bằng giây**, còn `pollTimeout` được biểu diễn **bằng millisecond**. Nhầm đơn vị có thể tạo monitor quá dày, cảnh báo trễ hoặc làm hành vi khác hẳn dự kiến.

## 5. Nhận NonResponsiveConsumerEvent bằng @EventListener

Ví dụ listener ghi log và metric theo từng sự kiện:

```java
@Component
public class NonResponsiveConsumerMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(NonResponsiveConsumerMonitor.class);

    private final MeterRegistry meterRegistry;

    public NonResponsiveConsumerMonitor(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Kafka consumer not responsive: listenerId={}, " +
            "timeSinceLastPollMs={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions());

        meterRegistry.counter(
                "app.kafka.consumer.nonresponsive.events",
                "listener", event.getListenerId())
                .increment();
    }
}
```

Các import chính:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;
```

Ví dụ giả định ứng dụng đã cấu hình Micrometer `MeterRegistry`. `app.kafka.consumer.nonresponsive.events` là **metric do ứng dụng tự tạo**, không phải tên metric mặc định bắt buộc của Spring Kafka.

`getTimeSinceLastPoll()` biểu diễn số millisecond mà event báo consumer chưa có tiến triển poll theo cách container đo. `getListenerId()` giúp liên hệ với endpoint/container; `getTopicPartitions()` cung cấp context partition khi có sẵn. Với các API/event field, nên đối chiếu chữ ký theo phiên bản Spring Kafka được dự án sử dụng.

Trong ứng dụng có nhiều listener, nên log cả `application`, `pod`, `consumerGroup`, `listenerId` và `topicPartition`. Không cần log payload record chỉ để phát hiện consumer không phản hồi; event không phải là một record nghiệp vụ đang được xử lý.

## 6. Sự kiện có thể lặp lại và không tương đương incident mới

Nếu consumer vẫn bị kẹt qua nhiều chu kỳ `monitorInterval`, ứng dụng có thể nhận **nhiều `NonResponsiveConsumerEvent` cho cùng một trạng thái**. Nếu mỗi event đều tạo ticket, gửi cảnh báo trực tiếp hoặc restart consumer, hệ thống sẽ tạo notification storm và recovery loop.

Thiết kế cảnh báo nên có:

- **Deduplication** theo listener ID, instance và khoảng thời gian incident.
- **Cooldown** giữa hai cảnh báo cùng nguyên nhân.
- **Escalation** khi tình trạng kéo dài hoặc nhiều member bị ảnh hưởng.
- **Resolved signal** khi consumer poll bình thường trở lại, đo bằng metric/health thực tế.
- **Không tự kết luận** một event là một consumer mới hỏng.

Ví dụ logic:

```text
T0: lần đầu nhận NonResponsiveConsumerEvent
    -> log cảnh báo; đánh dấu incident OPEN

T1: nhận thêm event cho cùng listener/pod
    -> tăng counter, cập nhật duration; không mở incident mới

T2: poll hoạt động bình thường và lag tiến triển
    -> xác nhận phục hồi; đóng incident
```

Chỉ việc không nhận thêm event cũng chưa đủ để kết luận consumer khỏe: container có thể đã stop hoặc pod đã crash. Kết hợp trạng thái container, group assignment, poll rate, committed offset và ứng dụng downstream.

## 7. Vì sao không gọi KafkaConsumer tùy tiện trong event handler?

Kafka `Consumer` không phải đối tượng thread-safe. `NonResponsiveConsumerEvent` được phát từ cơ chế giám sát, có thể không chạy trên cùng thread đang gọi `poll()`. Vì thế **không được gọi tùy tiện `consumer.poll()`, `commitSync()`, `seek()` hoặc `pause()` trên consumer lấy từ event**.

Spring Kafka cung cấp API của `MessageListenerContainer` để điều khiển lifecycle, pause/resume và một số hoạt động được điều phối. Nếu cần thao tác consumer ở ngữ cảnh thread đúng, dùng cơ chế mà framework hỗ trợ thay vì chuyển raw consumer qua callback bất đồng bộ.

Kafka `Consumer.wakeup()` là một ngoại lệ đáng chú ý: nó được thiết kế để có thể được gọi từ thread khác nhằm đánh thức `poll()` hoặc một số phương thức blocking. Tuy nhiên:

- `wakeup()` có thể gây `WakeupException` trên consumer thread.
- Đây là hành động can thiệp vào quá trình poll, **không phải thao tác khôi phục an toàn mặc định**.
- Nếu consumer bị block trong code nghiệp vụ, DB lock hoặc thao tác không phản hồi với Kafka wakeup, `wakeup()` không chữa được nguyên nhân.
- Cần bảo đảm cách Spring container đang xử lý wakeup và lifecycle trong phiên bản hiện tại.
- Không gọi wakeup liên tục ở mọi event khi chưa có giới hạn/cooldown.

Ví dụ **chỉ để minh họa cơ chế, không phải chính sách mặc định**:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    log.error("Consumer appears stuck: {}", event.getListenerId());

    // Chỉ bật khi runbook đã phê duyệt và có điều kiện bảo vệ.
    // if (recoveryPolicy.shouldWakeup(event)) {
    //     event.getConsumer().wakeup();
    // }
}
```

Trong nhiều hệ thống, bước đầu tiên đúng hơn là **thu thập thread dump, log và metric** trước khi stop/restart. Restart ngay có thể làm mất bằng chứng của deadlock và kích hoạt một rebalance không cần thiết.

## 8. Phân biệt poll timeout và max.poll.interval.ms

Hai cấu hình có tên gần nhau nhưng giải quyết các vấn đề khác nhau:

| Cấu hình | Thuộc thành phần | Vai trò |
|---|---|---|
| `ContainerProperties.pollTimeout` | Spring Kafka container | Thời lượng mỗi lời gọi Kafka `poll()` chờ lấy record khi hoạt động bình thường. |
| `noPollThreshold` | Spring Kafka container | Hệ số ngưỡng mà monitor dùng để nhận diện consumer không phản hồi. |
| `monitorInterval` | Spring Kafka container | Chu kỳ monitor đánh giá trạng thái poll. |
| `max.poll.interval.ms` | Kafka consumer client | Giới hạn thời gian giữa các lần `poll()` theo quy tắc consumer group, có thể dẫn đến mất membership/rebalance khi vượt. |
| `session.timeout.ms` | Kafka consumer/group protocol | Liên quan thời gian phát hiện member không còn đáp ứng heartbeat theo cơ chế group. |

**`NonResponsiveConsumerEvent` không đồng nghĩa Kafka đã vượt `max.poll.interval.ms`.** Monitor của Spring Kafka có ngưỡng riêng và có thể phát event trước khi client thực sự bị group coordinator loại, hoặc phát hiện muộn hơn tùy cấu hình.

Ví dụ:

```text
pollTimeout          = 5 giây
noPollThreshold      = 3
monitorInterval      = 10 giây
max.poll.interval.ms = 300 giây

Ngưỡng monitor xấp xỉ 15 giây.
Ngưỡng group poll interval là 300 giây.
```

Một `NonResponsiveConsumerEvent` ở mốc vài chục giây chưa đủ chứng minh consumer đã mất assignment. Ngược lại, nếu listener tiếp tục kẹt nhiều phút, Kafka có thể xử lý timeout group và rebalance; lúc đó event ban đầu giúp cảnh báo trước khi incident lan rộng.

## 9. Poll bị chặn hay listener xử lý quá lâu?

Đây là câu hỏi quan trọng nhất khi triage. Event nói consumer không tiến triển poll; lý do có thể là:

**Trường hợp A — Bị kẹt ở Kafka client `poll()`:**

```text
Consumer thread
  -> KafkaConsumer.poll()
       -> network/coordinator/selector ...
          (đang chờ bất thường)
```

Điều tra broker/network, DNS, TLS, coordinator, client logs, Kafka request latency và thread dump.

**Trường hợp B — Poll đã trả record nhưng listener giữ thread quá lâu:**

```text
Consumer thread
  -> KafkaMessageListenerContainer.invokeListener(...)
       -> OrderService.process(...)
            -> RestClient.execute(...)
               (HTTP timeout rất dài)
```

Điều tra timeout của dependency, thread pool, database locks và xử lý record. Đừng tập trung sửa Kafka broker nếu thread dump cho thấy consumer đang kẹt trong HTTP client.

**Trường hợp C — JVM stop-the-world GC hoặc CPU starvation:**

```text
Nhiều application threads cùng ngừng tiến triển
GC pause dài / CPU throttling / scheduler starvation
```

Điều tra GC logs, CPU quota, container throttling và memory pressure. Nếu toàn JVM có dấu hiệu không tiến triển, một Kafka-specific restart có thể chỉ che giấu vấn đề tài nguyên.

**Trường hợp D — Transaction hoặc rebalance callback bị chặn:**

```text
Consumer thread
  -> commit callback / after rollback /
     rebalance listener / transaction integration
       -> blocking operation
```

Đánh giá các callback do ứng dụng tự viết, thời gian xử lý, deadlock và trạng thái transaction coordinator.

## 10. Tương quan với consumer lag và group assignment

Khi consumer không poll, committed offset có thể ngừng tiến và consumer lag có thể tăng nếu producer vẫn ghi record. Nhưng **lag tăng không nhất thiết có nghĩa consumer bị kẹt trong poll**: nó cũng có thể do tải đầu vào vượt throughput, retry nhiều hoặc partition bị pause có chủ đích.

Ví dụ:

```text
orders-2
  committed offset = 150
  log end offset   = 350
  lag              = 200

Sau 60 giây:
  committed offset = 150
  log end offset   = 550
  lag              = 400
```

Nếu cùng thời gian có `NonResponsiveConsumerEvent` cho listener sở hữu `orders-2`, đó là tín hiệu mạnh cần điều tra consumer thread. Nhưng vẫn phải xác định:

- Partition hiện tại có assigned cho consumer không?
- Container có đang pause toàn bộ hoặc pause riêng partition?
- Record có đang retry/processing trong một listener invocation dài?
- Group có rebalance khiến assignment thay đổi?
- Producer có thực sự vẫn ghi dữ liệu hay không?

Có thể kiểm tra group qua CLI:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service

kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group order-service \
  --members --verbose
```

Các lệnh này giúp thấy assignment, member, committed offset và lag. Kafka CLI **không trực tiếp phản ánh `NonResponsiveConsumerEvent` của Spring**; sự kiện đó được phát trong JVM và cần đọc từ log/metric của ứng dụng.

## 11. NonResponsiveConsumerEvent khác các application event khác

Spring Kafka có nhiều event liên quan đến consumer lifecycle và pause/resume:

| Event | Tín hiệu | Không nên hiểu nhầm |
|---|---|---|
| `NonResponsiveConsumerEvent` | Monitor phát hiện consumer không tiến triển poll vượt ngưỡng. | Không chứng minh broker down hoặc đã mất assignment. |
| `ConsumerPausedEvent` | Consumer/container được pause ở cấp tương ứng. | Không nhất thiết là sự cố; có thể pause do vận hành. |
| `ConsumerResumedEvent` | Consumer/container được resume. | Không bảo đảm backlog đã xử lý hết. |
| `ConsumerPartitionPausedEvent` | Một partition đã được pause theo API hỗ trợ. | Không làm Kafka group chuyển partition sang member khác. |
| `ConsumerPartitionResumedEvent` | Một partition đã được resume. | Không tự chứng minh listener xử lý thành công. |
| `ConsumerStoppedEvent` | Consumer thread/container dừng, kèm nguyên nhân theo phiên bản. | Không phải chỉ báo duy nhất của non-responsive poll. |

Các event có thể xuất hiện gần nhau trong một incident. Ví dụ listener bị kẹt, monitor phát `NonResponsiveConsumerEvent`, operator quyết định stop container rồi nhận `ConsumerStoppedEvent`. Đây là **chuỗi trạng thái**, không phải nhiều sự cố độc lập.

Nếu container pause có chủ đích, vẫn cần hiểu cách monitor đo poll trong phiên bản hiện tại; không mặc định “pause” đồng nghĩa “consumer không phản hồi”. Khi pause đúng cách, container vẫn có thể tiếp tục `poll()` để duy trì group membership.

## 12. Thiết kế cảnh báo với ngưỡng hợp lý

Không đặt `noPollThreshold` thấp chỉ để có nhiều alert hơn. Nên lựa chọn dựa trên:

1. `pollTimeout` thực tế của listener container.
2. Thời gian xử lý record bình thường và p99 processing latency.
3. Timeout của HTTP/database và retry/backoff.
4. `max.poll.interval.ms` và yêu cầu về consumer group stability.
5. Độ trễ cảnh báo mong muốn, `monitorInterval` và chi phí false positive.
6. Khả năng ứng dụng tự hồi phục sau một đợt downstream chậm.

Ví dụ một service có p99 xử lý record khoảng 2 giây và `pollTimeout=5s` có thể bắt đầu với ngưỡng monitor khoảng vài chục giây rồi hiệu chỉnh từ số liệu. Nhưng service xử lý batch 90 giây sẽ cần chính sách riêng; ngưỡng 15 giây có thể cảnh báo cho các batch hợp lệ, dù đó vẫn là dấu hiệu cần xem nếu liên quan `max.poll.interval.ms`.

Nên có hai cấp cảnh báo:

- **Warning:** một listener vượt ngưỡng non-responsive trong một hoặc vài lần monitor, chưa có dấu hiệu mất group.
- **Critical:** nhiều member cùng bị ảnh hưởng, lag tăng nhanh, commit offset đứng yên kéo dài, group rebalance liên tục hoặc downstream có SLA vi phạm.

Không bắt buộc phải triển khai đúng hai cấp; quan trọng là phân biệt **triệu chứng tạm thời** với **sự cố cần can thiệp khẩn cấp**.

## 13. Tránh restart storm khi tự động khôi phục

Một automation đơn giản:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    container.stop();
    container.start();
}
```

**Không nên triển khai nguyên mẫu này.** Event có thể lặp lại, monitor thread có thể khác consumer thread, stop/start có lifecycle riêng và nhiều sự kiện gần nhau có thể gây restart liên tục, rebalance storm hoặc che dấu nguyên nhân gốc.

Một bộ điều khiển tự khôi phục tốt hơn cần:

- Ghi lại lần đầu phát hiện, số lần lặp và thời gian kéo dài.
- Thu thập thread dump hoặc thông tin stack trước can thiệp nếu hệ thống cho phép.
- Chỉ kích hoạt recovery khi thỏa một **chính sách rõ ràng** (ví dụ liên tục không tiến triển qua nhiều lần monitor, không đang deploy, không pause có chủ đích).
- Giới hạn số lần restart trong một khoảng thời gian và có cooldown.
- Điều phối lifecycle trên thread/executor phù hợp, không block event listener.
- Kiểm tra Kafka group rejoin, assignment, committed offset và lag sau restart.
- Escalate cho operator nếu không phục hồi hoặc lập tức tái diễn.

Khi consumer đang có Kafka transaction, restart có thể làm transaction abort và record được giao lại. Hãy đảm bảo listener idempotent và kiểm soát side effect ngoài Kafka trước khi tự động stop/start.

## 14. Runbook: NonResponsiveConsumerEvent sau deployment

Giả sử sau khi triển khai bản mới, log có:

```text
Kafka consumer not responsive:
listenerId=orders-consumer-0
timeSinceLastPollMs=48000
partitions=[orders-2, orders-5]
```

Đây là log minh họa của ứng dụng, không phải format mặc định bắt buộc của Spring Kafka.

**Bước 1 — Xác định phạm vi.** Có bao nhiêu pod/listener gặp event? Topic/partition nào đang assigned? Một instance bị ảnh hưởng hay tất cả consumer trong group?

**Bước 2 — Thu thập trạng thái.** Lấy thời điểm event, `pollTimeout`, `noPollThreshold`, `monitorInterval`, `max.poll.interval.ms`, committed offset, lag và tình trạng deployment.

**Bước 3 — Lấy thread dump.** Tìm consumer thread đang đứng ở `poll()`, listener code, HTTP/DB call, commit/transaction hay callback. Không kết luận nguyên nhân chỉ từ tên exception/event.

**Bước 4 — Kiểm tra Kafka cluster.** Xem broker/controller/coordinator health, network, DNS/TLS, request latency và client log nếu thread đang chờ Kafka client.

**Bước 5 — Kiểm tra dependency.** Nếu thread bị block trong listener, xem HTTP/database timeout, lock, queue depth, thread pool và circuit breaker.

**Bước 6 — Kiểm tra JVM/host.** Xem GC pauses, CPU throttling, memory pressure, OOM và dấu hiệu thread starvation.

**Bước 7 — Quyết định can thiệp.** Có thể sửa dependency, hạn chế concurrency, pause consumption, điều chỉnh timeout hoặc thực hiện restart có kiểm soát. Không sửa bằng cách chỉ tăng `noPollThreshold` để giấu sự cố.

**Bước 8 — Xác nhận phục hồi.** Consumer quay lại poll bình thường, group assignment ổn định, committed offset tiến, lag giảm, tỷ lệ lỗi và DLT không tăng bất thường.

**Bước 9 — Hậu kiểm.** Lưu thread dump/metric, xác định root cause, cải thiện timeout hoặc instrumentation và cập nhật runbook để lần sau không tạo restart storm.

Không reset consumer offset hay seek tới log end chỉ vì consumer bị kẹt; các thao tác đó có thể bỏ qua record chưa xử lý.

## 15. Nếu event xuất hiện nhưng pod vẫn Ready

Kubernetes `readinessProbe` có thể kiểm tra HTTP endpoint trả 200 trong khi Kafka consumer thread đang block. JVM vẫn chạy, thread HTTP còn rảnh và pod tiếp tục nhận traffic, nên Kubernetes không tự thay pod.

Một health signal cho Kafka consumption có thể kết hợp:

- `NonResponsiveConsumerEvent` gần nhất và thời gian kể từ đó.
- Thời điểm poll/commit offset cuối cùng theo container/metric phù hợp.
- Trạng thái listener container đang running và assigned partitions.
- Consumer lag đang tăng hay không.
- Container có pause chủ đích theo incident hay không.
- Group rebalance hoặc exception khác gần thời điểm đó.

Không nhất thiết đưa **mỗi** `NonResponsiveConsumerEvent` vào readiness failure ngay lập tức; nếu readiness liên tục flip, hệ thống có thể gây nhiều pod restart/rebalance đồng thời. Có thể chọn alert trước, tự khôi phục giới hạn sau, và chỉ đánh fail readiness khi consumer đã thực sự không đáp ứng SLO.

Liveness failure có thể khiến pod bị restart bằng cơ chế Kubernetes; đây là hành động mạnh cần cân nhắc khi record có side effect chưa commit. Nếu áp dụng, phải có idempotency, grace period và đủ năng lực của group để xử lý khi member thay thế.

## 16. Kiểm thử hành vi event

Với integration test, có thể dùng Kafka Testcontainers hoặc embedded Kafka, listener container thật và một dependency giả lập. Kịch bản:

1. Tạo topic, consumer group test và cấu hình `pollTimeout`, `noPollThreshold`, `monitorInterval` đủ nhỏ cho môi trường test nhưng không quá sát ngưỡng gây flaky test.
2. Tạo listener bình thường và xác nhận consumer nhận record.
3. Giả lập một handler bị block (ví dụ `CountDownLatch`) hoặc một dependency chậm **trong môi trường test cô lập**.
4. Lắng nghe `NonResponsiveConsumerEvent` bằng một bean `@EventListener`, ghi listener ID và elapsed time.
5. Chờ event với await điều kiện có timeout thay vì `Thread.sleep` cố định.
6. Giải phóng latch để listener quay lại xử lý; kiểm tra consumer tiếp tục poll và committed offset tiến theo ack mode.
7. Nếu cần, kiểm tra monitor không tạo alert mới khi consumer đã hoạt động bình thường.
8. Thêm một test khi pause đúng cách để phân biệt intentional pause với consumer bị block.

Không cố tình khóa consumer thread hoặc gọi Kafka `Consumer.wakeup()` trên topic production để kiểm thử. Những tình huống có khả năng làm group rebalance hoặc xử lý trùng phải dùng môi trường và consumer group riêng.

Khi test dùng blocking listener, timeout của dependency mô phỏng nên ngắn hơn `max.poll.interval.ms` hoặc test cần xử lý rõ khả năng rebalance. Không kết luận test fail vì chưa có event ở giây đúng bằng ngưỡng: `monitorInterval` khiến thời điểm phát hiện có độ trễ.

## 17. Những lỗi vận hành thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Nhiều `NonResponsiveConsumerEvent` lặp cho cùng listener | Consumer vẫn kẹt qua nhiều lần monitor. | Deduplicate alert; kiểm tra thread dump, không restart mỗi event. |
| Event sau một batch xử lý dài | Listener không quay lại poll đủ nhanh. | Đo thời gian batch, giảm `max.poll.records` hoặc tối ưu dependency/timeout. |
| Event xuất hiện ngay cả khi broker healthy | Consumer thread bị block trong code nghiệp vụ, DB hoặc JVM stall. | Tìm stack trace của consumer thread và metric ngoài Kafka. |
| Không thấy event dù consumer lag tăng | Consumer vẫn poll nhưng xử lý chậm, bị pause có chủ đích, hoặc monitor chưa đến chu kỳ. | Kiểm tra `monitorInterval`, pause state, listener throughput và offset. |
| Sau event, group liên tục rebalance | Xử lý lâu vượt `max.poll.interval.ms` hoặc restart storm. | Kiểm tra thời gian xử lý/poll, restart policy và group logs. |
| `wakeup()` không giúp consumer chạy lại | Thread đang kẹt trong HTTP/DB hoặc deadlock ngoài Kafka. | Khắc phục nguyên nhân trong stack, không gọi wakeup lặp. |
| Alert không rõ instance nào lỗi | Metric chỉ gắn topic hoặc group, thiếu listener ID/pod. | Thêm listener ID, instance/pod, thời gian và assignment vào log. |
| Event hết nhưng lag không giảm | Consumer đã stop, không có assignment hoặc vẫn lỗi khi xử lý. | Kiểm tra container state, group assignment, committed offset và DLT. |
| Monitor cảnh báo quá thường xuyên | `noPollThreshold` quá thấp so với xử lý thực tế. | Điều chỉnh sau khi đo p99 processing latency và `max.poll.interval.ms`. |

## 18. Nguyên tắc vận hành

- Dùng `NonResponsiveConsumerEvent` như một **triệu chứng của consumer không tiến triển poll**, không như kết luận nguyên nhân.
- Hiểu quan hệ giữa `pollTimeout`, `noPollThreshold` và `monitorInterval`, đặc biệt đơn vị millisecond so với giây.
- Nhận event bằng `@EventListener` và log listener ID, elapsed time, partition context cùng instance/pod.
- Tách cảnh báo monitor của Spring Kafka khỏi `max.poll.interval.ms` của Kafka client và group membership.
- Không gọi các phương thức `KafkaConsumer` không thread-safe từ event listener; `wakeup()` chỉ dùng khi chính sách khôi phục đã được xác nhận.
- Không stop/start container hoặc restart pod trên **mọi** event mà thiếu deduplication, cooldown và điều kiện bảo vệ.
- Ưu tiên thread dump, dependency latency, broker/client logs, GC và CPU metrics để tìm root cause.
- Kết hợp event với group assignment, committed offset, lag, retry/DLT và business throughput.
- Không reset offset để xóa lag khi chưa xác định record nào đã xử lý.
- Kiểm tra side effect/idempotency nếu một transaction hoặc listener invocation có thể bị abort và giao lại sau restart.
- Kiểm thử trong môi trường cô lập với listener blocking có kiểm soát; đừng phá consumer production để xác nhận event.

**`NonResponsiveConsumerEvent`** bổ sung một lớp giám sát quan trọng cho Spring Kafka: ứng dụng có thể nhận biết khi consumer thread dường như không quay lại hoạt động poll trong thời gian quá ngưỡng, ngay cả khi JVM và pod vẫn sống. Độ tin cậy không đến từ việc event được phát, mà đến từ cách đội vận hành **đặt ngưỡng hợp lý, thu thập bằng chứng, khôi phục có giới hạn và xác nhận offset cùng nghiệp vụ thực sự tiến triển trở lại**.

# noPollThreshold trong Spring Kafka: phát hiện consumer không poll đúng hạn

Trong Spring Kafka, một listener có thể còn chạy trong JVM nhưng **không tiến triển trong vòng gọi `KafkaConsumer.poll()`**. Nguyên nhân có thể là một lệnh `poll()` bị chặn bất thường, listener xử lý quá lâu, một callback bị treo, GC pause kéo dài hoặc consumer thread không được cấp CPU. Những tình huống này nguy hiểm vì service nhìn bên ngoài vẫn còn process, nhưng tiến độ nhận và xử lý message có thể ngừng, consumer lag tăng và cuối cùng consumer group có thể xảy ra rebalance.

`noPollThreshold` là một cấu hình của Spring Kafka listener container giúp **phát hiện sớm dấu hiệu consumer không gọi poll trong khoảng thời gian kỳ vọng**. Nó được sử dụng cùng `pollTimeout` và `monitorInterval`. Khi cơ chế theo dõi nhận thấy đã quá lâu kể từ lần poll gần nhất theo ngưỡng cấu hình, Spring Kafka có thể phát **`NonResponsiveConsumerEvent`** để ứng dụng ghi log, tăng metrics, cảnh báo hoặc phục vụ chẩn đoán.

Điều phải nhớ ngay từ đầu:

- **`noPollThreshold` không phải thời gian tính bằng mili giây.** Nó là một *hệ số* nhân với `pollTimeout` của listener container.
- **`monitorInterval` là chu kỳ kiểm tra.** Sự kiện không nhất thiết được phát chính xác tại thời điểm vượt ngưỡng.
- **`NonResponsiveConsumerEvent` là tín hiệu nghi ngờ, không phải kết luận chắc chắn broker hỏng hay consumer đã chết.**
- **`noPollThreshold` không tự restart consumer, không commit offset, không hủy listener và không điều khiển `max.poll.interval.ms`.** Chính sách phục hồi phải được thiết kế riêng.

Bài học tập trung vào cách hiểu ngưỡng này, cấu hình trong Spring Boot/Spring Kafka, phân biệt non-responsive với idle, pause và rebalance, cùng chiến lược vận hành/kiểm thử để không biến một cảnh báo liveness thành hành động gây mất dữ liệu.

## 1. poll() là trung tâm của vòng đời Kafka consumer

Kafka consumer đọc record bằng cách liên tục gọi `poll()`. Với `@KafkaListener`, listener container của Spring Kafka thực hiện vòng lặp này, gọi listener và phối hợp commit, seek, retry hoặc transaction theo cấu hình.

Một mô hình đơn giản:

```text
Spring Kafka listener container
          |
          v
    KafkaConsumer.poll()
          |
          +-- Không có record --> quay lại poll sau xử lý cần thiết
          |
          +-- Có record --> gọi @KafkaListener
                                  |
                                  +-- Xử lý thành công
                                  +-- Acknowledgement / offset
                                  +-- Retry / recovery khi lỗi
          |
          v
       poll() tiếp
```

Trong mô hình listener đồng bộ, phần xử lý record thường diễn ra trong luồng của consumer container. Nếu một listener chạy quá lâu, consumer thread có thể **không quay lại `poll()` đúng hạn**, dù bản thân `poll()` của Kafka không có lỗi.

Các biểu hiện thường gặp:

1. Consumer vẫn còn trong danh sách thành viên của group nhưng lag tăng.
2. JVM vẫn trả HTTP health check trong khi một consumer thread không tiến triển.
3. Một partition xử lý chậm kéo theo record phía sau chờ lâu.
4. Consumer bị loại khỏi group hoặc rebalance sau khi vi phạm giới hạn liên quan đến poll.
5. Thread dump cho thấy consumer thread đang chờ HTTP response, database lock, future hoặc ở trong Kafka client.

`noPollThreshold` giúp phát hiện tín hiệu “đã lâu không poll” để operator điều tra **trước hoặc trong khi** tác động của tình trạng này lan rộng.

## 2. noPollThreshold được tính như thế nào?

Ba tham số tạo thành cơ chế monitor:

| Thuộc tính | Vai trò | Đơn vị |
|---|---|---|
| `pollTimeout` | Timeout tối đa được truyền cho một vòng poll theo cấu hình container | Mili giây |
| `noPollThreshold` | Hệ số dùng để xác định khoảng thời gian không poll bất thường | Không có đơn vị |
| `monitorInterval` | Chu kỳ tác vụ monitor kiểm tra tiến độ poll | Giây trong API container phổ biến |

Công thức khái niệm:

```text
no-poll threshold time
  = noPollThreshold × pollTimeout
```

Ví dụ:

```text
pollTimeout     = 3.000 ms
noPollThreshold = 3.0
monitorInterval = 10 giây

Ngưỡng cảnh báo  = 3 × 3.000 ms = 9.000 ms
Tác vụ monitor  = kiểm tra định kỳ mỗi 10 giây
```

Nếu monitor phát hiện khoảng thời gian kể từ lần poll gần nhất vượt khoảng 9 giây, container có thể phát `NonResponsiveConsumerEvent`.

**Không nên hiểu “ngưỡng 9 giây” là chắc chắn có event sau đúng 9 giây.** Tác vụ monitor chỉ kiểm tra theo chu kỳ `monitorInterval`, chịu ảnh hưởng scheduler, CPU, GC và lifecycle. Một lần không poll vượt ngưỡng có thể được phát hiện muộn hơn hoặc không được quan sát nếu nó đã kết thúc trước lần monitor kiểm tra.

### 2.1. Một ví dụ timeline

```text
Thời gian (giây)
0        5        9       10       15       20
|--------|--------|--------|--------|--------|
^                                   ^
poll cuối                            consumer vẫn chưa poll

Ngưỡng cấu hình = 9 s
Monitor mỗi 10 s

Tại t=10: monitor thấy elapsed=10s > 9s -> phát event
Tại t=20: nếu vẫn không poll, monitor có thể tiếp tục
         ghi nhận trạng thái không responsive tùy implementation
```

Ví dụ giả định lịch monitor bắt đầu tại cùng mốc thời gian để dễ hình dung. Trong runtime thực tế, phase của scheduled task có thể lệch và không đảm bảo chính xác các mốc đó.

### 2.2. noPollThreshold không phải max.poll.interval.ms

`max.poll.interval.ms` là thuộc tính của Kafka consumer client, biểu diễn khoảng thời gian tối đa được phép giữa những lần gọi `poll()` trước khi consumer có nguy cơ bị coi là không tiến triển và mất quyền sở hữu partition theo protocol.

`noPollThreshold` chỉ điều khiển **cơ chế quan sát ở Spring Kafka**. Một event được phát không tự làm Kafka group rebalance. Ngược lại, Kafka có thể xử lý việc mất consumer ownership dù Spring Kafka monitor chưa phát kịp event.

Mục tiêu vận hành thường là đặt ngưỡng monitor đủ sớm để còn thời gian điều tra trước giới hạn liveness của consumer group, nhưng tránh alert giả trong những đợt xử lý hợp lệ kéo dài.

## 3. Ba loại thời gian: poll timeout, monitor interval, max poll interval

Những thời gian này thường bị nhầm lẫn:

| Cấu hình | Thuộc lớp | Điều nó giới hạn/quyết định |
|---|---|---|
| `pollTimeout` | Spring Kafka container | Khoảng chờ của một lần `poll()` |
| `noPollThreshold` | Spring Kafka container | Hệ số để nhận diện quá lâu không poll |
| `monitorInterval` | Spring Kafka container | Chu kỳ kiểm tra của monitor |
| `max.poll.interval.ms` | Apache Kafka consumer | Giới hạn liveness theo tiến độ gọi poll |
| `session.timeout.ms` | Apache Kafka consumer | Giới hạn phát hiện session không còn sống theo group protocol |
| `heartbeat.interval.ms` | Apache Kafka consumer, tùy group protocol | Nhịp heartbeat khi được client quản lý theo cấu hình |
| `idleEventInterval` | Spring Kafka container | Khoảng không có record để phát idle event |

Cùng một con số `30000` có thể có ý nghĩa rất khác theo từng thuộc tính.

### 3.1. pollTimeout thấp không đồng nghĩa throughput cao

`pollTimeout` chi phối khoảng chờ một lần poll khi thiếu dữ liệu và cách container lặp poll. Giảm timeout quá thấp có thể làm poll loop thức dậy thường xuyên hơn và tăng overhead không cần thiết.

Nếu thay `pollTimeout` từ 5 giây xuống 1 giây nhưng giữ `noPollThreshold=3`, ngưỡng monitor cũng giảm từ 15 giây xuống 3 giây. Đây có thể là một thay đổi **cảnh báo** không được dự đoán trước nếu người vận hành nghĩ chỉ chỉnh latency.

Cần xem `pollTimeout` và `noPollThreshold` như một cặp khi đặt alert policy.

### 3.2. monitorInterval quá dài sẽ phát hiện muộn

Giả sử:

```text
pollTimeout = 2s
noPollThreshold = 3  -> ngưỡng 6s
monitorInterval = 60s
```

Mặc dù ngưỡng là 6 giây, monitor chỉ chạy theo chu kỳ 60 giây. Một lần treo 20 giây có thể kết thúc trước khi monitor kiểm tra nên không tạo được tín hiệu mong đợi. Vì vậy phải chọn `monitorInterval` dựa trên độ trễ phát hiện chấp nhận được, chi phí scheduling và ngưỡng poll.

### 3.3. max.poll.interval.ms không tự thay đổi khi chỉnh noPollThreshold

Tăng `noPollThreshold` chỉ làm monitor ít nhạy hơn. Nó không tăng khoảng thời gian Kafka cho phép listener ngừng poll. Nếu công việc thật sự cần chạy lâu, phải xử lý kiến trúc, batch size, timeout và poll interval thay vì chỉ che cảnh báo bằng một hệ số lớn.

## 4. Cấu hình noPollThreshold bằng Java

Một cách rõ ràng là cấu hình `ContainerProperties` thông qua listener container factory.

```java
@Configuration
public class KafkaMonitoringConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, String>
            kafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    ConcurrentKafkaListenerContainerFactoryConfigurer configurer) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();

        // Giữ các tùy chỉnh mà Spring Boot đã cấu hình.
        configurer.configure(factory, consumerFactory);

        var properties = factory.getContainerProperties();

        // Mỗi poll có timeout 3 giây.
        properties.setPollTimeout(3_000L);

        // Monitor nghi ngờ non-responsive sau 3 × 3 giây.
        properties.setNoPollThreshold(3.0f);

        // Monitor kiểm tra định kỳ mỗi 10 giây.
        properties.setMonitorInterval(10);

        return factory;
    }
}
```

Cấu hình này minh họa cách giữ nguyên phần cấu hình của Spring Boot rồi điều chỉnh riêng giám sát poll. Tên bean `kafkaListenerContainerFactory` là tên mặc định mà `@KafkaListener` thường sử dụng khi không chỉ định `containerFactory`.

Các kiểu import liên quan:

```java
import org.springframework.boot.autoconfigure.kafka.ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
```

`setNoPollThreshold(3.0f)` sử dụng hằng số kiểu `float`, tương thích với chữ ký nhận float hoặc có thể mở rộng sang double trong phiên bản tương ứng. `setPollTimeout(long)` tính bằng mili giây và `setMonitorInterval(int)` tính theo giây theo các API container phổ biến; xác nhận bằng Javadoc dependency đang dùng.

### 4.1. Nếu không dùng Spring Boot

Khi tự tạo `ConcurrentKafkaListenerContainerFactory`, có thể bỏ `Configurer`, trực tiếp set `ConsumerFactory` và `ContainerProperties`.

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, String> customFactory(
        ConsumerFactory<String, String> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();

    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setPollTimeout(5_000L);
    factory.getContainerProperties().setNoPollThreshold(3.0f);
    factory.getContainerProperties().setMonitorInterval(15);

    return factory;
}
```

Nếu đã có auto-configured error handler, transaction manager, message converter, observation hoặc listener properties của Boot, một factory tùy chỉnh cần kế thừa các thành phần cần thiết. Không mặc định factory tự tạo sẽ có mọi cấu hình của factory mặc định.

### 4.2. Nên cấu hình cho đúng factory

Một ứng dụng có thể có nhiều listener factories:

```java
@KafkaListener(
    topics = "orders.events",
    containerFactory = "ordersContainerFactory"
)
public void onOrder(String payload) {
    // ...
}
```

Khi đó cấu hình `noPollThreshold` trên một factory khác không nhất thiết ảnh hưởng đến listener này. Hãy xác định chính xác factory mà `@KafkaListener` đang sử dụng.

Có thể đặt chính sách khác nhau cho listener có latency thấp và listener xử lý batch dài, nhưng mỗi chính sách phải gắn với SLO và `max.poll.interval.ms` thực tế.

## 5. Giá trị mặc định và nguyên tắc chọn ngưỡng

Trong nhiều phiên bản Spring Kafka, `noPollThreshold` có giá trị mặc định khoảng **3.0** và `monitorInterval` mặc định khoảng **30 giây**. Đây là thông tin tham khảo cần kiểm tra lại theo phiên bản, không nên xây hệ thống giám sát production dựa vào giả định mặc định không được xác minh.

Ví dụ cấu hình tham khảo:

| Workload | pollTimeout | noPollThreshold | Ngưỡng tính toán | monitorInterval |
|---|---:|---:|---:|---:|
| Listener xử lý nhanh | 2 s | 3.0 | 6 s | 5 s |
| Listener thông thường | 5 s | 3.0 | 15 s | 10 s |
| Listener batch có xử lý dài | 5 s | 6.0 | 30 s | 10 s |
| Khảo sát độ nhạy monitor | 1 s | 2.0 | 2 s | 1 s |

Các giá trị chỉ là minh họa, không phải cấu hình mặc định hoặc khuyến nghị chung cho mọi hệ thống. Một listener xử lý record lâu hơn 15 giây thường xuyên mà `noPollThreshold × pollTimeout = 15s` có thể phát event dù nó vẫn đang thực hiện nghiệp vụ hợp lệ.

### 5.1. Đừng tăng ngưỡng chỉ để tắt cảnh báo

Nếu consumer thường xuyên không poll 40 giây vì HTTP dependency không có timeout, tăng `noPollThreshold` thành 20 để “hết alert” không sửa được nguyên nhân. Nó chỉ khiến monitor phát hiện trễ hơn.

Nên kiểm tra:

- Thời gian xử lý listener p95/p99.
- Số record nhận trong một poll (`max.poll.records`).
- Thời gian retry/backoff.
- HTTP/database timeouts.
- JVM GC pause.
- CPU saturation hoặc thread contention.
- Consumer group rebalance rate.

Ngưỡng hợp lý được chọn **sau** khi biết phân bố thời gian poll thực tế và ngưỡng liveness của Kafka.

### 5.2. Không đặt threshold sát poll timeout

Một `poll()` có thể chờ gần hết `pollTimeout` khi không có record. Vì vậy, hệ số quá thấp gần 1 có thể nhạy với jitter thông thường. Một hệ số lớn hơn 1, có khoảng đệm cho scheduler/network, thường giúp giảm false positives.

Khoảng đệm phải dựa trên môi trường thực tế và latency SLO, không có một con số duy nhất phù hợp với tất cả consumer groups.

## 6. NonResponsiveConsumerEvent là gì?

`NonResponsiveConsumerEvent` là sự kiện do Spring Kafka phát khi cơ chế monitor nhận thấy một consumer có dấu hiệu **không poll** trong khoảng thời gian lớn hơn ngưỡng.

Có thể nhận sự kiện qua Spring `@EventListener`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.NonResponsiveConsumerEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaNoPollObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaNoPollObserver.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Kafka consumer appears non-responsive: " +
            "source={}, timeSinceLastPollMs={}",
            event.getSource(),
            event.getTimeSinceLastPoll()
        );
    }
}
```

Giá trị `getTimeSinceLastPoll()` mô tả khoảng thời gian kể từ lần poll gần nhất theo cách Spring Kafka quan sát, thường được dùng để phân tích độ nghiêm trọng của tình huống. Kiểm tra đơn vị trả về theo Javadoc phiên bản đang sử dụng; với API phổ biến giá trị này được diễn giải bằng mili giây.

Sự kiện không mang ý nghĩa:

- Kafka broker chắc chắn đã mất kết nối.
- Consumer đã bị loại khỏi group.
- Toàn bộ listener container không còn running.
- Offset commit chắc chắn thất bại.
- Việc gọi `stop()` hoặc `restart()` là an toàn ngay tại thời điểm event.

Nó là tín hiệu để kết hợp với metrics và log, từ đó điều tra nguyên nhân thực tế.

### 6.1. Event source trong container có concurrency

Nếu một listener có concurrency nhiều hơn 1, mỗi child consumer có poll loop riêng. Có thể xảy ra một consumer con bị chậm trong khi các consumer khác vẫn poll tốt.

Đừng chuyển một event của một consumer thành kết luận “toàn bộ service đã chết” nếu chưa xem source/container identity, client ID, partition assignment và tiến độ của các child khác.

Nên phân tích theo:

- Listener ID logic.
- Container/concurrent-child identity.
- Topic/partition assignment.
- Consumer group.
- Pod/instance.
- Thời điểm phát event.

Các ID chi tiết có thể được dùng trong log/traces; metric labels cần được chuẩn hóa để tránh cardinality quá cao.

## 7. noPollThreshold và ListenerContainerIdleEvent là hai câu chuyện khác nhau

Một consumer có thể **poll rất đều** nhưng không nhận được record vì producer chưa gửi gì. Đó là *idle* theo dữ liệu, không phải consumer bị treo.

Ngược lại, consumer có thể có backlog rất lớn nhưng **không poll** vì listener đang kẹt trong một HTTP call. Đó là dấu hiệu non-responsive.

| Trạng thái | Có poll thường xuyên? | Có record mới? | Event phù hợp |
|---|---|---|---|
| Topic rỗng, consumer vẫn poll | Có | Không | `ListenerContainerIdleEvent` (khi bật idle interval) |
| Listener kẹt lâu | Không đủ thường xuyên | Có thể backlog | `NonResponsiveConsumerEvent` |
| Container pause và duy trì polling | Có thể vẫn poll | Delivery có thể tạm dừng | `ConsumerPausedEvent`/pause state |
| Consumer group rebalance | Có thể gián đoạn | Tùy tình huống | Rebalance callbacks/consumer metrics |
| Container đã stop | Không | Không | Lifecycle events như `ContainerStoppedEvent` |

### 7.1. Idle không phải dấu hiệu lỗi

`idleEventInterval` điều khiển khi nào Spring Kafka phát sự kiện cho listener container không nhận record trong một khoảng thời gian. Nó phù hợp để phát hiện topic không có dữ liệu theo business expectation.

`noPollThreshold` ngược lại kiểm tra **liveness của vòng poll**, không kiểm tra producer có gửi message không.

Nếu dashboard chỉ có “no message received” và không có “poll progress”, đội vận hành khó phân biệt hệ thống không có traffic với consumer bị treo.

### 7.2. Idle và non-responsive có thể cùng xuất hiện ở thời điểm khác nhau

Một listener ban đầu idle hợp lệ nhưng sau đó bị kẹt trong callback hoặc dependency call. Khi đó nó có thể không poll nữa và monitor phát `NonResponsiveConsumerEvent`.

Không dùng idle event như bằng chứng rằng consumer luôn khỏe mạnh sau thời điểm event được phát. Sự kiện chỉ phản ánh một khoảng thời gian và một kiểu quan sát.

## 8. non-responsive và max.poll.interval.ms

`max.poll.interval.ms` giới hạn khoảng thời gian giữa các lần `poll()` mà Kafka consumer được phép không tiến triển trong group protocol. Nếu xử lý một batch quá lâu, consumer có thể mất assignment, gây redelivery và rebalance.

Giả sử:

```text
pollTimeout               = 5 giây
noPollThreshold           = 3.0
Ngưỡng Spring monitor     = 15 giây
monitorInterval           = 10 giây
max.poll.interval.ms      = 300.000 ms = 5 phút
```

Sự kiện non-responsive có thể xuất hiện sau vài chục giây, **trước rất lâu** khi consumer vi phạm `max.poll.interval.ms`. Đó là lợi ích của monitor: tạo tín hiệu sớm để điều tra.

Nhưng không có quan hệ bắt buộc giữa hai ngưỡng:

- Nếu Spring monitor có `noPollThreshold` quá cao hoặc `monitorInterval` dài, Kafka có thể quyết định consumer không hợp lệ trước khi monitor phát hiện.
- Nếu monitor quá nhạy, nó có thể phát event khi listener vẫn đang xử lý một batch hợp lệ.
- Nếu consumer thread bị treo nghiêm trọng, event có thể phát từ monitor scheduler nhưng callback xử lý event cũng có thể bị ảnh hưởng bởi CPU starvation hoặc shutdown.

### 8.1. max.poll.records và tổng thời gian một poll

Một nguyên nhân thường gặp là tính toán thời gian theo **một record**, trong khi container nhận **nhiều record trong một poll**.

Ví dụ:

```text
max.poll.records = 200
Mỗi record xử lý trung bình 150 ms
Tổng thời gian lý thuyết: 200 × 150 ms = 30 giây
Chưa tính network, database, GC và error handling
```

Nếu `noPollThreshold × pollTimeout = 15s`, monitor có thể phát event trong khi listener vẫn tuần tự xử lý batch.

Cách khắc phục đúng là cân nhắc giảm `max.poll.records`, tối ưu xử lý, tăng concurrency theo partition hoặc chuyển kiến trúc xử lý công việc dài sang durable queue. Chỉnh ngưỡng giám sát chỉ là bước bổ sung, không thay thế sizing workload.

### 8.2. session timeout và heartbeat không phải poll progress

Heartbeat có thể được consumer client thực hiện theo cơ chế riêng và group protocol. Một consumer có thể vẫn được xem là kết nối trong một khoảng thời gian nhưng ứng dụng không tiếp tục poll đủ nhanh.

Vì vậy `session.timeout.ms` và `heartbeat.interval.ms` không thay thế `noPollThreshold`. Chúng giải quyết các khía cạnh khác nhau của group membership và liveness.

Không suy ra “heartbeat còn gửi được” nghĩa là listener đang xử lý message bình thường.

## 9. Các nguyên nhân làm poll không tiến triển

### 9.1. Listener gọi dependency lâu hoặc treo

```java
@KafkaListener(topics = "orders.events")
public void onOrder(String json) {
    remoteService.callWithoutTimeout(json);
}
```

Nếu HTTP client không có connect/read timeout phù hợp, listener có thể bị kẹt trong một lời gọi bên ngoài. Consumer thread không quay lại `poll()` đúng thời hạn.

Biện pháp:

- Đặt HTTP connect, read và overall deadline.
- Sử dụng circuit breaker/bulkhead phù hợp với nghiệp vụ.
- Trả exception về Spring Kafka error handler khi không thể hoàn tất.
- Dùng retry có giới hạn và backoff thay vì vòng lặp vô hạn trong listener.

### 9.2. Database lock hoặc connection pool exhaustion

Một database transaction có thể chờ lock, hoặc listener chờ lấy connection từ pool quá lâu.

Các chỉ số cần ghép:

- Hikari active/idle/pending connections.
- JDBC query latency.
- Database lock waits/deadlocks.
- Transaction duration.
- Consumer poll progress và group lag.

Một cảnh báo non-responsive lúc này có thể là hệ quả của database chậm, không phải Kafka broker lỗi.

### 9.3. Retry/backoff chặn consumer thread

Một error handler hoặc code ứng dụng có thể chờ retry theo cách khiến thread không quay lại poll đủ thường xuyên.

Với Spring Kafka hiện đại, `DefaultErrorHandler` và `ContainerPausingBackOffHandler` có các lựa chọn liên quan đến retry/backoff và duy trì polling. Khi cần chờ lâu, cân nhắc cơ chế container pausing backoff thay vì sleep trực tiếp hàng phút trong listener.

Cần phân biệt: backoff theo policy là delay có chủ đích, nhưng nó vẫn có thể kéo dài tiến độ poll nếu cơ chế chờ không được cấu hình tương thích với container.

### 9.4. Một lời gọi Kafka poll hoặc callback bị chặn

Mục đích ban đầu của non-responsive monitor cũng bao gồm việc quan sát consumer có vẻ kẹt trong thao tác `poll()` hoặc các bước liên quan.

Có thể gặp tình huống network, metadata, interceptor, deserializer, callback hoặc Kafka client xử lý bất thường. Thread dump và Kafka client debug metrics giúp tìm điểm chờ cụ thể.

Không kết luận “broker lỗi” chỉ từ `NonResponsiveConsumerEvent` mà chưa xem stack trace/thread dump.

### 9.5. JVM và tài nguyên máy

Stop-the-world GC, CPU throttling, memory pressure, scheduler starvation hoặc thread deadlock có thể khiến monitor và consumer thread đều bị chậm.

Nếu nhiều consumers trên nhiều topics đồng thời phát tín hiệu non-responsive, nên kiểm tra tài nguyên chung của pod/node trước khi coi từng topic có lỗi độc lập.

## 10. Quan sát bằng metrics và structured logs

Một `@EventListener` có thể tăng counter ứng dụng mỗi khi nhận event.

```java
@Component
public class KafkaPollMonitorMetrics {

    private final MeterRegistry registry;

    public KafkaPollMonitorMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        registry.counter(
                "app.kafka.consumer.non_responsive.events",
                "source_type",
                event.getSource().getClass().getSimpleName()
        ).increment();

        registry.summary(
                "app.kafka.consumer.no_poll.elapsed",
                "source_type",
                event.getSource().getClass().getSimpleName()
        ).record(event.getTimeSinceLastPoll());
    }
}
```

Trong ví dụ này, `MeterRegistry` là Micrometer, tên `app.kafka.*` là **metric tùy chỉnh**, không phải Spring Kafka tự xuất sẵn những tên đó.

`DistributionSummary` ghi thời gian dưới dạng số tổng quát; nếu muốn hệ thống histogram ghi duration có đơn vị rõ ràng, có thể dùng `Timer` với `TimeUnit.MILLISECONDS`. Khi đổi representation, bảo đảm dashboard và alert không nhầm mili giây với giây.

### 10.1. Một log đáng dùng khi điều tra

```json
{
  "event": "kafka_non_responsive_consumer",
  "service": "orders-service",
  "listenerId": "orders-listener",
  "consumerInstance": "orders-pod-2",
  "timeSinceLastPollMs": 24750,
  "pollTimeoutMs": 5000,
  "noPollThreshold": 3.0,
  "monitorIntervalSeconds": 10
}
```

Đây là cấu trúc log minh họa do ứng dụng ghi. Các trường cấu hình như `pollTimeoutMs` và `noPollThreshold` phải được lấy từ cấu hình thực tế; Spring Kafka event không nhất thiết tự chứa mọi field trong JSON.

Không gắn message key, offset, event ID, payload hay exception message động vào metric labels. Những định danh chi tiết phù hợp hơn với log/trace để điều tra từng consumer.

### 10.2. Nên có gauge tiến độ riêng

Một counter sự kiện non-responsive chỉ cho biết monitor đã phát cảnh báo bao nhiêu lần. Nó không khẳng định consumer hiện tại còn kẹt hay đã hồi phục.

Dashboard nên kết hợp:

- Event count/rate trong 5–15 phút.
- Khoảng thời gian kể từ poll được quan sát gần nhất.
- Consumer group lag theo partition.
- Processed records rate.
- Listener processing latency p95/p99.
- Rebalance count.
- Container running/paused state.
- JVM CPU, GC pause, thread count.
- DB/HTTP dependency latency.

Nếu monitor ngừng phát event sau khi consumer stop, điều đó **không có nghĩa consumer đã hồi phục**. Cần xem container lifecycle và progress hiện tại.

## 11. Thiết kế cảnh báo: phát hiện nhưng không báo giả liên tục

Một sự kiện đơn lẻ có thể xuất hiện do GC pause hoặc xử lý batch lớn hợp lệ. Thay vì page ngay ở mọi event, nên định nghĩa mức độ nghiêm trọng:

| Mức | Tín hiệu ví dụ | Phản ứng |
|---|---|---|
| Theo dõi | Một event ngắn, lag ổn định | Ghi metrics/log và xem xu hướng |
| Cảnh báo | Nhiều events liên tiếp, không có processed progress | Điều tra thread dump/dependency |
| Nghiêm trọng | Non-responsive + lag tăng nhanh + gần max.poll.interval | Xử lý sự cố, kiểm tra rebalance |
| Mất dịch vụ | Container stopped/consumer lost, backlog không giảm | Theo runbook phục hồi |

Các ngưỡng cụ thể phải lấy từ SLO, throughput và phân bố processing time của dịch vụ.

### 11.1. Tránh tạo restart storm

Không nên thực hiện ngay trong event handler:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    // Không tự động stop/start toàn bộ listener ở mọi event.
}
```

Nếu nguyên nhân là database đang treo, restart consumer ngay có thể chỉ tạo thêm connections/rebalance mà không làm DB khỏe lại.

Nếu cần automation phục hồi, hãy yêu cầu nhiều tín hiệu độc lập, rate limit, cooldown, giới hạn số lần thử và phân biệt planned pause với unexpected stall. Đối với external side effects, bảo đảm idempotency trước khi cưỡng bức restart vì record có thể được giao lại.

### 11.2. Đừng dùng threshold của Spring như SLA tuyệt đối

Nếu `noPollThreshold × pollTimeout = 15s`, monitor không phải một service watchdog được bảo đảm chính xác tuyệt đối. Kết quả còn phụ thuộc `monitorInterval` và khả năng chạy của scheduled monitor.

Đặt SLA theo **business event age, processing latency và consumer lag**, sau đó dùng no-poll events để tìm nguyên nhân của SLO violations.

## 12. Event handler không được điều khiển KafkaConsumer tùy tiện

Trong Spring Kafka, application event có thể được phát từ thread quản lý container hoặc thread monitor. Với custom async `ApplicationEventMulticaster`, event listener còn có thể chạy trên executor riêng.

`KafkaConsumer` không thread-safe, nên callback này **không** phải nơi tùy tiện gọi `poll()`, `seek()`, `commitSync()`, `pause()` hoặc `resume()` trên consumer gốc.

Ví dụ nguy hiểm:

```java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    // Không tự gọi commitSync() hoặc seek() trên KafkaConsumer
    // được lấy từ event từ một thread giám sát.
}
```

Nếu cần kiểm soát tiếp nhận record, ưu tiên `MessageListenerContainer.pause()`, `resume()` hoặc API container phù hợp, và có chính sách vận hành an toàn. Nếu cần dump thread để chẩn đoán, nên thu thập thông tin JVM ở tầng monitoring/diagnostic thay vì sửa trực tiếp trạng thái consumer.

### 12.1. Một event không nên làm phát sinh thao tác nặng

Một logger hoặc counter nhẹ là phù hợp. Ngược lại, đừng để event handler đồng bộ gọi database nhiều giây, chặn gửi alert hoặc gọi external admin API vô thời hạn.

Có thể phát một tín hiệu sang hệ thống quan sát hoặc queue được thiết kế riêng cho operational actions, rồi để controller xử lý có timeout và rate limit.

## 13. Pause/resume liên hệ với noPollThreshold thế nào?

Spring Kafka hỗ trợ pause/resume listener container để giảm intake khi downstream quá tải hoặc một đường recovery không khả dụng.

```java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null) {
    container.pause();
}
```

Trong trạng thái pause bình thường, Spring Kafka vẫn điều phối `poll()` để giữ consumer group liveness dù không deliver thêm record mới từ những partition đã pause. Do vậy **pause không nhất thiết gây `NonResponsiveConsumerEvent`**.

Nếu listener đang bị chặn trong một task trước khi pause có hiệu lực, monitor vẫn có thể nhận thấy không poll; gọi pause không lập tức hủy task đó.

Các trường hợp cần phân biệt:

| Tình huống | Poll progress | NonResponsiveConsumerEvent |
|---|---|---|
| Pause đã áp dụng, consumer vẫn poll | Vẫn có poll | Không nhất thiết |
| Pause được yêu cầu nhưng listener kẹt | Chưa tiếp tục poll | Có thể xảy ra |
| Consumer stop hoàn toàn | Container không chạy | Dùng lifecycle events để theo dõi |
| Long retry backoff dùng container pausing | Có thể tiếp tục poll theo cơ chế handler | Phụ thuộc thực tế |
| Broker không có record | Consumer vẫn poll | Không phải non-responsive chỉ vì rỗng |

Không dùng `noPollThreshold` như cách giám sát trạng thái “đã pause” hoặc như thay thế cho `ConsumerPausedEvent` và container pause state.

## 14. Retry, error handler và các khoảng không poll

Một listener bị lỗi có thể được xử lý bởi `DefaultErrorHandler`, chờ backoff rồi retry.

Ví dụ:

```java
@Bean
CommonErrorHandler commonErrorHandler() {
    return new DefaultErrorHandler(
            new FixedBackOff(2_000L, 2L)
    );
}
```

Đoạn code này minh họa backoff hai giây và tối đa hai lần retry sau lần xử lý đầu. Nhưng tổng thời gian retry của một record còn gồm processing time, exception handling và poll/seek behavior.

Nếu một policy backoff dài hơn `max.poll.interval.ms`, cách thực thi backoff có thể ảnh hưởng liveness. Trong các phiên bản Spring Kafka hỗ trợ, `ContainerPausingBackOffHandler` có thể phối hợp pause container trong backoff dài, cho phép poll loop diễn ra phù hợp hơn so với chặn consumer thread trong toàn bộ khoảng chờ.

**Không thể kết luận có/không NonResponsiveConsumerEvent chỉ từ giá trị FixedBackOff.** Cần hiểu handler sử dụng cơ chế chờ nào và event monitor quan sát poll thật sự ra sao.

### 14.1. Non-responsive không chứng minh lỗi đã được recovery

Một record có thể vừa bị retry, vừa làm consumer tạm không poll, và chưa hề được gửi DLT. Cảnh báo no-poll chỉ phát hiện tiến độ poll bị chậm; nó không nói rằng record đã hết retry hay recovery thành công.

Nếu thiết kế dashboard reliability, cần tách:

- Listener failure rate.
- Retry attempts và backoff time.
- DLT/recovery outcomes.
- Consumer no-poll events.
- Consumer lag và offset commit progress.

## 15. Concurrency và phân tích một consumer bị chậm

Với `@KafkaListener(concurrency = "3")` hoặc `ConcurrentKafkaListenerContainerFactory.setConcurrency(3)`, Spring Kafka thường tạo nhiều child consumer containers.

```text
orders-listener
    |
    +-- consumer-0 --> partitions 0, 3
    +-- consumer-1 --> partitions 1, 4
    +-- consumer-2 --> partitions 2, 5
```

Nếu consumer-1 chậm, các partition 1 và 4 có thể tăng lag; consumer-0 và consumer-2 vẫn tiến triển.

Cách điều tra:

1. Xác định source/child consumer của `NonResponsiveConsumerEvent`.
2. Xem những partitions đang assigned cho child đó.
3. So sánh lag theo partition, không chỉ lag tổng.
4. Xem thread dump của consumer bị chậm.
5. Xem listener processing latency và dependency calls đang chạy.
6. Kiểm tra consumer group có rebalance hay mất assignment không.

Đừng tự động tăng concurrency mà chưa kiểm tra số partitions. Concurrency nhiều hơn partition count không bảo đảm nhiều record của một partition được xử lý song song; số consumer dư có thể không có assignment.

### 15.1. Một event ở child không chứng minh parent đã stop

`NonResponsiveConsumerEvent` là tín hiệu quan sát. `ContainerStoppedEvent` hoặc trạng thái registry mới liên quan đến lifecycle dừng container. Nếu một consumer không poll, parent concurrent container có thể vẫn đang chạy, và các child khác vẫn có thể hoạt động bình thường.

## 16. Khi không có NonResponsiveConsumerEvent nhưng hệ thống vẫn chậm

Đây là một trường hợp vận hành rất quan trọng. Consumer có thể poll đều nhưng xử lý nghiệp vụ vẫn không đáp ứng SLO, chẳng hạn:

- Producer nguồn tăng throughput vượt năng lực consumer.
- Mỗi poll trả nhiều records, nhưng xử lý vẫn nằm dưới ngưỡng monitor.
- Kafka consumer bị pause có chủ đích vì backpressure.
- Retry topic chứa backlog dài trong khi topic gốc không bị kẹt.
- Database side effect đã hoàn tất nhưng downstream còn chậm.
- Một event đang chờ trong durable work queue sau khi Kafka đã ack.
- Consumer lag tăng vì số partition/concurrency không đủ.

Vì vậy, **không có no-poll event không đồng nghĩa dịch vụ khỏe mạnh**. Cần thêm business event latency, consumer lag, throughput, pending work age và dependency health.

### 16.1. Trường hợp poll vẫn chạy nhưng record không được xử lý

Ví dụ một listener dispatch công việc vào in-memory executor rồi trả về rất nhanh:

```java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {
    workerPool.submit(() -> orderService.process(event));
    // Consumer thread có thể tiếp tục poll rất đều.
}
```

Trong ví dụ này, monitor poll có thể hoàn toàn khỏe mạnh nhưng queue nội bộ tăng liên tục hoặc các task bị lỗi sau khi listener đã trả về. Nếu container commit offset trước khi task hoàn tất, dữ liệu có thể mất khi process crash.

Đây là lý do không nên dùng `noPollThreshold` làm thước đo đầy đủ cho reliability. Nếu cần async processing, phải thiết kế ack sau completion hoặc durable inbox/work queue, cùng backpressure và idempotency.

## 17. Tính thời gian phát hiện và lựa chọn cấu hình

Khi đặt cấu hình, có thể ước lượng:

```text
Ngưỡng phát hiện cơ bản:
  T = noPollThreshold × pollTimeout

Độ trễ đến lần monitor tiếp theo:
  từ gần 0 đến khoảng monitorInterval
  (chưa tính scheduler delay / GC / CPU starvation)

Thời điểm event thực tế:
  phụ thuộc thời gian bắt đầu poll, lịch monitor và runtime
```

Ví dụ:

```text
pollTimeout = 4.000ms
noPollThreshold = 4.0
monitorInterval = 5s

T = 4 × 4s = 16s

Nếu consumer ngừng poll tại t=0:
  monitor thấy bất thường ở một lần kiểm tra sau khi T bị vượt.
  Event có thể đến vào khoảng t≈16–21s trong điều kiện scheduler ổn định.
```

Khoảng này là ước lượng mô hình, **không phải SLA hoặc giới hạn chắc chắn**. Nếu scheduler không được chạy đúng hạn do GC/node pause, phát hiện có thể muộn hơn.

### 17.1. Gợi ý chọn cấu hình theo ràng buộc

Một cách chọn thực dụng:

1. Xác định thời gian processing p99 của listener trong workload bình thường.
2. Xác định thời gian tối đa giữa các lần poll khi xử lý một batch thông thường.
3. Xác định `max.poll.interval.ms` và mức độ sớm mong muốn để phát hiện.
4. Chọn `pollTimeout` theo nhu cầu poll loop/latency, không chỉ theo mục tiêu alert.
5. Chọn `noPollThreshold` để ngưỡng lớn hơn jitter hợp lệ nhưng nhỏ hơn khoảng stall cần cảnh báo.
6. Chọn `monitorInterval` đủ ngắn để event có giá trị chẩn đoán.
7. Bật logs/metrics và đo false positive rate trong môi trường staging.
8. Điều chỉnh theo từng listener factory nếu workload khác nhau.

Nên đặt mỗi ngưỡng cùng mục tiêu: “Nếu consumer không poll hơn X giây, team cần biết trong tối đa khoảng Y giây nữa”.

## 18. Integration test cho noPollThreshold

Để kiểm thử monitor có thể phát hiện một poll stall thực tế, nên dùng Kafka broker test (Testcontainers hoặc EmbeddedKafka) và listener container thực. Mock một `NonResponsiveConsumerEvent` chỉ kiểm tra observer, không chứng minh monitor đang hoạt động.

### 18.1. Cấu hình test với ngưỡng ngắn

Ví dụ:

```java
factory.getContainerProperties().setPollTimeout(1_000L);
factory.getContainerProperties().setNoPollThreshold(2.0f);
factory.getContainerProperties().setMonitorInterval(1);
```

Các giá trị nhỏ dùng cho integration test để không chờ lâu. Production cần cấu hình khác tùy latency, số records mỗi poll và yêu cầu liveness.

### 18.2. Chủ động tạo listener xử lý chậm

Một listener test có thể dùng `CountDownLatch`:

```java
@Component
public class SlowListener {

    private final CountDownLatch entered = new CountDownLatch(1);
    private final CountDownLatch release = new CountDownLatch(1);

    @KafkaListener(
        id = "slow-listener",
        topics = "slow-test-topic",
        groupId = "slow-consumer-group"
    )
    public void listen(String value) throws InterruptedException {
        entered.countDown();

        // Chờ có timeout để test không bị treo vô hạn.
        if (!release.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Test did not release slow listener"
            );
        }
    }

    public boolean awaitEntered() throws InterruptedException {
        return entered.await(10, TimeUnit.SECONDS);
    }

    public void release() {
        release.countDown();
    }
}
```

Khi listener đang chờ latch, consumer thread không tiếp tục vòng poll. Với monitor interval/ngưỡng đủ ngắn và broker chạy ổn định, `NonResponsiveConsumerEvent` có thể được phát.

Đảm bảo `finally` của integration test gọi `release()` để không giữ thread nếu assertion thất bại.

### 18.3. Quan sát event bằng probe bean

```java
@Component
public class NonResponsiveEventProbe {

    private final BlockingQueue<NonResponsiveConsumerEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void capture(NonResponsiveConsumerEvent event) {
        events.offer(event);
    }

    public NonResponsiveConsumerEvent await(
            long timeout,
            TimeUnit unit) throws InterruptedException {
        return events.poll(timeout, unit);
    }
}
```

Một test có thể:

1. Tạo Kafka topic và listener container riêng.
2. Gửi một record để listener bắt đầu.
3. Đợi `entered` latch xác nhận listener đang bị chặn.
4. Đợi probe nhận một `NonResponsiveConsumerEvent` trong khoảng timeout hợp lý.
5. Xác nhận event đến từ listener/container mong muốn.
6. Xác nhận `timeSinceLastPoll` phản ánh khoảng không poll đáng kể.
7. Giải phóng listener và cho container tiếp tục polling.
8. Kiểm tra consumer xử lý tiếp các record và group ổn định.

Không assert event xuất hiện chính xác ở mili giây thứ 2. Monitor chạy theo chu kỳ và CI có scheduler jitter, nên cần timeout đủ rộng.

### 18.4. Kịch bản không có record nhưng vẫn poll

Dùng cùng container khi topic không có message. Consumer poll rỗng đều đặn vẫn phải được phân biệt với consumer không poll. Kiểm tra monitor không liên tục phát event giả chỉ vì topic đang idle.

Nếu muốn đo idle, bật cơ chế idle listener event riêng và xác nhận hai loại event có ý nghĩa khác nhau.

### 18.5. Kịch bản pause

Gọi container `pause()` qua registry, quan sát trạng thái pause thực tế rồi kiểm tra consumer vẫn có polling/liveness theo cơ chế container.

Không dựa vào số lần listener được gọi để kết luận poll còn diễn ra, vì pause chủ đích làm listener không nhận record.

### 18.6. Kịch bản có GC hoặc CPU contention

Trong integration/performance test riêng, tạo tải có kiểm soát hoặc dùng công cụ mô phỏng GC pause để xem event monitor phản ứng ra sao. Không cố tình làm JVM mất kiểm soát trong test thông thường.

Khi phân tích kết quả, đối chiếu poll gaps với JVM pause time để tránh kết luận sai rằng Kafka broker bị lỗi.

## 19. Runbook khi nhận NonResponsiveConsumerEvent

Một runbook tốt nên theo thứ tự **xác định phạm vi → tìm nơi bị chặn → khôi phục an toàn**.

### Giai đoạn A: xác định phạm vi

1. Xác định listener ID, container/child identity, consumer group và pod.
2. Ghi `timeSinceLastPoll`, `pollTimeout`, `noPollThreshold`, `monitorInterval`.
3. Kiểm tra container đang running, paused, stopping hay rebalancing.
4. Kiểm tra consumer lag, các partition có backlog, số records xử lý gần nhất.
5. Xác định event xảy ra đơn lẻ hay kéo dài/nhiều consumers cùng lúc.

### Giai đoạn B: điều tra nguyên nhân

1. Thu thread dump của consumer thread bị nghi ngờ.
2. Kiểm tra HTTP/database calls, lock waits, thread pool saturation.
3. Kiểm tra retry/backoff, đặc biệt long blocking retries.
4. Kiểm tra JVM GC, CPU throttling, memory pressure.
5. Kiểm tra Kafka client metrics, metadata/network errors và broker health.
6. So sánh với `max.poll.interval.ms`, `max.poll.records` và batch duration.

### Giai đoạn C: phục hồi

1. Khắc phục dependency hoặc code khiến listener bị chặn.
2. Nếu cần pause/backpressure, dùng container APIs và đảm bảo polling phù hợp.
3. Chỉ restart/stop khi đã đánh giá việc redelivery và in-flight side effects.
4. Đảm bảo offset chưa xử lý không bị ack/commit trước.
5. Kiểm tra idempotency khi consumer có thể nhận lại cùng record.
6. Theo dõi lag giảm và business throughput phục hồi.
7. Điều chỉnh ngưỡng monitor **sau** khi có dữ liệu latency thực tế.

### 19.1. Một tình huống thực tế

Hệ thống xử lý order có consumer lag tăng từ 1.000 lên 50.000 records trong 10 phút. Monitor ghi nhận một child consumer không poll hơn 40 giây, nhưng các child khác vẫn tiến triển.

Thread dump cho thấy child đó bị chặn ở database lock. Nếu chỉ tăng `max.poll.interval.ms` hoặc `noPollThreshold`, database lock vẫn tồn tại và backlog tiếp tục tăng. Hướng xử lý là giải quyết contention/timeout database, giảm thời gian transaction, cân nhắc giảm `max.poll.records` hoặc thay đổi concurrency, rồi kiểm tra redelivery/idempotency.

No-poll event trong trường hợp này là **tín hiệu chỉ đường** chứ không phải nguyên nhân gốc.

## 20. Những sai lầm phổ biến

**Nghĩ noPollThreshold tính bằng milliseconds.** Nó là hệ số nhân `pollTimeout`. Thay `pollTimeout` cũng làm đổi ngưỡng monitor.

**Nghĩ event xuất hiện đúng lúc chạm ngưỡng.** `monitorInterval` và scheduler tạo độ trễ; event không phải real-time watchdog.

**Đồng nhất non-responsive với idle.** Consumer không có message vẫn có thể poll khỏe mạnh. Idle event và non-responsive event là hai quan sát khác nhau.

**Tăng noPollThreshold để che listener đang treo.** Chỉ làm phát hiện muộn hơn; không sửa HTTP timeout, DB lock hoặc CPU starvation.

**Coi event là chắc chắn broker mất kết nối.** Nguyên nhân có thể nằm trong listener, error handler, JVM hoặc dependency.

**Tự gọi KafkaConsumer.seek/commitSync từ @EventListener.** Kafka Consumer không thread-safe, event handler có thể không chạy trên consumer thread.

**Restart container ở mỗi event.** Dễ tạo restart/rebalance storm và duplicate side effects.

**Coi absence of event là health.** Monitor có thể không được chạy đúng lịch hoặc service vẫn chậm vì queue/backlog dù poll đều.

**Bỏ qua monitorInterval.** Ngưỡng ngắn nhưng monitor kiểm tra mỗi phút có thể không phát hiện các stall ngắn cần quan tâm.

**Chỉ xem lag tổng của group.** Một child consumer hoặc một partition có thể bị kẹt trong khi các partition khác vẫn chạy tốt.

**Không kiểm tra max.poll.records.** Batch quá lớn có thể khiến consumer không poll trong thời gian dài dù mỗi record xử lý nhanh.

**Nhầm pause với non-responsive.** Container pause có chủ đích thường vẫn poll; cần metrics pause riêng.

**Phát hành cảnh báo thiếu bối cảnh.** Event count đơn lẻ không cho biết thời gian xử lý, dependency, group lag và trạng thái hiện tại.

**Dùng monitor event để kết luận mọi offset đã commit hay chưa.** Event không liên quan trực tiếp tới acknowledgement policy; phải kiểm tra committed offsets và error handler separately.

## 21. Quy trình triển khai production

Với một Spring Kafka service đang vận hành, có thể thực hiện:

1. Xác định từng listener factory và `pollTimeout` thực tế.
2. Đo listener processing latency, thời gian xử lý một poll và consumer lag.
3. Đối chiếu `max.poll.interval.ms`, `max.poll.records` và retry/backoff policy.
4. Cấu hình `noPollThreshold` theo tỷ lệ mong muốn với `pollTimeout`.
5. Cấu hình `monitorInterval` đủ ngắn để phát hiện có ích.
6. Gắn `@EventListener(NonResponsiveConsumerEvent)` ghi log và metric nhẹ.
7. Bổ sung dashboard theo listener, consumer child, lag, poll gaps và dependency latencies.
8. Tách idle, paused, non-responsive và stopped thành các trạng thái khác nhau.
9. Đặt alert trên nhiều tín hiệu, tránh tự restart ở mọi event.
10. Bảo đảm mọi external side effect chịu được redelivery khi consumer bị mất assignment.
11. Kiểm thử poll stall có chủ đích, idle topic và pause trên broker test.
12. Kiểm tra lại getter/defaults/units khi nâng cấp Spring Kafka hoặc Spring Boot.

### 21.1. Câu hỏi code review

Một cấu hình `noPollThreshold=3`, `pollTimeout=5000` và `monitorInterval=30000` **có nghĩa gì**?

- Ngưỡng nghi ngờ không poll là khoảng **15.000 ms**.
- Monitor không kiểm tra liên tục; với chu kỳ 30 giây, event có thể đến muộn hơn nhiều so với 15 giây.
- Nó không thay đổi `max.poll.interval.ms` và không tự restart consumer.
- Sự kiện xuất hiện cần được ghép với processing/lag/GC/dependency metrics để kết luận nguyên nhân.

Nếu đội vận hành chưa giải thích được sự khác biệt giữa **ngưỡng monitor** và **thời điểm phát hiện**, cảnh báo no-poll có thể bị diễn giải sai.

## 22. Tài liệu tham chiếu theo phiên bản

Khi triển khai cần đối chiếu đúng phiên bản Spring Kafka, Spring Boot và Kafka client:

- **Spring for Apache Kafka Reference — Detecting Idle and Non-Responsive Consumers:** `noPollThreshold`, `monitorInterval`, `pollTimeout` và `NonResponsiveConsumerEvent`.
- **Spring Kafka Javadoc — `ContainerProperties`:** `setNoPollThreshold`, `setMonitorInterval`, `setPollTimeout` và các mặc định tương ứng.
- **Spring Kafka Javadoc — `NonResponsiveConsumerEvent`:** event source, elapsed time và metadata consumer/container.
- **Spring Kafka Reference — Application Events:** cách nhận event qua `@EventListener`, event publisher và threading.
- **Spring Kafka Reference — Listener Container Lifecycle:** pause, resume, concurrent containers và shutdown.
- **Spring Kafka Reference — Error Handling:** retry/backoff, `DefaultErrorHandler` và `ContainerPausingBackOffHandler`.
- **Spring Boot Reference — Kafka auto-configuration:** listener factory configurer, consumer properties và container factory.
- **Apache Kafka Documentation — Consumer Configs:** `max.poll.interval.ms`, `max.poll.records`, group membership, `session.timeout.ms`.
- **Micrometer Documentation:** counters, timers, distribution summaries, cardinality và percentile histograms.

Tên method, default value, đơn vị thời gian của event getters và cơ chế scheduling có thể thay đổi theo dependency. Khi nâng cấp, cần xác nhận API/giá trị thực tế thay vì áp dụng số liệu cố định từ ví dụ.

**Kết luận kỹ thuật:** `noPollThreshold` giúp Spring Kafka nhận diện **consumer có dấu hiệu quá lâu không poll**, bằng một ngưỡng tính từ `pollTimeout` và được kiểm tra định kỳ theo `monitorInterval`. Nó là một **tín hiệu liveness để quan sát và điều tra**, không phải bảo đảm consumer đã chết hay một cơ chế phục hồi tự động. Hệ thống đáng tin cậy kết hợp tín hiệu này với listener latency, consumer lag, retry, rebalance, tài nguyên JVM và idempotency để xử lý nguyên nhân gốc mà không làm sai tiến độ offset hoặc trạng thái nghiệp vụ.

# wakeup, WakeupException và dừng consumer an toàn

Kafka consumer thường chạy trong một vòng lặp gọi `poll()` để lấy record. Khi ứng dụng cần dừng, vòng lặp có thể đang chờ dữ liệu hoặc đang xử lý một batch. Nếu chỉ đặt một biến boolean rồi chờ, consumer có thể phải đợi hết thời gian poll hoặc tiếp tục chạy ngoài ý muốn.

Kafka cung cấp `wakeup()` để một thread khác yêu cầu consumer thoát khỏi thao tác đang chờ. Consumer sẽ nhận `WakeupException` ở thread đang sử dụng KafkaConsumer. Ứng dụng cần nhận diện đây là tín hiệu dừng có chủ đích, hoàn tất phần xử lý được phép, commit offset phù hợp và đóng consumer trên chính thread sở hữu nó.

## 1. Vì sao cần dừng consumer có kiểm soát?

Một consumer chạy lâu dài thường thực hiện chu trình:

1. Gọi `poll()` để lấy record.
2. Xử lý record trong ứng dụng.
3. Commit offset sau khi xử lý đạt điều kiện thành công.
4. Quay lại `poll()` để nhận batch tiếp theo.

Khi process nhận tín hiệu dừng, cần bảo đảm:

- Không nhận thêm batch mới ngoài ý muốn.
- Record đã lấy về được xử lý hoặc để lại khả năng đọc lại.
- Offset chỉ tiến lên sau khi công việc tương ứng hoàn tất.
- Consumer rời group và giải phóng network connection, thread cùng tài nguyên nội bộ.
- Thời gian shutdown nằm trong giới hạn của môi trường chạy.

Nếu process kết thúc đột ngột, broker sẽ phát hiện consumer rời group theo cơ chế heartbeat/session timeout và có thể rebalance partition sang consumer khác. Điều này có thể làm tăng thời gian gián đoạn và tạo thêm lần xử lý lặp nếu offset chưa được commit.

## 2. KafkaConsumer không thread-safe

`KafkaConsumer` không được thiết kế để nhiều thread cùng gọi các phương thức như `poll()`, `commitSync()`, `subscribe()` hoặc `close()`. Thông thường, một thread ứng dụng sở hữu consumer và thực hiện toàn bộ thao tác vòng đời của nó.

Có một ngoại lệ quan trọng: **`wakeup()` được thiết kế để gọi an toàn từ thread khác**. Đây là cách chuẩn để yêu cầu thread đang chạy consumer thoát khỏi thao tác chờ.

| Thao tác | Có thể gọi từ thread khác không? | Ghi chú |
|---|---|---|
| `poll()` | Không | Chỉ thread sở hữu consumer gọi |
| `subscribe()` / `assign()` | Không | Không thay đổi subscription từ shutdown thread |
| `commitSync()` / `commitAsync()` | Không | Commit trên thread sở hữu consumer |
| `close()` | Không nên | Để thread sở hữu consumer đóng tài nguyên |
| `wakeup()` | Có | Thread khác có thể gọi để đánh thức consumer |

Không gọi `consumer.close()` trực tiếp trong shutdown hook trong khi thread chính vẫn đang poll hoặc xử lý record. Hãy gọi `wakeup()` từ shutdown thread, sau đó để thread sở hữu consumer đi vào `finally` và đóng consumer.

## 3. wakeup() và WakeupException hoạt động thế nào?

`wakeup()` là tín hiệu đánh thức consumer. Khi thread sở hữu consumer đang ở một thao tác có thể bị đánh thức, chẳng hạn `poll()`, Kafka client ném `WakeupException` để thoát khỏi thao tác đó.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant Hook as Shutdown thread
    participant App as Consumer thread
    participant Kafka as Kafka broker

    App->>Kafka: poll()
    Note over App,Kafka: Consumer đang chờ record
    Hook->>App: consumer.wakeup()
    App->>App: Kafka client đánh thức thao tác poll
    App->>App: WakeupException
    App->>App: Nhận diện đang shutdown
    App->>App: finally -> consumer.close()
~~~

Một số điểm quan trọng:

- `wakeup()` không phải lỗi kết nối broker; nó là tín hiệu điều khiển từ ứng dụng.
- `WakeupException` thường xuất hiện trên thread đang thực hiện thao tác consumer.
- Nếu gọi `wakeup()` khi consumer chưa ở trong `poll()`, thao tác blocking tiếp theo có thể nhận `WakeupException`.
- Nếu consumer đang chạy logic xử lý record trong Java code, `wakeup()` không tự ngắt đoạn code đó. Nó có hiệu lực ở thao tác consumer tiếp theo có thể bị đánh thức.
- Nếu `WakeupException` xuất hiện trong khi ứng dụng không có ý định dừng, cần xử lý như một tín hiệu bất thường và không được âm thầm bỏ qua.

Vì vậy, catch `WakeupException` cần kiểm tra trạng thái shutdown. Không nên bắt exception rồi luôn tiếp tục vòng lặp, vì điều đó có thể làm consumer không bao giờ dừng.

## 4. Mẫu dừng an toàn với shutdown hook

Ví dụ dưới đây dùng một thread chính sở hữu KafkaConsumer và một shutdown hook chỉ thay đổi cờ chạy rồi gọi `wakeup()`.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.errors.WakeupException;
import org.apache.kafka.common.serialization.StringDeserializer;

public class SafeOrderConsumer {

    public static void main(String[] args) {
        Properties props = new Properties();

        props.put(
            ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "order-worker"
        );
        props.put(
            ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(
            ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class.getName()
        );
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);

        AtomicBoolean running = new AtomicBoolean(true);

        KafkaConsumer<String, String> consumer =
            new KafkaConsumer<>(props);

        Thread shutdownHook = new Thread(() -> {
            running.set(false);
            consumer.wakeup();
        }, "kafka-consumer-shutdown");

        Runtime.getRuntime().addShutdownHook(shutdownHook);

        try {
            consumer.subscribe(List.of("orders"));

            while (running.get()) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofMillis(1000));

                // Hoàn tất batch hiện tại trước khi thoát vòng lặp.
                for (var record : records) {
                    processOrder(record.key(), record.value());
                }

                // Chỉ commit sau khi toàn bộ batch đã xử lý thành công.
                if (!records.isEmpty()) {
                    consumer.commitSync();
                }
            }
        } catch (WakeupException exception) {
            // Wakeup là bình thường khi ứng dụng đang shutdown.
            if (running.get()) {
                // Wakeup ngoài ý muốn: truyền lỗi để xử lý ở tầng ứng dụng.
                throw exception;
            }
        } finally {
            // Chỉ thread sở hữu consumer thực hiện close().
            consumer.close(Duration.ofSeconds(10));
        }
    }

    private static void processOrder(String key, String value) {
        // Thay bằng xử lý nghiệp vụ thực tế.
    }
}
~~~

Trong ví dụ:

- Shutdown hook không gọi `poll()`, `commitSync()` hay `close()`.
- Hook đặt `running=false` rồi gọi `wakeup()`.
- Consumer thread bắt `WakeupException` và chỉ xem đó là kết thúc bình thường khi cờ `running` đã tắt.
- `finally` luôn đóng consumer.
- Auto commit bị tắt; ứng dụng chỉ commit sau khi xử lý batch thành công.

Ví dụ hoàn tất batch đã được poll trước khi thoát. Nếu batch có nhiều record hoặc xử lý lâu, hãy đặt `max.poll.records` và giới hạn thời gian xử lý sao cho shutdown không vượt quá grace period của nền tảng. Trong ứng dụng cần dừng nhanh hơn, có thể kiểm tra cờ dừng giữa các record nhưng phải commit offset riêng cho những record đã xử lý liên tục và thành công; không commit vượt qua record chưa hoàn tất.

## 5. Xử lý batch và commit offset khi shutdown

Dừng consumer an toàn phụ thuộc vào thời điểm commit offset. Với manual commit, chỉ commit tiến độ mà ứng dụng đã hoàn tất.

Giả sử `poll()` trả về các offset 10, 11, 12 của partition `orders-0`:

| Tình huống | Offset đã xử lý | Hành động commit phù hợp |
|---|---|---|
| Cả 10, 11, 12 thành công | 10–12 | Commit offset tiếp theo là 13 |
| 10 và 11 thành công, 12 lỗi | 10–11 | Có thể commit 12 để record 12 được đọc lại |
| Chưa xử lý record nào | Không có | Không tiến offset |
| Xử lý xong nhưng commit bị wakeup/timeout | Nghiệp vụ đã chạy, offset chưa chắc được lưu | Có thể đọc lại; xử lý cần idempotent |

Offset commit là vị trí tiếp theo cần đọc. Nếu record cuối cùng đã xử lý là offset 11, commit offset 12 để lần sau consumer tiếp tục từ 12.

### 5.1. Đơn giản: xử lý hết batch rồi commit

Đây là cách dùng trong ví dụ Java phía trên. Chỉ khi mọi record trong batch xử lý thành công, consumer mới gọi `commitSync()`.

Ưu điểm:

- Logic dễ hiểu.
- Không commit vượt qua record chưa xử lý.
- Nếu một record lỗi, batch có thể được đọc lại sau restart hoặc rebalance.

Đánh đổi là những record đã xử lý thành công trước record lỗi có thể được xử lý lại. Vì vậy, handler cần idempotent hoặc dùng event ID để chống side effect trùng.

### 5.2. Xử lý từng record và commit theo partition

Nếu muốn tiếp tục từ record đầu tiên chưa hoàn tất, ứng dụng có thể theo dõi offset tiếp theo cần commit cho từng partition. Chỉ commit offset liên tục đã xử lý thành công; không commit một offset cao hơn khi còn khoảng trống chưa hoàn tất phía trước.

Khi xử lý song song, không thể chỉ lấy offset lớn nhất đã hoàn thành. Ví dụ offset 12 hoàn tất trước offset 11 thì commit 13 có thể làm mất cơ hội đọc lại offset 11. Cần quản lý watermark hoàn tất theo từng partition hoặc thiết kế xử lý tuần tự theo partition.

### 5.3. Không dựa vào close() để lưu tiến độ thủ công

`close()` giải phóng consumer và rời group. Nếu dùng manual commit, hãy commit ở điểm nghiệp vụ đã xác định. Không coi `close()` là lệnh tự động commit mọi record mà ứng dụng đã lấy về.

Nếu commit bị gián đoạn bởi `WakeupException`, timeout hoặc lỗi mạng, trạng thái commit có thể không chắc chắn. Đọc lại record là hành vi bình thường của at-least-once; consumer cần idempotent để xử lý an toàn.

## 6. Shutdown trong lúc đang xử lý record

`wakeup()` không dừng một đoạn Java code đang chạy. Nếu consumer đang ở trong `processOrder()`, shutdown hook chỉ đặt cờ và gửi tín hiệu wakeup. Consumer tiếp tục chạy cho đến khi quay lại một thao tác Kafka có thể bị đánh thức.

Có hai chính sách thường dùng:

| Chính sách | Cách làm | Khi phù hợp |
|---|---|---|
| Hoàn tất batch hiện tại | Tiếp tục xử lý mọi record đã poll, commit nếu toàn batch thành công, sau đó thoát | Batch nhỏ, xử lý có giới hạn thời gian |
| Dừng sau record hiện tại | Kiểm tra cờ giữa các record, dừng nhận việc mới và commit chính xác phần liên tục đã hoàn tất | Batch lớn hoặc shutdown cần nhanh |

Nếu xử lý record có thể chạy lâu, hãy đặt timeout cho lời gọi downstream và hỗ trợ cancellation ở tầng nghiệp vụ. Kafka không thể tự hủy một HTTP request hoặc transaction database đang chạy trong code ứng dụng.

Không commit offset của toàn batch chỉ vì consumer chuẩn bị shutdown. Nếu chỉ xử lý một phần batch, cần commit đúng offset tiếp theo của phần đã hoàn tất liên tục theo từng partition hoặc để các record chưa xử lý được phát lại.

## 7. Phân biệt wakeup với các cơ chế timeout khác

Các cấu hình consumer có mục tiêu khác nhau:

| Cơ chế | Mục đích | Có thay thế wakeup không? |
|---|---|---|
| `poll(Duration)` | Giới hạn thời gian một lần chờ record | Không; chỉ giới hạn thời gian poll |
| `wakeup()` | Chủ động đánh thức thao tác consumer từ thread khác | Đây là cơ chế yêu cầu dừng tức thời |
| `max.poll.interval.ms` | Giới hạn thời gian giữa các lần poll để phát hiện consumer không tiến triển | Không; liên quan đến group membership |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat trước khi loại consumer | Không; phát hiện consumer mất hoạt động |
| `close(Duration)` | Đóng consumer trong thời gian chờ giới hạn | Không; dùng sau khi vòng lặp đã dừng |

Nếu chỉ dùng `poll(Duration.ofSeconds(1))`, consumer có thể phải chờ tối đa khoảng thời gian poll mới kiểm tra lại cờ dừng. `wakeup()` giúp đánh thức ngay khi đang ở thao tác chờ.

Không tăng `max.poll.interval.ms` để thay thế shutdown signal. Cấu hình này xử lý tiến độ consumer group, không phải cơ chế dừng ứng dụng.

## 8. Xử lý WakeupException đúng cách

Một số cách xử lý sai thường gặp:

**Sai: bỏ qua mọi WakeupException**

~~~java
try {
    consumer.poll(Duration.ofSeconds(1));
} catch (WakeupException ignored) {
    // Không làm gì rồi tiếp tục.
}
~~~

Nếu không có cờ dừng, vòng lặp có thể tiếp tục poll và consumer không thoát.

**Sai: đóng consumer từ shutdown hook**

~~~java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    consumer.close();
}));
~~~

Nếu thread chính đang dùng consumer, thao tác này vi phạm nguyên tắc sở hữu một thread và có thể gây lỗi đồng thời.

**Đúng: wakeup từ thread khác, close trên thread sở hữu**

~~~java
AtomicBoolean running = new AtomicBoolean(true);

Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    running.set(false);
    consumer.wakeup();
}));

try {
    while (running.get()) {
        consumer.poll(Duration.ofMillis(500));
    }
} catch (WakeupException exception) {
    if (running.get()) {
        throw exception;
    }
} finally {
    consumer.close();
}
~~~

Đoạn code rút gọn minh họa nguyên tắc. Ứng dụng thực tế vẫn cần xử lý batch, commit offset, lỗi nghiệp vụ và timeout đóng consumer.

## 9. Dừng consumer khi ứng dụng có nhiều thread

Một service có thể có HTTP thread, scheduler, worker thread và consumer thread. Chỉ consumer thread được gọi các API KafkaConsumer thông thường. Các thread khác gửi tín hiệu dừng thông qua một đối tượng điều phối.

Có thể thiết kế một lifecycle component:

- `start()`: tạo consumer và khởi động consumer thread.
- `stop()`: đặt cờ dừng và gọi `wakeup()`.
- Consumer thread: sở hữu `subscribe()`, `poll()`, commit và close.
- `awaitTermination()`: chờ consumer thread kết thúc trong giới hạn thời gian.

Không dùng `Future.cancel(true)` hoặc `Thread.interrupt()` làm cơ chế chính để điều khiển KafkaConsumer. Dùng API `wakeup()` được Kafka cung cấp; nếu ứng dụng có công việc khác cần interrupt, hãy xử lý riêng theo hợp đồng của công việc đó.

Khi có nhiều consumer, mỗi instance cần tín hiệu wakeup riêng và thread sở hữu riêng. Không dùng một consumer instance chung cho nhiều thread chỉ để giảm số kết nối.

## 10. Spring Kafka: để listener container quản lý lifecycle

Khi dùng `@KafkaListener`, Spring Kafka tạo và quản lý KafkaMessageListenerContainer hoặc ConcurrentMessageListenerContainer. Container sở hữu consumer thread, poll loop, rebalance và lifecycle.

Trong trường hợp này:

- Không tự gọi `wakeup()` hoặc `close()` trên consumer do container quản lý.
- Dùng `KafkaListenerEndpointRegistry` để tìm và dừng listener container khi cần.
- Có thể gọi `stop()` để yêu cầu container dừng theo lifecycle của Spring.
- Cấu hình acknowledgement mode và error handler để quyết định offset nào được commit.
- Chờ container dừng trước khi đóng các dependency mà listener đang sử dụng.

Ví dụ dừng listener container theo ID:

~~~java
@Component
public class ListenerShutdown {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerShutdown(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrderListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

        if (container != null) {
            container.stop();
        }
    }
}
~~~

Listener cần có ID tương ứng:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders",
    groupId = "order-worker"
)
public void onOrder(String payload) {
    processOrder(payload);
}
~~~

Cách dừng cụ thể phụ thuộc cấu hình container và phiên bản Spring Kafka. Với ứng dụng Spring Boot, nên tích hợp vào lifecycle/shutdown phase của Spring để listener dừng trước khi database, executor hoặc HTTP client mà listener phụ thuộc bị đóng.

## 11. Các lỗi thường gặp khi shutdown

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng không dừng sau Ctrl+C | Chỉ đặt cờ nhưng poll đang chờ lâu hoặc không gọi wakeup | Gọi `consumer.wakeup()` từ shutdown thread |
| WakeupException bị log như lỗi nghiêm trọng | Không phân biệt tín hiệu shutdown với lỗi ngoài ý muốn | Kiểm tra cờ running trong catch |
| Consumer vẫn xử lý sau khi nhận shutdown | Đang ở trong logic xử lý record; wakeup không ngắt code ứng dụng | Đặt timeout/cancellation cho công việc và chọn chính sách drain batch |
| Record bị đọc lại sau restart | Offset chưa commit hoặc commit không xác định | Thiết kế xử lý idempotent và commit sau khi xử lý |
| Record bị bỏ qua | Commit offset trước khi xử lý hoàn tất | Chỉ commit offset của phần liên tục đã xử lý thành công |
| Lỗi concurrent access | Shutdown thread gọi close/commit trong khi consumer thread đang chạy | Chỉ gọi wakeup từ thread khác; để owner thread đóng |
| Shutdown kéo dài | Batch quá lớn hoặc downstream xử lý chậm | Giới hạn max.poll.records, timeout và thời gian xử lý |
| Spring listener không dừng đúng | Đóng consumer do container quản lý trực tiếp | Dừng container qua KafkaListenerEndpointRegistry |

## 12. Quy trình shutdown đề xuất

Một trình tự có thể áp dụng cho consumer Java thuần:

1. Ngừng nhận công việc mới từ nguồn gọi bên ngoài.
2. Đặt cờ dừng để vòng lặp không bắt đầu batch tiếp theo.
3. Gọi `consumer.wakeup()` từ shutdown thread.
4. Consumer thread nhận `WakeupException` và xác nhận đó là tín hiệu shutdown.
5. Hoàn tất batch hiện tại theo chính sách đã chọn.
6. Commit offset chỉ khi record tương ứng đã xử lý thành công.
7. Trong `finally`, gọi `consumer.close(Duration)` trên thread sở hữu.
8. Chờ thread kết thúc trong shutdown grace period.
9. Ghi metric/log về batch chưa hoàn tất và event có thể được đọc lại.

Với Spring Kafka, thay bước gọi wakeup/close trực tiếp bằng dừng listener container qua lifecycle của Spring.

## 13. Checklist trước khi triển khai

- [ ] Mỗi KafkaConsumer chỉ được sở hữu bởi một thread.
- [ ] Thread khác chỉ gọi `wakeup()` để đánh thức consumer.
- [ ] Có cờ trạng thái để phân biệt shutdown có chủ đích và WakeupException bất thường.
- [ ] Catch WakeupException đúng chỗ và không âm thầm tiếp tục poll khi đang dừng.
- [ ] Có chính sách hoàn tất hoặc dừng giữa batch rõ ràng.
- [ ] Chỉ commit offset sau khi xử lý thành công và liên tục theo từng partition.
- [ ] Xử lý nghiệp vụ có tính idempotent để chịu được redelivery.
- [ ] Có timeout cho downstream và giới hạn kích thước batch.
- [ ] Consumer được close trên thread sở hữu trong finally.
- [ ] Shutdown grace period đủ cho xử lý batch và đóng consumer.
- [ ] Với Spring Kafka, dừng listener container thay vì tự quản lý consumer bên trong container.
- [ ] Đã thử nghiệm shutdown khi consumer đang poll, đang xử lý và đang commit.

`wakeup()` là cơ chế điều khiển an toàn để thread khác yêu cầu KafkaConsumer thoát khỏi thao tác chờ. `WakeupException` là tín hiệu mà consumer thread cần phân biệt với lỗi thực sự. Một quy trình shutdown đúng sẽ giữ quyền sở hữu consumer trên một thread, xử lý batch và offset theo trạng thái hoàn tất, rồi đóng consumer trong `finally`. Cách này giúp ứng dụng dừng nhanh, giảm rebalance kéo dài và giữ khả năng đọc lại an toàn khi một phần công việc chưa được commit.

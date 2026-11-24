# Tối ưu batching, prefetch và giới hạn poll

Trong Spring Cloud Stream, throughput và latency phụ thuộc cả function, binder, client và broker. Producer có thể gom nhiều message thành một lần gửi; consumer có thể nhận trước một số message; framework có thể chuyển một nhóm record vào function; Kafka còn giới hạn số record trả về trong mỗi lần poll. Những cơ chế này giảm overhead nhưng cũng làm tăng bộ nhớ đang sử dụng, thời gian chờ và phạm vi redelivery khi xử lý lỗi.

Trước khi điều chỉnh, hãy phân biệt bốn khái niệm:

1. **Producer batching:** gom nhiều message thành một lần gửi hoặc một request tới broker.
2. **Consumer batch delivery:** đưa nhiều record vào function/listener trong một lần gọi, thường dưới dạng `List<?>`.
3. **Prefetch/receiver queue:** số message consumer được phép nhận trước khi ứng dụng xử lý hoặc xác nhận xong.
4. **Poll limit:** giới hạn số record một lần lấy dữ liệu có thể trả về. Kafka có `max.poll.records`; poller Spring Integration có giới hạn riêng.

Các thông số này liên quan nhưng không thay thế nhau. Tăng `max.poll.records` không tự bật batch mode của function; tăng RabbitMQ prefetch không khiến listener tự nhận `List`; bật Pulsar producer batching không có nghĩa function nhận một batch object.

## 1. Bốn cơ chế nằm ở những tầng khác nhau

| Cơ chế | Tầng hoạt động | Điều được giới hạn hoặc gom | Tác động chính |
|---|---|---|---|
| Producer batching | Producer/client | Nhiều message thành một request hoặc batch protocol | Giảm request overhead, thường cải thiện throughput và compression. |
| Consumer batch mode | Framework/listener | Nhiều record trong một lần gọi function | Giảm số lần gọi framework và cho phép xử lý theo lô. |
| Prefetch | Broker/consumer protocol | Số message đã giao nhưng chưa ACK | Giữ consumer có dữ liệu sẵn; tăng lượng dữ liệu đang nằm trong bộ nhớ consumer. |
| Receiver queue | Client consumer | Số message được buffer cục bộ trước khi ứng dụng nhận | Hấp thụ burst và giảm round trip; queue quá lớn làm tăng memory và thời gian chờ. |
| Poll limit | Consumer API | Số record tối đa được trả về trong một lần poll | Giới hạn kích thước một lượt xử lý và hỗ trợ kiểm soát thời gian giữa các lần poll. |
| Poller Spring Integration | Application scheduler | Số message xử lý trong mỗi lần kích hoạt poller | Điều khiển nhịp lấy dữ liệu từ Supplier hoặc pollable source. |

Một luồng có thể dùng nhiều cơ chế cùng lúc. Kafka producer gom record theo partition; Kafka consumer lấy một nhóm record trong mỗi poll; Spring Cloud Stream chuyển nhóm đó vào function khi bật batch mode. RabbitMQ có prefetch trên mỗi consumer và container có thể gom delivery thành batch. Pulsar có producer batching và receiver queue ở client.

~~~mermaid
flowchart LR
    A[Producer] --> B[Producer batching]
    B --> C[(Broker)]
    C --> D[Prefetch / receiver queue / poll]
    D --> E[Consumer batch delivery]
    E --> F[Function]
    F --> G[ACK hoặc commit]
~~~

## 2. Đo baseline trước khi tăng batch

Trước khi thay đổi cấu hình, hãy đo:

- Throughput đầu vào và đầu ra: message/giây, byte/giây.
- Kích thước message trung bình và p95/p99.
- Thời gian xử lý một message và một batch.
- Độ trễ từ lúc publish đến lúc function bắt đầu xử lý.
- Consumer lag, queue depth hoặc subscription backlog.
- CPU, heap, direct memory, GC pause và network throughput.
- Tỷ lệ retry, redelivery, timeout và lỗi xử lý.
- Số consumer/partition, concurrency và số instance.

Nếu consumer xử lý nhanh hơn tốc độ message đến, tăng prefetch hoặc batch size có thể không mang lại lợi ích. Nếu producer phát message thưa, batch lớn có thể chỉ khiến message chờ lâu hơn. Nếu function nghẽn ở database hoặc API chậm, tăng số message đang chờ trong JVM thường chỉ chuyển backlog từ broker sang ứng dụng.

Hãy xác định trước throughput tối thiểu cần đạt và latency tối đa mà nghiệp vụ chấp nhận, bao gồm cả thời gian chờ để gom batch. Tối ưu là cân bằng throughput, latency, memory và khả năng phục hồi; không có một batch size hoặc prefetch value phù hợp cho mọi hệ thống.

## 3. Producer batching

Producer batching gom nhiều message thành một lần gửi. Lợi ích thường đến từ việc giảm số request, giảm overhead serialization/protocol và tận dụng compression tốt hơn khi các message có cấu trúc tương tự.

Một batch thường được gửi khi đạt một trong các điều kiện:

- Đã đủ số message tối đa.
- Đã đạt giới hạn byte.
- Đã hết thời gian chờ gom batch.
- Producer cần flush vì đóng, lỗi hoặc điều kiện gửi khác.

Nếu traffic thấp, batch có thể không đầy và message phải chờ hết thời gian gom. Nếu traffic cao, batch có thể đầy nhanh. Batch size lớn thường giảm số lần gửi nhưng tăng lượng dữ liệu giữ trước khi gửi; batch delay lớn có thể cải thiện throughput khi tải thấp nhưng tăng latency.

Compression có thể giảm network traffic, nhưng làm tăng CPU producer/consumer. Đo cả CPU và network trước khi bật compression ở mức cao.

## 4. Kafka: producer batching và consumer poll

Kafka có hai nhóm cấu hình riêng:

- Producer: `batch.size`, `linger.ms`, `compression.type`, `buffer.memory`.
- Consumer: `max.poll.records`, `max.poll.interval.ms`, `fetch.min.bytes`, `fetch.max.wait.ms`.

### 4.1. Cấu hình producer batching

Ví dụ cấu hình output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
      kafka:
        bindings:
          orders-out-0:
            producer:
              batch-timeout: 5
              configuration:
                batch.size: 65536
                linger.ms: 5
                compression.type: lz4
~~~

- `batch.size` là kích thước byte mục tiêu của batch cho mỗi partition. Batch có thể được gửi trước khi đầy.
- `linger.ms` là thời gian producer chờ thêm record để gom batch trước khi gửi. Tăng giá trị này có thể tăng throughput nhưng thêm latency.
- `compression.type` chọn thuật toán nén. Hãy đo CPU và network để chọn `lz4`, `snappy` hoặc `zstd` theo client/broker version.
- `batch-timeout` là thuộc tính của Kafka binder để cho phép message tích lũy thêm trong batch.

Kafka binder cũng có thuộc tính `bufferSize` cho giới hạn byte mà producer cố gom trước khi gửi; tài liệu binder mô tả mặc định là 16 KiB. Thuộc tính này và các Kafka client producer properties có thể tác động tới cùng đường gửi, vì vậy cần kiểm tra cấu hình hiệu lực khi đặt cả hai.

Producer Kafka tạo batch riêng theo partition. Nếu key phân phối message ra nhiều partition, tốc độ đến từng partition có thể thấp và batch khó đầy. Không tăng `batch.size` quá lớn nếu traffic mỗi partition thấp; bộ nhớ producer có thể bị giữ lâu hơn mà throughput không cải thiện.

### 4.2. Consumer batch mode

Khi bật `batch-mode`, Kafka binder đưa các record nhận được từ một lần `poll()` vào function dưới dạng `List<?>`. Nếu tắt batch mode, function được gọi từng record.

~~~java
@Bean
Consumer<List<OrderCreated>> processOrders() {
    return orders -> orderService.processBatch(orders);
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            batch-mode: true
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                max.poll.records: 200
                max.poll.interval.ms: 300000
                fetch.min.bytes: 65536
                fetch.max.wait.ms: 100
~~~

`max.poll.records` là giới hạn số record tối đa trả về từ một lần poll. Giá trị thực tế có thể thấp hơn nếu broker chưa có đủ dữ liệu, fetch limit hoặc partition không có record sẵn.

`fetch.min.bytes` yêu cầu broker cố gắng gom đủ dữ liệu trước khi trả response; `fetch.max.wait.ms` giới hạn thời gian broker chờ điều kiện fetch. Tăng `fetch.min.bytes` có thể giảm số response nhỏ và tăng throughput khi tải cao, nhưng làm message chờ lâu hơn khi tải thấp.

`max.poll.interval.ms` là khoảng thời gian tối đa giữa các lần gọi poll trước khi consumer có thể bị xem là không còn tiến triển và bị loại khỏi group. Đây không phải timeout cho một message riêng lẻ. Nếu function xử lý một batch quá lâu, consumer có thể vượt ngưỡng này và gây rebalance.

### 4.3. Tính thời gian xử lý batch

Giả sử `max.poll.records = 200`, thời gian xử lý p95 mỗi record là 20 ms và xử lý tuần tự trong một thread:

\[
200 \times 20\text{ ms} = 4\,000\text{ ms}
\]

Đây mới là thời gian nghiệp vụ ước tính. Cần cộng thời gian deserialize, database/API, commit offset, GC, retry và các khoảng dừng khác. Nếu có retry/backoff dài, thời gian thực tế có thể cao hơn nhiều.

Giữ khoảng đệm đáng kể giữa thời gian xử lý batch p99 và `max.poll.interval.ms`. Nếu không thể bảo đảm, giảm `max.poll.records`, chia batch nhỏ hơn, tối ưu function hoặc chuyển retry sang error handler/container phù hợp.

### 4.4. Batch mode ảnh hưởng retry và ACK

Kafka binder không hỗ trợ retry nội bộ binder theo cách thông thường khi bật batch mode; `maxAttempts` có thể bị ghi đè thành 1. Nếu cần retry batch, phải cấu hình batch error handler ở listener container hoặc dùng manual acknowledgment/nack theo API Spring Kafka phù hợp.

Khi dùng manual acknowledgment, cần xác định rõ batch nào đã xử lý thành công, offset nào được commit, record nào cần redelivery và DLQ sẽ nhận một record hay nhiều record. Batch processing có thể tăng phạm vi redelivery khi một phần tử lỗi; function nên idempotent và dùng event ID để tránh side effect trùng.

### 4.5. Phân biệt pollTimeout và max.poll.records

Kafka binder có `pollTimeout` cho pollable consumer; tài liệu binder mô tả giá trị mặc định là 5 giây. Thuộc tính này là thời gian chờ của thao tác poll trên pollable source. `max.poll.records` giới hạn số record trả về từ một lần Kafka poll.

| Thuộc tính | Tác dụng |
|---|---|
| `pollTimeout` | Thời gian chờ khi ứng dụng dùng pollable consumer. |
| `max.poll.records` | Số record tối đa trả về từ mỗi lần Kafka consumer poll. |
| `max.poll.interval.ms` | Giới hạn khoảng thời gian giữa các lần poll để duy trì consumer group. |
| `fetch.max.wait.ms` | Thời gian broker tối đa chờ dữ liệu đáp ứng fetch request. |

## 5. Poller Spring Integration và PollableMessageSource

Spring Cloud Stream có poller Spring Integration cho Supplier hoặc thành phần lấy dữ liệu theo lịch. Cấu hình poller không phải Kafka consumer poll configuration.

~~~yaml
spring:
  integration:
    poller:
      fixed-delay: 500
      max-messages-per-poll: 10
~~~

Trong ví dụ, poller kích hoạt mỗi 500 ms và cho phép tối đa 10 message mỗi lần kích hoạt. Giá trị mặc định của Spring Integration poller hiện đại là 1.000 ms cho fixed delay và 1 message mỗi lần; hãy kiểm tra cấu hình Spring Boot/Spring Integration đang dùng.

Với `PollableMessageSource`, ứng dụng chủ động gọi `poll()` để lấy message. Một lần gọi nhận một message; ứng dụng quyết định tần suất gọi, số thread và cách lặp. Không dùng `max-messages-per-poll` để điều khiển `max.poll.records` của Kafka.

Ví dụ vòng poll có kiểm soát:

~~~java
@Bean
ApplicationRunner pollOrders(PollableMessageSource source) {
    return args -> {
        while (!Thread.currentThread().isInterrupted()) {
            boolean received = source.poll(message ->
                orderService.process((OrderCreated) message.getPayload())
            );
            if (!received) {
                Thread.sleep(250);
            }
        }
    };
}
~~~

Đây là ví dụ khái niệm. Ứng dụng thực tế cần quản lý lifecycle của worker, interrupt, exception và acknowledgment; không tạo vòng lặp vô hạn mà không có cơ chế dừng.

## 6. RabbitMQ: prefetch và batching

RabbitMQ đẩy message tới consumer theo cơ chế delivery. `prefetch` giới hạn số message chưa được xác nhận (unacknowledged) mà broker có thể giao cho mỗi consumer theo QoS.

Spring Cloud Stream Rabbit binder có thuộc tính `prefetch`; mặc định binder hiện đặt là 1. Điều này giữ số message chưa ACK thấp, nhưng có thể giới hạn throughput khi consumer xử lý nhanh và round trip ACK chiếm đáng kể thời gian.

### 6.1. Tính số message in-flight

Nếu mỗi instance có C consumer và mỗi consumer có prefetch P, số message chưa ACK tối đa xấp xỉ:

\[
N_{\text{in-flight}} \approx C \times P
\]

Ví dụ 4 consumer, prefetch 25:

\[
4 \times 25 = 100\text{ message}
\]

Nếu message trung bình 64 KiB, payload thô đang được giữ có thể khoảng 6,25 MiB. Con số thực tế cao hơn do object Java, header, byte buffer, batch list, deserialization và dữ liệu tạm trong business logic. Nhiều instance sẽ nhân tổng in-flight theo số instance.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-processor
      rabbit:
        bindings:
          orders-in-0:
            consumer:
              prefetch: 25
              max-concurrency: 4
~~~

`max-concurrency` giới hạn số consumer của container. Hãy xem prefetch theo từng consumer và concurrency của từng instance; không lấy prefetch nhân với số instance một cách thiếu kiểm soát.

### 6.2. Chọn prefetch theo thời gian xử lý

Prefetch quá thấp khiến consumer có thể chờ broker giao message mới sau mỗi ACK, làm throughput giảm khi round trip lớn. Prefetch quá cao giữ nhiều message trong JVM, có thể dồn message vào một consumer, tăng redelivery khi consumer chết và làm latency p95/p99 xấu đi.

Tăng prefetch theo từng bước nhỏ và quan sát throughput, unacked count, memory, redelivery và phân bố tải giữa các consumer. Nếu function xử lý message lâu hoặc payload lớn, nên giữ prefetch thấp hơn.

### 6.3. Producer-side batching

Rabbit binder có thể gom nhiều message ở producer thành một message batch. Các thuộc tính chính:

| Thuộc tính | Ý nghĩa | Giá trị mặc định trong tài liệu binder |
|---|---|---:|
| `batching-enabled` | Bật batching phía producer. | `false` |
| `batch-size` | Số message mục tiêu trong buffer. | `100` |
| `batch-buffer-limit` | Giới hạn buffer khi batching bật. | `10000` |
| `batch-timeout` | Thời gian tối đa chờ gom batch. | `5000` ms |

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
      rabbit:
        bindings:
          orders-out-0:
            producer:
              batching-enabled: true
              batch-size: 100
              batch-buffer-limit: 2000
              batch-timeout: 25
~~~

Timeout 25 ms trong ví dụ là lựa chọn minh họa để giảm thời gian chờ so với mặc định 5 giây; cần đo với traffic thực tế. Producer batching của Rabbit binder có thể đóng gói message thành batch ở tầng AMQP. Consumer mặc định có thể de-batch để gọi listener từng phần tử; muốn nhận `List` cần cấu hình consumer batch mode phù hợp.

### 6.4. Consumer-side batching

Rabbit binder hỗ trợ consumer gom nhiều delivery riêng lẻ thành một batch:

~~~java
@Bean
Consumer<List<OrderCreated>> processOrders() {
    return orders -> orderService.processBatch(orders);
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            batch-mode: true
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              enable-batching: true
              batch-size: 20
              receive-timeout: 200
              prefetch: 20
~~~

- `enable-batching` bật việc container gom các message nhận được thành batch.
- `batch-size` là số message mục tiêu của batch.
- `receive-timeout` là thời gian chờ gom thêm message; hết thời gian, container có thể chuyển batch chưa đủ kích thước.
- `consumer.batch-mode` yêu cầu Spring Cloud Stream chuyển batch vào function dưới dạng `List`.
- `prefetch` quyết định số delivery chưa ACK mà mỗi consumer có thể giữ; nên cân nhắc tương quan với batch size.

Consumer-side batching trong Rabbit binder chỉ được hỗ trợ với container type `simple`. Nếu đang dùng `direct` container, cần kiểm tra hỗ trợ của phiên bản binder và chọn container phù hợp.

### 6.5. Phân biệt batch do producer và consumer tạo

Producer tạo batch nghĩa là nhiều message được đóng gói ở phía gửi; consumer có thể de-batch thành các lần gọi riêng hoặc chuyển cả batch thành `List` nếu bật batch mode. Consumer tạo batch nghĩa là container nhận nhiều message riêng lẻ trong khoảng thời gian nhất định rồi gom thành `List`.

Không bật cả hai chỉ vì nghĩ batch lớn hơn sẽ luôn nhanh hơn. Hãy xác định mục tiêu, kiểm tra cách binder de-batch và xác minh header của từng phần tử.

## 7. Pulsar: producer batching và receiver queue

Pulsar có producer batching tự động. Trong Spring Boot/Spring for Apache Pulsar, batching phía producer được bật mặc định ở các phiên bản hiện hành; có thể cấu hình qua `spring.pulsar.producer.batching-enabled`.

~~~yaml
spring:
  pulsar:
    producer:
      batching-enabled: true
~~~

Pulsar producer batch có thể được gửi khi đạt số message tối đa, giới hạn byte hoặc hết thời gian chờ gom batch. Các thuộc tính của Pulsar `ProducerBuilder` gồm `batchingMaxMessages`, `batchingMaxBytes` và `batchingMaxPublishDelay`. Giá trị mặc định phụ thuộc phiên bản Pulsar client; các bản client thường dùng giới hạn 1.000 message và 128 KiB, còn thời gian gom batch có thể khác giữa các phiên bản.

Nếu cần tinh chỉnh các giới hạn đó, Spring for Apache Pulsar cung cấp `ProducerBuilderCustomizer`:

~~~java
@Bean
ProducerBuilderCustomizer<OrderCreated> orderProducerBatching() {
    return builder -> builder
        .enableBatching(true)
        .batchingMaxMessages(200)
        .batchingMaxBytes(128 * 1024)
        .batchingMaxPublishDelay(2, TimeUnit.MILLISECONDS);
}
~~~

Customizer được áp dụng ở producer factory theo phạm vi cấu hình của Spring Pulsar. Nếu ứng dụng có nhiều producer với yêu cầu khác nhau, hãy kiểm tra cách factory cache và phạm vi áp dụng customizer của phiên bản đang dùng; không để một customizer global vô tình thay đổi tất cả producer.

### 7.1. Receiver queue

Pulsar consumer có receiver queue ở phía client. `receiverQueueSize` là số message được tích lũy cục bộ trước khi consumer lấy message từ queue để xử lý. Giá trị quá thấp có thể làm consumer thường xuyên chờ broker; giá trị quá cao có thể giữ nhiều payload trong heap/direct memory.

Với topic partitioned, cần xem cả `receiverQueueSize`, `maxTotalReceiverQueueSizeAcrossPartitions`, số partition, số consumer/concurrency, kích thước message và tốc độ xử lý.

Ví dụ ở các phiên bản Spring Pulsar hỗ trợ các property này:

~~~yaml
spring:
  pulsar:
    consumer:
      receiver-queue-size: 500
      max-total-receiver-queue-size-across-partitions: 10000
~~~

Đường dẫn property và khả năng cấu hình theo từng binding phụ thuộc phiên bản Spring Boot/Spring Pulsar mà BOM của dự án chọn. Spring Cloud Stream Pulsar binder dùng Spring Boot auto-configuration và cho phép cấu hình consumer properties ở binder hoặc extended binding level. Hãy kiểm tra metadata của đúng phiên bản; nếu property không được expose, có thể truyền native consumer property qua map `properties` hoặc dùng consumer builder customizer phù hợp.

### 7.2. Batching ở consumer

Spring for Apache Pulsar listener container dùng API `batchReceive` để nhận dữ liệu từ consumer. Với listener xử lý từng record, container có thể nhận một batch nội bộ rồi gọi listener từng message. Với API `@PulsarListener`, thuộc tính `batch=true` cho phép listener nhận cả `List`.

Điểm này không đồng nghĩa mọi function binding của Spring Cloud Stream Pulsar binder đều hỗ trợ cấu hình `batch-mode` giống Kafka hoặc Rabbit. Hãy kiểm tra tài liệu và configuration metadata của đúng phiên bản binder trước khi đổi kiểu function thành `Consumer<List<T>>`.

### 7.3. ACK khi xử lý batch

Trong Spring for Apache Pulsar:

- Với listener từng record và ACK mode `BATCH` mặc định, container nhận batch nội bộ rồi gọi listener từng message; các record thành công có thể được ACK và record lỗi được NACK riêng sau khi batch được xử lý.
- Với batch listener nhận `List`, nếu toàn batch thành công thì ACK toàn batch; nếu một record ném exception thì mặc định toàn batch có thể bị NACK.
- Batch listener không dùng `RECORD` ACK mode; nếu cần ACK/NACK từng message, dùng `MANUAL` và acknowledgment theo message ID.

Đây là khác biệt quan trọng khi thiết kế idempotency và retry. Một lỗi ở phần tử cuối của batch có thể khiến các phần tử trước được giao lại nếu chính sách ACK áp dụng cho cả batch.

## 8. Giới hạn bộ nhớ và số message in-flight

Batch size, prefetch và receiver queue đều có thể làm tăng số message đang nằm trong ứng dụng. Một ước lượng đơn giản:

\[
M_{\text{payload}} \approx N_{\text{in-flight}} \times S_{\text{avg}}
\]

Trong đó `N_in-flight` là số message đã được giao/đọc nhưng chưa xử lý xong hoặc chưa được xác nhận; `S_avg` là kích thước payload trung bình.

Đây chỉ là kích thước payload thô. Heap thực tế còn có object header, String/collection, byte buffer, header, bản sao khi deserialize, batch list và dữ liệu tạm của business logic.

Ví dụ RabbitMQ: 4 consumer, prefetch 50, payload trung bình 64 KiB. Số message đang được giữ tối đa xấp xỉ 200; payload thô khoảng 12,5 MiB. Nếu có 3 instance, con số có thể lên khoảng 37,5 MiB trước khi tính overhead.

Ví dụ Kafka: `max.poll.records = 200`, payload trung bình 64 KiB. Một batch có thể chứa khoảng 12,5 MiB payload thô. Nếu nhiều consumer thread cùng xử lý, cần nhân theo số consumer đang có batch và cộng fetch buffers, producer buffers và object đã deserialize.

Ví dụ Pulsar: `receiverQueueSize = 500`, payload trung bình 64 KiB. Receiver queue có thể giữ khoảng 31,25 MiB payload thô cho mỗi consumer queue trước overhead; topic partitioned và tổng queue limit có thể làm cấu trúc buffer phức tạp hơn.

Không dùng công thức này như giới hạn chính xác của heap. Hãy lấy kích thước message p95/p99, số consumer, concurrency, số partition và cách client buffer dữ liệu để lập ngân sách an toàn.

## 9. Backpressure: đừng dùng buffer để che nghẽn

Giả sử producer gửi 10.000 message/giây nhưng consumer chỉ xử lý được 6.000 message/giây. Chênh lệch 4.000 message/giây sẽ tích lũy thành backlog.

Tăng prefetch hoặc receiver queue có thể giúp consumer có dữ liệu sẵn trong một khoảng ngắn, nhưng không giải quyết chênh lệch tốc độ dài hạn. Khi buffer lớn hơn, ứng dụng có thể giữ backlog trong RAM thay vì để broker giữ; điều này làm tăng memory và thời gian khôi phục sau sự cố.

Khi backlog tăng liên tục:

1. Xác định bottleneck là CPU, database, API ngoài, serialization hay network.
2. Đo throughput mỗi consumer và mức độ phân phối giữa partition/queue.
3. Tăng concurrency nếu còn partition/consumer capacity và hệ thống phụ thuộc chịu được.
4. Tối ưu batch size nếu chi phí xử lý từng message chiếm tỷ lệ lớn.
5. Giới hạn in-flight để không làm đầy heap khi downstream chậm.
6. Dùng pause/resume hoặc cơ chế flow control phù hợp nếu cần giảm tốc độ nhận.
7. Theo dõi backlog và thời gian drain sau khi downstream phục hồi.

Nếu downstream bị giới hạn connection pool, tăng concurrency có thể làm tình trạng tệ hơn. Concurrency cần đồng bộ với giới hạn tài nguyên của database/API.

## 10. Chọn batch size theo latency và throughput

Batch size nhỏ có thời gian chờ gom thấp, ít bộ nhớ, phạm vi retry/redelivery nhỏ hơn nhưng overhead trên mỗi message cao hơn.

Batch size lớn có thể giảm số lần gọi framework, request hoặc commit; thường cải thiện throughput với payload nhỏ và tải cao. Đổi lại, nó tăng memory và latency khi batch chưa đầy, một lỗi có thể ảnh hưởng nhiều record hơn và function xử lý lâu hơn cho mỗi lượt.

Nên thử các mức tăng dần, ví dụ 10, 25, 50, 100, rồi đo throughput, p95 latency và memory. Dừng tăng khi throughput không cải thiện đáng kể hoặc latency/memory bắt đầu vượt ngân sách.

Một batch size hợp lý không nhất thiết bằng số tối đa broker cho phép. Hãy chọn theo thời gian xử lý thực tế và kích thước payload, không chỉ dựa vào số message.

## 11. Concurrency và partition/consumer count

Batching không thay thế concurrency. Một function nhận `List<T>` vẫn có thể chạy tuần tự trên một consumer thread. Nếu xử lý CPU-bound hoặc I/O-bound, hãy đo xem batch processing hay tăng consumer count mang lại lợi ích lớn hơn.

### Kafka

- Một partition tại một thời điểm chỉ được gán cho một consumer trong cùng group.
- Số consumer vượt số partition sẽ có consumer nhàn rỗi.
- Tăng concurrency không thể vượt giới hạn song song do partition count đặt ra.
- Key/partitioning quyết định phân phối tải; một key nóng có thể làm một partition nghẽn.

### RabbitMQ

- Mỗi consumer nhận delivery theo queue.
- Tăng concurrency tạo thêm consumer cạnh tranh message từ queue.
- Prefetch áp dụng theo consumer; tổng in-flight tăng theo concurrency.
- Với thứ tự nghiêm ngặt, cần xem xét single-active-consumer hoặc chiến lược routing phù hợp.

### Pulsar

- Concurrency phụ thuộc subscription type và số partition.
- Subscription `Exclusive` chỉ có một consumer hoạt động.
- `Shared` cho phép phân phối message cho nhiều consumer nhưng không đảm bảo thứ tự toàn cục.
- `Key_Shared` cho phép song song theo key và giữ thứ tự trong phạm vi key theo cấu hình.
- `Failover` có cơ chế consumer active/standby và có thể giữ thứ tự trên partitioned topic.

Tăng concurrency phải đi cùng đánh giá ordering, partition, key affinity và khả năng xử lý song song của nghiệp vụ.

## 12. Delivery semantics và lỗi khi xử lý batch

Batching và prefetch có thể thay đổi số message đã được giao nhưng chưa ACK. Khi consumer chết, các message chưa xác nhận có thể được giao lại. Nếu function đã thực hiện side effect ngoài broker trước khi crash, message redelivery có thể tạo side effect trùng.

Các nguyên tắc nên áp dụng:

- Xử lý idempotent bằng event ID hoặc business key.
- Chỉ ACK/commit sau khi bước xử lý cần thiết hoàn tất theo delivery contract.
- Với batch có thể xử lý một phần, lưu trạng thái từng phần tử hoặc dùng manual acknowledgment nếu binder hỗ trợ.
- Không giả định một batch là transaction nguyên tử nếu binder/broker không cung cấp guarantee đó.
- Kiểm tra hành vi retry/DLQ khi một phần tử lỗi giữa batch.
- Không tăng prefetch đến mức shutdown/rebalance làm lượng message redelivery quá lớn.

Với Kafka batch mode, binder retry nội bộ không được hỗ trợ theo cách thường dùng và `maxAttempts` có thể bị đặt thành 1. Với Pulsar batch listener, lỗi một phần tử có thể NACK cả batch theo ACK mode mặc định. Với Rabbit, cách container de-batch và ACK phụ thuộc producer batch, consumer batch mode và acknowledgment mode.

## 13. Đo hiệu năng và quan sát

Không chỉ đo tổng throughput. Nên theo dõi:

| Chỉ số | Điều cần phát hiện |
|---|---|
| Producer batch size thực tế | Batch có thường xuyên đầy hay thường bị gửi vì timeout? |
| Producer send latency | Batching có làm latency tăng quá mục tiêu? |
| Consumer batch size thực tế | Batch có đủ lớn để giảm overhead? |
| Processing time per batch | Có batch nào xử lý quá lâu so với poll/ACK timeout? |
| In-flight/unacked messages | Prefetch hoặc receiver queue có quá cao? |
| Consumer lag/backlog | Tốc độ xử lý có theo kịp tốc độ đến? |
| Redelivery/retry rate | Batch lỗi có gây lặp xử lý? |
| Heap/direct memory và GC | Buffer có làm tăng memory pressure? |
| Partition/consumer utilization | Tải có phân bố đều hay có hot partition/consumer? |
| End-to-end latency p95/p99 | Người dùng có phải chờ lâu hơn sau khi tăng batch? |

Đo cả steady state và burst. Một cấu hình có throughput trung bình tốt nhưng p99 latency rất cao hoặc memory tăng liên tục không phải cấu hình ổn định.

## 14. Quy trình benchmark có kiểm soát

1. Tạo tải chuẩn với cùng payload size và phân bố key như production.
2. Ghi baseline khi batch mode tắt hoặc dùng cấu hình hiện tại.
3. Chỉ thay một nhóm thông số trong mỗi lượt thử.
4. Tăng producer batch size hoặc linger/delay và đo throughput/latency.
5. Tăng consumer batch size hoặc poll limit và đo thời gian xử lý batch.
6. Tăng prefetch/receiver queue từng bước và đo in-flight, memory, redelivery.
7. Thử tải burst và giai đoạn downstream chậm.
8. Dừng consumer giữa batch để kiểm tra redelivery và idempotency.
9. Đo thời gian drain backlog sau khi tải giảm.
10. Chọn cấu hình đáp ứng đồng thời throughput, latency, memory và recovery objectives.

Không so sánh hai cấu hình nếu thay đổi cùng lúc batch size, concurrency, partition count và compression. Khi nhiều biến thay đổi, khó xác định yếu tố nào tạo ra cải thiện hoặc regression.

## 15. Cấu hình gợi ý theo tình huống

| Tình huống | Hướng điều chỉnh | Điều cần theo dõi |
|---|---|---|
| Message nhỏ, throughput cao, latency cho phép thêm vài ms | Tăng producer batching và compression phù hợp. | Producer latency, CPU, network và batch fill ratio. |
| Kafka consumer xử lý nhanh, overhead gọi function cao | Bật batch mode, chọn `max.poll.records` vừa phải. | Thời gian xử lý batch và `max.poll.interval.ms`. |
| Rabbit consumer xử lý nhanh nhưng thường xuyên chờ delivery | Tăng prefetch từng bước, cân nhắc concurrency. | Unacked count, fairness và memory. |
| Rabbit cần gọi database theo lô | Bật consumer-side batching với batch size/receive timeout phù hợp. | Batch fill ratio, DB batch latency và redelivery. |
| Pulsar producer phát nhiều message nhỏ | Giữ batching bật, điều chỉnh max messages/bytes/delay theo client version. | Publish latency, batch size và pending messages. |
| Pulsar consumer có burst nhưng function xử lý chậm | Giảm receiver queue hoặc tăng consumer capacity phù hợp. | Queue memory, backlog và redelivery. |
| Message lớn | Giảm số message trong batch/prefetch, cân nhắc byte limit và compression. | Heap/direct memory và p99 processing time. |
| Tải thấp, message cần đến nhanh | Giảm batch delay/receive timeout, giảm fetch wait phù hợp. | End-to-end latency và số request. |
| Batch xử lý quá lâu | Giảm batch/poll limit hoặc chia nhỏ công việc. | Rebalance, timeout, retry và batch p99. |

Các hướng trên là điểm bắt đầu. Cần kiểm tra cấu hình thực tế và đặc tính broker/client version trước khi triển khai.

## 16. Lỗi thường gặp

1. Nghĩ bật producer batching sẽ tự động khiến function nhận `List`.
2. Tăng Kafka `max.poll.records` mà không kiểm tra thời gian xử lý và `max.poll.interval.ms`.
3. Nhầm Kafka `pollTimeout` với `max.poll.records`.
4. Tăng `fetch.min.bytes` nhưng quên rằng tải thấp có thể làm message chờ lâu hơn.
5. Bật Kafka batch mode nhưng vẫn kỳ vọng binder retry `maxAttempts` hoạt động như record mode.
6. Tăng Rabbit prefetch mà không tính số consumer/concurrency và memory.
7. Đặt Rabbit prefetch quá cao làm một consumer giữ nhiều message trong khi consumer khác nhàn rỗi.
8. Bật cả producer batching và consumer batching nhưng không hiểu container de-batch như thế nào.
9. Đặt Rabbit `receive-timeout` quá lớn khiến batch nhỏ phải chờ lâu.
10. Nhầm Pulsar receiver queue với batch size mà function nhận.
11. Dùng một cấu hình receiver queue lớn cho topic partitioned mà không xem tổng queue across partitions.
12. Tăng batch size nhưng không xử lý idempotency và redelivery.
13. Đo throughput mà bỏ qua p95/p99 latency, GC và thời gian drain backlog.
14. Thay đổi nhiều thông số cùng lúc nên không xác định được nguyên nhân cải thiện.
15. Dùng cấu hình mặc định từ tài liệu một phiên bản broker/client khác với BOM của ứng dụng.

## 17. Checklist trước khi triển khai

- [ ] Đã phân biệt producer batching, consumer batch mode, prefetch/receiver queue và poll limit.
- [ ] Đã đo payload size, throughput, processing time và latency p95/p99.
- [ ] Đã tính số message in-flight theo consumer count và prefetch/queue size.
- [ ] Đã kiểm tra heap, direct memory và GC khi tải burst.
- [ ] Kafka: batch mode và `max.poll.records` được chọn cùng với `max.poll.interval.ms`.
- [ ] Kafka: retry/ACK/DLQ đã được kiểm tra khi batch có record lỗi.
- [ ] Rabbit: prefetch phù hợp với concurrency và batch size.
- [ ] Rabbit: producer batching và consumer-side batching được cấu hình có chủ đích.
- [ ] Pulsar: producer batching và receiver queue phù hợp với client/broker version.
- [ ] Pulsar: tổng receiver queue across partitions được tính đến khi dùng partitioned topic.
- [ ] Ordering và partition/key affinity vẫn đáp ứng nghiệp vụ.
- [ ] Consumer xử lý idempotent khi message được giao lại.
- [ ] Đã thử lỗi giữa batch, consumer restart và downstream chậm.
- [ ] Có dashboard/alert cho backlog, in-flight, redelivery, batch latency và memory.
- [ ] Đã benchmark với payload và phân bố key gần production.

Tối ưu batching, prefetch và poll limit là điều chỉnh lượng dữ liệu được gom hoặc giữ trước khi xử lý. Producer batching giảm overhead gửi; consumer batch mode giảm overhead gọi handler; prefetch/receiver queue giúp consumer luôn có dữ liệu sẵn; poll limit kiểm soát lượng record của một lượt Kafka poll hoặc poller ứng dụng. Chọn giá trị theo throughput, latency, memory, concurrency và delivery semantics sẽ giúp Spring Cloud Stream đạt hiệu năng ổn định mà không biến backlog thành áp lực bộ nhớ hoặc redelivery khó kiểm soát.

## Tài liệu tham khảo

- [Spring Cloud Stream – Kafka Binder: Consuming Batches and Consumer Properties](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Cloud Stream – RabbitMQ Binder: Prefetch and Batching](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream – Apache Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Cloud Stream – Pollable Consumers and Polling Configuration](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring for Apache Pulsar – Message Consumption and Batch Acknowledgment](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Spring for Apache Pulsar – Producer Builder Customization](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-production.html)
- [Apache Kafka – Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [Apache Pulsar – Producer Batching](https://pulsar.apache.org/docs/client-libraries/producers/)

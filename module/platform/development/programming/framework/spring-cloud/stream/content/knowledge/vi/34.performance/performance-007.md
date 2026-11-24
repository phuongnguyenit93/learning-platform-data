# Giữ thứ tự khi tăng mức xử lý song song

Trong ứng dụng xử lý sự kiện với **Spring Cloud Stream**, tăng số consumer, thread hoặc replica thường cải thiện throughput. Đổi lại, việc xử lý đồng thời có thể khiến sự kiện hoàn thành khác thứ tự đã phát, đặc biệt khi các sự kiện cùng thay đổi một thực thể nghiệp vụ. Một yêu cầu đặt hàng có thể phát `CREATED`, `PAID`, rồi `CANCELLED`; nếu `CANCELLED` hoàn thành trước `PAID`, trạng thái cuối cùng có thể sai dù broker đã lưu message đúng thứ tự.

Bài học thuộc chương **Hiệu năng** của module `SPRING_CLOUD_STREAM` và dùng mô hình hàm `Supplier`/`Function`/`Consumer`, binding cùng binder cho Kafka, RabbitMQ hoặc Pulsar. Mục tiêu là xác định **đơn vị cần giữ thứ tự** (toàn topic, partition, queue hay khóa nghiệp vụ), lựa chọn mức song song phù hợp và kiểm thử rằng thứ tự **tác động nghiệp vụ** vẫn đúng khi tăng tải, retry hoặc chuyển quyền xử lý giữa các instance.

## 1. Xác định chính xác lời hứa về thứ tự

"Giữ thứ tự" có nhiều nghĩa. Phải ghi rõ điều hệ thống cần bảo đảm trước khi chọn `concurrency` hay số partition.

| Loại thứ tự | Ví dụ | Phạm vi bảo đảm |
|---|---|---|
| Thứ tự phát (publish order) | Producer gửi `E1`, sau đó `E2` | Trong trình tự gửi của producer; có thể phụ thuộc retry và cấu hình client |
| Thứ tự trong log/queue | `E1` xuất hiện trước `E2` trong một partition | Thứ tự broker đã ghi hoặc sắp xếp trong đơn vị lưu trữ |
| Thứ tự nhận (delivery order) | Consumer nhận `E1` rồi `E2` | Theo broker, subscription, redelivery và mô hình tiêu thụ |
| Thứ tự bắt đầu xử lý | Handler bắt đầu `E1` trước `E2` | Theo lịch của listener/executor |
| Thứ tự hoàn thành | `E1` ghi database xong trước `E2` | Theo thời gian hoàn thành tác vụ nghiệp vụ |
| Thứ tự trạng thái hiệu lực | Version 10 được áp dụng trước version 11 | Theo quy tắc kiểm tra version/transaction ở dữ liệu đích |

Broker có thể bảo đảm thứ tự **log** nhưng không thể tự bảo đảm thứ tự **commit vào database** nếu code gọi `CompletableFuture`, chuyển message sang một pool thread hoặc thực hiện những tác vụ có thời gian khác nhau. Cần bảo vệ thứ tự từ lúc nhận cho đến khi tác động nghiệp vụ hoàn thành.

## 2. Thứ tự toàn cục và thứ tự theo khóa

Hai yêu cầu có chi phí rất khác nhau:

- **Thứ tự toàn cục:** mọi sự kiện của mọi đơn hàng phải hoàn thành theo một chuỗi duy nhất. Một luồng xử lý tuần tự là thiết kế dễ xác minh nhất; mức song song bị giới hạn nghiêm ngặt.
- **Thứ tự theo khóa nghiệp vụ:** chỉ sự kiện của **cùng `orderId`** phải theo thứ tự; các đơn hàng khác nhau có thể xử lý song song. Đây thường là lựa chọn mở rộng tốt nhất cho ứng dụng sự kiện.

Ví dụ:

```text
Order A: A-1 -> A-2 -> A-3  (phải giữ thứ tự)
Order B: B-1 -> B-2         (phải giữ thứ tự)

Lịch xử lý hợp lệ:
  A-1, B-1, B-2, A-2, A-3

Lịch xử lý không hợp lệ với Order A:
  A-1, A-3, B-1, A-2, B-2
```

Hai khóa A và B độc lập có thể nằm trên worker khác nhau. Cùng một khóa thì không nên có hai tác vụ cập nhật trạng thái chạy đồng thời, trừ khi storage có cơ chế version/compare-and-set ngăn cập nhật cũ ghi đè cập nhật mới.

## 3. Vì sao tăng concurrency có thể gây đảo thứ tự?

Giả sử một consumer nhận hai sự kiện cùng đơn hàng:

```text
Thời điểm       Worker 1                     Worker 2
-------------------------------------------------------------
t0              nhận Order#42 version=1
t1                                           nhận version=2
t2                                           xử lý nhanh
t3                                           ghi DB version=2
t4              xử lý chậm xong
t5              ghi DB version=1   <-- ghi đè trạng thái mới
```

Nếu tất cả bản ghi cho `Order#42` thực sự được xử lý tuần tự trong một listener đồng bộ, tình huống trên không xảy ra theo đường xử lý đó. Nó có thể xuất hiện khi message cùng key bị định tuyến sang nhiều consumer, khi listener tự chuyển việc sang thread pool, khi message từ nhiều topic được ghép thiếu điều phối hoặc khi retry/replay tách riêng.

**Quy tắc thiết kế:** tăng số đường xử lý **giữa các key**; giữ một đường tuần tự **trong từng key** khi cần thứ tự theo key.

## 4. Khóa nghiệp vụ là ranh giới đặt lịch

Chọn khóa tương ứng với thực thể có invariant cần bảo vệ:

| Nghiệp vụ | Khóa gợi ý | Vì sao |
|---|---|---|
| Cập nhật trạng thái đơn hàng | `orderId` | Tất cả thay đổi một đơn hàng phải tuần tự |
| Điều chỉnh số dư ví | `walletId` | Tránh cập nhật cạnh tranh trên cùng số dư |
| Cập nhật tồn kho theo mặt hàng/kho | `warehouseId + productId` | Tuần tự trong một cặp kho và sản phẩm |
| Hồ sơ khách hàng | `customerId` | Đảm bảo thứ tự thay đổi một hồ sơ |
| Đo lường telemetry độc lập | `deviceId` nếu cần thứ tự mỗi thiết bị | Cho phép nhiều thiết bị chạy song song |

Không chọn khóa ngẫu nhiên (`eventId`, UUID mới mỗi message) khi các sự kiện có liên quan phải cùng luồng. Khóa thay đổi theo mỗi message sẽ làm mất tính nhất quán khi partition. Cũng không gom mọi sự kiện vào một khóa cố định như `all-orders`: nó tạo **hot partition** và triệt tiêu lợi ích tăng partition.

Một số luồng cần nhiều khóa (ví dụ chuyển tiền giữa hai ví). Chỉ định tuyến theo một khóa không giải quyết được invariant liên quan đồng thời hai khóa. Khi đó cần transaction, khóa phối hợp, saga hoặc cơ chế kiểm soát đồng thời ở nguồn dữ liệu; không tuyên bố Kafka partition key tự bảo đảm tính nguyên tử đa thực thể.

## 5. Thứ tự broker khác thứ tự thời gian nghiệp vụ

Kafka bảo đảm thứ tự offset trong **mỗi partition**. Kafka không bảo đảm thứ tự giữa các partition; các producer độc lập có thể tạo sự kiện theo thời gian nghiệp vụ khác thứ tự khi đến broker.

Ví dụ:

```text
Service A tạo E1 lúc 10:00:00 nhưng network chậm.
Service B tạo E2 lúc 10:00:01 nhưng gửi đến broker trước.

Broker append: E2 rồi E1.
```

Ngay cả khi `E1` và `E2` dùng cùng key, partition chỉ bảo toàn **thứ tự append đã quan sát**, không sắp xếp lại theo `occurredAt`. Khi cần chứng minh E1 phải đứng trước E2 theo nghiệp vụ, nên có **sequence number** hoặc **entity version** được cấp từ nguồn thống nhất (ví dụ transaction cập nhật aggregate), không dùng đồng hồ giữa nhiều service làm nguồn thứ tự duy nhất.

Một envelope sự kiện nên có:

```json
{
  "eventId": "evt-873",
  "aggregateId": "order-42",
  "aggregateVersion": 17,
  "type": "OrderPaid",
  "occurredAt": "2026-11-24T04:20:11Z",
  "payload": { "paymentId": "pay-91" }
}
```

`aggregateId` hỗ trợ chọn partition; `aggregateVersion` giúp kiểm tra thứ tự trạng thái; `eventId` hỗ trợ khử trùng lặp; `occurredAt` hữu ích cho phân tích thời gian nhưng không thay version. Các trường này cần schema và quy tắc tăng version rõ ràng.

## 6. Kafka: bảo vệ thứ tự bằng cùng record key

Với Kafka Binder, các record mang cùng key thông thường được định tuyến đến cùng partition bằng partitioner của producer Kafka. Trong một consumer group, tại một thời điểm một partition được gán cho một consumer trong nhóm. Vì vậy có thể xử lý nhiều partition song song mà vẫn giữ thứ tự **bản ghi trong mỗi partition**, nếu handler xử lý đồng bộ và không tự đảo thứ tự ở downstream.

```text
Topic orders.events (4 partitions)

order-11: v1, v2, v3 ----> P1 ----> Consumer A (tuần tự)
order-22: v1, v2 --------> P3 ----> Consumer B (tuần tự)
order-33: v1, v2 --------> P0 ----> Consumer C (tuần tự)

P2 chứa các khóa khác; được xử lý độc lập.
```

Nếu producer không gán key, client có thể phân tán record theo partitioning strategy mà không giữ các sự kiện một đơn hàng cùng partition. Do đó, phải kiểm tra **record key thật được gửi lên Kafka**, không chỉ thấy `orderId` nằm trong JSON payload rồi giả định broker sẽ hash trường này.

## 7. Gán Kafka record key từ Spring Cloud Stream

Trong mô hình hàm Spring Cloud Stream, output có thể trả về `Message<T>` và đặt Kafka record key trong header `KafkaHeaders.KEY`. Ví dụ một function chuẩn hóa khóa trước khi publish:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderEvent(String eventId, String orderId, long version, String status) {}

@Bean
Function<OrderEvent, Message<OrderEvent>> keyByOrder() {
    return event -> MessageBuilder
        .withPayload(event)
        .setHeader(KafkaHeaders.KEY, event.orderId())
        .build();
}
```

Cấu hình input/output:

```yaml
spring:
  cloud:
    function:
      definition: keyByOrder
    stream:
      bindings:
        keyByOrder-in-0:
          destination: orders.raw
        keyByOrder-out-0:
          destination: orders.keyed
```

Function nhận `OrderEvent` từ input, trả `Message<OrderEvent>` có Kafka key là `orderId`. Nếu chỉ có một producer upstream, cũng có thể gán key ngay tại upstream producer hoặc khi dùng `StreamBridge` với `MessageBuilder`. Nếu binder đang dùng custom partitioning (`partition-key-expression`), cần đối chiếu thuật toán của binder với native Kafka partitioner vì chúng có thể chọn partition khác nhau cho cùng key.

**Lưu ý:** ví dụ tập trung vào key và binding. Ứng dụng cần dependency Kafka Binder, serializer/content type tương thích với `OrderEvent`, cũng như topic được provision đúng. Header `KafkaHeaders.KEY` là cách đặt native Kafka record key; không dùng header tùy ý `orderId` rồi mặc định broker hiểu đó là key.

## 8. Cấu hình concurrency cho Kafka consumer

Ví dụ consumer function xử lý tuần tự sự kiện trong listener:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderEvent>> applyOrder(OrderStateService service) {
    return message -> service.applyInTransaction(message.getPayload());
}
```

`OrderStateService` là thành phần nghiệp vụ do ứng dụng cung cấp; trong ví dụ, `applyInTransaction` **đợi thao tác ghi hoàn thành rồi mới trả về**, đồng thời kiểm tra event version và event ID. Không chuyển thao tác này sang một executor rồi trả về trước khi hoàn tất nếu yêu cầu thứ tự.

```yaml
spring:
  cloud:
    function:
      definition: applyOrder
    stream:
      bindings:
        applyOrder-in-0:
          destination: orders.keyed
          group: order-state-projector
          consumer:
            concurrency: 3
      kafka:
        binder:
          brokers: localhost:9092
```

`concurrency: 3` cấu hình số consumer thread/container theo binder cho **một instance**. Nếu chạy hai replica, mỗi replica cấu hình ba, hệ thống có thể tạo tới sáu consumer tham gia **cùng group**. Với topic có sáu partition, Kafka có thể phân phối các partition giữa chúng. Nếu chỉ có ba partition, một số consumer không được gán partition; tăng concurrency tiếp không tạo thêm thứ tự hoặc throughput.

Đây là mức song song **giữa các partition**. Cùng partition không bị hai consumer của một group xử lý đồng thời theo assignment bình thường. Tuy nhiên, tính đúng đắn còn phụ thuộc việc code xử lý đồng bộ, retry/rebalance và storage-side version check.

## 9. Công thức sizing cơ bản

Với một Kafka topic đơn lẻ và một consumer group, số consumer thread có thể nhận partition hữu ích bị giới hạn bởi số partition:

\[
T_{useful} \leq \min(P, I \times C)
\]

Trong đó (P) là số partition, (I) là số instance và (C) là concurrency mỗi instance. Công thức là xấp xỉ giới hạn trên cho số consumer đồng thời có partition, không phải dự báo throughput tuyệt đối. CPU, tỷ lệ key nóng, độ trễ database và thời gian retry cũng giới hạn năng lực.

| Partition | Instance | Concurrency/instance | Thread cấu hình | Thread tối đa có partition |
|---:|---:|---:|---:|---:|
| 4 | 1 | 1 | 1 | 1 |
| 4 | 2 | 2 | 4 | 4 |
| 4 | 4 | 2 | 8 | 4 |
| 12 | 3 | 2 | 6 | 6 |
| 12 | 6 | 2 | 12 | 12 |

Khi một key chiếm 70% lưu lượng, một partition có thể trở thành bottleneck, dù tổng CPU còn dư. Tăng partition hoặc instance chỉ hữu ích nếu key phân bố đủ đều, và vẫn không làm một **key duy nhất** được xử lý song song một cách an toàn.

## 10. Kafka producer: retry có thể ảnh hưởng thứ tự

Kafka ghi thứ tự record vào từng partition, nhưng producer còn có retry và nhiều request đang chờ. Khi không bật idempotence, một request trước bị retry còn request sau thành công có thể tạo thứ tự append ngoài mong đợi trong một số cấu hình `max.in.flight.requests.per.connection`.

Cấu hình producer idempotent giúp broker nhận diện các lần gửi lại từ producer session, tránh duplicate do retry và bảo vệ thứ tự theo cơ chế Kafka producer. Ví dụ cấu hình Kafka Binder cho một output:

```yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          keyByOrder-out-0:
            producer:
              configuration:
                enable.idempotence: true
                acks: all
                max.in.flight.requests.per.connection: 5
```

Khi `enable.idempotence=true`, Kafka producer ràng buộc các giá trị tương thích (bao gồm `acks=all`, retries và giới hạn số request đang chờ). Các giá trị xung đột có thể khiến producer báo lỗi cấu hình. Kiểm tra theo phiên bản Kafka client đang dùng. Nếu cần một cấu hình cực kỳ thận trọng cho thí nghiệm, có thể giảm `max.in.flight.requests.per.connection` xuống 1, nhưng điều đó làm giảm throughput và không giải quyết được thứ tự giữa các **producer độc lập**.

Idempotent producer không thay thế `eventId`/version check ở database, không tự cung cấp thứ tự business toàn cục và không loại bỏ mọi duplicate khi hệ thống phát lại message từ một giao dịch nghiệp vụ khác.

## 11. Không dùng asynchronous processing tùy tiện trong listener

Mẫu dễ gây đảo thứ tự:

```java
@Bean
Consumer<OrderEvent> unsafeOrderProcessor(Executor executor,
                                          OrderStateService service) {
    return event -> executor.execute(() -> service.applyInTransaction(event));
}
```

Listener trả về ngay sau `execute`. Consumer có thể tiếp tục message kế tiếp trong cùng partition và kết thúc/ack theo cấu hình, trong khi task cũ vẫn chạy. Nếu task version 2 nhanh hơn version 1, hệ thống có thể cập nhật trạng thái sai. Nếu process chết sau khi listener đã coi message thành công, dữ liệu cũng có thể chưa được ghi.

Mẫu an toàn đơn giản cho yêu cầu tuần tự:

```java
@Bean
Consumer<OrderEvent> orderedProcessor(OrderStateService service) {
    return service::applyInTransaction;
}
```

Nếu bắt buộc phải xử lý bất đồng bộ, thiết kế một **serial executor theo key** hoặc partition, giữ backpressure và chỉ ack/commit sau khi công việc liên quan hoàn tất. Đây là một cơ chế điều phối riêng cần kiểm thử; không mặc định mọi `Flux.flatMap` hoặc thread pool đều giữ thứ tự. Với Reactor, `concatMap` có thể duy trì thứ tự trong **một sequence đầu vào**, nhưng cần chú ý ranh giới partition, cách ack và hiệu ứng bên ngoài; `flatMap` đồng thời có thể phát kết quả theo thứ tự hoàn tất khác với thứ tự đầu vào.

## 12. Kafka Streams: task và stream thread

Kafka Streams Binder xử lý topology bằng stream task; mỗi task đọc tập partition được gán của một subtopology. `num.stream.threads` quyết định số stream thread trên instance. Tăng thread/replica phân phối **task độc lập**, không làm hai thread xử lý cùng một active task ở cùng thời điểm.

Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            applicationId: order-aggregator-v1
            configuration:
              num.stream.threads: 2
```

Nếu function dùng `KStream` với stateful operators như `groupByKey`, `aggregate`, `join` hoặc `selectKey` sau đó repartition, Kafka Streams có thể tạo **repartition topic** và subtopology mới. Cần bảo đảm key và partitioning sau repartition vẫn phù hợp với ranh giới ordering. Một join giữa các nguồn độc lập không tự khôi phục thứ tự nghiệp vụ vốn không tồn tại giữa các topic.

`applicationId` phải ổn định và chung giữa replica cùng topology. Mỗi replica dùng application ID khác nhau sẽ chạy như ứng dụng độc lập, có thể xử lý cùng dữ liệu và phát duplicate output. Standby task chủ yếu phục vụ phục hồi state; không tăng số active task cho một key.

## 13. RabbitMQ: một queue và nhiều consumer

RabbitMQ queue giữ trật tự message khi enqueue, nhưng **nhiều consumer** cùng đọc queue có thể hoàn thành xử lý khác thứ tự vì tải hoặc thời gian xử lý khác nhau. Prefetch lớn còn cho phép một consumer nhận nhiều message chưa ack. Requeue/redelivery có thể thay đổi thứ tự quan sát sau lỗi.

Để giữ thứ tự xử lý của **toàn queue**, cách rõ ràng là một active consumer và listener tuần tự. RabbitMQ hỗ trợ **Single Active Consumer (SAC)**: nhiều consumer có thể đăng ký nhưng broker chỉ cấp message cho một active consumer tại một thời điểm, và chuyển sang consumer dự phòng khi active bị ngắt.

```yaml
spring:
  cloud:
    function:
      definition: applyOrder
    stream:
      bindings:
        applyOrder-in-0:
          destination: orders.events
          group: ordered-processors
          consumer:
            concurrency: 1
      rabbit:
        bindings:
          applyOrder-in-0:
            consumer:
              singleActiveConsumer: true
              prefetch: 1
```

`singleActiveConsumer` đặt queue argument `x-single-active-consumer=true` khi binder khai báo queue; cần kiểm tra điều kiện provisioning của release đang dùng. Queue đã tồn tại với argument khác có thể không được khai báo lại cùng tên; hãy provision/migrate queue có kiểm soát. `prefetch: 1` giảm lượng message chưa ack đang giữ trong một consumer, dễ kiểm soát thứ tự khi có lỗi, nhưng có thể giảm throughput.

**Giới hạn quan trọng:** SAC bảo đảm chỉ một active consumer trên queue, không sửa lỗi đảo thứ tự do listener tự phân luồng hoặc do retry/requeue. Nếu muốn xử lý các đơn hàng độc lập song song mà vẫn giữ thứ tự theo `orderId`, có thể phân tuyến key nhất quán qua nhiều queue, mỗi queue dùng SAC, rồi scale số queue/consumer theo năng lực. RabbitMQ đề cập `x-modulus-hash` exchange cho mô hình phân tuyến này; cần plugin/topology và kế hoạch thay đổi số queue phù hợp.

## 14. Pulsar: chọn subscription đúng loại

Pulsar có nhiều subscription type; semantics ordering khác nhau. Đừng tăng consumer trên `Shared` rồi mặc định message cùng key vẫn được xử lý tuần tự.

| Subscription | Song song | Ordering cần chú ý |
|---|---|---|
| `Exclusive` | Một consumer active cho subscription | Mô hình tuần tự đơn giản; không mở rộng bằng nhiều consumer trên cùng subscription |
| `Failover` | Active/standby, có thể phân phối partition cho các consumer | Giữ thứ tự theo partition khi được cấu hình phù hợp |
| `Shared` | Nhiều consumer nhận message | Không bảo đảm thứ tự message; phù hợp workload độc lập |
| `Key_Shared` | Nhiều consumer, phân phối theo key | Message cùng key được gắn với consumer theo semantics của Key_Shared |

Với `Key_Shared`, producer **phải** gán key/ordering key nhất quán và phải **tắt batching thường hoặc dùng key-based batching** (`BatcherBuilder.KEY_BASED` ở Pulsar Java client). Batching mặc định có thể trộn nhiều key trong một batch và broker dùng key của message đầu để dispatch cả batch, phá vỡ phân phối theo key như dự kiến.

Spring Cloud Stream Pulsar Binder cho phép dùng Spring Pulsar consumer/producer properties ở binder hoặc binding scope; property liên quan subscription type/batching cần được đối chiếu với release Spring Pulsar đi kèm trước khi cấu hình. Ví dụ định hướng (tên binding của consumer phải đúng function bean):

```yaml
spring:
  cloud:
    function:
      definition: applyOrder
    stream:
      bindings:
        applyOrder-in-0:
          destination: persistent://acme/orders/orders.events
          group: order-processing
      pulsar:
        bindings:
          applyOrder-in-0:
            consumer:
              subscription-type: key-shared
```

Giá trị và cách bind của enum có thể khác giữa phiên bản (`Key_Shared` trong Pulsar API); kiểm tra configuration metadata và integration test. Không chỉ đặt subscription type rồi coi xong: cần xác minh producer key, batching strategy, subscription name, ack/redelivery và khả năng mở rộng thực tế. Message cùng key vẫn có thể bị xử lý sai thứ tự nếu application tự chạy chúng đồng thời bên ngoài consumer.

## 15. Retry và redelivery có thể phá thứ tự nghiệp vụ

Retry không chỉ ảnh hưởng độ trễ; nó quyết định có cho sự kiện tiếp theo vượt qua sự kiện thất bại hay không. Giả sử một `orderId` phát ba sự kiện:

```text
order-42: v10 CREATED -> v11 PAID -> v12 SHIPPED

v11 thất bại ở database.
v12 có được xử lý ngay không?
```

Câu trả lời phụ thuộc **ordering contract**:

| Chính sách | Cách thực hiện | Đánh đổi |
|---|---|---|
| Stop-on-error | Giữ partition/key chờ v11 phục hồi | Bảo toàn tiến trình tuần tự nhưng tạo head-of-line blocking |
| Retry có giới hạn tại chỗ | Thử lại v11 trước khi tiến tiếp | Hợp lỗi tạm thời; tăng latency của các sự kiện phía sau |
| Gửi v11 sang DLQ rồi xử lý v12 | Luồng chính tiếp tục | Throughput cao hơn nhưng trạng thái có thể thiếu v11 |
| Cho v12 chạy, kiểm tra version tại storage | v12 được giữ ở trạng thái chờ nếu thiếu v11 | Cần buffer/version coordinator và xử lý gap |

Với Kafka Binder, hãy đối chiếu các cấu hình `maxAttempts`, backoff, error handler, ack mode và DLQ của release đang dùng. Một message được chuyển sang DLQ thường không còn giữ vai trò "chặn thứ tự" trên luồng chính; các record sau nó có thể tiếp tục. Với RabbitMQ, `requeueRejected`, retry và queue DLX cũng làm message quay lại hoặc rời queue theo semantics cụ thể. Với Pulsar, negative acknowledgment và redelivery có thể làm thứ tự xử lý quan sát khác đi.

**Không có một cấu hình retry/DLQ duy nhất vừa luôn giữ thứ tự tuyệt đối, vừa không chặn luồng, vừa luôn đạt throughput cao.** Thiết kế phải chọn chính sách phù hợp với mức độ phụ thuộc giữa các sự kiện và có cách phục hồi được kiểm chứng.

## 16. Ví dụ chính sách xử lý lỗi cho đơn hàng

Giả sử `OrderPaid(v11)` thất bại do database tạm mất kết nối. Nếu v12 phụ thuộc v11, tiếp tục xử lý v12 có thể vi phạm bất biến `CREATED -> PAID -> SHIPPED`.

Quy trình an toàn theo key:

1. Nhận v11, kiểm tra version hiện tại của `order-42`.
2. Nếu lỗi tạm thời, retry có backoff và giới hạn, nhưng không công nhận v11 đã hoàn tất.
3. Nếu cần đưa v11 vào DLQ, đánh dấu key `order-42` đang có **ordering gap** và không áp dụng v12 vào projection đích.
4. Điều tra/khôi phục v11 hoặc quyết định nghiệp vụ hợp lệ để bỏ qua v11.
5. Sau khi xử lý gap, áp dụng v12 và các sự kiện sau theo version.

Đây là logic ứng dụng, không phải hành vi mặc định của DLQ. DLQ chỉ giữ message thất bại để điều tra/replay, thường không phối hợp tự động với version của aggregate. Nếu chọn best-effort và không cần mọi trạng thái trung gian, có thể chấp nhận đi tiếp nhưng phải ghi rõ contract và kiểm thử hậu quả.

## 17. Idempotency và version check ở nguồn dữ liệu đích

Thứ tự nhận đúng chưa đủ để xử lý chính xác các lần redelivery. Kafka, RabbitMQ và Pulsar đều có tình huống message được nhận lại sau crash, timeout hoặc xử lý ack không hoàn tất. Vì vậy consumer cần **idempotent** và, với dữ liệu có thứ tự, nên có **version check**.

Ví dụ bảng projection:

```sql
CREATE TABLE order_projection (
    order_id         VARCHAR(100) PRIMARY KEY,
    applied_version  BIGINT NOT NULL,
    status           VARCHAR(32) NOT NULL
);

CREATE TABLE consumed_event (
    event_id VARCHAR(100) PRIMARY KEY
);
```

Mỗi sự kiện mang `eventId`, `orderId`, `aggregateVersion`. Trong **một database transaction**, consumer xác minh event chưa được ghi nhận, kiểm tra version kế tiếp, cập nhật projection và lưu `eventId` đã xử lý. Phép cập nhật có điều kiện cho một record đã tồn tại có thể là:

```sql
UPDATE order_projection
SET applied_version = :incomingVersion,
    status = :incomingStatus
WHERE order_id = :orderId
  AND applied_version = :incomingVersion - 1;
```

Nếu `rowCount = 0`, cần phân biệt ba trường hợp: message trùng/cũ (`incomingVersion <= appliedVersion`), gap (`incomingVersion > appliedVersion + 1`) hoặc projection chưa được tạo. Với insert lần đầu cần upsert/transaction phù hợp; không coi `rowCount=0` là thành công trong mọi trường hợp. Thêm unique constraint trên `eventId` giúp phát hiện duplicate, nhưng chỉ khi kiểm tra/insert và cập nhật trạng thái nằm trong **cùng transaction** thì mới tránh được ghi trạng thái xong nhưng quên lưu dấu đã xử lý.

**Ví dụ thuật toán quyết định:**

```text
Khi nhận event (aggregateId, eventId, version):
  1. Nếu eventId đã xử lý: ack duplicate, không áp dụng lại.
  2. Đọc/khóa hoặc cập nhật có điều kiện projection hiện tại.
  3. Nếu version == currentVersion + 1:
       áp dụng thay đổi và lưu eventId trong cùng transaction.
  4. Nếu version <= currentVersion:
       kiểm tra audit; bỏ qua hoặc cảnh báo stale/conflict.
  5. Nếu version > currentVersion + 1:
       ghi nhận gap, hoãn xử lý/đưa vào cơ chế khôi phục.
  6. Chỉ xác nhận message theo policy khi quyết định trên bền vững.
```

Thuật toán này giúp bảo vệ dữ liệu khi có lỗi hoặc producer cạnh tranh; nó không phải tính năng tự động của binder. Việc "ack một event có gap" chỉ hợp lệ nếu hệ thống đã **lưu bền vững** event đó trong hàng chờ khôi phục và có quy trình drain.

## 18. Ack/commit phải đi sau tác động nghiệp vụ bền vững

Ở phía consumer, nếu ack/commit offset trước khi cập nhật state xong, một crash có thể làm event mất khỏi luồng xử lý trong khi thao tác nghiệp vụ chưa được thực hiện. Nếu cập nhật database xong rồi crash trước ack, event có thể được giao lại: đây là lý do phải có idempotency.

```text
Lựa chọn an toàn theo at-least-once:
  receive -> validate version -> DB transaction commit -> ack/offset commit
                                                     |
                                                     +-- crash trước ack -> redelivery
                                                         -> idempotency bỏ qua duplicate
```

Không tuyên bố Kafka transaction hoặc exactly-once processing tự động bao phủ một database bên ngoài. Kafka Streams exactly-once semantics có phạm vi Kafka transaction/state/changelog tương ứng; tác động HTTP, email, database không tham gia transaction đó cần bảo đảm riêng (outbox, idempotency hoặc phối hợp giao dịch thích hợp).

Nếu sử dụng Kafka Binder `ackMode`, hãy dùng cú pháp/semantics tương ứng với phiên bản Spring Kafka. Với RabbitMQ/Pulsar, thời điểm ack phụ thuộc listener/container và binder. Kiểm thử crash **sau DB commit nhưng trước ack** để chứng minh replay không làm giảm version hoặc nhân đôi tác động.

## 19. Batch, reactive pipeline và side effect

Batching có thể tăng throughput nhờ giảm số roundtrip, nhưng thứ tự **phát tác động** cần được bảo vệ. Một batch có các event cùng key `[v20, v21, v22]` không được ghi song song bằng ba transaction độc lập nếu yêu cầu trạng thái tuần tự.

Với Reactor, xét hai hình thức:

```java
// Có thể xử lý các phần tử đồng thời, kết quả đến khác thứ tự:
Flux<OrderEvent> parallel = source.flatMap(this::asyncProcess);

// Xử lý tuần tự từng phần tử của cùng một sequence:
Flux<OrderEvent> sequential = source.concatMap(this::asyncProcess);
```

Ví dụ minh họa API; `asyncProcess` ở đây là hàm do ứng dụng cung cấp, trả `Publisher<OrderEvent>`. `concatMap` giữ thứ tự trong **sequence mà nó nhận được**, nhưng không tự gộp các sequence từ nhiều consumer hay partition theo thứ tự nghiệp vụ. `flatMapSequential` có thể giữ thứ tự **phát kết quả** trong một stream nhưng các side effect bên trong vẫn có thể chạy đồng thời: không dựa vào thứ tự output để khẳng định database đã được cập nhật theo thứ tự.

Khi cần xử lý bất đồng bộ theo key, có thể chia một input stream thành các lane theo hash của key rồi cho mỗi lane dùng `concatMap`, đồng thời mở rộng nhiều lane. Cần kiểm tra backpressure, quản lý lane lifecycle, giới hạn hàng chờ và xử lý crash/retry. Sử dụng lane count cố định khi đã có state hoặc phải có kế hoạch thay đổi ánh xạ khóa.

## 20. Tăng partition có thể thay đổi vị trí của cùng key

Thêm partition cho Kafka/Pulsar có thể tăng năng lực xử lý nhiều key, nhưng cũng có thể làm cùng key hash sang partition mới vì công thức partitioning phụ thuộc số partition. Các bản ghi cũ vẫn nằm partition trước, còn bản ghi mới ở partition sau.

```text
Trước:  topic có 4 partition; order-42 -> P1
Sau:    topic có 8 partition; order-42 -> P5 (có thể)

E10 đang chờ ở P1, E11 mới đến P5.
Hai partition có thể được xử lý độc lập.
```

Kết quả là thứ tự hoàn thành cho một key có thể bị phá trong giai đoạn chuyển đổi. Nếu topic đã có dữ liệu tồn đọng, không tăng partition chỉ để thêm consumer mà không có migration plan.

Các lựa chọn gồm: chờ drain backlog trước khi đổi partition count, tạo topic phiên bản mới và chuyển producer/consumer có điểm cắt rõ ràng, hoặc bảo vệ bằng version/gap handling tại storage. Mỗi lựa chọn có chi phí downtime, dữ liệu tồn và replay riêng. Tương tự, thay đổi thuật toán hash, serializer của key hoặc số lane ở routing layer cũng có thể đổi key-to-worker mapping.

## 21. Nhiều topic và nhiều producer không có thứ tự tổng quát

Giả sử `OrderCreated` đến từ `orders.events`, còn `PaymentConfirmed` đến từ `payments.events`. Cho dù mỗi topic có thứ tự theo `orderId`, consumer ghép hai topic không nhận được bảo đảm message payment tới sau message order ở thời gian wall-clock.

```text
orders.events:       OrderCreated(order-42, v1)
payments.events:     PaymentConfirmed(order-42, v2)

Do delay mạng hoặc scheduling, v2 có thể được consumer nhìn thấy trước v1.
```

Với Kafka Streams join, phải hiểu record-time/stream-time, window, grace period và state store. Kafka Streams không phát minh một thứ tự business tuyệt đối giữa hai topic độc lập. Nếu yêu cầu tuần tự cùng aggregate qua nhiều nguồn, cần nguồn cấp version đáng tin cậy và strategy đệm/chờ, hoặc hợp nhất các sự kiện qua một log canonical có key thống nhất.

Nếu một service phát cả event và cập nhật database trong một transaction nghiệp vụ, có thể cân nhắc **transactional outbox** để bảo đảm không mất sự kiện. Tuy nhiên, CDC/outbox không loại bỏ yêu cầu chọn key và điều phối đúng khi có nhiều producer hoặc nhiều luồng publish song song.

## 22. Scale ngang an toàn: từng bước một

Một kế hoạch scale từ một replica sang nhiều replica nên theo trình tự:

1. Xác định contract: toàn cục hay theo key; viết ít nhất một ví dụ business cần giữ thứ tự.
2. Xác nhận key được gửi thật lên broker và các event liên quan dùng cùng key.
3. Xác nhận topic/queue/subscription có đủ đơn vị song song để chia tải.
4. Giữ consumer `group` (Kafka) hoặc subscription name (Pulsar) ổn định khi tăng replica.
5. Không đổi Kafka Streams `applicationId` theo tên pod/replica.
6. Bảo đảm handler không ack trước khi side effect bền vững.
7. Dùng event ID, version và transaction/conditional update để khử duplicate và chặn stale event.
8. Quyết định retry/DLQ có được cho event sau đi tiếp hay phải block key.
9. Thử nghiệm rebalance, restart, failover và replay trước khi tăng tải production.
10. Tăng từ từ concurrency/replica, theo dõi throughput, lag và số lần out-of-order/version gap.

Không dùng mỗi tiêu chí throughput để đánh giá scale thành công. Một hệ thống có thể xử lý message nhanh hơn nhưng projection cuối cùng sai. Điều kiện nghiệm thu gồm cả khả năng giữ invariant và phục hồi sau lỗi.

## 23. Theo dõi điều gì để phát hiện thứ tự bị phá?

Để điều tra ordering, log nên có `eventId`, `aggregateId`, `aggregateVersion`, destination, partition/queue/subscription, consumer instance và attempt count. Tránh log payload nhạy cảm, token hoặc nội dung riêng tư không cần thiết.

| Tín hiệu | Mục đích |
|---|---|
| `out_of_order_events_total` | Đếm version cao đến khi chưa xử lý version trước |
| `stale_events_total` | Theo dõi event cũ/trùng tới sau trạng thái mới |
| `duplicate_events_total` | Xác minh idempotency và redelivery |
| `ordering_gap_oldest_age` | Đo thời gian một key bị chờ vì thiếu version |
| Lag/backlog theo partition | Phát hiện partition nóng hoặc stuck key |
| Processing latency theo key/partition | Tìm tác vụ chậm kéo dài khóa |
| Retry/DLQ count | Đánh giá tác động lỗi lên continuity |
| Rebalance/task reassignment | Liên hệ thay đổi consumer với khoảng gián đoạn |
| End-to-end event age | Đánh giá freshness của projection |

Tránh dùng một metric trung bình toàn topic để đánh giá ordering. Một hot partition có thể chậm hàng phút trong khi các partition khác xử lý gần thời gian thực. Dashboard nên có phân vị latency, histogram backlog và phân bố theo partition; gắn nhãn `orderId` trực tiếp vào mọi metric có thể làm bùng cardinality, nên chỉ đưa ID cụ thể vào log/tracing có kiểm soát.

## 24. Bộ kịch bản kiểm thử thứ tự

Integration test với broker thật hoặc Testcontainers nên kiểm tra ít nhất các trường hợp sau:

| Kịch bản | Thực hiện | Điều phải xác minh |
|---|---|---|
| Cùng key | Phát 100 event tuần tự một `orderId` | Audit của key tăng version 1..100, không có đảo thứ tự |
| Nhiều key | Phát xen kẽ 100 key | Có xử lý song song giữa key nhưng mỗi key vẫn tăng version |
| Tăng concurrency | Từ 1 lên 3 consumer thread | Không làm version của cùng key giảm |
| Tăng replica | Từ 1 lên 3 instance cùng group | Task/partition phân bổ lại nhưng invariant giữ nguyên |
| Hot key | Một key chiếm 70% traffic | Đo bottleneck và p95/p99 của key đó |
| Retry giữa chuỗi | Bắt v11 lỗi tạm thời, gửi v12 | Thực thi đúng stop/skip/gap policy đã công bố |
| DLQ và replay | Đẩy v11 vào DLQ, v12 đến sau | Replay không ghi đè state mới; gap được giải quyết |
| Crash trước ack | Commit DB rồi kill consumer trước ack | Redelivery bị dedupe và không sinh side effect trùng |
| Rebalance | Dừng replica đang sở hữu partition | Consumer mới xử lý tiếp theo version hợp lệ |
| Tăng partition | Từ 4 lên 8 partition khi có backlog | Phát hiện hoặc ngăn out-of-order qua migration/version check |
| Producer song song | Hai producer cùng phát một key | Version từ nguồn thống nhất quyết định thứ tự business |
| RabbitMQ SAC | Hai consumer cùng queue | Chỉ một active; failover giữ quy tắc xử lý |
| Pulsar Key_Shared | Bật key-based batching và nhiều consumer | Message cùng key theo semantics của subscription, side effect tuần tự |

`spring-cloud-stream-test-binder` hữu ích để kiểm tra function, nhưng không mô phỏng đầy đủ Kafka partition assignment, RabbitMQ queue/SAC hay Pulsar Key_Shared. Muốn chứng minh đúng thứ tự khi scale cần integration test với đúng binder/broker và nhiều instance thực hoặc môi trường tương đương.

## 25. Xác minh bằng lịch sử phiên bản, không chỉ trạng thái cuối

Chỉ kiểm tra `status = SHIPPED` sau 100 message là chưa đủ: một ứng dụng có thể viết v100 rồi v99 rồi ghi lại v100 và vẫn qua test. Nên ghi **audit các lần áp dụng bền vững**, gắn version và sequence tại storage, rồi xác minh:

```text
expected: 1, 2, 3, 4, ..., 100
actual:   1, 2, 4, 3, ..., 100   --> fail
```

Ví dụ bảng audit có `audit_id` tăng theo thứ tự commit trong transaction và `aggregate_version`. Truy vấn kiểm thử có thể là:

```sql
SELECT aggregate_id, aggregate_version
FROM order_projection_audit
WHERE aggregate_id = 'order-42'
ORDER BY audit_id;
```

Audit table phải được ghi **trong cùng transaction** với projection để phản ánh các event thực sự đã được áp dụng. Nếu dùng timestamp do client tạo làm thứ tự audit, đồng hồ và độ phân giải có thể không đủ; ưu tiên sequence/commit order do storage cung cấp và không nhầm nó với thứ tự thời gian sự kiện.

Nếu chấp nhận event cũ bị bỏ qua theo policy, lịch sử áp dụng có thể thiếu một số version, nhưng phải có audit rõ vì sao bỏ qua và bảo đảm trạng thái nghiệp vụ vẫn đúng. Không yêu cầu chuỗi 1..N khi contract cho phép coalescing hoặc snapshot thay thế event trung gian.

## 26. Bảng lựa chọn kiến trúc theo yêu cầu

| Yêu cầu | Thiết kế gợi ý | Cần kiểm soát thêm |
|---|---|---|
| Thứ tự toàn cục nghiêm ngặt | Một stream/partition hoặc một active queue consumer | Throughput thấp, head-of-line blocking |
| Thứ tự theo `orderId` với Kafka | Record key là `orderId`, nhiều partition, consumer group đồng nhất | Không async side effect cùng key; retry và version check |
| Stateful aggregation với Kafka Streams | `KStream`/state store keyed, đủ task/threads | Repartition, task restore, application ID, state migration |
| RabbitMQ queue cần ordered consumption | Một active consumer/SAC, listener tuần tự | Prefetch, requeue, queue arguments và failover |
| RabbitMQ theo key với tải cao | Hash routing key vào nhiều queue, SAC mỗi queue | Chọn hash, số queue, migration/replay |
| Pulsar có nhiều consumer và giữ thứ tự theo key | `Key_Shared`, key ổn định, batching theo key hoặc tắt batching | Subscription semantics, redelivery, app side effect |
| Chỉ cần xử lý event độc lập nhanh | Nhiều consumer/`Shared`, cho phép cạnh tranh | Idempotency và xử lý duplicate |
| Producer đa nguồn / nhiều topic | Version/sequence từ nguồn tin cậy + state gate | Gap buffering, replay và conflict resolution |

Thiết kế tốt nhất là thiết kế **vừa đủ** với yêu cầu thứ tự. Nếu nghiệp vụ chỉ cần xử lý mỗi event đúng một lần theo tính chất idempotent và không phụ thuộc thứ tự, không cần ép toàn bộ pipeline vào một worker duy nhất.

## 27. Bài thực hành: tăng tốc hệ thống đơn hàng

Giả sử ứng dụng ban đầu có một Kafka topic `orders.events` với sáu partition, một replica và `concurrency: 1`; xử lý trung bình 60 ms/event. Hệ thống cần tăng tốc nhưng vẫn bảo đảm các sự kiện cùng `orderId` được áp dụng theo `aggregateVersion`.

Hãy thiết kế như sau:

1. Producer dùng `KafkaHeaders.KEY = orderId` và cấu hình idempotent producer.
2. Consumer giữ group `order-projection`, tăng `concurrency` từ 1 lên 3 trên mỗi replica.
3. Triển khai hai replica cùng group, tạo tổng sáu consumer thread để chia sáu partition.
4. Handler cập nhật projection đồng bộ trong transaction, kiểm tra `eventId` và `aggregateVersion`.
5. Với lỗi tạm thời, retry tại key/partition theo policy. Với lỗi lâu dài, lưu event vào cơ chế khôi phục có trạng thái gap rõ ràng.
6. Phát 100 event cho mỗi 1.000 `orderId` xen kẽ, sau đó xác minh audit phiên bản của **từng** order.
7. Kill một replica lúc đang xử lý; xác minh không ghi version thấp đè version cao, và các retry/redelivery không làm duplicate side effect.

Vì có sáu partition, tổng sáu consumer thread chỉ là **mức song song tối đa theo partition**, không phải bảo đảm sáu lần throughput. Nếu một `orderId` chiếm phần lớn message, partition chứa key đó vẫn chậm. Không thêm partition trong lúc backlog chưa được xử lý mà bỏ qua kế hoạch di chuyển key.

## 28. Những ngộ nhận cần tránh

| Ngộ nhận | Thực tế |
|---|---|
| "Broker có ordering nên database cũng đúng thứ tự" | Async handler, retry và external side effect có thể làm đảo thứ tự hoàn thành |
| "Tăng consumer thì một key chạy nhanh hơn" | Nếu giữ thứ tự nghiêm ngặt, một key phải được điều phối tuần tự hoặc bảo vệ bằng version gate |
| "Record có `orderId` trong JSON thì Kafka tự partition theo nó" | Phải gán record key hoặc cấu hình partitioning tường minh |
| "Kafka chỉ có một producer thì luôn có thứ tự nghiệp vụ" | App thread, retry, transaction và thời gian tạo event vẫn cần kiểm tra |
| "Pulsar `Shared` giữ thứ tự cùng key" | `Shared` không bảo đảm ordering; xem `Key_Shared` và producer batching |
| "RabbitMQ nhiều consumer vẫn giữ completion order" | Queue dispatch order khác hoàn thành; dùng SAC/partition queue nếu cần |
| "DLQ không ảnh hưởng thứ tự" | Việc bỏ qua event lỗi có thể tạo gap và thay đổi trạng thái |
| "Idempotency đủ để giữ thứ tự" | Khử trùng lặp không ngăn version cũ ghi đè version mới nếu thiếu version check |
| "Exactly-once tự giải quyết database ngoài Kafka" | External side effect cần transactional/idempotent strategy riêng |
| "Tăng partition lúc nào cũng an toàn" | Thay đổi key-to-partition mapping có thể tạo ordering gap khi có backlog |

## 29. Checklist trước khi mở rộng production

- [ ] Có văn bản định nghĩa đơn vị giữ thứ tự (toàn cục, per key, per partition/queue).
- [ ] Mọi sự kiện liên quan chứa key ổn định, event ID và version nếu cần.
- [ ] Producer thực sự gán record key/routing key, không chỉ lưu key trong payload.
- [ ] Producer retry/idempotence và batching không phá điều kiện ordering.
- [ ] Consumer group/subscription name/application ID ổn định khi tăng replica.
- [ ] Concurrency phù hợp partition/task/queue, không cấp quá nhiều worker vô ích.
- [ ] Handler không trả thành công trước khi side effect bắt buộc hoàn tất.
- [ ] Có storage-side idempotency và version/gap handling.
- [ ] Retry/DLQ/replay có policy rõ cho record cùng key ở phía sau.
- [ ] Bất kỳ repartition hoặc thay đổi partition count nào có kế hoạch migration.
- [ ] Có integration test với nhiều replica, rebalance, lỗi và redelivery.
- [ ] Có metrics cho out-of-order, lag, hot partition và thời gian gap.

## 30. Câu hỏi tự kiểm tra

1. Kafka bảo đảm thứ tự theo topic hay theo partition? Cần cấu hình gì để hai sự kiện cùng `orderId` vào cùng partition?
2. Vì sao `concurrency: 8` trên topic có bốn partition không làm tám consumer cùng xử lý tám partition độc lập?
3. Nếu listener nhận v10 rồi v11 nhưng tự dùng thread pool, điều gì có thể xảy ra với database?
4. `singleActiveConsumer` của RabbitMQ giải quyết điều gì và không giải quyết điều gì?
5. Vì sao Pulsar `Key_Shared` cần key-based batching hoặc tắt batching thông thường?
6. Khi v11 được đưa DLQ nhưng v12 tiếp tục, ứng dụng cần cơ chế nào để phát hiện/khôi phục gap?
7. Tại sao idempotency không thể thay thế version check khi có event out-of-order?
8. Tăng Kafka partition count từ bốn lên tám có thể đổi key-to-partition mapping như thế nào?
9. Kiểm thử nào phát hiện trạng thái trung gian bị cập nhật sai dù trạng thái cuối vẫn đúng?
10. Khi nào nên chấp nhận ordering theo key thay vì thứ tự toàn cục để đạt throughput tốt hơn?

## Kết luận

Giữ thứ tự khi tăng xử lý song song bắt đầu bằng việc chọn **đơn vị tuần tự nhỏ nhất mà nghiệp vụ cần**. Với Kafka, dùng record key ổn định để gom event của cùng thực thể vào một partition, rồi tăng concurrency/replica giữa các partition. Với Kafka Streams, tăng task/thread nhưng bảo vệ key và các ranh giới repartition. Với RabbitMQ, Single Active Consumer giữ một consumer active theo queue; muốn mở rộng theo key có thể phân tuyến sang nhiều queue. Với Pulsar, chọn subscription như `Key_Shared` phù hợp và cấu hình batching theo key. Trong mọi trường hợp, retry/DLQ, xử lý bất đồng bộ, redelivery và thay đổi partition có thể làm thay đổi thứ tự tác động; cần idempotency, version gate, chính sách gap và kiểm thử thực tế để bảo đảm dữ liệu chính xác sau khi scale.

## Tài liệu tham khảo

- Spring Cloud Stream — Partitioning with Kafka Binder: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html
- Spring Cloud Stream — Kafka Binder Configuration: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html
- Spring Cloud Stream — Kafka Streams Binder Configuration: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html
- Spring Cloud Stream — RabbitMQ Consumer Properties: https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html
- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Apache Kafka — Partition Ordering and Consumer Groups: https://kafka.apache.org/documentation/
- RabbitMQ — Consumers and Single Active Consumer: https://www.rabbitmq.com/docs/consumers
- RabbitMQ — Queue Ordering: https://www.rabbitmq.com/docs/queues
- Apache Pulsar — Messaging and Key_Shared: https://pulsar.apache.org/docs/5.0.x/concepts-messaging/

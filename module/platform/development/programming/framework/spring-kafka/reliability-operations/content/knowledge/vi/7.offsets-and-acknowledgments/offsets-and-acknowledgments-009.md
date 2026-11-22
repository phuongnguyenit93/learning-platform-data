# commitCallback

Trong Spring Kafka, `commitCallback` là callback nhận kết quả của thao tác commit offset bất đồng bộ. Callback cho ứng dụng biết lần commit đã thành công hay thất bại, cùng với các offset được gửi trong lần commit đó. Đây là điểm mở rộng hữu ích để ghi log, tạo metric và điều tra lỗi commit trong consumer group.

`commitCallback` không quyết định record nào đã được xử lý và cũng không thay thế acknowledgment của listener. Listener container vẫn xác định thời điểm offset đủ điều kiện commit dựa trên `AckMode`. Cấu hình `syncCommits` quyết định container dùng commit đồng bộ hay bất đồng bộ. Khi dùng commit bất đồng bộ, callback được gọi khi Kafka client nhận kết quả của yêu cầu commit.

## 1. Ba bước khác nhau: xử lý, acknowledgment và commit

Khi một listener xử lý record, cần phân biệt ba sự kiện:

1. **Xử lý nghiệp vụ:** listener thực hiện công việc với record, chẳng hạn cập nhật đơn hàng hoặc ghi dữ liệu vào database.
2. **Acknowledgment:** listener container ghi nhận record hoặc batch đã được xử lý theo `AckMode`. Với chế độ manual, listener gọi `Acknowledgment.acknowledge()` để xác nhận.
3. **Commit offset:** container gửi offset đã chọn đến Kafka để lưu tiến độ của consumer group.

`commitCallback` liên quan đến bước thứ ba. Nó báo kết quả của yêu cầu commit bất đồng bộ, không phải thông báo listener vừa xử lý xong một record.

```text
Kafka poll()
    |
    v
Listener xử lý record
    |
    v
Container ghi nhận acknowledgment theo AckMode
    |
    v
Container chọn offset cần commit
    |
    v
commitAsync(offsets, commitCallback)
    |
    v
Kafka trả kết quả commit
    |
    v
commitCallback(offsets, exception)
```

Nếu listener xử lý thành công nhưng yêu cầu commit thất bại, record có thể được giao lại sau khi consumer khởi động lại hoặc partition được chuyển sang member khác. Nếu commit thành công, consumer group có mốc tiến độ mới để tiếp tục đọc. Vì vậy, callback giúp quan sát kết quả lưu tiến độ, còn tính an toàn của nghiệp vụ vẫn phụ thuộc thứ tự xử lý và acknowledgment.

## 2. Offset trong callback biểu diễn điều gì?

Kafka commit offset thường lưu **vị trí kế tiếp cần đọc**, không phải offset của record cuối cùng đã xử lý. Ví dụ, listener xử lý record ở offset `41` thành công và container commit offset `42`. Khi callback nhận map offset, giá trị `42` là mốc consumer group sẽ dùng để tiếp tục đọc.

Callback có chữ ký từ Kafka client:

```java
void onComplete(
    Map<TopicPartition, OffsetAndMetadata> offsets,
    Exception exception
)
```

Hai tham số có ý nghĩa:

| Tham số | Ý nghĩa |
|---|---|
| `offsets` | Map gồm partition và offset metadata mà client đã gửi trong yêu cầu commit. Key là `TopicPartition`; value là `OffsetAndMetadata`. |
| `exception` | `null` khi commit thành công; chứa exception nếu yêu cầu commit thất bại. |

Ví dụ một lần commit có thể chứa nhiều partition:

```text
orders-0 -> offset 120
orders-1 -> offset 85
orders-2 -> offset 310
```

Mỗi giá trị offset độc lập theo partition. Không cộng các offset lại để tạo một tiến độ chung cho topic. Khi log kết quả, nên ghi cả topic, partition và offset để có thể đối chiếu với log xử lý record.

## 3. Khi nào Spring Kafka gọi commitCallback?

`ContainerProperties` của Spring Kafka cung cấp hai cấu hình liên quan:

- `syncCommits`: quyết định container commit bằng `commitSync()` hay `commitAsync()`; mặc định là `true`.
- `commitCallback`: callback được truyền cho thao tác commit bất đồng bộ; mặc định Spring Kafka cung cấp `LoggingCommitCallback` để ghi nhận lỗi commit.

Khi `syncCommits` là `false`, listener container dùng commit bất đồng bộ và gọi callback khi Kafka client nhận kết quả. Khi `syncCommits` là `true`, container dùng `commitSync()`; callback bất đồng bộ không được gọi cho lần commit đồng bộ đó.

Hai lựa chọn này giải quyết hai vấn đề khác nhau:

| Cấu hình | Cách commit | Hành vi quan sát kết quả |
|---|---|---|
| `syncCommits=true` | Container chờ `commitSync()` hoàn tất hoặc ném lỗi. | Kết quả được xử lý theo luồng commit đồng bộ; `commitCallback` không phải hook của lần commit này. |
| `syncCommits=false` | Container gửi `commitAsync()` và tiếp tục hoạt động mà không chờ kết quả ngay tại lời gọi. | `commitCallback` nhận map offset và exception khi kết quả bất đồng bộ được trả về. |

`AckMode` vẫn quyết định lúc nào container chọn offset để commit. Chẳng hạn, `AckMode.RECORD` chọn tiến độ sau từng record listener thành công, còn `AckMode.BATCH` thường commit sau khi xử lý xong batch của một lần poll. Chuyển `syncCommits` sang `false` không tự thay đổi quy tắc acknowledgment này; nó thay đổi cách gửi và nhận kết quả commit.

## 4. Cấu hình callback trong Spring Kafka

Có thể cấu hình callback trên `ContainerProperties` của listener container factory. Ví dụ dưới đây bật asynchronous commit và ghi log kết quả:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    ContainerProperties container = factory.getContainerProperties();
    container.setSyncCommits(false);
    container.setCommitCallback((offsets, exception) -> {
        if (exception != null) {
            log.error("Kafka offset commit failed for {} partitions",
                    offsets.size(), exception);
            return;
        }

        offsets.forEach((topicPartition, offsetMetadata) ->
                log.debug("Kafka offset committed: topic={}, partition={}, nextOffset={}",
                        topicPartition.topic(),
                        topicPartition.partition(),
                        offsetMetadata.offset()));
    });

    return factory;
}
```

Các import chính:

```java
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
```

Trong ứng dụng thực tế, `ConsumerFactory` thuộc package `org.springframework.kafka.core`; chỉ cần import đúng kiểu Spring Kafka này. Các kiểu `TopicPartition` và `OffsetAndMetadata` thường không cần khai báo tường minh trong lambda, nhưng hữu ích khi viết callback thành một class riêng.

Nếu dùng nhiều listener container factory, hãy cấu hình callback trên factory mà `@KafkaListener` thực sự sử dụng. Có thể chỉ định factory theo tên:

```java
@KafkaListener(
    topics = "orders",
    containerFactory = "kafkaListenerContainerFactory"
)
public void consume(OrderCreated event) {
    orderService.handle(event);
}
```

Để listener container quản lý offset, Kafka consumer thường được cấu hình `enable.auto.commit=false`. Trong Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      group-id: order-service
```

Nếu ứng dụng dùng custom `ConsumerFactory`, hãy kiểm tra thuộc tính thực tế của factory vì cấu hình tự tạo có thể ghi đè giá trị từ Spring Boot.

## 5. Viết callback thành một thành phần riêng

Khi callback cần dùng ở nhiều listener factory hoặc cần kiểm thử độc lập, có thể triển khai `OffsetCommitCallback` thành một class:

```java
import java.util.Map;

import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.consumer.OffsetCommitCallback;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderOffsetCommitCallback implements OffsetCommitCallback {

    private static final Logger log =
            LoggerFactory.getLogger(OrderOffsetCommitCallback.class);

    @Override
    public void onComplete(
            Map<TopicPartition, OffsetAndMetadata> offsets,
            Exception exception) {

        if (exception != null) {
            log.error("Offset commit failed: partitions={}",
                    offsets.keySet(), exception);
            return;
        }

        offsets.forEach((partition, metadata) ->
                log.info("Offset commit succeeded: topic={}, partition={}, offset={}",
                        partition.topic(),
                        partition.partition(),
                        metadata.offset()));
    }
}
```

Gắn class vào container factory:

```java
factory.getContainerProperties()
       .setSyncCommits(false);

factory.getContainerProperties()
       .setCommitCallback(new OrderOffsetCommitCallback());
```

Callback là một thành phần quan sát và ghi nhận kết quả. Không nên đưa logic nghiệp vụ như trừ tiền, cập nhật đơn hàng hoặc gửi thông báo cho khách hàng vào đây. Nếu callback chạy lại hoặc commit thành công nhưng nghiệp vụ bên ngoài gặp sự cố, logic trong callback sẽ khó bảo đảm tính nhất quán với record gốc.

## 6. Xử lý commit thành công

Khi `exception == null`, Kafka client xác nhận yêu cầu commit đã thành công. Ứng dụng có thể dùng thông tin này để:

- Ghi log debug hoặc audit kỹ thuật về offset đã commit.
- Tăng metric số lần commit thành công.
- Ghi nhận thời gian hoặc số partition được commit nếu hệ thống có đo latency.
- Phục vụ điều tra khi cần đối chiếu tiến độ consumer group với log xử lý.

Ví dụ log có cấu trúc:

```text
event=offset_commit_result
status=success
group=order-service
topic=orders
partition=2
next_offset=311
```

`group.id` không phải tham số của `OffsetCommitCallback`; nếu cần log group, hãy lấy từ cấu hình ứng dụng hoặc metadata của listener container. Không suy ra group ID từ tên thread hoặc `client.id` vì chúng có ý nghĩa khác.

Commit thành công chỉ chứng minh Kafka đã lưu offset được gửi trong yêu cầu commit. Nó không chứng minh database đã commit cùng transaction, API bên ngoài đã hoàn tất, hoặc mọi hiệu ứng nghiệp vụ đã bền vững. Những bảo đảm đó phải được thiết kế ở tầng xử lý record.

## 7. Xử lý commit thất bại

Khi `exception != null`, callback cho biết yêu cầu commit thất bại. Cần ghi nhận exception và ngữ cảnh partition/offset để điều tra. Một số nguyên nhân có thể gặp:

- Consumer đã mất quyền sở hữu partition do rebalance.
- Group membership thay đổi trong lúc yêu cầu commit đang được xử lý.
- Coordinator hoặc broker tạm thời không khả dụng.
- Kết nối mạng bị gián đoạn hoặc request timeout.
- Consumer đang shutdown hoặc group generation đã thay đổi.

Không nên chỉ log một dòng chung như “commit failed” rồi bỏ qua exception. Loại exception, thông tin partition và thời điểm xảy ra giúp phân biệt lỗi tạm thời với lỗi do consumer đã rời group.

Với asynchronous commit, `commitAsync()` không tự retry mọi lỗi như một vòng retry nghiệp vụ. Kafka giữ thứ tự callback theo thứ tự các lời gọi commit bất đồng bộ; việc tự gửi lại một map offset cũ sau khi đã có commit mới có thể làm tiến độ bị lùi. Thông thường, hãy ghi nhận lỗi và để các lần commit tiếp theo của container cập nhật tiến độ mới. Chỉ xây dựng cơ chế retry riêng khi đã kiểm soát thứ tự commit và hiểu rõ trạng thái group.

Nếu yêu cầu nghiệp vụ cần biết kết quả commit ngay và muốn xử lý lỗi đồng bộ, cân nhắc giữ `syncCommits=true`. `commitSync()` chờ kết quả và có thể ném exception để container xử lý. Cách này có thể tăng độ trễ xử lý nhưng dễ xác định kết quả commit tại điểm gọi hơn.

## 8. Callback chạy ở đâu và nên làm gì trong đó?

Kafka client xử lý callback bất đồng bộ trong luồng consumer khi kết quả commit được nhận và xử lý. Trong listener container, đây là luồng điều phối consumer. Vì vậy, callback nên thực hiện nhanh và không block.

Các thao tác phù hợp gồm ghi log ngắn, cập nhật bộ đếm thread-safe hoặc phát tín hiệu metric nhẹ. Tránh thực hiện các việc sau trong callback:

- Gọi HTTP hoặc database đồng bộ có thể chờ lâu.
- Chờ `Future.get()` hoặc chờ một thread khác hoàn tất.
- Thực hiện nghiệp vụ nặng hoặc xử lý lại toàn bộ record.
- Gọi Kafka consumer từ một thread tùy ý hoặc chia sẻ consumer cho thread nền.

Nếu cần gửi dữ liệu commit đến một hệ thống giám sát từ xa, có thể đẩy một event nhỏ vào queue hoặc executor chuyên dụng rồi để worker khác gửi đi. Hãy giữ callback ngắn, giới hạn queue và xử lý trường hợp queue đầy để tránh làm nghẽn consumer thread.

Callback có thể được gọi cho một commit chứa nhiều partition. Vì vậy, nên xử lý từng phần tử trong map và tránh giả định map luôn chỉ có một partition. Khi chỉ quan tâm lỗi, có thể ghi nhận exception và số partition bị ảnh hưởng mà không cần tạo một log cho từng offset.

## 9. commitCallback không phải acknowledgment callback

Một nhầm lẫn phổ biến là dùng `commitCallback` như nơi chạy code sau khi listener hoàn tất. Hai thời điểm này không giống nhau.

| Cơ chế | Thời điểm | Mục đích |
|---|---|---|
| Listener return | Phương thức listener kết thúc bình thường. | Báo cho container biết xử lý record đã hoàn tất theo quy tắc listener. |
| `Acknowledgment.acknowledge()` | Listener gọi trong chế độ manual. | Xác nhận record hoặc batch với container. |
| `commitCallback` | Kết quả của một commit bất đồng bộ được Kafka client trả về. | Quan sát commit thành công hay thất bại. |

Ví dụ listener manual:

```java
@KafkaListener(topics = "orders")
public void consume(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    orderService.handle(event);
    acknowledgment.acknowledge();
}
```

Listener xác nhận sau khi nghiệp vụ hoàn tất. Container sau đó chọn offset theo `AckMode` và gửi commit. Callback chỉ được gọi nếu container sử dụng asynchronous commit. Không chuyển `acknowledge()` xuống callback vì lúc đó callback đang báo kết quả commit, tức là đã quá muộn để dùng nó làm xác nhận xử lý record ban đầu.

## 10. Ảnh hưởng đến at-least-once và xử lý lặp

Giả sử listener xử lý record offset `90`, cập nhật database thành công, rồi container gửi commit offset `91` theo chế độ bất đồng bộ. Nếu callback báo lỗi, committed offset có thể vẫn ở `90` hoặc một mốc cũ hơn. Khi consumer khởi động lại hoặc partition được giao cho member khác, record `90` có thể được đọc lại.

Đây là một lý do quan trọng để thiết kế nghiệp vụ idempotent. Ví dụ, ứng dụng có thể dùng event ID làm khóa duy nhất hoặc lưu inbox record trong cùng transaction với thay đổi database. Nếu record được giao lại, ứng dụng nhận ra event đã được áp dụng và không tạo hiệu ứng lần hai.

Ngược lại, nếu ứng dụng commit offset trước khi nghiệp vụ hoàn tất, callback thành công không cứu được công việc bị mất khi process dừng giữa commit và xử lý. Callback chỉ quan sát kết quả commit, không phối hợp transaction Kafka với transaction database.

Với luồng Kafka-to-Kafka cần exactly-once semantics, hãy dùng Kafka transactions và cấu hình phù hợp cho producer/consumer. Với hệ thống ghi vào database ngoài Kafka, cần thiết kế inbox/outbox hoặc cơ chế idempotency và phối hợp giao dịch phù hợp; `commitCallback` không cung cấp bảo đảm exactly-once cho hệ thống ngoài.

## 11. Chọn sync hay async commit

Không có một lựa chọn phù hợp cho mọi consumer. Cần cân nhắc độ trễ, thông lượng và mức độ cần biết kết quả commit tại điểm gọi.

| Tiêu chí | Synchronous commit | Asynchronous commit + callback |
|---|---|---|
| Chờ kết quả | Container chờ `commitSync()` hoàn tất. | Container gửi yêu cầu và tiếp tục; callback nhận kết quả sau. |
| Độ trễ trên poll loop | Có thể cao hơn vì phải chờ broker phản hồi. | Thường giảm thời gian chờ ngay tại lời gọi commit. |
| Quan sát lỗi | Exception được phát sinh trong luồng commit đồng bộ. | Lỗi được chuyển vào callback. |
| Điều khiển retry | Có thể xử lý exception đồng bộ theo chính sách container/ứng dụng. | Cần cẩn thận với thứ tự commit; tránh retry offset cũ sau commit mới. |
| Phù hợp khi | Muốn kết quả commit rõ ràng trước khi tiếp tục. | Muốn tránh chờ commit tại mỗi lần gọi và có thể quan sát kết quả bất đồng bộ. |

Trước khi chuyển sang async, hãy đo thời gian commit và xác định nó có thực sự là nút thắt hay không. Nếu listener chậm do database hoặc HTTP, đổi commit mode có thể không cải thiện throughput đáng kể. Khi dùng async, phải có callback ghi nhận lỗi và có dashboard/alert phù hợp để lỗi commit không bị bỏ sót.

## 12. Các lỗi thường gặp khi cấu hình commitCallback

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Callback không được gọi | `syncCommits` vẫn là `true`; container đang dùng commit đồng bộ. | Kiểm tra `ContainerProperties.setSyncCommits(false)` trên đúng factory. |
| Callback không log lỗi | Callback tùy chỉnh chỉ xử lý nhánh thành công hoặc không ghi exception. | Kiểm tra nhánh `exception != null`; custom callback thay thế callback mặc định. |
| Log offset khó đối chiếu | Chỉ log số offset, không log topic và partition. | Ghi `topic`, `partition` và `OffsetAndMetadata.offset()`. |
| Commit thất bại sau rebalance | Consumer không còn giữ quyền sở hữu hoặc group generation đã đổi. | Đối chiếu log revoke/assign, group membership và exception. |
| Consumer bị chậm sau khi thêm callback | Callback thực hiện I/O đồng bộ hoặc chờ tác vụ lâu. | Đo thời gian callback và chuyển việc gửi dữ liệu từ xa sang worker riêng. |
| Nghiệp vụ vẫn bị xử lý lặp dù callback báo thành công ở một lần khác | Record được giao lại trước khi commit thành công hoặc nghiệp vụ không idempotent. | Đối chiếu event ID, offset và thời điểm xử lý/commit; thêm idempotency. |

Một callback tùy chỉnh nên luôn xử lý cả hai nhánh thành công và thất bại. Nếu chỉ quan tâm lỗi, ít nhất cần log exception cùng thông tin map offset. Khi thay callback mặc định `LoggingCommitCallback`, đừng vô tình bỏ mất khả năng ghi nhận commit failure.

## 13. Nguyên tắc vận hành

- Hiểu `commitCallback` là callback kết quả của asynchronous offset commit, không phải callback sau mỗi listener invocation.
- Giữ `enable.auto.commit=false` khi listener container quản lý acknowledgment và commit offset.
- Chọn `AckMode` để xác định lúc nào offset đủ điều kiện commit; chọn `syncCommits` để quyết định cách gửi commit.
- Đặt `syncCommits=false` khi muốn dùng `commitAsync()` và nhận kết quả qua callback.
- Xử lý rõ `exception == null` và `exception != null`; ghi log topic, partition, offset và exception.
- Giữ callback nhanh, không gọi database/HTTP đồng bộ và không block consumer thread.
- Không retry tùy tiện một commit cũ sau khi đã có commit mới; tránh làm committed offset lùi lại.
- Thiết kế nghiệp vụ idempotent vì record có thể được giao lại khi commit thất bại hoặc consumer rebalance.
- Theo dõi số lần commit, commit failure và thời gian commit cùng consumer lag để phát hiện bất thường.

`commitCallback` giúp quan sát kết quả lưu tiến độ của consumer group khi Spring Kafka dùng asynchronous commit. Khi tách rõ acknowledgment, commit và kết quả callback, ứng dụng có thể ghi nhận lỗi chính xác, điều tra rebalance dễ hơn và duy trì xử lý an toàn khi record được giao lại.
